"""Tree-sitter contract extraction for Rust — traits and their implementors.

BACK-403 pt 2 (contracts breadth). Rust's contract construct is the **trait**
(`trait Foo { ... }`); a type satisfies it through an **explicit** `impl Foo for
Bar` block — so, unlike Go's implicit method-set satisfaction, implementors are
*declared* and need no structural inference. Rust needs its own scanner (rather
than the shared `_scan_contracts_ts` classifier) only because of node shape: a
trait is a `trait_item` (not an `interface_declaration`/`class` keyword grammar
`collect_structures` handles), and an implementation is an `impl_item` whose
trait/type pair straddles a `for` keyword.

Emits per file:
- interfaces: [{name, file, line, methods: [str]}]   (traits)
- impls:      [{trait: str, type: str, file, line}]   (`impl Trait for Type`)

`contracts.py::_scan_contracts_rust` joins impls to traits by name.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse


def scan_file_contracts_rust(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Rust file → {'interfaces', 'impls'}."""
    empty: Dict[str, List[Dict[str, Any]]] = {'interfaces': [], 'impls': []}
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('rust')
        tree = ts_parse(parser, source)
    except Exception:
        return empty

    content_bytes = source.encode('utf-8')
    result: Dict[str, List[Dict[str, Any]]] = {'interfaces': [], 'impls': []}

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = node.kind()
        if kind == 'trait_item':
            _process_trait(node, file_path, content_bytes, result)
        elif kind == 'impl_item':
            _process_impl(node, file_path, content_bytes, result)
        for ch in reversed(_children(node)):
            stack.append(ch)

    return result


def _type_name(node: Any, content_bytes: bytes) -> Optional[str]:
    """Base type name, unwrapping generic (`Vec<u8>`→`Vec`) and scoped
    (`a::B`→`B`) forms to the rightmost type_identifier."""
    if node.kind() == 'type_identifier':
        return _get_text(node, content_bytes)
    if node.kind() in ('generic_type', 'scoped_type_identifier', 'reference_type'):
        found = None
        for ch in _children(node):
            name = _type_name(ch, content_bytes)
            if name is not None:
                found = name
        return found
    return None


def _process_trait(node: Any, file_path: str, content_bytes: bytes,
                   result: Dict[str, List[Dict[str, Any]]]) -> None:
    name = next((_get_text(c, content_bytes) for c in _children(node)
                 if c.kind() == 'type_identifier'), None)
    if name is None:
        return
    methods: List[str] = []
    body = next((c for c in _children(node) if c.kind() == 'declaration_list'), None)
    if body is not None:
        for item in _children(body):
            if item.kind() in ('function_signature_item', 'function_item'):
                mname = next((_get_text(c, content_bytes) for c in _children(item)
                              if c.kind() == 'identifier'), None)
                if mname:
                    methods.append(mname)
    result['interfaces'].append({
        'name': name, 'file': file_path, 'line': _get_line(node), 'methods': methods,
    })


def _process_impl(node: Any, file_path: str, content_bytes: bytes,
                  result: Dict[str, List[Dict[str, Any]]]) -> None:
    """`impl Trait for Type` — the type names straddle a `for` token. An
    inherent `impl Type { }` has no `for` and is not a contract implementation."""
    kids = _children(node)
    for_idx = next((i for i, c in enumerate(kids) if c.kind() == 'for'), None)
    if for_idx is None:
        return
    trait_name = None
    for c in kids[:for_idx]:
        n = _type_name(c, content_bytes)
        if n is not None:
            trait_name = n
    type_name = None
    for c in kids[for_idx + 1:]:
        n = _type_name(c, content_bytes)
        if n is not None:
            type_name = n
            break
    if trait_name is None or type_name is None:
        return
    result['impls'].append({
        'trait': trait_name, 'type': type_name, 'file': file_path, 'line': _get_line(node),
    })
