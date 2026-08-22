"""Shared tree-sitter nav helpers (BACK-570, BACK-912).

Three helpers were copy-pasted byte-for-byte across every per-language
``nav_surface_<lang>.py`` scanner (and ``nav_contracts_ruby.py``): a UTF-8
node-text slice, a 1-based line number, and a dedup-on-``(name, file, line)``
list append. Consolidated here so a change to the dedup key or the
tree-sitter node API lands in one place instead of eight.

``categorize_by_prefix`` (BACK-912) consolidates a second duplicate: five
language scanners (kotlin, php, csharp, java, go) each defined their own
``_categorize_module`` with an identical prefix-match loop over a
``(group, category)`` taxonomy, differing only in the taxonomy constant name
and the path separator (``.`` for the dotted-package languages, ``/`` for
Go's slash-delimited module paths, ``\\`` for PHP namespaces). Not every
scanner fits this shape — Swift matches only the top-level module segment
(no prefix chain) and TypeScript layers exact/scoped/root lookups across
three separate package sets — so those two keep their own bespoke
``_categorize_module``.
"""

import re
from typing import Any, Dict, List, Tuple

from reveal.core.treesitter_compat import _zero_arg


def _get_text(node, content_bytes: bytes) -> str:
    return content_bytes[_zero_arg(node, 'start_byte'):_zero_arg(node, 'end_byte')].decode('utf-8')


def _get_line(node) -> int:
    return _zero_arg(node, 'start_position').row + 1


def _add_once(lst: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    key = (entry.get('name', ''), entry.get('file', ''), entry.get('line', 0))
    for existing in lst:
        if (existing.get('name', ''), existing.get('file', ''), existing.get('line', 0)) == key:
            return
    lst.append(entry)


def categorize_by_prefix(
    module: str,
    file_path: str,
    line: int,
    surfaces: Dict[str, List[Dict[str, Any]]],
    taxonomy: Tuple[Tuple[Any, str], ...],
    sep: str,
) -> None:
    """Record `module` as an import surface entry under the first taxonomy
    category whose group contains it exactly, or as a `sep`-delimited
    ancestor path (e.g. `module == prefix` or `module.startswith(prefix +
    sep)`). `taxonomy` is an ordered sequence of `(group, category)` pairs,
    `group` any container supporting `in`-free iteration of prefix strings.
    No-op if no group matches (BACK-912).
    """
    for group, category in taxonomy:
        for prefix in group:
            if module == prefix or module.startswith(prefix + sep):
                entry = {'type': 'import', 'name': module, 'file': file_path, 'line': line}
                _add_once(surfaces[category], entry)
                return


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
