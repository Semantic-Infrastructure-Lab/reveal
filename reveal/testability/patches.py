"""Patch pressure scanner for Python tests."""

from __future__ import annotations

import ast
import os
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..defaults import SKIP_DIRECTORIES


# Canonical skip set lives in reveal.defaults (shared by every directory walk).
_SKIP_DIRS = SKIP_DIRECTORIES

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
    """Return Python test files under the given paths."""
    files: List[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_file() and path.suffix == '.py':
            files.append(path)
        elif path.is_dir():
            for root, dirs, names in os.walk(path):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
                for name in names:
                    if name.endswith('.py'):
                        files.append(Path(root) / name)
    return sorted(set(files))


def scan_patches(paths: Sequence[str | Path]) -> List[PatchUse]:
    """Scan Python test files for patch-like calls."""
    uses: List[PatchUse] = []
    for file_path in iter_python_test_files(paths):
        uses.extend(_scan_file(file_path))
    return uses


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
