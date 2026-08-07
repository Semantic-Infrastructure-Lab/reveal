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

Method-set matching is on **name + syntactic signature text** (parameter and
return type text as written, not resolved/aliased/generic-instantiated types)
— a struct must carry a method of every name the interface declares, with
matching parameter and return type text (BACK-816). This is structural
inference over unresolved source text, disclosed as such, not a full Go
type-checker: known gaps are type aliases, generics, and cross-package
promoted methods, which can still produce a false negative or false positive
in the corners this text match doesn't resolve.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List
from .nav_surface_common import _get_text, _get_line

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

logger = logging.getLogger(__name__)


def scan_file_contracts_go(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Go file → {'interfaces', 'structs', 'methods'}.

    - interfaces: [{name, file, line, methods: [{name, params: [str], returns: [str]}], embeds: [str]}]
    - structs:    [{name, file, line}]
    - methods:    [{recv: str, name: str, params: [str], returns: [str]}]  (receiver type → method)

    `params`/`returns` are syntactic type text (whitespace-normalised), not
    resolved types — see module docstring for the disclosed limitations.
    """
    empty: Dict[str, List[Dict[str, Any]]] = {'interfaces': [], 'structs': [], 'methods': []}
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('go')
        tree = ts_parse(parser, source)
    except Exception as e:
        logger.warning("contracts scan (Go) failed to parse %s: %s", file_path, e)
        return empty

    content_bytes = source.encode('utf-8')
    result: Dict[str, List[Dict[str, Any]]] = {'interfaces': [], 'structs': [], 'methods': []}

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind == 'type_spec':
            _process_type_spec(node, file_path, content_bytes, result)
        elif kind == 'method_declaration':
            _process_method(node, content_bytes, result)
        for ch in reversed(_children(node)):
            stack.append(ch)

    return result


def _type_spec_name(node: Any, content_bytes: bytes):
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'type_identifier':
            return _get_text(ch, content_bytes)
    return None


def _process_type_spec(node: Any, file_path: str, content_bytes: bytes,
                       result: Dict[str, List[Dict[str, Any]]]) -> None:
    name = _type_spec_name(node, content_bytes)
    if name is None:
        return
    body = next((c for c in _children(node) if _zero_arg(c, 'kind') in ('interface_type', 'struct_type')), None)
    if body is None:
        return
    line = _get_line(node)
    if _zero_arg(body, 'kind') == 'struct_type':
        result['structs'].append({'name': name, 'file': file_path, 'line': line})
        return
    # interface_type: method_elem children are methods; bare type_identifier
    # children are embedded interfaces (their methods are inherited).
    methods: List[Dict[str, Any]] = []
    embeds: List[str] = []
    for ch in _children(body):
        if _zero_arg(ch, 'kind') == 'method_elem':
            sig = _method_elem_signature(ch, content_bytes)
            if sig is not None:
                methods.append(sig)
        elif _zero_arg(ch, 'kind') == 'type_identifier':
            embeds.append(_get_text(ch, content_bytes))
    result['interfaces'].append({
        'name': name, 'file': file_path, 'line': line,
        'methods': methods, 'embeds': embeds,
    })


def _normalize_type_text(text: str) -> str:
    """Collapse whitespace so formatting differences don't defeat a text match."""
    return ' '.join(text.split())


def _param_type_texts(param_list: Any, content_bytes: bytes) -> List[str]:
    """Extract each parameter's type text (not its name) from a parameter_list,
    marking variadic params with a `...` prefix so `...string` != `string`."""
    types: List[str] = []
    for pdecl in _children(param_list):
        kind = _zero_arg(pdecl, 'kind')
        if kind not in ('parameter_declaration', 'variadic_parameter_declaration'):
            continue
        type_node = None
        for ch in _children(pdecl):
            if _zero_arg(ch, 'kind') != 'identifier':
                type_node = ch
        if type_node is None:
            continue
        prefix = '...' if kind == 'variadic_parameter_declaration' else ''
        types.append(prefix + _normalize_type_text(_get_text(type_node, content_bytes)))
    return types


def _result_type_texts(node: Any, content_bytes: bytes) -> List[str]:
    """Extract return type text: a bare type (single return) or a
    parameter_list (parenthesized multi-return, possibly named)."""
    if node is None:
        return []
    if _zero_arg(node, 'kind') == 'parameter_list':
        return _param_type_texts(node, content_bytes)
    return [_normalize_type_text(_get_text(node, content_bytes))]


def _method_elem_signature(node: Any, content_bytes: bytes):
    """Extract {name, params, returns} from an interface method_elem node
    (`Foo(a int) error`): field_identifier name, parameter_list params, then
    an optional trailing result node (bare type or parenthesized multi-return)."""
    name_node = None
    param_list = None
    result_node = None
    stage = 0  # 0=seeking name, 1=seeking params, 2=seeking result
    for ch in _children(node):
        kind = _zero_arg(ch, 'kind')
        if stage == 0:
            if kind == 'field_identifier':
                name_node = ch
                stage = 1
            continue
        if stage == 1:
            if kind == 'parameter_list':
                param_list = ch
                stage = 2
            continue
        result_node = ch
        break
    if name_node is None:
        return None
    params = _param_type_texts(param_list, content_bytes) if param_list is not None else []
    returns = _result_type_texts(result_node, content_bytes)
    return {'name': _get_text(name_node, content_bytes), 'params': params, 'returns': returns}


def _receiver_type(param_list: Any, content_bytes: bytes):
    """Extract the receiver type name from a method's receiver parameter_list,
    unwrapping a pointer receiver (`*T` → `T`)."""
    for pdecl in _children(param_list):
        if _zero_arg(pdecl, 'kind') != 'parameter_declaration':
            continue
        for ch in _children(pdecl):
            if _zero_arg(ch, 'kind') == 'type_identifier':
                return _get_text(ch, content_bytes)
            if _zero_arg(ch, 'kind') == 'pointer_type':
                for pc in _children(ch):
                    if _zero_arg(pc, 'kind') == 'type_identifier':
                        return _get_text(pc, content_bytes)
    return None


def _process_method(node: Any, content_bytes: bytes,
                    result: Dict[str, List[Dict[str, Any]]]) -> None:
    # method_declaration: 'func' parameter_list(receiver) field_identifier(name)
    # parameter_list(params) [result] block — a state machine over that fixed
    # order, since the receiver and params nodes share the same node kind.
    recv_list = None
    name_node = None
    param_list = None
    result_node = None
    stage = 0  # 0=seeking receiver, 1=seeking name, 2=seeking params, 3=seeking result
    for ch in _children(node):
        kind = _zero_arg(ch, 'kind')
        if stage == 0:
            if kind == 'parameter_list':
                recv_list = ch
                stage = 1
            continue
        if stage == 1:
            if kind == 'field_identifier':
                name_node = ch
                stage = 2
            continue
        if stage == 2:
            if kind == 'parameter_list':
                param_list = ch
                stage = 3
            continue
        if kind == 'block':
            break
        result_node = ch
        break
    if recv_list is None or name_node is None:
        return
    recv = _receiver_type(recv_list, content_bytes)
    if recv is None:
        return
    params = _param_type_texts(param_list, content_bytes) if param_list is not None else []
    returns = _result_type_texts(result_node, content_bytes)
    result['methods'].append({
        'recv': recv, 'name': _get_text(name_node, content_bytes),
        'params': params, 'returns': returns,
    })
