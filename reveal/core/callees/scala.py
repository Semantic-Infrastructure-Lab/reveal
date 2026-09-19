"""Scala call shapes: `new Foo[T](args)` and infix method calls (shared by analyzer and nav)."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .generic import CHAIN_FULL

# Scala type-node kinds that can appear as the constructed type in an instance_expression.
_SCALA_TYPE_KINDS = frozenset({
    'type_identifier', 'generic_type', 'stable_type_identifier', 'field_expression',
})


def _simple_type_name(type_node: Any, get_text: Callable[[Any], str]) -> Optional[str]:
    """Simple (last) name of a Scala constructor type, unwrapping generics
    (`new Array[Byte]`), qualified paths (`new java.io.File`, BACK-747), and
    qualified generics (`new scala.Array[Byte]`)."""
    kind = _zero_arg(type_node, 'kind')
    if kind == 'type_identifier':
        return get_text(type_node).strip() or None
    if kind == 'generic_type':
        base = next((c for c in _children(type_node)
                     if _zero_arg(c, 'kind') in _SCALA_TYPE_KINDS), None)
        return _simple_type_name(base, get_text) if base is not None else None
    if kind == 'stable_type_identifier':
        names = [c for c in _children(type_node)
                 if _zero_arg(c, 'kind') == 'type_identifier']
        return (get_text(names[-1]).strip() or None) if names else None
    if kind == 'field_expression':
        text = get_text(type_node).strip()
        return text.split('.')[-1] if text else None
    return None


def instance(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """Scala `instance_expression`: `new <type>(args)` -> "new <name>".

    A DISTINCT kind from PHP/C#'s object_creation_expression despite the same
    source shape (BACK-718/720/730); same `new <name>` convention so taxonomy
    patterns apply unchanged.
    """
    for child in _children(node):
        if _zero_arg(child, 'kind') in _SCALA_TYPE_KINDS:
            name = _simple_type_name(child, get_text)
            if name:
                return f"new {name}"
    return None


def infix(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """Scala `infix_expression`: `a :: b` / `list map f` -> the operator as the method name.

    Every single-argument method can be called without dot or parens and
    operators are methods (BACK-746). The `operator` field is an `identifier`
    (alphabetic) or `operator_identifier` (symbolic). Swift shares the kind but
    its operators (`a != b`) are not calls and use an `op` field: None keeps them
    out of the call graph.
    """
    if node.child_by_field_name('op') is not None:
        return None
    op = node.child_by_field_name('operator')
    if op is not None:
        text = get_text(op).strip()
        if text:
            return text
    kids = _children(node)
    if len(kids) >= 3:
        text = get_text(kids[1]).strip()
        if text:
            return text
    return None
