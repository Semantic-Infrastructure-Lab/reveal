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
import hashlib
import json
import os
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
    # Importers the oracle defines no edges for (a file no build compiles): left out of the scored population.
    unscored: Callable[[Scope], set[Path]] | None = None


def tracked_files(root: Path, directories: list[str], suffixes: frozenset[str]) -> list[Path]:
    """Git-tracked files under ``directories`` (relative to ``root``) with one of ``suffixes``."""
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z'],
                            check=True, capture_output=True, timeout=30)
    files = [Path(p.decode('utf-8')) for p in result.stdout.split(b'\0') if p]
    return [root / p for p in files if p.suffix in suffixes and
            any(p.is_relative_to(Path(d)) for d in directories)]


def _relative(scope: Scope, path: Path) -> str:
    return path.relative_to(scope.root).as_posix()


def test_importers(scope: Scope) -> set[str]:
    """Independent corpus labels: every importer under a reviewed test/fixture directory.

    These are corpus-root-relative directories declared in the manifest from the
    corpus's own test layout, never Reveal's filename/path classifier. Absence of
    the declaration means unqualified, not a population with no tests.
    """
    directories = scope.config['test_importer_dirs']
    if not isinstance(directories, list) or not directories:
        raise RuntimeError('test_importer_dirs must be a nonempty list of corpus-relative directories')
    for directory in directories:
        if (not isinstance(directory, str) or not directory or Path(directory).is_absolute()
                or '..' in Path(directory).parts or not (scope.root / directory).is_dir()
                or not (scope.root / directory).resolve().is_relative_to(scope.root)):
            raise RuntimeError(f'Invalid test_importer_dirs directory: {directory!r}')
    labels = {_relative(scope, path) for path in scope.importers
              if any(path.is_relative_to(scope.root / directory) for directory in directories)}
    if not labels:
        raise RuntimeError('Declared test importer population is empty; measurement unavailable')
    return labels


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


# ---- Rust: cargo's crate roots, rustc's module tree and its use bindings ----
#
# Cargo says which files are crate roots and which workspace crates each crate may name (`cargo metadata`).
# rustc's module tree (`mod x;` from each root, `#[path]` honoured) says which file holds each module, and its
# `use` bindings (globs included) say which module a path segment names. None of it comes from the filesystem
# conventions the resolver uses (BACK-2549: a crate root outside src/, a workspace crate named bare).

_LIB_KINDS = frozenset({'lib', 'rlib', 'dylib', 'cdylib', 'staticlib', 'proc-macro'})
_RUST_TOKENS = re.compile(r'''
    (?P<comment>//[^\n]*)
  | (?P<block>/\*)
  | (?P<raw>b?r(?P<hashes>\#*)")
  | (?P<string>b?"(?:\\.|[^"\\])*")
  | (?P<char>b?'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F_]*\}|.)|[^'\\\n])')
  | (?P<ident>(?:r\#)?[A-Za-z_][A-Za-z0-9_]*)
  | (?P<punct>::|[{};#\[\]=*,])
''', re.VERBOSE | re.DOTALL)
Token = tuple[str, str]
ModulePath = tuple[str, ...]


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


def rust_use_items(body: str) -> list[tuple[str, str | None]]:
    """Expand one use-declaration body into ``(a::b::c, alias)`` items: groups nest to any depth and
    ``self`` in a group names the group's base."""
    body = ' '.join(body.split())
    match = re.match(r'^(.*?)::\{(.*)\}$', body)
    if not match:
        if '{' in body:
            return []
        path, _, alias = body.partition(' as ')
        return [(path.strip(), alias.strip() or None)]
    base, inner = match.groups()
    items: list[tuple[str, str | None]] = []
    for item in _split_top_level(inner):
        # `self` names the group's base; anything else (a::b, a::{b, c}, a bare {b, c}) recurses.
        name, _, alias = item.partition(' as ')
        items += ([(base, alias.strip() or None)] if name.strip() == 'self'
                  else rust_use_items(f'{base}::{item}'))
    return items


def rust_use_paths(body: str) -> list[str]:
    """The ``a::b::c`` paths of one use-declaration body, aliases dropped."""
    return [path for path, _alias in rust_use_items(body)]


def _rust_tokens(text: str) -> list[Token]:
    """Identifiers, string literals and the punctuation of `mod` and `use` declarations, in order. Comments
    (block comments nest, as in rustc), char literals and everything else are dropped."""
    tokens: list[Token] = []
    position = 0
    while (match := _RUST_TOKENS.search(text, position)) is not None:
        kind, position = match.lastgroup, match.end()
        if kind == 'block':
            depth = 1
            while depth and position < len(text):
                step = text[position:position + 2]
                depth += (step == '/*') - (step == '*/')
                position += 2 if step in ('/*', '*/') else 1
        elif kind == 'raw':
            close = '"' + match.group('hashes')
            end = text.find(close, position)
            end = len(text) if end < 0 else end
            tokens.append(('string', text[position:end]))
            position = end + len(close)
        elif kind == 'string':
            tokens.append(('string', match.group()[match.group().index('"') + 1:-1]))
        elif kind in ('ident', 'punct'):
            word = match.group()
            tokens.append((kind, word[2:] if word.startswith('r#') else word))
    return tokens


def _module_suffix(stack: list[str | None]) -> ModulePath | None:
    """The inline modules a position sits in, or None inside a module that is inside a function body."""
    names: list[str] = []
    for frame in stack:
        if frame is None:
            break
        names.append(frame)
    return None if any(frame is not None for frame in stack[len(names):]) else tuple(names)


