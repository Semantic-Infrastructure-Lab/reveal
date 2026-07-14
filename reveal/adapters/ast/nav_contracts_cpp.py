"""Tree-sitter contract extraction for C++ — abstract classes and their subclasses.

BACK-403 pt 2 (contracts breadth). C++ has no `interface` keyword; the idiomatic
contract is an **abstract class** — a `class`/`struct` with at least one *pure
virtual* method (`virtual T f() = 0;`). Implementors are declared **explicitly**
via inheritance (`class Derived : public Base`), so no structural inference is
needed (unlike Go).

Emits per file:
- classes: [{name, file, line, bases: [str], is_abstract: bool}]

`contracts.py::_scan_contracts_cpp` treats every abstract class as a contract
and every class listing a contract in its bases as an implementor.

**Known limitation — `.h`-declared classes.** C++ conventionally declares
classes in `.h` headers, but reveal's registry classifies `.h` as C (not C++),
so header-only class declarations (e.g. Godot's abstract classes, all in `.h`)
are not reached by the `.cpp`/`.cc`/`.cxx`/`.hpp`/`.hxx`/`.hh` file set this
scanner runs on. The `contracts` coverage census warns honestly in that case
(`Dominant language 'C' … not analyzed`) rather than returning a misleading
blank. Reaching `.h`-declared classes is a follow-on tied to the broader
`.h`→C-vs-C++ classification question (matrix footnote 2), not a silent gap here.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse


def scan_file_contracts_cpp(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one C++ file → {'classes': [...]}."""
    empty: Dict[str, List[Dict[str, Any]]] = {'classes': []}
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('cpp')
        tree = ts_parse(parser, source)
    except Exception:
        return empty

    content_bytes = source.encode('utf-8')
    result: Dict[str, List[Dict[str, Any]]] = {'classes': []}

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        if node.kind() in ('class_specifier', 'struct_specifier'):
            _process_class(node, file_path, content_bytes, result)
        for ch in reversed(_children(node)):
            stack.append(ch)

    return result


def _class_name(node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(node):
        if ch.kind() == 'type_identifier':
            return _get_text(ch, content_bytes)
    return None


def _base_names(node: Any, content_bytes: bytes) -> List[str]:
    """Base-class names from a `base_class_clause` (`: public A, private B`),
    unwrapping qualified/template forms to the rightmost type name."""
    clause = next((c for c in _children(node) if c.kind() == 'base_class_clause'), None)
    if clause is None:
        return []
    names: List[str] = []
    for ch in _children(clause):
        name = _type_tail(ch, content_bytes)
        if name is not None:
            names.append(name)
    return names


def _type_tail(node: Any, content_bytes: bytes) -> Optional[str]:
    """Rightmost type name of a base entry: `type_identifier`, or the tail of a
    `qualified_identifier`/`template_type` (`ns::Base`→`Base`, `Base<T>`→`Base`)."""
    if node.kind() == 'type_identifier':
        return _get_text(node, content_bytes)
    if node.kind() in ('qualified_identifier', 'template_type'):
        found = None
        for ch in _children(node):
            tail = _type_tail(ch, content_bytes)
            if tail is not None:
                found = tail
        return found
    return None


def _is_pure_virtual_field(field: Any) -> bool:
    """A `field_declaration` is a pure virtual method if it carries a `virtual`
    specifier and a `= 0` pure-specifier (a `number_literal` 0 sibling)."""
    has_virtual = any(c.kind() == 'virtual' for c in _children(field))
    if not has_virtual:
        return False
    return any(c.kind() == 'number_literal' for c in _children(field))


def _class_is_abstract(node: Any) -> bool:
    body = next((c for c in _children(node) if c.kind() == 'field_declaration_list'), None)
    if body is None:
        return False
    for item in _children(body):
        if item.kind() == 'field_declaration' and _is_pure_virtual_field(item):
            return True
    return False


def _process_class(node: Any, file_path: str, content_bytes: bytes,
                   result: Dict[str, List[Dict[str, Any]]]) -> None:
    name = _class_name(node, content_bytes)
    if name is None:
        return
    # A forward declaration / opaque reference has no body — skip (no field list).
    if not any(c.kind() == 'field_declaration_list' for c in _children(node)):
        return
    result['classes'].append({
        'name': name,
        'file': file_path,
        'line': _get_line(node),
        'bases': _base_names(node, content_bytes),
        'is_abstract': _class_is_abstract(node),
    })
