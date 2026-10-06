"""Independent import oracles for the pinned-corpus recall gate (scripts/recall_gate.py).

Every oracle answers "which in-corpus file does each import in each importer resolve
to" WITHOUT importing reveal: a real compiler (GCC), the language's own parser
(Python's ast), or a from-scratch reimplementation of the language's resolution rule
(Rust module paths, Java's one-public-type-per-file JLS rule). tests/test_recall_gate.py
fails if this module ever imports reveal, so the oracle cannot drift into agreeing with
the resolver it measures.

An oracle returns ``(edges, coverage)``: ``edges`` maps a target path to the sorted
importer paths (both corpus-root-relative POSIX strings) and ``coverage`` counts what
the oracle read, so a population change is visible and a zero is never a clean answer.
"""
from __future__ import annotations

import ast
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Callable, NamedTuple

Edges = dict[str, list[str]]
Coverage = dict[str, int]

# One-line probes take milliseconds; a cold macOS runner (clang shim, first-run caches) stalled past 15 s
# once (BACK-1678). Generous, but a probe that still hangs is a measurement failure, never an empty row.
ORACLE_PROBE_TIMEOUT = 60


class Scope(NamedTuple):
    """What one oracle run reads: the corpus root, the project directory both sides
    treat as the scan root, and the importer population (files under importer_dirs)."""
    root: Path
    scan: Path
    importers: list[Path]
    config: dict


class Oracle(NamedTuple):
    suffixes: frozenset[str]
    build: Callable[[Scope], tuple[Edges, Coverage]]


def tracked_files(root: Path, directories: list[str], suffixes: frozenset[str]) -> list[Path]:
    """Git-tracked files under ``directories`` (relative to ``root``) with one of ``suffixes``."""
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'],
                            check=True, capture_output=True, timeout=30)
    files = [Path(p.decode('utf-8')) for p in result.stdout.split(b'\0') if p]
    return [root / p for p in files if p.suffix in suffixes and
            any(p.is_relative_to(Path(d)) for d in directories)]


def _relative(scope: Scope, path: Path) -> str:
    return path.relative_to(scope.root).as_posix()


def _finish(scope: Scope, edges: dict[Path, set[Path]]) -> Edges:
    return {_relative(scope, t): sorted(_relative(scope, i) for i in importers)
            for t, importers in sorted(edges.items()) if importers}


# ---- C / C++: the real preprocessor resolves each quoted include in isolation ----

INCLUDES = re.compile(r'^\s*#\s*include\s*"([^"]+)"', re.MULTILINE)
DEPTH_ONE = re.compile(r'^\. (.+)$', re.MULTILINE)


def resolve_include(root: Path, importer: Path, target: str, include_dirs: list[str], stub: Path,
                    language: str) -> str | None:
    stub.write_text(f'#include "{target}"\n', encoding='utf-8')
    try:
        result = subprocess.run(['gcc', '-H', '-fsyntax-only', f'-x{language}', f'-iquote{importer.parent}',
                                 *[f'-I{root / d}' for d in include_dirs], str(stub)],
                                cwd=root, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=ORACLE_PROBE_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'GCC oracle probe timed out after {ORACLE_PROBE_TIMEOUT}s resolving '
                           f'"{target}" from {importer}; measurement unavailable') from exc
    # Compilation can fail after opening the direct header (generated config,
    # platform macros). GCC's depth-one opened path is still authoritative.
    for opened in DEPTH_ONE.findall(result.stderr):
        path = (root / opened.strip()).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path.relative_to(root).as_posix()
    return None


def _gcc_oracle(language: str) -> Callable[[Scope], tuple[Edges, Coverage]]:
    def build(scope: Scope) -> tuple[Edges, Coverage]:
        if sys.platform == 'win32':
            raise RuntimeError('GCC oracle prerequisite unavailable: Windows probe not qualified')
        if not shutil.which('gcc'):
            raise RuntimeError('GCC prerequisite unavailable')
        edges: dict[str, set[str]] = defaultdict(set)
        resolved: dict[tuple[Path, str], str | None] = {}
        directives = unresolved = 0
        with tempfile.TemporaryDirectory(prefix='reveal-include-oracle-') as tmp:
            stub = Path(tmp) / 'include.src'
            for importer in scope.importers:
                source = importer.read_text(encoding='utf-8', errors='replace')
                for target in INCLUDES.findall(source):
                    directives += 1
                    key = (importer.parent, target)
                    if key not in resolved:
                        resolved[key] = resolve_include(scope.root, importer, target,
                                                        scope.config['include_dirs'], stub, language)
                    path = resolved[key]
                    if path is None:
                        unresolved += 1
                    elif scope.root / path != importer:
                        edges[path].add(_relative(scope, importer))
        return {t: sorted(v) for t, v in sorted(edges.items())}, {
            'files': len(scope.importers), 'directives': directives, 'unresolved_directives': unresolved,
            'gcc_probes': len(resolved),
        }
    return build


# ---- Python: ast.parse (no execution) + filesystem module resolution ----