def rust_file_items(text: str) -> tuple[list[tuple[ModulePath, str, str | None, bool]],
                                         list[tuple[ModulePath, str, bool]]]:
    """A file's module declarations ``(inline modules, name, #[path] or None, has a body)``, outside function
    bodies and other items, and its use declarations ``(inline modules, body, at module level)``."""
    tokens = _rust_tokens(text)
    declarations: list[tuple[ModulePath, str, str | None, bool]] = []
    uses: list[tuple[ModulePath, str, bool]] = []
    stack: list[str | None] = []   # one entry per open brace: the inline module's name, else None
    path_attr: str | None = None
    i = 0
    while i < len(tokens):
        kind, word = tokens[i]
        names_module = i >= 2 and tokens[i - 2] == ('ident', 'mod') and tokens[i - 1][0] == 'ident'
        if (kind, word) == ('ident', 'use') and (suffix := _module_suffix(stack)) is not None:
            end, depth = i + 1, 0
            while end < len(tokens) and (depth or tokens[end] != ('punct', ';')):
                depth += (tokens[end] == ('punct', '{')) - (tokens[end] == ('punct', '}'))
                end += 1
            uses.append((suffix, ''.join(' as ' if t == ('ident', 'as') else t[1] for t in tokens[i + 1:end]),
                         None not in stack))
            i, path_attr = end + 1, None
            continue
        if (kind, word) == ('punct', '{'):
            stack.append(tokens[i - 1][1] if names_module else None)
            if names_module and None not in stack[:-1]:
                declarations.append((tuple(stack[:-1]), tokens[i - 1][1], path_attr, True))
            path_attr = None
        elif (kind, word) == ('punct', '}'):
            if stack:
                stack.pop()
            path_attr = None
        elif (kind, word) == ('punct', ';'):
            if names_module and None not in stack:
                declarations.append((tuple(stack), tokens[i - 1][1], path_attr, False))
            path_attr = None
        elif (kind == 'string' and i >= 3 and tokens[i - 1] == ('punct', '=')
              and tokens[i - 2] == ('ident', 'path') and tokens[i - 3] == ('punct', '[')):
            path_attr = word
        i += 1
    return declarations, uses


class _RustCrate(NamedTuple):
    package: str        # cargo package id
    root: Path          # the crate root file
    is_lib: bool
    is_build: bool      # a build script sees only build-dependencies
    edition_2015: bool  # a bare use path is crate-root relative


class _RustTree(NamedTuple):
    # module -> the files holding its items: one, or one per `#[cfg]` alternative (`#[path = "a.rs"] mod imp;`
    # beside `#[path = "b.rs"] mod imp;`); no configuration is evaluated, so every alternative is in the tree
    modules: dict[ModulePath, list[Path]]
    owned: dict[Path, set[ModulePath]]   # file -> the modules it is a file of (not its inline ones)
    uses: dict[ModulePath, list[tuple[Path, str, bool]]]  # module -> (file, use body, at module level)


def _rust_module_tree(root: Path) -> _RustTree:
    """rustc's module tree from one crate root. An inline ``mod x { }`` lives in its parent's file."""
    tree = _RustTree({(): [root]}, defaultdict(set), defaultdict(list))
    tree.owned[root].add(())
    pending: list[tuple[Path, ModulePath]] = [(root, ())]
    while pending:
        file, path = pending.pop()
        try:
            declarations, uses = rust_file_items(file.read_text(encoding='utf-8', errors='replace'))
        except OSError:
            continue
        for suffix, body, top in uses:
            tree.uses[path + suffix].append((file, body, top))
        directory = file.parent if file == root or file.name == 'mod.rs' else file.with_suffix('')
        for inline, name, attr, has_body in declarations:
            module = path + inline + (name,)
            if has_body:
                child: Path | None = file
            else:
                # A #[path] outside inline modules is relative to the declaring file's own directory.
                base = file.parent if attr is not None and not inline else directory.joinpath(*inline)
                candidates = [base / attr] if attr is not None else [base / f'{name}.rs', base / name / 'mod.rs']
                child = next((c.resolve() for c in candidates if c.is_file()), None)
            if child is None or child in tree.modules.get(module, ()):
                continue
            tree.modules.setdefault(module, []).append(child)
            if not has_body:
                tree.owned[child].add(module)
                pending.append((child, module))
    return tree


def _cargo_packages(scope: Scope) -> tuple[list[dict], int]:
    """Every package of every tracked Cargo.toml's workspace, as ``cargo metadata --no-deps`` lists it, and
    how many manifests cargo could not read. A rust-toolchain.toml pin must not download a toolchain."""
    cargo = shutil.which('cargo')
    if not cargo:
        raise RuntimeError('Rust oracle prerequisite unavailable: cargo is required')
    env = {**os.environ, 'RUSTUP_TOOLCHAIN': os.environ.get('RUSTUP_TOOLCHAIN', 'stable')}
    manifests = sorted(p for p in tracked_files(scope.root, ['.'], frozenset({'.toml'})) if p.name == 'Cargo.toml')
    packages: dict[str, dict] = {}
    covered: set[Path] = set()
    failed = 0
    for manifest in manifests:
        if manifest.resolve() in covered:
            continue
        try:
            listed = subprocess.run([cargo, 'metadata', '--no-deps', '--offline', '--format-version', '1',
                                     '--manifest-path', str(manifest)], cwd=manifest.parent, env=env,
                                    capture_output=True, text=True, encoding='utf-8', timeout=ORACLE_PROBE_TIMEOUT)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f'cargo metadata timed out on {manifest}; measurement unavailable') from exc
        if listed.returncode:
            failed += 1
            continue
        for package in json.loads(listed.stdout)['packages']:
            packages.setdefault(package['id'], package)
            covered.add(Path(package['manifest_path']).resolve())
    if not packages:
        raise RuntimeError('Rust oracle found no cargo packages; measurement unavailable')
    return sorted(packages.values(), key=lambda p: p['manifest_path']), failed


