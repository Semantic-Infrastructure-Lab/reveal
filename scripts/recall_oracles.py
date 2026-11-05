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


# ---- Kotlin and Scala: a declaration is indexed under its package, whatever the file is named ----
#
# Neither language ties a file name to its types (Kotlin: any file; Scala: any file), so ``import a.b.C``
# names the file that DECLARES ``C`` in package ``a.b``. The rule here is independent of Reveal's
# extractor and resolver (BACK-2507): comments and string literals are blanked, braces are counted, and a
# declaration keyword at brace depth 0 declares its name. One shared policy with Reveal's documented
# member-index behaviour, not an independent check of it: a name declared in several files of one package
# (Kotlin multiplatform source sets) is an edge to each. Explicit imports only; wildcards are counted in
# the coverage, never scored (BACK-2506/2508), and Scala selector lists are scored only when the manifest
# sets ``score_selector_lists: true`` (BACK-1237 is a separate population, never mixed into the gated row).

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
                      r'(?:package\s+object|class|trait|object|enum|type|def|val|var|given)\s+(\w+)')
_JVM_PACKAGE = re.compile(r'^\s*package\s+([\w.]+)\s*(\{)?\s*$')
_JVM_IMPORT = re.compile(r'^[ \t]*import\s+(.+?)\s*;?\s*$', re.MULTILINE)


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


def _jvm_import_paths(clean: str, language: str, counts: dict[str, int], score_selectors: bool) -> list[str]:
    """Dotted names an explicit import statement names; wildcard and wildcard forms are only counted; a selector list is read name by name only when ``score_selectors``."""
    paths: list[str] = []
    for statement in _JVM_IMPORT.findall(clean):
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
                if not score_selectors:
                    continue
                prefix, _, body = piece.partition('{')
                for item in body.rstrip('} \t').split(','):
                    name = item.split('=>')[0].split(' as ')[0].strip()
                    if '=>' in item and item.split('=>')[1].strip() == '_':
                        continue  # `X => _` hides X
                    if name in ('_', '*'):
                        counts['wildcard_statements'] += 1
                    elif re.fullmatch(r'\w+', name):
                        paths.append(prefix.strip() + name)
            elif piece.endswith(('.*', '._')):
                counts['wildcard_statements'] += 1
            elif re.fullmatch(r'[\w.`]+', piece):
                paths.append(piece.replace('`', ''))
    return paths


def _build_jvm_declared_oracle(scope: Scope, language: str, suffix: str,
                               declared_name: 'Callable[[str], str | None]') -> tuple[Edges, Coverage]:
    sources = {p: jvm_strip_noise(p.read_text(encoding='utf-8', errors='replace'))
               for p in tracked_files(scope.root, [_relative(scope, scope.scan)], frozenset({suffix}))}
    declared: dict[tuple[str, str], set[Path]] = defaultdict(set)
    file_packages: dict[Path, str] = {}
    for path, clean in sources.items():
        packages, lines = _top_level_lines(clean, language)
        package = '.'.join(packages) if language == 'scala' else (packages[0] if packages else '')
        file_packages[path] = package
        for line in lines:
            name = declared_name(line)
            if name:
                declared[(package, name)].add(path)
    counts = {'wildcard_statements': 0, 'selector_lists': 0}
    edges: dict[Path, set[Path]] = defaultdict(set)
    statements = resolved = 0

    packages: set[str] = set()
    for package in file_packages.values():
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
        if clean is None:  # an importer outside the scan root
            clean = jvm_strip_noise(importer.read_text(encoding='utf-8', errors='replace'))
        own = file_packages.get(importer) or '.'.join(_top_level_lines(clean, language)[0])
        for dotted in _jvm_import_paths(clean, language, counts, bool(scope.config.get('score_selector_lists'))):
            statements += 1
            targets = resolve(dotted)
            if not targets and language == 'scala' and own:  # an import relative to an enclosing package
                parts = own.split('.')
                for keep in range(len(parts), 0, -1):
                    targets = resolve('.'.join(parts[:keep]) + '.' + dotted)
                    if targets:
                        break
            if importer in targets:  # the file declares the name itself: its own declaration, no other file
                continue
            resolved += bool(targets)
            for target in targets:
                edges[target].add(importer)
    return _finish(scope, edges), {'files': len(scope.importers), 'indexed_symbols': len(declared),
                                   'import_statements': statements, 'resolved_statements': resolved, **counts}


def build_kotlin_declared_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    return _build_jvm_declared_oracle(scope, 'kotlin', '.kt', _kotlin_declared_name)


def build_scala_declared_oracle(scope: Scope) -> tuple[Edges, Coverage]:
    return _build_jvm_declared_oracle(scope, 'scala', '.scala', _scala_declared_name)


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
    'rust-use': Oracle(frozenset({'.rs'}), build_rust_oracle),
    'typescript-compiler': Oracle(frozenset({'.ts', '.tsx', '.js', '.jsx', '.mts', '.cts', '.mjs', '.cjs'}), build_typescript_oracle, typescript_lazy_only_edges),
    'java-jls': Oracle(frozenset({'.java'}), build_java_oracle),
    'kotlin-declared': Oracle(frozenset({'.kt'}), build_kotlin_declared_oracle),
    'scala-declared': Oracle(frozenset({'.scala'}), build_scala_declared_oracle),
}