def _python_module(base: Path, dotted: str) -> Path | None:
    """``a.b.c`` -> base/a/b/c.py, else base/a/b/c/__init__.py; None if not in tree."""
    parts = dotted.split('.')
    for part in parts[:-1]:
        base = base / part
        if not base.is_dir():
            return None
    for candidate in (base / f'{parts[-1]}.py', base / parts[-1] / '__init__.py'):
        if candidate.is_file():
            return candidate
    return None


def _python_targets(scan: Path, importer: Path, node: ast.Import | ast.ImportFrom) -> list[Path]:
    if isinstance(node, ast.Import):
        return [t for alias in node.names if (t := _python_module(scan, alias.name))]
    names = [a.name for a in node.names if a.name != '*']
    if node.level:
        base = importer.parent
        for _ in range(node.level - 1):
            base = base.parent
    else:
        base = scan
    if node.module:
        # `from a.b import n`: the package a.b is always imported, and each name
        # may itself be a submodule of it.
        found = [_python_module(base, node.module)]
        found += [_python_module(base, f'{node.module}.{n}') for n in names]
        return [t for t in found if t]
    if not node.level:
        return []
    # `from . import n1, n2`: each name is a sibling submodule, or a symbol that
    # lives in the package's own __init__.py.
    found, symbol = [], False
    for name in names:
        module = _python_module(base, name)
        if module:
            found.append(module)
        else:
            symbol = True
    if symbol and (base / '__init__.py').is_file():
        found.append(base / '__init__.py')
    return found


def _type_checking_test(expr: ast.expr) -> bool:
    return any(isinstance(n, ast.Name) and n.id == 'TYPE_CHECKING' or
               isinstance(n, ast.Attribute) and n.attr == 'TYPE_CHECKING' for n in ast.walk(expr))


def _python_imports(tree: ast.AST) -> list[tuple[ast.Import | ast.ImportFrom, bool]]:
    """Every import with whether it sits under ``if TYPE_CHECKING:`` (depends:// skips those)."""
    found: list[tuple[ast.Import | ast.ImportFrom, bool]] = []

    def walk(node: ast.AST, in_type_checking: bool) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append((node, in_type_checking))
        elif isinstance(node, ast.If):
            for stmt in node.body:
                walk(stmt, in_type_checking or _type_checking_test(node.test))
            for stmt in node.orelse:
                walk(stmt, in_type_checking)
        else:
            for child in ast.iter_child_nodes(node):
                walk(child, in_type_checking)

    walk(tree, False)
    return found


def build_python_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    edges: dict[Path, set[Path]] = defaultdict(set)
    statements = type_checking = resolved = 0
    unparsed = []
    for importer in scope.importers:
        try:
            tree = ast.parse(importer.read_text(encoding='utf-8', errors='replace'), filename=str(importer))
        except (SyntaxError, ValueError) as exc:
            unparsed.append(f'{_relative(scope, importer)}: {exc}')
            continue
        for node, in_type_checking in _python_imports(tree):
            if in_type_checking:
                type_checking += 1
                continue
            statements += 1
            targets = [t for t in _python_targets(scope.scan, importer, node) if t != importer]
            resolved += bool(targets)
            for target in targets:
                edges[target].add(importer)
    if unparsed:
        # A file the oracle cannot parse is missing ground truth; this interpreter is too old for the corpus.
        raise RuntimeError(f'Python oracle could not parse {len(unparsed)} file(s) under '
                           f'Python {sys.version.split()[0]}; measurement unavailable: {unparsed[:3]}')
    return _finish(scope, edges), {'files': len(scope.importers), 'import_statements': statements,
                                   'resolved_statements': resolved, 'type_checking_skipped': type_checking}


# ---- Rust: deepest existing module file for crate::/super::/self:: use paths ----

USE = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?use\s+([^;]+);', re.MULTILINE)


def _split_top_level(text: str) -> list[str]:
    parts, depth, current = [], 0, []
    for char in text:
        depth += (char == '{') - (char == '}')
        if char == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(char)
    parts.append(''.join(current))
    return [p.strip() for p in parts if p.strip()]


def rust_use_paths(body: str) -> list[str]:
    """Expand one use-declaration body into ``a::b::c`` paths: groups nest to any depth,
    ``self`` in a group names the group's base, and ``as`` aliases are dropped."""
    body = ' '.join(body.split())
    match = re.match(r'^(.*?)::\{(.*)\}$', body)
    if not match:
        return [] if '{' in body else [body.split(' as ')[0].strip()]
    base, inner = match.groups()
    paths = []
    for item in _split_top_level(inner):
        # `self` names the group's base; anything else (a::b, a::{b, c}, a bare {b, c}) recurses.
        paths += [base] if item == 'self' else rust_use_paths(f'{base}::{item}')
    return paths


