"""Shared tree-sitter nav helpers (BACK-570).

Three helpers were copy-pasted byte-for-byte across every per-language
``nav_surface_<lang>.py`` scanner (and ``nav_contracts_ruby.py``): a UTF-8
node-text slice, a 1-based line number, and a dedup-on-``(name, file, line)``
list append. Consolidated here so a change to the dedup key or the
tree-sitter node API lands in one place instead of eight.

The import-taxonomy helper that used to live here (``categorize_by_prefix``,
BACK-912) is gone: import-based network/db/sdk classification is rule-driven
(``surface_rules_imports.py``, BACK-1334) for every language but TypeScript,
which keeps its own ``_categorize_module``.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from reveal.core.treesitter_compat import _zero_arg, error_node_spans, tree_has_recovery_artifacts, tree_root

from .surface_matrix import RECOVERED_KEY


def _get_text(node, content_bytes: bytes) -> str:
    return content_bytes[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')


def _get_line(node) -> int:
    return int(_zero_arg(node, 'start_position').row) + 1


def disclose_parse_recovery(tree, file_path: str, surfaces: Dict[str, Any]) -> Dict[str, Any]:
    """BACK-1480: say so when a tree-sitter scan walked a partly-recovered parse.

    tree-sitter never fails, it guesses: after it loses sync (a PHP docblock, a
    macro-heavy C++ file) it emits ERROR nodes whose contents still look like code,
    and a scanner walking the tree reports them as real surface (WordPress
    formatting.php: 10 fabricated `subprocess` hits from backticks in a docblock).
    Entries are kept -- most in-region C++ hits are real (`getenv("LC_ALL")`) -- but
    each one whose line lies in an ERROR region is tagged `in_error_region`, and the
    file is listed under RECOVERED_KEY so the report can name it. Line granularity:
    entries carry a line, not a node.
    """
    if not tree_has_recovery_artifacts(tree):
        return surfaces
    spans = error_node_spans(tree_root(tree))
    for key, entries in surfaces.items():
        if key.startswith('_'):
            continue
        for entry in entries:
            line = entry.get('line', 0)
            if any(first <= line <= last for first, last in spans):
                entry['in_error_region'] = True
    surfaces[RECOVERED_KEY] = [file_path]
    return surfaces


def _add_once(lst: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    key = (entry.get('name', ''), entry.get('file', ''), entry.get('line', 0))
    for existing in lst:
        if (existing.get('name', ''), existing.get('file', ''), existing.get('line', 0)) == key:
            return
    lst.append(entry)


# ---------------------------------------------------------------------------
# BACK-1418: controller-level route prefixes (ASP.NET [Route], Spring
# @RequestMapping on the class) -- every action path used to be reported
# without its controller's prefix.
# ---------------------------------------------------------------------------

# Spring MVC route annotations (Java and Kotlin) -> HTTP method. RequestMapping
# names its verbs in `method = RequestMethod.X`; ANY when it names none.
SPRING_ROUTE_ANNOTATIONS: Dict[str, str] = {
    'GetMapping': 'GET',
    'PostMapping': 'POST',
    'PutMapping': 'PUT',
    'DeleteMapping': 'DELETE',
    'PatchMapping': 'PATCH',
    'RequestMapping': 'ANY',
}


def join_route_path(prefix: Optional[str], path: Optional[str]) -> Optional[str]:
    """An action's route path under its controller's prefix.

    None prefix (the class declares none): the path as written. None or empty
    path (a bare `[HttpGet]` / `@GetMapping`): the prefix itself, '/' when
    that is empty too. Exactly one '/' joins the two.
    """
    if prefix is None:
        return path
    if not path:
        return prefix or '/'
    if not prefix:
        return path
    return prefix.rstrip('/') + '/' + path.lstrip('/')


def replace_route_tokens(path: Optional[str], class_name: Optional[str],
                         action: Optional[str]) -> Optional[str]:
    """ASP.NET token replacement: [controller] is the class name without its
    'Controller' suffix, [action] the method name."""
    if not path:
        return path
    if class_name:
        controller = class_name[:-len('Controller')] if class_name.endswith('Controller') else class_name
        path = re.sub(r'\[controller\]', controller, path, flags=re.IGNORECASE)
    if action:
        path = re.sub(r'\[action\]', action, path, flags=re.IGNORECASE)
    return path


# Not a surface category: a C#/Java/Kotlin scanner lists each class's name,
# base types and own route prefixes here, and marks a route whose class
# declares no prefix but has base types with INHERIT_KEY. surface.py resolves
# those across every scanned file (resolve_inherited_route_prefixes) -- a
# controller commonly inherits [Route("[controller]")] from a base class in
# another file (26 of Jellyfin's 60 controllers).
ROUTE_CLASSES_KEY = '_route_classes'
INHERIT_KEY = '_route_inherit'


def type_simple_name(text: str) -> str:
    """`Base` for `Base`, `Ns.Base<T>`, `x.Base<T>()` (a Kotlin supertype call)."""
    return re.sub(r'<.*', '', text).strip().rstrip('()').rsplit('.', 1)[-1]


def resolve_inherited_route_prefixes(http_entries: List[Dict[str, Any]],
                                     class_records: List[Dict[str, Any]]) -> None:
    """Re-path every route marked INHERIT_KEY under the prefix of its nearest
    base type that declares one (ASP.NET walks the class chain to the first
    class with route attributes; Spring's class-level @RequestMapping lookup
    searches superclasses and interfaces). No such base, or bases of the same
    name disagreeing: the route keeps the path it was scanned with."""
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for record in class_records:
        by_name.setdefault(record['name'], []).append(record)

    def inherited(class_name: str) -> Optional[List[str]]:
        seen = {class_name}
        frontier = [class_name]
        while frontier:
            found: List[Tuple[str, ...]] = []
            next_frontier = []
            for name in frontier:
                for record in by_name.get(name, []):
                    for base in record['bases']:
                        if base in seen:
                            continue
                        seen.add(base)
                        own = [tuple(r['prefixes']) for r in by_name.get(base, [])
                               if r['prefixes'] is not None]
                        found.extend(own)
                        if not own:
                            next_frontier.append(base)
            if found:
                return list(found[0]) if len(set(found)) == 1 else None
            frontier = next_frontier
        return None

    resolved: List[Dict[str, Any]] = []
    for entry in http_entries:
        info = entry.pop(INHERIT_KEY, None)
        prefixes = inherited(info['class']) if info else None
        if not prefixes:
            resolved.append(entry)
            continue
        for prefix in prefixes:
            resolved_prefix = (replace_route_tokens(prefix, info['class'], info['action'])
                               if info['tokens'] else prefix)
            resolved.append({**entry, 'path': join_route_path(resolved_prefix, info['template']) or '?'})
    http_entries[:] = resolved


def route_prefixes(prefixes: Optional[List[str]]) -> List[Optional[str]]:
    """A controller's class-level route prefixes, or [None] -- one unprefixed
    route -- when the class declares none."""
    return list(prefixes) if prefixes else [None]


def mapping_paths(elements: Dict[str, List[str]]) -> List[Optional[str]]:
    """Paths of a Spring mapping annotation (`value`, else `path`); [None] for a
    bare `@GetMapping`."""
    paths: List[Optional[str]] = list(elements.get('value') or elements.get('path') or [])
    return paths or [None]


def merge_routes_by_path(routes: List[Tuple[List[str], Optional[str]]]) -> List[Tuple[str, Optional[str]]]:
    """(verbs, path) pairs -> one (methods, path) per distinct path, in first-seen
    order: `[HttpGet("x")] [HttpHead("x")]` is one route answering GET|HEAD.
    ANY absorbs nothing -- a path with a named verb reports the named verbs."""
    merged: Dict[Optional[str], List[str]] = {}
    for verbs, path in routes:
        bucket = merged.setdefault(path, [])
        bucket.extend(v for v in verbs if v not in bucket)
    result = []
    for path, verbs in merged.items():
        named = [v for v in verbs if v != 'ANY']
        result.append(('|'.join(named) if named else 'ANY', path))
    return result


# ---------------------------------------------------------------------------
# BACK-796: C++ macro/attribute modifier before a class/struct name.
# ---------------------------------------------------------------------------

_CPP_CLASS_KEYWORD_RE = re.compile(r'\b(?:class|struct)\b')
_CPP_IDENT_RE = re.compile(r'[A-Za-z_]\w*')
_CPP_FINAL_RE = re.compile(r'final\b')
_CPP_WS = ' \t\r\n'


def _skip_trivia(source: str, pos: int) -> int:
    """Advance past whitespace, `//`/`/* */` comments, and preprocessor
    directive lines (`#ifndef SWIG` / `#endif` / etc, to end of line) —
    real-world macro-prefixed class headers commonly interleave a
    conditional base-class clause this way (`class ASSIMP_API IOStream
    #ifndef SWIG
        : public Base
    #endif
    { ... }`, confirmed in Assimp's own `IOStream.hpp`/`Logger.hpp`/4 other
    files) between the class name and its `{`/`:`, which a naive
    whitespace-only skip can't see past."""
    n = len(source)
    moved = True
    while moved:
        moved = False
        while pos < n and source[pos] in _CPP_WS:
            pos += 1
            moved = True
        if source[pos:pos + 2] == '//':
            end = source.find('\n', pos)
            pos = n if end == -1 else end
            moved = True
        elif source[pos:pos + 2] == '/*':
            end = source.find('*/', pos + 2)
            pos = n if end == -1 else end + 2
            moved = True
        elif pos < n and source[pos] == '#':
            end = source.find('\n', pos)
            pos = n if end == -1 else end
            moved = True
    return pos


