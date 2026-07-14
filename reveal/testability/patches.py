"""Patch pressure scanner for Python and TypeScript/JavaScript tests."""

from __future__ import annotations

import ast
import logging
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..core.treesitter_compat import suppress_treesitter_warnings, tree_root, ts_parse
from ..utils.path_utils import is_skippable_dir

suppress_treesitter_warnings()

logger = logging.getLogger(__name__)

# I/O handles that are always noisy — patching them says nothing about production design.
# Suppressed by default in group_patches; pass suppress=False to include them.
_SUPPRESSED_TARGETS: frozenset[str] = frozenset({
    'sys.stdout',
    'sys.stderr',
    'sys.stdin',
    'builtins.print',
    'builtins.input',
})


@dataclass(frozen=True)
class PatchUse:
    """One patch/monkeypatch use in a test file."""

    test_file: str
    test_name: str
    line: int
    patch_kind: str
    target_raw: str
    target_module: Optional[str]
    target_symbol: Optional[str]
    target_qualname: Optional[str]
    is_private_target: bool
    context_depth: int
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatchGroup:
    """Grouped patch pressure summary."""

    key: str
    group_by: str
    patch_count: int
    test_count: int
    test_files: List[str]
    patch_kinds: Dict[str, int]
    private_patch_count: int
    max_patches_in_test: int
    examples: List[Dict[str, Any]]
    score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def iter_python_test_files(paths: Sequence[str | Path]) -> List[Path]:
    """Return Python test files under the given paths (backward-compat alias)."""
    return iter_test_files(paths, extensions=('.py',))


_TS_TEST_EXTENSIONS = frozenset({'.ts', '.tsx', '.js', '.jsx'})
_TS_TEST_SUFFIXES = ('.spec.ts', '.test.ts', '.spec.tsx', '.test.tsx',
                     '.spec.js', '.test.js', '.spec.jsx', '.test.jsx')


def _is_ts_test_file(p: Path) -> bool:
    """Return True if the path looks like a TypeScript/JavaScript test file."""
    name = p.name
    return (
        any(name.endswith(s) for s in _TS_TEST_SUFFIXES)
        or ('__tests__' in p.parts and p.suffix in _TS_TEST_EXTENSIONS)
    )