class _RustProject(NamedTuple):
    packages: int
    manifests_failed: int
    trees: dict[_RustCrate, _RustTree]
    names: dict[tuple[str, bool], dict[str, _RustCrate]]  # (package, build script?) -> workspace crates it names
    homes: dict[Path, list[tuple[_RustCrate, ModulePath]]]  # file -> every (crate, module) it is the file of


def _rust_project(scope: Scope) -> _RustProject:
    """Every crate root and module tree, and the workspace crates each crate may name: its path dependencies
    under the names code spells (renames applied) and, outside the library, its own package's library."""
    packages, failed = _cargo_packages(scope)
    lib_of: dict[str, _RustCrate] = {}
    trees: dict[_RustCrate, _RustTree] = {}
    for package in packages:
        for target in package['targets']:
            kinds = set(target['kind'])
            crate = _RustCrate(package['id'], Path(target['src_path']).resolve(), bool(kinds & _LIB_KINDS),
                               'custom-build' in kinds, target.get('edition', package.get('edition')) == '2015')
            trees[crate] = _rust_module_tree(crate.root)
            if crate.is_lib:
                lib_of[package['id']] = crate
    package_at = {Path(p['manifest_path']).resolve().parent: p['id'] for p in packages}
    lib_names = {p['id']: next(t['name'] for t in p['targets'] if set(t['kind']) & _LIB_KINDS)
                 for p in packages if p['id'] in lib_of}
    names: dict[tuple[str, bool], dict[str, _RustCrate]] = {}
    for package in packages:
        for build in (False, True):
            spelled = names.setdefault((package['id'], build), {})
            for dependency in package['dependencies']:
                if (dependency.get('kind') == 'build') != build or not dependency.get('path'):
                    continue
                local = lib_of.get(package_at.get(Path(dependency['path']).resolve(), ''))
                if local is not None:
                    spelled[(dependency.get('rename') or dependency['name']).replace('-', '_')] = local
            if package['id'] in lib_of and not build:
                spelled.setdefault(lib_names[package['id']].replace('-', '_'), lib_of[package['id']])
    homes: dict[Path, list[tuple[_RustCrate, ModulePath]]] = defaultdict(list)
    for crate, tree in trees.items():
        for file, modules in tree.owned.items():
            homes[file].extend((crate, module) for module in sorted(modules))
    return _RustProject(len(packages), failed, trees, names, homes)


class _RustPaths:
    """rustc's path resolution over the module trees, at module granularity: a segment names a child
    module, else a module a ``use`` in that module binds by name, else one a glob ``use`` brings in."""

    def __init__(self, project: _RustProject):
        self.project = project
        self._bindings: dict[tuple[_RustCrate, ModulePath], tuple[dict[str, str], list[str]]] = {}
        self._active: set[tuple[_RustCrate, ModulePath, str]] = set()

    def _bound(self, crate: _RustCrate, module: ModulePath) -> tuple[dict[str, str], list[str]]:
        key = (crate, module)
        if key not in self._bindings:
            named: dict[str, str] = {}
            globs: list[str] = []
            for _file, body, top in self.project.trees[crate].uses.get(module, ()):
                for path, alias in (rust_use_items(body) if top else ()):
                    if path.endswith('::*'):
                        globs.append(path[:-3])
                    else:
                        named.setdefault(alias or path.rsplit('::', 1)[-1], path)
            self._bindings[key] = (named, globs)
        return self._bindings[key]

    def child(self, crate: _RustCrate, module: ModulePath, name: str) -> tuple[_RustCrate, ModulePath] | None:
        if module + (name,) in self.project.trees[crate].modules:
            return crate, module + (name,)
        key = (crate, module, name)
        if key in self._active:
            return None
        self._active.add(key)
        try:
            named, globs = self._bound(crate, module)
            if name in named and (found := self.module_of(crate, module, named[name])) is not None:
                return found
            for glob in globs:
                if (base := self.module_of(crate, module, glob)) is not None:
                    if (found := self.child(*base, name)) is not None:
                        return found
            return None
        finally:
            self._active.discard(key)

    def module_of(self, crate: _RustCrate, module: ModulePath, path: str) -> tuple[_RustCrate, ModulePath] | None:
        """The module the whole of ``path`` names from ``module``, or None."""
        walked = self.walk(crate, module, path)
        return (walked[1], walked[2]) if walked is not None and walked[3] else None

    def walk(self, crate: _RustCrate, module: ModulePath, path: str):
        """``(kind, crate, module, complete, below_anchor)`` for the deepest module ``path`` reaches from
        ``module``: kind is ``anchored`` (crate::, self::, super::, a 2015 crate-relative path), ``extern``
        (a workspace crate named bare; its root counts) or ``bare`` (a local name); None when the path names
        nothing in the workspace."""
        absolute = path.startswith('::')
        head, *rest = path.lstrip(':').split('::')
        spelled = self.project.names.get((crate.package, crate.is_build), {})
        if head in ('crate', 'self', 'super') and not absolute:
            kind, current = 'anchored', () if head == 'crate' else module[:-1] if head == 'super' else module
        elif head in spelled:
            kind, crate, current = 'extern', spelled[head], ()
        elif absolute:
            return None
        elif crate.edition_2015:
            kind, current, rest = 'anchored', (), [head, *rest]
        elif (found := self.child(crate, module, head)) is not None:
            kind, (crate, current) = 'bare', found
        else:
            return None
        below = 0
        for segment in rest:
            if segment in ('super', 'self') and kind == 'anchored' and not below:
                current = current[:-1] if segment == 'super' else current
                continue
            found = self.child(crate, current, segment)
            if found is None:
                return kind, crate, current, False, below
            (crate, current), below = found, below + 1
        return kind, crate, current, True, below


def _rust_scored(scope: Scope, project: _RustProject) -> tuple[list[Path], list[Path]]:
    """(importers some crate compiles, importers no crate's module tree holds: dead or macro-included files,
    whose edges no compiler defines)."""
    held = [p for p in scope.importers if project.homes.get(p.resolve())]
    return held, [p for p in scope.importers if not project.homes.get(p.resolve())]


