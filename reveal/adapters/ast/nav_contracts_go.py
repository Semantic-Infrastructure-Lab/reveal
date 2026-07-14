"""Tree-sitter contract extraction for Go — interfaces and their implementers.

BACK-403 pt 2 (contracts breadth). Go's contract construct is the **interface**
(`type Foo interface { ... }`), the public-API / moat surface a DD read wants.
Two things make Go need its own scanner rather than the shared
`_scan_contracts_ts` interface-family classifier used by Java/C#/PHP/Swift/Kotlin:

1. **Node shape.** Go has no distinct `interface_declaration` node — an
   interface is a `type_declaration` → `type_spec` whose second child is an
   `interface_type`; a struct is the same shape with a `struct_type`. So the
   generic `collect_structures` class/interface extraction (built for the
   `class`/`interface` keyword grammars) does not surface them.

2. **Implicit satisfaction.** Go has no `implements` keyword — a type satisfies
   an interface purely by having every method in the interface's method set.
   Implementers therefore cannot come from an explicit `bases` list (the way
   `_add_implementations` derives them for the interface-family and Ruby
   scanners); they must be *computed* by matching method sets. This scanner
   emits the raw material for that (interfaces with their method names, structs,
   and each receiver method); `contracts.py::_scan_contracts_go` does the
   cross-file superset match.

Method-set matching is on **method names** (Go satisfaction is by name +
signature; the name set is the tractable, low-false-positive proxy — a struct
must carry a method of every name the interface declares). This is structural
inference, disclosed as such, not an explicit-declaration read.
"""

from pathlib import Path
from typing import Any, Dict, List
from .nav_surface_common import _get_text, _get_line

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse


def scan_file_contracts_go(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Go file → {'interfaces', 'structs', 'methods'}.

    - interfaces: [{name, file, line, methods: [str], embeds: [str]}]
    - structs:    [{name, file, line}]
    - methods:    [{recv: str, name: str}]  (receiver type → method name)
    """
    empty: Dict[str, List[Dict[str, Any]]] = {'interfaces': [], 'structs': [], 'methods': []}
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('go')
        tree = ts_parse(parser, source)
    except Exception:
        return empty

    content_bytes = source.encode('utf-8')
    result: Dict[str, List[Dict[str, Any]]] = {'interfaces': [], 'structs': [], 'methods': []}

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = node.kind()
        if kind == 'type_spec':
            _process_type_spec(node, file_path, content_bytes, result)
        elif kind == 'method_declaration':
            _process_method(node, content_bytes, result)
        for ch in reversed(_children(node)):
            stack.append(ch)

    return result


def _type_spec_name(node: Any, content_bytes: bytes):
    for ch in _children(node):
        if ch.kind() == 'type_identifier':
            return _get_text(ch, content_bytes)
    return None


def _process_type_spec(node: Any, file_path: str, content_bytes: bytes,
                       result: Dict[str, List[Dict[str, Any]]]) -> None:
    name = _type_spec_name(node, content_bytes)
    if name is None:
        return
    body = next((c for c in _children(node) if c.kind() in ('interface_type', 'struct_type')), None)
    if body is None:
        return
    line = _get_line(node)
    if body.kind() == 'struct_type':
        result['structs'].append({'name': name, 'file': file_path, 'line': line})
        return
    # interface_type: method_elem children are methods; bare type_identifier
    # children are embedded interfaces (their methods are inherited).
    methods: List[str] = []
    embeds: List[str] = []
    for ch in _children(body):
        if ch.kind() == 'method_elem':
            mname = _method_elem_name(ch, content_bytes)
            if mname:
                methods.append(mname)
        elif ch.kind() == 'type_identifier':
            embeds.append(_get_text(ch, content_bytes))
    result['interfaces'].append({
        'name': name, 'file': file_path, 'line': line,
        'methods': methods, 'embeds': embeds,
    })


def _method_elem_name(node: Any, content_bytes: bytes):
    for ch in _children(node):
        if ch.kind() == 'field_identifier':
            return _get_text(ch, content_bytes)
    return None


def _receiver_type(param_list: Any, content_bytes: bytes):
    """Extract the receiver type name from a method's receiver parameter_list,
    unwrapping a pointer receiver (`*T` → `T`)."""
    for pdecl in _children(param_list):
        if pdecl.kind() != 'parameter_declaration':
            continue
        for ch in _children(pdecl):
            if ch.kind() == 'type_identifier':
                return _get_text(ch, content_bytes)
            if ch.kind() == 'pointer_type':
                for pc in _children(ch):
                    if pc.kind() == 'type_identifier':
                        return _get_text(pc, content_bytes)
    return None


def _process_method(node: Any, content_bytes: bytes,
                    result: Dict[str, List[Dict[str, Any]]]) -> None:
    kids = _children(node)
    # method_declaration: 'func' parameter_list(receiver) field_identifier(name) ...
    recv_list = next((c for c in kids if c.kind() == 'parameter_list'), None)
    name_node = next((c for c in kids if c.kind() == 'field_identifier'), None)
    if recv_list is None or name_node is None:
        return
    recv = _receiver_type(recv_list, content_bytes)
    if recv is None:
        return
    result['methods'].append({'recv': recv, 'name': _get_text(name_node, content_bytes)})