def normalize_cpp_macro_class_modifiers(source: str) -> str:
    """Blank a bare macro/attribute identifier sitting between `class`/
    `struct` and the real class name — `class ASSIMP_API BaseProcess {`,
    Qt's `class Q_CORE_EXPORT QFile {`, wxWidgets' `class
    WXDLLIMPEXP_CORE wxWindow {`, etc. This is a near-universal DLL-export/
    visibility-attribute idiom in real-world C++ (the macro expands to
    `__declspec(dllexport)`/`__attribute__((visibility(...)))`/nothing, but
    tree-sitter never runs the preprocessor, so it sees the bare macro
    identifier literally).

    Left unblanked, tree-sitter-cpp's grammar has no rule for "two bare
    identifiers in a row" after `class`/`struct` and mis-parses it: the
    resulting `class_specifier` node ends up bodyless with its
    `type_identifier` set to the *macro* name, not the real class, and the
    real class body (every member, every pure-virtual method) is absorbed
    elsewhere in the tree as unrelated/garbage structure — invisible to
    every AST-based scanner, not just contracts/surface. Confirmed via a
    direct parse of `samples/cpp_assimp/code/Common/BaseProcess.h`
    (BACK-795 measurement session): `ASSIMP_API`-prefixed `BaseProcess` — a
    genuinely abstract base with 2 pure-virtual methods — was completely
    absent from `_scan_contracts_cpp`'s output before this fix, in a file
    with 42 sibling files in the same corpus using the identical idiom.

    Two bare identifiers back-to-back is never legal C++ grammar *on its
    own* — the only real-world shapes that produce it are (a) a
    macro-prefixed class/struct **definition** (`class MACRO Name { ... }`
    or `class MACRO Name : public Base { ... }`, ends in `{` or `:`) or (b)
    an **elaborated-type-specifier variable declaration**
    (`class Point p;` / `struct stat st;`, C-compatibility syntax — ends in
    `;`/`=`/`,`, never `{`/`:`). Only (a) is blanked; (b) is left alone
    since its first identifier is a real type name, not a macro, and
    blanking it would corrupt a legitimate declaration. The distinction is
    made by scanning past the second identifier (and an optional trailing
    `final`) to see which terminator it actually reaches.

    The macro token is replaced with spaces (newlines preserved) rather
    than deleted, so every subsequent byte offset / line number tree-sitter
    reports back stays valid against the *original* source text.
    """
    if 'class' not in source and 'struct' not in source:
        return source
    n = len(source)
    out = None
    for km in _CPP_CLASS_KEYWORD_RE.finditer(source):
        i = km.end()
        while i < n and source[i] in _CPP_WS:
            i += 1
        m1 = _CPP_IDENT_RE.match(source, i)
        if not m1:
            continue
        j = m1.end()
        ws2_start = j
        while j < n and source[j] in _CPP_WS:
            j += 1
        if j == ws2_start:
            continue  # ident1 directly followed by non-space (`{`/`:`/`;`/`<`) — ordinary `class Name`
        m2 = _CPP_IDENT_RE.match(source, j)
        if not m2:
            continue  # only one identifier present before the next token
        if m2.group(0) == 'final':
            continue  # `class Name final : ...` — ident1 IS the real name,
            # `final` is the trailing specifier, not a second real
            # identifier; blanking ident1 here would corrupt the real name.
        k = _skip_trivia(source, m2.end())
        fm = _CPP_FINAL_RE.match(source, k)
        if fm:
            k = _skip_trivia(source, fm.end())
        if k < n and source[k] in '{:':
            if out is None:
                out = list(source)
            for p in range(m1.start(), m1.end()):
                if out[p] != '\n':
                    out[p] = ' '
    return source if out is None else ''.join(out)