def build_rust_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    """Each use path from each importer, in each crate module holding the importer, to the file of the
    deepest module it reaches: below its anchor for ``crate::``/``self::``/``super::``, from the named
    crate's root (which counts) for a workspace crate named bare. Counted, not scored: a path that stays at
    its anchor (``crate::Item``, ``super::*``), a 2018 path through a local name (``mod a; use a::B;``), and
    importers no crate compiles (left out of the scored population)."""
    project = _rust_project(scope)
    paths = _RustPaths(project)
    real_root = scope.root.resolve()
    held, unheld = _rust_scored(scope, project)
    importer_at = {p.resolve(): p for p in held}
    edges: dict[Path, set[Path]] = defaultdict(set)
    counts = dict.fromkeys(('use_statements', 'local_paths', 'anchor_item_paths', 'bare_local_paths'), 0)
    # Per crate: a file two crates compile (a shared tests/common/mod.rs) is read in each.
    for crate, tree in sorted(project.trees.items(), key=lambda item: str(item[0].root)):
        for module, uses in sorted(tree.uses.items()):
            for source, body, _top in uses:
                importer = importer_at.get(source)
                if importer is None:
                    continue
                counts['use_statements'] += 1
                for path in rust_use_paths(body):
                    walked = paths.walk(crate, module, path)
                    if walked is None:
                        continue
                    kind, target_crate, target, _complete, below = walked
                    if kind == 'bare':
                        counts['bare_local_paths'] += 1
                    elif kind == 'anchored' and not below:
                        counts['anchor_item_paths'] += 1
                    else:
                        counts['local_paths'] += 1
                        for file in project.trees[target_crate].modules[target]:
                            if file != source and file.is_relative_to(real_root):
                                edges[scope.root / file.relative_to(real_root)].add(importer)
    return _finish(scope, edges), {
        'files': len(scope.importers), 'unscored_importers': len(unheld), 'packages': project.packages,
        'crate_roots': len(project.trees), 'manifests_failed': project.manifests_failed, **counts}


def rust_unscored_importers(scope: Scope) -> set[Path]:
    """Importers no crate compiles (a file a commented-out ``mod`` names, a macro-included file)."""
    return set(_rust_scored(scope, _rust_project(scope))[1])


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

    def resolve(dotted: str) -> list[Path]:
        parts = dotted.split('.')
        # a.b.C, then a.b.Outer for a.b.Outer.Nested, a.b.Outer.Mid.Nested, ...
        for cut in range(1, len(parts)):
            if hit := types.get(('.'.join(parts[:-cut]), parts[-cut])):
                return hit
        return []

    edges: dict[Path, set[Path]] = defaultdict(set)
    statements = resolved = package_wildcards = member_wildcards = 0
    for importer in scope.importers:
        text = sources.get(importer)
        if text is None:  # an importer outside the scan root
            text = importer.read_text(encoding='utf-8', errors='replace')
        for static, dotted, wildcard in IMPORT.findall(text):
            if static and not wildcard:
                dotted = dotted.rsplit('.', 1)[0]  # import static a.b.C.member -> a.b.C
            statements += 1
            if wildcard and not static and dotted in packages:
                # One rule with Kotlin and Scala (BACK-1711 D-W1/D-W2): a package wildcard names no file.
                # It is counted, never scored; Reveal discloses it instead of guessing edges (BACK-2506).
                package_wildcards += 1
                continue
            # a.b.C.* and static a.b.C.* import C's members: an explicit import of the file declaring C
            # (resolve peels the last segment, so a '.*' placeholder makes it start at C itself).
            targets = [t for t in resolve(dotted + '.*' if wildcard else dotted) if t != importer]
            member_wildcards += bool(wildcard and targets)
            resolved += bool(targets)
            for target in targets:
                edges[target].add(importer)
    return _finish(scope, edges), {'files': len(scope.importers), 'indexed_types': len(types),
                                   'import_statements': statements, 'resolved_statements': resolved,
                                   'in_tree_package_wildcards': package_wildcards,
                                   'type_member_wildcards': member_wildcards}


# ---- Kotlin and Scala: a declaration is indexed under its package, whatever the file is named ----
#
# Neither language ties a file name to its types (Kotlin: any file; Scala: any file), so ``import a.b.C``
# names the file that DECLARES ``C`` in package ``a.b``. The rule here is independent of Reveal's
# extractor and resolver (BACK-2507): comments and string literals are blanked, braces are counted, and a
# declaration keyword at brace depth 0 declares its name. One shared policy with Reveal's documented
# member-index behaviour, not an independent check of it: a name declared in several files of one package
# (Kotlin multiplatform source sets) is an edge to each. Every import that names a symbol is scored: an
# explicit import, each name of a Scala selector list, and a type-member wildcard (``a.Implicits._``,
# ``a.Obj.*``) through the symbol it names (BACK-1237). A package wildcard names no file: it is counted in
# the coverage (``in_tree_package_wildcards`` when the tree declares the package), never scored
# (BACK-1711/2506).

def _blank(text: str, start: int, end: int) -> str:
    """Spaces for ``text[start:end]``, keeping newlines so line numbers and brace lines survive."""
    return ''.join(c if c in '\r\n' else ' ' for c in text[start:end])


