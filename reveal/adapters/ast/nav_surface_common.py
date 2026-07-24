"""Shared tree-sitter nav helpers (BACK-570).

Three helpers were copy-pasted byte-for-byte across every per-language
``nav_surface_<lang>.py`` scanner (and ``nav_contracts_ruby.py``): a UTF-8
node-text slice, a 1-based line number, and a dedup-on-``(name, file, line)``
list append. Consolidated here so a change to the dedup key or the
tree-sitter node API lands in one place instead of eight.
"""

import re
from typing import Any, Dict, List


def _get_text(node, content_bytes: bytes) -> str:
    return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')


def _get_line(node) -> int:
    return node.start_position().row + 1


def _add_once(lst: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    key = (entry.get('name', ''), entry.get('file', ''), entry.get('line', 0))
    for existing in lst:
        if (existing.get('name', ''), existing.get('file', ''), existing.get('line', 0)) == key:
            return
    lst.append(entry)


# ---------------------------------------------------------------------------
# BACK-796: C++ macro/attribute modifier before a class/struct name.
# ---------------------------------------------------------------------------

_CPP_CLASS_KEYWORD_RE = re.compile(r'\b(?:class|struct)\b')
_CPP_IDENT_RE = re.compile(r'[A-Za-z_]\w*')
_CPP_FINAL_RE = re.compile(r'final\b')
_CPP_WS = ' \t\r\n'


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
        k = m2.end()
        while k < n and source[k] in _CPP_WS:
            k += 1
        fm = _CPP_FINAL_RE.match(source, k)
        if fm:
            k = fm.end()
            while k < n and source[k] in _CPP_WS:
                k += 1
        if k < n and source[k] in '{:':
            if out is None:
                out = list(source)
            for p in range(m1.start(), m1.end()):
                if out[p] != '\n':
                    out[p] = ' '
    return source if out is None else ''.join(out)
