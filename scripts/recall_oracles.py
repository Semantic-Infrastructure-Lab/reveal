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
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Callable, NamedTuple

Edges = dict[str, list[str]]
Coverage = dict[str, object]

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
    # The edges (a subset of build's) whose every import is function-level; None when the oracle cannot tell.
    lazy_only: Callable[[Scope], Edges] | None = None


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


def _python_imports(tree: ast.AST) -> list[tuple[ast.Import | ast.ImportFrom, bool, bool]]:
    """Every import with whether it sits under ``if TYPE_CHECKING:`` (depends:// skips those) and whether
    its nearest enclosing scope is a function (a class body runs at load time, so it does not count)."""
    found: list[tuple[ast.Import | ast.ImportFrom, bool, bool]] = []

    def walk(node: ast.AST, in_type_checking: bool, in_function: bool) -> None:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found.append((node, in_type_checking, in_function))
        elif isinstance(node, ast.If):
            for stmt in node.body:
                walk(stmt, in_type_checking or _type_checking_test(node.test), in_function)
            for stmt in node.orelse:
                walk(stmt, in_type_checking, in_function)
        else:
            # The nearest function-like ancestor decides, as the engine's edge_scope does: a class body
            # at module level runs at load time, a class body inside a function does not.
            inner = in_function or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
            for child in ast.iter_child_nodes(node):
                walk(child, in_type_checking, inner)

    walk(tree, False, False)
    return found


def _python_scoped_edges(scope: Scope) -> tuple[dict[Path, set[Path]], dict[Path, set[Path]], Coverage]:
    """(every edge, the edges whose every import is function-level, coverage), from one parse of each file."""
    edges: dict[Path, set[Path]] = defaultdict(set)
    load_time: dict[Path, set[Path]] = defaultdict(set)
    statements = type_checking = resolved = 0
    unparsed = []
    for importer in scope.importers:
        try:
            tree = ast.parse(importer.read_text(encoding='utf-8', errors='replace'), filename=str(importer))
        except (SyntaxError, ValueError) as exc:
            unparsed.append(f'{_relative(scope, importer)}: {exc}')
            continue
        for node, in_type_checking, in_function in _python_imports(tree):
            if in_type_checking:
                type_checking += 1
                continue
            statements += 1
            targets = [t for t in _python_targets(scope.scan, importer, node) if t != importer]
            resolved += bool(targets)
            for target in targets:
                edges[target].add(importer)
                if not in_function:
                    load_time[target].add(importer)
    if unparsed:
        # A file the oracle cannot parse is missing ground truth; this interpreter is too old for the corpus.
        raise RuntimeError(f'Python oracle could not parse {len(unparsed)} file(s) under '
                           f'Python {sys.version.split()[0]}; measurement unavailable: {unparsed[:3]}')
    lazy_only = {t: importers - load_time.get(t, set()) for t, importers in edges.items()}
    return edges, lazy_only, {'files': len(scope.importers), 'import_statements': statements,
                              'resolved_statements': resolved, 'type_checking_skipped': type_checking}


def build_python_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    edges, _, coverage = _python_scoped_edges(scope)
    return _finish(scope, edges), coverage


def python_lazy_only_edges(scope: Scope) -> Edges:
    """The Python edges every import behind which is function-level: the engine's ``&lazy=only`` view."""
    return _finish(scope, _python_scoped_edges(scope)[1])


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
        # a.b.C, then a.b.Outer for a.b.Outer.Nested, a.b.Outer.Mid.Nested, ...
        for cut in range(1, len(parts)):
            if hit := types.get(('.'.join(parts[:-cut]), parts[-cut])):
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


def _typescript_scoped_edges(scope: Scope) -> tuple[Edges, Edges, Coverage]:
    """The compiler parses/resolves the explicit population; Reveal is never imported."""
    if not shutil.which('node'):
        raise RuntimeError('TypeScript oracle prerequisite unavailable: Node is required')
    probe = Path(__file__).with_name('ts_import_oracle.cjs')
    result = subprocess.run(
        ['node', str(probe)], input=json.dumps({'root': str(scope.root), 'scan': str(scope.scan),
                                             'importers': [str(p) for p in scope.importers],
                                             'config': scope.config}),
        capture_output=True, text=True, encoding='utf-8', timeout=180)
    if result.returncode:
        raise RuntimeError(f'TypeScript compiler oracle failed: {result.stderr.strip()}')
    output = json.loads(result.stdout)
    return output['edges'], output['lazy_only'], output['coverage']


def build_typescript_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    edges, _, coverage = _typescript_scoped_edges(scope)
    return edges, coverage


def typescript_lazy_only_edges(scope: Scope) -> Edges:
    _, lazy_only, _ = _typescript_scoped_edges(scope)
    return lazy_only