def jvm_strip_noise(text: str) -> str:
    """``text`` with comments, string and character literals replaced by spaces (newlines kept), so a
    declaration or import that only appears inside a literal or comment is invisible. Block comments nest
    (both languages); a ``${ ... }`` template inside a string is blanked with the string."""
    out: list[str] = []
    n = len(text)
    i = 0

    def skip_braces(j: int) -> int:  # j points just past '${'; return the index past the matching '}'
        depth = 1
        while j < n and depth:
            if text.startswith('"""', j):
                j = skip_string(j, True)
                continue
            c = text[j]
            if c == '"':
                j = skip_string(j, False)
                continue
            depth += (c == '{') - (c == '}')
            j += 1
        return j

    def skip_string(j: int, triple: bool) -> int:  # j at the opening quote(s); return the index past the close
        j += 3 if triple else 1
        while j < n:
            if triple:
                if text.startswith('"""', j):
                    j += 3
                    while j < n and text[j] == '"':  # a closing run of 4+ quotes ends at the last
                        j += 1
                    return j
            elif text[j] == '"':
                return j + 1
            elif text[j] == '\n':
                return j  # an unterminated single-line string ends at the line
            if text[j] == '\\' and not triple:
                j += 2
                continue
            if text.startswith('${', j):
                j = skip_braces(j + 2)
                continue
            j += 1
        return j

    while i < n:
        two = text[i:i + 2]
        if two == '//':
            j = text.find('\n', i)
            j = n if j < 0 else j
        elif two == '/*':
            depth, j = 1, i + 2
            while j < n and depth:
                if text.startswith('/*', j):
                    depth, j = depth + 1, j + 2
                elif text.startswith('*/', j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
        elif text.startswith('"""', i):
            j = skip_string(i, True)
        elif text[i] == '"':
            j = skip_string(i, False)
        elif text[i] == "'" and re.match(r"'(?:\\.[^']{0,6}|[^\\'\n])'", text[i:i + 10]):
            j = i + re.match(r"'(?:\\.[^']{0,6}|[^\\'\n])'", text[i:i + 10]).end()
        else:
            out.append(text[i])
            i += 1
            continue
        out.append(_blank(text, i, j))
        i = j
    return ''.join(out)


_KT_MODS = (r'(?:(?:public|private|internal|protected|open|abstract|final|sealed|data|enum|annotation|inner|value|'
            r'inline|expect|actual|external|const|lateinit|tailrec|suspend|operator|infix|override|fun)\s+)*')
_KT_DECL = re.compile(r'^(?:@[\w.:]+(?:\([^)]*\))?\s*)*' + _KT_MODS +
                      r'(class|interface|object|typealias|fun|val|var)\s+(.*)$')
_SC_MODS = (r'(?:(?:private(?:\[\w+\])?|protected(?:\[\w+\])?|sealed|abstract|final|implicit|case|lazy|override|open|'
            r'inline|transparent|opaque|infix)\s+)*')
_SC_DECL = re.compile(r'^(?:@[\w.]+(?:\([^)]*\))?\s*)*' + _SC_MODS +
                      r'(?:class|trait|object|enum|type|def|val|var|given)\s+(\w+)')
# BACK-2515: `package object X` is not a top-level symbol; it declares package P.X and its members are declarations in it
_SC_PACKAGE_OBJECT = re.compile(r'^(?:@[\w.]+\s*)*(?:(?:private(?:\[\w+\])?|protected(?:\[\w+\])?)\s+)*package\s+object\s+(\w+)')
_JVM_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)\s*(\{)?\s*$')
# One import statement: the rest of the line, where a brace group may run over several lines (Scala
# `import a.{\n  X,\n  Y\n}`); comments and literals are already blanked, so a brace is syntax.
_JVM_IMPORT = re.compile(r'^[ \t]*import\s+((?:[^\n{]|\{[^}]*\})+?)\s*;?\s*$', re.MULTILINE)


def _kotlin_declared_name(line: str) -> str | None:
    """The name a top-level Kotlin declaration line declares: ``fun <T> Flow<T>.observeOn(...)`` declares
    ``observeOn`` (the receiver and the type parameters are not names), ``class Foo<T>(...)`` declares ``Foo``."""
    match = _KT_DECL.match(line)
    if not match:
        return None
    keyword, rest = match.groups()
    rest = rest.lstrip()
    if keyword in ('fun', 'val', 'var') and rest.startswith('<'):
        depth = 0
        for index, ch in enumerate(rest):  # skip the type parameters; `->` is an arrow, not a closing bracket
            if ch == '<':
                depth += 1
            elif ch == '>' and rest[index - 1] != '-':
                depth -= 1
                if not depth:
                    rest = rest[index + 1:].lstrip()
                    break
    header = re.match(r'[^(:={;]*', rest).group(0)
    while True:  # drop the receiver's type arguments: Flow<T>.name -> Flow.name
        reduced = re.sub(r'<[^<>]*>', '', header)
        if reduced == header:
            break
        header = reduced
    names = re.findall(r'[\w`]+', header)
    if not names:
        return None
    return names[-1].strip('`') if keyword in ('fun', 'val', 'var') else names[0].strip('`')


def _scala_declared_name(line: str) -> str | None:
    match = _SC_DECL.match(line)
    return match.group(1) if match else None


def _top_level_lines(clean: str, language: str) -> tuple[list[str], list[str]]:
    """``(packages, declaration-lines)``: the braceless package clauses of the file in order, and each line
    that starts at brace depth 0 (a braced ``package a { ... }`` body counts as depth 0, as the language does)."""
    packages: list[str] = []
    lines: list[str] = []
    stack: list[bool] = []  # True: a package-body brace (not a nesting level)
    depth = 0
    for line in clean.split('\n'):
        stripped = line.strip()
        if depth == 0 and stripped:
            header = _JVM_PACKAGE.match(stripped) if not stripped.startswith('package object') else None
            if header and not header.group(2):
                packages.append(header.group(1))
            lines.append(stripped)
        header = _JVM_PACKAGE.match(stripped)
        for ch in line:
            if ch == '{':
                is_package = bool(header and header.group(2)) and language == 'scala'
                stack.append(is_package)
                depth += 0 if is_package else 1
            elif ch == '}' and stack:
                depth -= 0 if stack.pop() else 1
    return packages, lines


def _scala_package_object_members(clean: str) -> list[tuple[str, str]]:
    """``(package object name, member name)`` for each declaration directly inside a top-level
    ``package object X { ... }`` (BACK-2515). A member starts a line at brace depth 1 of the object's body; a
    body written on one line is not read (none on the pinned corpora)."""
    members: list[tuple[str, str]] = []
    current: str | None = None
    pending: str | None = None
    depth = 0
    for line in clean.split('\n'):
        stripped = line.strip()
        if depth == 0 and stripped and not stripped.startswith('{'):
            found = _SC_PACKAGE_OBJECT.match(stripped)
            pending = found.group(1) if found else None
        elif depth == 1 and current:
            name = _scala_declared_name(stripped)
            if name:
                members.append((current, name))
        for ch in line:
            if ch == '{':
                depth += 1
                if depth == 1 and pending:
                    current, pending = pending, None
            elif ch == '}' and depth:
                depth -= 1
                if depth == 0:
                    current = None
    return members


_SCALA_DEF = re.compile(r'(?<![\w$])def(?![\w$])')


def _scala_def_body_lines(clean: str, raw: str) -> set[int]:
    """Indexes of the lines that start inside a ``def`` body (BACK-2079), read from braces and indentation alone.

    A ``{`` at parenthesis depth 0 after a ``def`` header (``def f(...) = {`` or procedure syntax ``def f() {``)
    opens a body; every block nested in a body is in it. A header ending in ``=`` with no brace on its line
    continues on the following more-indented lines (Scala 2 expression bodies, Scala 3 indentation syntax).
    A lambda or block outside every ``def`` is not a body: Reveal leaves such an import unclassified, which
    counts with the load-time edges, as here. ``clean`` has comments and literals blanked, with the same lines
    as ``raw``; indentation is read from ``raw``, since a blanked string at a line start reads as indentation.
    """
    local: set[int] = set()
    stack: list[bool] = []  # one per open '{': whether it is inside a def body
    indent_bodies: list[int] = []  # the indent of each `def ... =` whose body continues on deeper lines
    pending: dict[str, int] | None = None  # an open def header: its line indent and whether '=' was seen
    paren = 0  # across lines: a def header may wrap its parameter list
    for index, (line, raw_line) in enumerate(zip(clean.split('\n'), raw.split('\n'))):
        stripped = line.strip()
        indent = len(raw_line) - len(raw_line.lstrip())
        if stripped:
            while indent_bodies and indent <= indent_bodies[-1]:
                indent_bodies.pop()
        if (stack and stack[-1]) or indent_bodies:
            local.add(index)
        defs = {match.start() for match in _SCALA_DEF.finditer(line)}
        for i, ch in enumerate(line):
            if i in defs:
                pending = {'indent': indent, 'eq': 0}
            elif ch in '([':
                paren += 1
            elif ch in ')]':
                paren = max(paren - 1, 0)
            elif ch == '=' and pending is not None and paren <= 0 \
                    and line[i + 1:i + 2] not in ('=', '>') and line[i - 1:i] not in ('=', '!', '<', '>'):
                pending['eq'] = 1
            elif ch == '{':
                opens_body = pending is not None and paren <= 0
                stack.append((stack[-1] if stack else False) or bool(indent_bodies) or opens_body)
                if opens_body:
                    pending = None
            elif ch == '}' and stack:
                stack.pop()
        if pending is not None and paren <= 0:
            if pending['eq']:
                indent_bodies.append(pending['indent'])  # the body is on the following deeper lines
            pending = None  # an abstract def, or a body already opened on this line
    return local


def _jvm_import_paths(clean: str, language: str, counts: dict[str, int]) -> list[tuple[str, bool, int]]:
    """``(dotted name, is_wildcard, line index)`` for every name an import statement names; a wildcard's name
    is its prefix.

    Scala ``import a.B, c.D`` is two names; a selector list ``a.{X, Y => Z, W => _, _}`` names ``a.X``, ``a.Y``
    and the wildcard ``a`` (``W`` is hidden). Selector lists and wildcards are also counted in ``counts``.
    """
    names: list[tuple[str, bool, int]] = []
    for match in _JVM_IMPORT.finditer(clean):
        line = clean.count('\n', 0, match.start())
        names.extend((dotted, wildcard, line)
                     for dotted, wildcard in _jvm_statement_names(' '.join(match.group(1).split()), language, counts))
    return names


def _jvm_statement_names(statement: str, language: str, counts: dict[str, int]) -> list[tuple[str, bool]]:
    """``(dotted name, is_wildcard)`` for each name one import statement's text names."""
    names: list[tuple[str, bool]] = []
    pieces, depth, current = [], 0, ''
    for ch in statement:  # Scala allows `import a.B, c.D`
        if ch == ',' and depth == 0 and language == 'scala':
            pieces.append(current)
            current = ''
            continue
        depth += (ch == '{') - (ch == '}')
        current += ch
    pieces.append(current)
    for piece in pieces:
        piece = re.sub(r'\s+as\s+\w+\s*$', '', piece.strip())
        if not piece:
            continue
        if '{' in piece:
            counts['selector_lists'] += 1
            prefix, _, body = piece.partition('{')
            for item in body.rstrip('} \t').split(','):
                name = item.split('=>')[0].split(' as ')[0].strip()
                if '=>' in item and item.split('=>')[1].strip() == '_':
                    continue  # `X => _` hides X
                if name in ('_', '*'):
                    counts['wildcard_statements'] += 1
                    names.append((prefix.strip().rstrip('.'), True))
                elif re.fullmatch(r'\w+', name):
                    names.append((prefix.strip() + name, False))
        elif piece.endswith(('.*', '._')):
            counts['wildcard_statements'] += 1
            names.append((piece[:-2].replace('`', ''), True))
        elif re.fullmatch(r'[\w.`]+', piece):
            names.append((piece.replace('`', ''), False))
    return names


def _build_jvm_declared_oracle(scope: Scope, language: str, suffix: str,
                               declared_name: 'Callable[[str], str | None]') -> tuple[Edges, Coverage]:
    edges, _load_time, coverage = _jvm_declared_scoped_edges(scope, language, suffix, declared_name)
    return _finish(scope, edges), coverage


def _jvm_declared_scoped_edges(scope: Scope, language: str, suffix: str,
                               declared_name: 'Callable[[str], str | None]'
                               ) -> tuple[dict[Path, set[Path]], dict[Path, set[Path]], Coverage]:
    """``(edges, load-time edges, coverage)``. A Scala import inside a ``def`` body is function-level
    (``_scala_def_body_lines``); every other import, and every Kotlin import, is load-time."""
    raw_sources = {p: p.read_text(encoding='utf-8', errors='replace')
                   for p in tracked_files(scope.root, [_relative(scope, scope.scan)], frozenset({suffix}))}
    sources = {p: jvm_strip_noise(text) for p, text in raw_sources.items()}
    declared: dict[tuple[str, str], set[Path]] = defaultdict(set)
    file_packages: dict[Path, str] = {}
    package_objects: set[str] = set()  # BACK-2515: packages a `package object` declares members of
    for path, clean in sources.items():
        packages, lines = _top_level_lines(clean, language)
        package = '.'.join(packages) if language == 'scala' else (packages[0] if packages else '')
        file_packages[path] = package
        for line in lines:
            name = declared_name(line)
            if name:
                declared[(package, name)].add(path)
        if language == 'scala':
            for container, member in _scala_package_object_members(clean):
                declared[(f'{package}.{container}' if package else container, member)].add(path)
                package_objects.add(f'{package}.{container}' if package else container)
    counts = {'wildcard_statements': 0, 'selector_lists': 0, 'in_tree_package_wildcards': 0,
              'type_member_wildcards': 0}
    edges: dict[Path, set[Path]] = defaultdict(set)
    load_time: dict[Path, set[Path]] = defaultdict(set)
    statements = resolved = 0

    packages: set[str] = set()
    for package in [*file_packages.values(), *package_objects]:
        parts = package.split('.') if package else []
        packages.update('.'.join(parts[:k]) for k in range(1, len(parts) + 1))

    def resolve(dotted: str) -> set[Path]:
        # The longest in-tree package prefix is the package; the next segment must be a top-level symbol
        # declared in it, and anything after that is a member or nested type of that symbol. A prefix that is
        # not a package is never peeled further (``cats.effect.X.y`` must not land on ``package object effect``).
        parts = dotted.split('.')
        for k in range(len(parts) - 1, 0, -1):
            if '.'.join(parts[:k]) in packages:
                # Anything after the symbol is a member or nested type reached THROUGH it: the file declaring
                # the symbol is a dependency even when the member itself is inherited from another file.
                return declared.get(('.'.join(parts[:k]), parts[k]), set())
        return set()

    for importer in scope.importers:
        clean = sources.get(importer)
        raw = raw_sources.get(importer)
        if clean is None or raw is None:  # an importer outside the scan root
            raw = importer.read_text(encoding='utf-8', errors='replace')
            clean = jvm_strip_noise(raw)
        own = file_packages.get(importer) or '.'.join(_top_level_lines(clean, language)[0])
        # Scala reads an import relative to each enclosing package too, innermost first.
        bases = [''] + (['.'.join(own.split('.')[:keep]) + '.' for keep in range(len(own.split('.')), 0, -1)]
                        if language == 'scala' and own else [])
        in_def = _scala_def_body_lines(clean, raw) if language == 'scala' else set()
        for dotted, wildcard, line in _jvm_import_paths(clean, language, counts):
            if wildcard and any(base + dotted in packages for base in bases):
                counts['in_tree_package_wildcards'] += 1  # a package wildcard names no file
                continue
            targets: set[Path] = set()
            for base in bases:
                targets = resolve(base + dotted)
                if targets:
                    break
            if not wildcard:
                statements += 1
            if importer in targets:  # the file declares the name itself: its own declaration, no other file
                continue
            if wildcard:
                counts['type_member_wildcards'] += bool(targets)
            else:
                resolved += bool(targets)
            for target in targets:
                edges[target].add(importer)
                if line not in in_def:
                    load_time[target].add(importer)
    return edges, load_time, {'files': len(scope.importers), 'indexed_symbols': len(declared),
                              'import_statements': statements, 'resolved_statements': resolved, **counts}


def build_kotlin_declared_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    return _build_jvm_declared_oracle(scope, 'kotlin', '.kt', _kotlin_declared_name)


def build_scala_declared_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    return _build_jvm_declared_oracle(scope, 'scala', '.scala', _scala_declared_name)


def scala_lazy_only_edges(scope: Scope) -> Edges:
    """The Scala edges every import behind which sits in a ``def`` body: the engine's ``&lazy=only`` view."""
    edges, load_time, _ = _jvm_declared_scoped_edges(scope, 'scala', '.scala', _scala_declared_name)
    return _finish(scope, {t: importers - load_time.get(t, set()) for t, importers in edges.items()})


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


def _probe_identity(scope: Scope, probe: Path) -> Coverage:
    """Identity of one native probe, its declared inputs and exact source population."""
    population = [[_relative(scope, path), hashlib.sha256(path.read_bytes()).hexdigest()]
                  for path in sorted(scope.importers)]
    return {
        'population_digest': hashlib.sha256(json.dumps(population).encode('utf-8')).hexdigest(),
        'oracle_digest': hashlib.sha256(probe.read_bytes()).hexdigest(),
        'config_digest': hashlib.sha256(json.dumps(scope.config, sort_keys=True).encode('utf-8')).hexdigest(),
    }


def _php_scoped_edges(scope: Scope) -> tuple[Edges, Edges, Coverage]:
    """Native tokens qualify static include sites, independently of Reveal parsing."""
    if not shutil.which('php'):
        raise RuntimeError('PHP oracle prerequisite unavailable: PHP CLI is required')
    probe = Path(__file__).parent / 'oracles' / 'php_import_oracle.php'
    result = subprocess.run(
        ['php', str(probe)], input=json.dumps({'root': str(scope.root),
                                             'importers': [str(p) for p in scope.importers],
                                             'config': scope.config}),
        capture_output=True, text=True, encoding='utf-8', timeout=ORACLE_PROBE_TIMEOUT)
    if result.returncode:
        raise RuntimeError(f'PHP native token oracle failed: {result.stderr.strip()}')
    output = json.loads(result.stdout)
    coverage = output['coverage']
    coverage.update(_probe_identity(scope, probe))
    return output['edges'], output['lazy_only'], coverage


def build_php_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    edges, _, coverage = _php_scoped_edges(scope)
    return edges, coverage


def php_lazy_only_edges(scope: Scope) -> Edges:
    _, lazy_only, _ = _php_scoped_edges(scope)
    return lazy_only


def _ruby_probe_identity(scope: Scope, probe: Path) -> Coverage:
    try:
        return _probe_identity(scope, probe)
    except OSError as error:
        raise RuntimeError(f'Ruby oracle input/probe identity unavailable ({type(error).__name__})') from error


def _ruby_target_inventory(scope: Scope) -> tuple[list[Path], str]:
    paths = tracked_files(scope.root, ['.'], frozenset({'.rb'}))
    digest = hashlib.sha256(json.dumps(sorted(_relative(scope, path) for path in paths)).encode('utf-8')).hexdigest()
    return paths, digest


def _ruby_scoped_edges(scope: Scope) -> tuple[Edges, Edges, Coverage]:
    """Opt-in native relative-loader facts; no scheduled or product gating promotion."""
    executable = shutil.which(os.environ.get('REVEAL_RUBY_ORACLE', 'ruby'))
    if executable is None:
        raise RuntimeError('Ruby oracle prerequisite unavailable: native Ruby Ripper is required')
    probe = Path(__file__).parent / 'oracles' / 'ruby_import_oracle.rb'
    frozen = scope._replace(importers=list(scope.importers),
                            config=json.loads(json.dumps(scope.config, sort_keys=True)))
    targets, target_inventory = _ruby_target_inventory(frozen)
    identity = _ruby_probe_identity(frozen, probe)
    env = {key: value for key, value in os.environ.items()
           if key not in {'RUBYOPT', 'RUBYLIB', 'RUBYGEMS_GEMDEPS'}}
    result = subprocess.run(
        [executable, '--disable-gems', str(probe)],
        input=json.dumps({'root': str(frozen.root), 'scan': str(frozen.scan),
                          'importers': [str(path) for path in frozen.importers],
                          'targets': [str(path) for path in targets], 'config': frozen.config}),
        capture_output=True, text=True, encoding='utf-8',
        timeout=ORACLE_PROBE_TIMEOUT, cwd=scope.root, env=env)
    if result.returncode:
        raise RuntimeError(f'Ruby native Ripper oracle failed: {result.stderr.strip()}')
    output = json.loads(result.stdout)
    coverage = output['coverage']
    if identity != _ruby_probe_identity(scope, probe):
        raise RuntimeError('Ruby oracle input/probe identity changed during native measurement')
    if target_inventory != _ruby_target_inventory(scope)[1]:
        raise RuntimeError('Ruby target inventory changed during native measurement')
    if coverage['oracle_digest'] != identity['oracle_digest']:
        raise RuntimeError('Ruby probe changed during native measurement')
    # Path order differs from string order for names such as pkg.rb and pkg/child.rb.
    native_population = sorted(coverage['source_digests'].items(), key=lambda item: Path(item[0]))
    if identity['population_digest'] != hashlib.sha256(json.dumps(native_population).encode('utf-8')).hexdigest():
        raise RuntimeError('Ruby importer content changed during native measurement')
    for target, digest in coverage['target_digests'].items():
        if hashlib.sha256((scope.root / target).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Ruby target content changed during native measurement')
    coverage.update(identity)
    coverage['target_inventory_digest'] = target_inventory
    coverage['ruby_executable'] = executable
    return output['edges'], output['lazy_only'], coverage


def build_ruby_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    edges, _, coverage = _ruby_scoped_edges(scope)
    return edges, coverage


def ruby_lazy_only_edges(scope: Scope) -> Edges:
    _, lazy_only, _ = _ruby_scoped_edges(scope)
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
    'ruby-ripper-relative': Oracle(frozenset({'.rb'}), build_ruby_oracle, ruby_lazy_only_edges),
    'php-token-static': Oracle(frozenset({'.php'}), build_php_oracle, php_lazy_only_edges),
    'go-toolchain': Oracle(frozenset({'.go'}), build_go_oracle),
    'gcc-c': Oracle(C_SUFFIXES, _gcc_oracle('c')),
    'gcc-cpp': Oracle(CPP_SUFFIXES, _gcc_oracle('c++')),
    'python-ast': Oracle(frozenset({'.py'}), build_python_oracle, python_lazy_only_edges),
    'rust-cargo': Oracle(frozenset({'.rs'}), build_rust_oracle, unscored=rust_unscored_importers),
    'typescript-compiler': Oracle(frozenset({'.ts', '.tsx', '.js', '.jsx', '.mts', '.cts', '.mjs', '.cjs'}), build_typescript_oracle, typescript_lazy_only_edges),
    'java-jls': Oracle(frozenset({'.java'}), build_java_oracle),
    'kotlin-declared': Oracle(frozenset({'.kt'}), build_kotlin_declared_oracle),
    'scala-declared': Oracle(frozenset({'.scala'}), build_scala_declared_oracle, scala_lazy_only_edges),
}