def _rust_module_file(base: Path, parts: list[str]) -> Path | None:
    """Deepest prefix of ``parts`` that is a real module file under ``base``: rustc's rule
    (``a::b::Item`` lives in a/b.rs or a/b/mod.rs; trailing segments name items)."""
    for n in range(len(parts), 0, -1):
        for candidate in (base.joinpath(*parts[:n]).with_suffix('.rs'), base.joinpath(*parts[:n], 'mod.rs')):
            if candidate.is_file():
                return candidate
    return None


def _crate_src(scope: Scope, importer: Path) -> Path | None:
    for directory in importer.parents:
        if not directory.is_relative_to(scope.root):
            return None
        if (directory / 'Cargo.toml').is_file():
            return directory / 'src' if (directory / 'src').is_dir() else directory
    return None


def _rust_target(scope: Scope, importer: Path, path: str) -> Path | None:
    head, _, rest = path.partition('::')
    parts = [p for p in rest.split('::') if p]
    if not parts:
        return None
    if head == 'crate':
        src = _crate_src(scope, importer)
        return _rust_module_file(src, parts) if src else None
    if head == 'self':
        return _rust_module_file(importer.parent, parts)
    if head == 'super':
        # 2015 mod.rs layout keeps the parent module's children in this directory;
        # 2018 sibling-file layout keeps them one level up. Either real file wins.
        return _rust_module_file(importer.parent, parts) or _rust_module_file(importer.parent.parent, parts)
    return None


def build_rust_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    edges: dict[Path, set[Path]] = defaultdict(set)
    statements = local_paths = 0
    for importer in scope.importers:
        for body in USE.findall(importer.read_text(encoding='utf-8', errors='replace')):
            statements += 1
            for path in rust_use_paths(body):
                if path.split('::')[0] not in ('crate', 'self', 'super'):
                    continue
                local_paths += 1
                target = _rust_target(scope, importer, path)
                if target and target != importer:
                    edges[target].add(importer)
    return _finish(scope, edges), {'files': len(scope.importers), 'use_statements': statements,
                                   'local_paths': local_paths}


# ---- Java: a public top-level type C of package a.b lives in a.b's C.java (JLS 7.6) ----

PACKAGE = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)
IMPORT = re.compile(r'^\s*import\s+(static\s+)?([\w.]+?)(\.\*)?\s*;', re.MULTILINE)


def build_java_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    sources = {p: p.read_text(encoding='utf-8', errors='replace')
               for p in tracked_files(scope.root, [_relative(scope, scope.scan)], frozenset({'.java'}))}
    types: dict[tuple[str, str], list[Path]] = defaultdict(list)
    packages: dict[str, list[Path]] = defaultdict(list)
    for path, text in sources.items():
        match = PACKAGE.search(text)
        package = match.group(1) if match else ''
        types[(package, path.stem)].append(path)
        packages[package].append(path)
    duplicates = sorted(f'{p}.{t}' for (p, t), paths in types.items() if len(paths) > 1)
    if duplicates:
        # Two files claiming one type make the truth ambiguous; narrow scan_root instead of guessing.
        raise RuntimeError(f'Java oracle found {len(duplicates)} duplicate type(s) under the scan root, '
                           f'e.g. {duplicates[:3]}; measurement unavailable')

    def resolve(dotted: str, wildcard: bool) -> list[Path]:
        if wildcard:
            return packages.get(dotted, [])
        parts = dotted.split('.')
        # a.b.C, then a.b.Outer for a nested a.b.Outer.Nested
        for cut in (1, 2):
            if len(parts) > cut and (hit := types.get(('.'.join(parts[:-cut]), parts[-cut]))):
                return hit
        return []

    edges: dict[Path, set[Path]] = defaultdict(set)
    statements = resolved = 0
    for importer in scope.importers:
        text = sources.get(importer)
        if text is None:  # an importer outside the scan root
            text = importer.read_text(encoding='utf-8', errors='replace')
        for static, dotted, wildcard in IMPORT.findall(text):
            if static and not wildcard:
                dotted = dotted.rsplit('.', 1)[0]  # import static a.b.C.member -> a.b.C
            statements += 1
            targets = [t for t in resolve(dotted, bool(wildcard)) if t != importer]
            resolved += bool(targets)
            for target in targets:
                edges[target].add(importer)
    return _finish(scope, edges), {'files': len(scope.importers), 'indexed_types': len(types),
                                   'import_statements': statements, 'resolved_statements': resolved}


C_SUFFIXES = frozenset({'.c', '.h'})
CPP_SUFFIXES = frozenset({'.cpp', '.cc', '.cxx', '.h', '.hpp', '.hh', '.hxx'})

ORACLES: dict[str, Oracle] = {
    'gcc-c': Oracle(C_SUFFIXES, _gcc_oracle('c')),
    'gcc-cpp': Oracle(CPP_SUFFIXES, _gcc_oracle('c++')),
    'python-ast': Oracle(frozenset({'.py'}), build_python_oracle),
    'rust-use': Oracle(frozenset({'.rs'}), build_rust_oracle),
    'java-jls': Oracle(frozenset({'.java'}), build_java_oracle),
}