def build_python_calls_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    """Python AST source calls, deduplicated by file/function and bare callee.

    Function bodies only; decorators, defaults, class initialization and module
    calls are outside this bounded population. Import aliases are resolved from
    Python's AST. This does not resolve runtime dispatch or receiver types.
    """
    edges: dict[str, set[str]] = defaultdict(set)
    functions = sites = 0
    for path in scope.importers:
        tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        aliases = {alias.asname: alias.name for node in ast.walk(tree)
                   if isinstance(node, ast.ImportFrom) for alias in node.names if alias.asname}
        class Visitor(ast.NodeVisitor):
            caller = None

            def visit_FunctionDef(self, node):
                nonlocal functions
                functions += 1
                previous, self.caller = self.caller, node.name
                for statement in node.body:
                    self.visit(statement)
                self.caller = previous

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node):
                previous, self.caller = self.caller, None
                for statement in node.body:
                    self.visit(statement)
                self.caller = previous

            def visit_Call(self, node):
                nonlocal sites
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
                if self.caller and name:
                    sites += 1
                    name = aliases.get(name, name).split('.')[-1]
                    edges[name].add(f"{_relative(scope, path)}::{self.caller}")
                self.generic_visit(node)
        Visitor().visit(tree)
    return {name: sorted(callers) for name, callers in sorted(edges.items())}, {
        'files': len(scope.importers), 'functions': functions, 'call_sites': sites,
        'population': 'python-function-body-bare-name-callers'}


def build_go_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    """Go resolves package directories; its standard parser supplies per-file imports.

    The declared population is buildless: every tracked .go file under importer_dirs,
    including tests and build-excluded generators. Targets fan out to that same file
    population in each toolchain-resolved directory, excluding the importing file.
    This is source dependency evidence, not a build-selected package graph.
    """
    go = shutil.which('go')
    if not go:
        raise RuntimeError('Go oracle prerequisite unavailable: Go is required')
    version = subprocess.run([go, 'version'], capture_output=True, text=True,
                             encoding='utf-8', check=True, timeout=30).stdout.split()[2]
    expected = scope.config.get('go_version', 'go1.21.5')
    if version != expected:
        raise RuntimeError(f'Go oracle requires {expected}, got {version}')
    patterns = ['./' + directory.strip('./') + '/...' if directory != '.' else './...'
                for directory in scope.config['importer_dirs']]
    listed = subprocess.run([go, 'list', '-json', *patterns], cwd=scope.root,
                            capture_output=True, text=True, encoding='utf-8', timeout=180)
    if listed.returncode:
        raise RuntimeError(f'Go package resolution failed: {listed.stderr.strip()}')
    decoder = json.JSONDecoder()
    remaining = listed.stdout.strip()
    packages = {}
    while remaining:
        package, end = decoder.raw_decode(remaining)
        packages[package['ImportPath']] = Path(package['Dir']).resolve()
        remaining = remaining[end:].lstrip()
    probe = Path(__file__).with_name('oracles') / 'go_import_oracle.go'
    parsed = subprocess.run([go, 'run', str(probe)], cwd=scope.root,
                            input=json.dumps([str(p) for p in scope.importers]),
                            capture_output=True, text=True, encoding='utf-8', timeout=180)
    if parsed.returncode:
        raise RuntimeError(f'Go source parse failed: {parsed.stderr.strip()}')
    facts = json.loads(parsed.stdout)
    if len(facts) != len(scope.importers) or not packages:
        raise RuntimeError('Go oracle population is empty or incomplete')
    by_directory: dict[Path, list[Path]] = defaultdict(list)
    for path in scope.importers:
        by_directory[path.parent].append(path)
    edges: dict[Path, set[Path]] = defaultdict(set)
    statements = resolved = 0
    for name, imports in facts.items():
        importer = Path(name)
        for specifier in imports:
            statements += 1
            directory = packages.get(specifier)
            if directory not in by_directory:
                continue
            resolved += 1
            for target in by_directory[directory]:
                if target != importer:
                    edges[target].add(importer)
    return _finish(scope, edges), {'files': len(facts), 'packages': len(packages),
                                  'import_statements': statements, 'resolved_statements': resolved,
                                  'go_version': version, 'population': 'tracked-buildless-source'}


ORACLES: dict[str, Oracle] = {
    'go-toolchain': Oracle(frozenset({'.go'}), build_go_oracle),
    'gcc-c': Oracle(C_SUFFIXES, _gcc_oracle('c')),
    'gcc-cpp': Oracle(CPP_SUFFIXES, _gcc_oracle('c++')),
    'python-ast': Oracle(frozenset({'.py'}), build_python_oracle, python_lazy_only_edges),
    'rust-use': Oracle(frozenset({'.rs'}), build_rust_oracle),
    'typescript-compiler': Oracle(frozenset({'.ts', '.tsx', '.js', '.jsx', '.mts', '.cts', '.mjs', '.cjs'}), build_typescript_oracle, typescript_lazy_only_edges),
    'java-jls': Oracle(frozenset({'.java'}), build_java_oracle),
}