def iter_test_files(
    paths: Sequence[str | Path],
    extensions: Optional[Sequence[str]] = None,
) -> List[Path]:
    """Return test files under the given paths, dispatching by extension.

    When *extensions* is given only files with those suffixes are returned.
    The default (None) returns both Python and TypeScript/JavaScript test files.
    """
    files: List[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_file():
            if _file_matches(path, extensions):
                files.append(path)
        elif path.is_dir():
            for root, dirs, names in os.walk(path):
                dirs[:] = [d for d in dirs if not is_skippable_dir(Path(root), d) and not d.startswith('.')]
                for name in names:
                    fp = Path(root) / name
                    if _file_matches(fp, extensions):
                        files.append(fp)
    return sorted(set(files))


def _file_matches(path: Path, extensions: Optional[Sequence[str]]) -> bool:
    """Return True if path is a scannable test file given the extension filter."""
    if extensions is not None:
        if path.suffix not in extensions:
            return False
        # For TS extensions, still filter to test files only
        if path.suffix in _TS_TEST_EXTENSIONS:
            return _is_ts_test_file(path)
        return True  # .py with no further restriction
    # Default: Python always, TS only if it looks like a test file
    if path.suffix == '.py':
        return True
    return _is_ts_test_file(path)


def scan_patches(paths: Sequence[str | Path]) -> List[PatchUse]:
    """Scan Python and TypeScript test files for patch-like calls."""
    uses: List[PatchUse] = []
    for file_path in iter_test_files(paths):
        if file_path.suffix == '.py':
            uses.extend(_scan_file(file_path))
        elif file_path.suffix in _TS_TEST_EXTENSIONS:
            uses.extend(_scan_file_ts(file_path))
    return uses


# ---------------------------------------------------------------------------
# TypeScript / JavaScript scanner (tree-sitter)
# ---------------------------------------------------------------------------

# Callee patterns we recognise: (namespace, method) → patch_kind
_TS_CALLEE_KINDS: Dict[tuple, str] = {
    ('jest', 'mock'): 'jest.mock',
    ('vi', 'mock'): 'vi.mock',
    ('jest', 'spyOn'): 'jest.spyOn',
    ('vi', 'spyOn'): 'vi.spyOn',
    ('jest', 'fn'): 'jest.fn',
    ('vi', 'fn'): 'vi.fn',
    ('jest', 'replaceProperty'): 'jest.replaceProperty',
    ('vi', 'replaceProperty'): 'vi.replaceProperty',
}

# Kinds that have (obj, symbol, ...) argument shape (like patch.object)
_SPY_KINDS = frozenset({'jest.spyOn', 'vi.spyOn', 'jest.replaceProperty', 'vi.replaceProperty'})
# Kinds that have (module_path, ...) argument shape (like patch)
_MOCK_MODULE_KINDS = frozenset({'jest.mock', 'vi.mock'})


def _ts_node_text(node, src_bytes: bytes) -> str:
    return src_bytes[node.start_byte():node.end_byte()].decode('utf-8', errors='replace')



_TEST_CALLEE_NAMES = frozenset({'describe', 'it', 'test', 'fit', 'xit', 'xtest'})


def _ts_enclosing_test_name(node, src_bytes: bytes) -> str:
    """Walk up the tree via parent() to find the innermost test/it/describe label."""
    current = node.parent()
    while current is not None:
        if current.kind() == 'call_expression':
            callee = current.child(0)
            if callee is not None:
                callee_text = _ts_node_text(callee, src_bytes)
                if callee_text in _TEST_CALLEE_NAMES:
                    for i in range(current.child_count()):
                        ch = current.child(i)
                        if ch.kind() == 'arguments':
                            for j in range(ch.child_count()):
                                arg = ch.child(j)
                                if arg.kind() == 'string':
                                    val = _ts_get_string_value(arg, src_bytes)
                                    if val:
                                        return val
                            break
        current = current.parent()
    return '<module>'



def _ts_get_string_value(string_node, src_bytes: bytes) -> Optional[str]:
    """Return the string content of a tree-sitter string literal node."""
    for i in range(string_node.child_count()):
        ch = string_node.child(i)
        if ch.kind() == 'string_fragment':
            return _ts_node_text(ch, src_bytes)
    # Fallback: strip surrounding quotes from raw text
    raw = _ts_node_text(string_node, src_bytes)
    if len(raw) >= 2 and raw[0] in ('"', "'", '`') and raw[-1] == raw[0]:
        return raw[1:-1]
    return raw


def _ts_args_list(call_node) -> List[Any]:
    """Return the argument nodes of a call_expression (excluding punctuation)."""
    for i in range(call_node.child_count()):
        ch = call_node.child(i)
        if ch.kind() == 'arguments':
            return [
                ch.child(j)
                for j in range(ch.child_count())
                if ch.child(j).kind() not in ('(', ')', ',')
            ]
    return []


def _ts_parse_callee(call_node, src_bytes: bytes) -> Optional[tuple]:
    """Return (namespace, method) if callee is a member_expression like jest.mock."""
    callee = call_node.child(0)
    if callee is None or callee.kind() != 'member_expression':
        return None
    # children: identifier, '.', property_identifier
    obj_node = prop_node = None
    for i in range(callee.child_count()):
        ch = callee.child(i)
        if ch.kind() == 'identifier' and obj_node is None:
            obj_node = ch
        elif ch.kind() == 'property_identifier':
            prop_node = ch
    if obj_node is None or prop_node is None:
        return None
    ns = _ts_node_text(obj_node, src_bytes)
    method = _ts_node_text(prop_node, src_bytes)
    return (ns, method)


def scan_patches_ts(paths: Sequence[str | Path]) -> List[PatchUse]:
    """Scan TypeScript/JavaScript test files for jest/vi mock calls.

    Recognises:
      jest.mock('./module') / vi.mock('./module')  → kind='jest.mock' / 'vi.mock'
      jest.spyOn(obj, 'method') / vi.spyOn(...)   → kind='jest.spyOn' / 'vi.spyOn'
      jest.fn() / vi.fn()                          → kind='jest.fn' / 'vi.fn'
      jest.replaceProperty(obj, 'prop', val)       → kind='jest.replaceProperty' / ...
    """
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        logger.warning('tree_sitter_language_pack not installed; TypeScript patch scanning skipped')
        return []

    uses: List[PatchUse] = []
    for file_path in iter_test_files(paths, extensions=list(_TS_TEST_EXTENSIONS)):
        uses.extend(_scan_file_ts(file_path))
    return uses


def _scan_file_ts(file_path: Path) -> List[PatchUse]:
    """Scan a single TypeScript/JS file for jest/vi mock calls (iterative DFS)."""
    try:
        from tree_sitter_language_pack import get_parser
    except ImportError:
        return []

    try:
        source = file_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []

    src_bytes = source.encode('utf-8', errors='replace')
    lang = 'tsx' if file_path.suffix in ('.tsx', '.jsx') else 'typescript'
    try:
        parser = get_parser(lang)
        tree = ts_parse(parser, source)
        root = tree_root(tree)
    except Exception as exc:
        logger.debug('tree-sitter parse failed for %s: %s', file_path, exc)
        return []

    uses: List[PatchUse] = []
    # Iterative DFS to avoid Python recursion-limit issues on large files
    stack = [root]
    while stack:
        node = stack.pop()
        if node.kind() == 'call_expression':
            callee_key = _ts_parse_callee(node, src_bytes)
            if callee_key is not None:
                patch_kind = _TS_CALLEE_KINDS.get(callee_key)
                if patch_kind is not None:
                    use = _ts_build_patch_use(node, patch_kind, src_bytes, str(file_path))
                    if use is not None:
                        uses.append(use)
        # Push children in reverse order to maintain document order
        for i in range(node.child_count() - 1, -1, -1):
            stack.append(node.child(i))
    return uses


def _ts_build_patch_use(
    node,
    patch_kind: str,
    src_bytes: bytes,
    file_path: str,
) -> Optional[PatchUse]:
    """Build a PatchUse from a matched call_expression node."""
    args = _ts_args_list(node)
    target_raw: str = '<unknown>'
    target_module: Optional[str] = None
    target_symbol: Optional[str] = None
    target_qualname: Optional[str] = None

    if patch_kind in _MOCK_MODULE_KINDS:
        if args and args[0].kind() == 'string':
            mod = _ts_get_string_value(args[0], src_bytes)
            if mod:
                target_raw = mod
                target_module = mod
                target_qualname = mod
        elif args:
            target_raw = _ts_node_text(args[0], src_bytes)

    elif patch_kind in _SPY_KINDS:
        if len(args) >= 2:
            obj_text = _ts_node_text(args[0], src_bytes)
            if args[1].kind() == 'string':
                sym: Optional[str] = _ts_get_string_value(args[1], src_bytes)
            else:
                sym = _ts_node_text(args[1], src_bytes)
            if sym:
                target_raw = f'{obj_text}.{sym}'
                target_module = obj_text
                target_symbol = sym
                target_qualname = target_raw
            else:
                target_raw = obj_text
                target_module = obj_text
        elif args:
            target_raw = _ts_node_text(args[0], src_bytes)
    # jest.fn() / vi.fn() — no meaningful target; target_raw stays '<unknown>'

    test_name = _ts_enclosing_test_name(node, src_bytes)
    line = node.start_position().row + 1  # rows are 0-indexed

    return PatchUse(
        test_file=file_path,
        test_name=test_name,
        line=line,
        patch_kind=patch_kind,
        target_raw=target_raw,
        target_module=target_module,
        target_symbol=target_symbol,
        target_qualname=target_qualname,
        is_private_target=_is_private_symbol(target_symbol),
        context_depth=0,
        confidence=1.0 if target_raw != '<unknown>' else 0.4,
    )


def group_patches(
    patches: Iterable[PatchUse],
    group_by: str = 'target',
    limit: int = 20,
    min_count: int = 1,
    target_filter: str = '',
    private_only: bool = False,
    suppress: bool = True,
) -> List[PatchGroup]:
    """Group patch uses by target, test, or file."""
    patch_list = list(patches)
    if suppress:
        patch_list = [p for p in patch_list if not _is_suppressed(p)]
    if private_only:
        patch_list = [p for p in patch_list if p.is_private_target]
    if target_filter:
        patch_list = [p for p in patch_list if _matches_target_filter(p, target_filter)]

    buckets: Dict[str, List[PatchUse]] = defaultdict(list)
    for patch in patch_list:
        buckets[_group_key(patch, group_by)].append(patch)

    groups: List[PatchGroup] = []
    for key, items in buckets.items():
        if len(items) < min_count:
            continue
        by_test = Counter((p.test_file, p.test_name) for p in items)
        patch_kinds = Counter(p.patch_kind for p in items)
        private_count = sum(1 for p in items if p.is_private_target)
        score = (
            len(items)
            + max(0, len(items) - 10) * 0.5
            + private_count * 0.5
            + max(0, max(by_test.values()) - 3)
        )
        examples = [
            {
                'test_file': p.test_file,
                'test_name': p.test_name,
                'line': p.line,
                'target_raw': p.target_raw,
                'patch_kind': p.patch_kind,
            }
            for p in items[:5]
        ]
        groups.append(PatchGroup(
            key=key,
            group_by=group_by,
            patch_count=len(items),
            test_count=len(by_test),
            test_files=sorted({p.test_file for p in items}),
            patch_kinds=dict(sorted(patch_kinds.items())),
            private_patch_count=private_count,
            max_patches_in_test=max(by_test.values()) if by_test else 0,
            examples=examples,
            score=score,
        ))

    groups.sort(key=lambda g: (g.score, g.patch_count, g.key), reverse=True)
    return groups[:limit] if limit > 0 else groups


def _scan_file(file_path: Path) -> List[PatchUse]:
    try:
        source = file_path.read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(source, filename=str(file_path))
    except (OSError, SyntaxError):
        return []

    parents = _parent_map(tree)
    uses: List[PatchUse] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target_raw, kind, confidence = _patch_call_target(node)
        if not kind:
            continue
        target_module, target_symbol, qualname = _split_target(target_raw)
        uses.append(PatchUse(
            test_file=str(file_path),
            test_name=_enclosing_test_name(node, parents),
            line=getattr(node, 'lineno', 0),
            patch_kind=kind,
            target_raw=target_raw,
            target_module=target_module,
            target_symbol=target_symbol,
            target_qualname=qualname,
            is_private_target=_is_private_symbol(target_symbol),
            context_depth=_context_depth(node, parents),
            confidence=confidence,
        ))
    return uses


def _parent_map(tree: ast.AST) -> Dict[ast.AST, ast.AST]:
    parents: Dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _patch_call_target(node: ast.Call) -> tuple[str, str, float]:
    name = _call_name(node.func)

    if name.endswith('monkeypatch.setattr'):
        target = _monkeypatch_target(node)
        return target, 'monkeypatch.setattr', 0.8 if target else 0.3

    if name in ('patch.dict', 'mock.patch.dict', 'unittest.mock.patch.dict') or name.endswith('.patch.dict'):
        target = _arg_text(node, 0) or '<unknown>'
        return target, 'patch.dict', 0.7 if target != '<unknown>' else 0.3

    if name in ('patch.object', 'mock.patch.object', 'unittest.mock.patch.object') or name.endswith('.patch.object'):
        target = _patch_object_target(node)
        return target, 'patch.object', 0.7 if target else 0.3

    if name in ('patch', 'mock.patch', 'unittest.mock.patch') or name.endswith('.patch'):
        target = _literal_or_text_arg(node, 0)
        return target or '<unknown>', 'patch', 1.0 if _is_string_arg(node, 0) else 0.5

    return '', '', 0.0


def _monkeypatch_target(node: ast.Call) -> str:
    if not node.args:
        return '<unknown>'
    if _is_string_arg(node, 0):
        return str(node.args[0].value)  # type: ignore[union-attr]
    if len(node.args) >= 2:
        obj = _unparse(node.args[0])
        attr = _literal_or_text_arg(node, 1)
        return f'{obj}.{attr}' if attr else obj
    return _unparse(node.args[0])


def _patch_object_target(node: ast.Call) -> str:
    if len(node.args) < 2:
        return '<unknown>'
    obj = _unparse(node.args[0])
    attr = _literal_or_text_arg(node, 1)
    return f'{obj}.{attr}' if attr else obj


def _literal_or_text_arg(node: ast.Call, index: int) -> Optional[str]:
    if index >= len(node.args):
        return None
    arg = node.args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return _unparse(arg)


def _arg_text(node: ast.Call, index: int) -> Optional[str]:
    if index >= len(node.args):
        return None
    return _unparse(node.args[index])


def _is_string_arg(node: ast.Call, index: int) -> bool:
    return (
        index < len(node.args)
        and isinstance(node.args[index], ast.Constant)
        and isinstance(node.args[index].value, str)
    )


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f'{base}.{node.attr}' if base else node.attr
    return ''


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f'{_unparse(node.value)}.{node.attr}'
        return '<unknown>'


def _split_target(target: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not target or target == '<unknown>':
        return None, None, None
    cleaned = target.strip().strip('"\'')
    parts = cleaned.split('.')
    if len(parts) < 2:
        return None, cleaned, cleaned
    symbol = parts[-1]
    module = '.'.join(parts[:-1])
    return module, symbol, cleaned


def _is_private_symbol(symbol: Optional[str]) -> bool:
    return bool(symbol and symbol.startswith('_') and not (symbol.startswith('__') and symbol.endswith('__')))


def _enclosing_test_name(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
    return '<module>'


def _context_depth(node: ast.AST, parents: Dict[ast.AST, ast.AST]) -> int:
    depth = 0
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.With):
            depth += 1
    return depth


def _group_key(patch: PatchUse, group_by: str) -> str:
    if group_by == 'test':
        return f'{patch.test_file}::{patch.test_name}'
    if group_by == 'file':
        return patch.test_file
    return patch.target_qualname or patch.target_raw or '<unknown>'


def _matches_target_filter(patch: PatchUse, pattern: str) -> bool:
    values = [
        patch.target_raw,
        patch.target_module or '',
        patch.target_symbol or '',
        patch.target_qualname or '',
    ]
    return any(pattern in value or fnmatch(value, pattern) for value in values)


def _is_suppressed(patch: PatchUse) -> bool:
    qualname = patch.target_qualname or patch.target_raw
    return qualname in _SUPPRESSED_TARGETS
