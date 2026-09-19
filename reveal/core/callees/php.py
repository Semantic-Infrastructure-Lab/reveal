"""PHP call shapes: `$obj->m()`, `self::m()`, and `new Foo()` (shared by analyzer and nav)."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .generic import CHAIN_FULL


def member_call(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """PHP member_call_expression: <receiver> (->|?->) <name> <arguments>.

    Emits `<receiver>-><name>` so taxonomy patterns like `->execute` can match.
    """
    receiver_text: Optional[str] = None
    method_name: Optional[str] = None
    seen_arrow = False
    for child in _children(node):
        if _zero_arg(child, 'kind') in ('->', '?->'):
            seen_arrow = True
            continue
        if _zero_arg(child, 'kind') == 'arguments':
            break
        if not seen_arrow:
            if receiver_text is None:
                receiver_text = get_text(child).strip()
        else:
            if _zero_arg(child, 'kind') == 'name':
                method_name = get_text(child).strip()
                break
    if receiver_text and method_name:
        return f"{receiver_text}->{method_name}"
    if method_name:
        return f"->{method_name}"
    return None


def scoped_call(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """PHP scoped_call_expression: self::m() / parent::m() / static::m() / Class::m().

    The 'scope' field is a 'relative_scope' (self/parent/static) or a plain
    'name' (a class constant); 'name' is the method (BACK-736, BACK-740).
    """
    scope_node = node.child_by_field_name('scope')
    name_node = node.child_by_field_name('name')
    if name_node is None:
        return None
    name_text = get_text(name_node).strip()
    if not name_text:
        return None
    if scope_node is None:
        return name_text
    scope_text = get_text(scope_node).strip()
    return f"{scope_text}::{name_text}" if scope_text else name_text


def object_creation(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """`object_creation_expression`: PHP `new <name|qualified_name>(args)`, C#
    `new <identifier|generic_name>(args) { init }` and Java `new Foo(args)`.

    The three share this node-kind name despite unrelated internal shapes.
    Generic types collapse to their base name (`Dictionary`, not
    `Dictionary<K, V>`) so they match plain `new Foo()`.
    """
    for child in _children(node):
        kind = _zero_arg(child, 'kind')
        if kind in ('name', 'qualified_name', 'scoped_type_identifier', 'identifier', 'type_identifier'):
            class_name = get_text(child).strip()
            if class_name:
                return f"new {class_name}"
        if kind in ('generic_name', 'generic_type'):
            base = next((c for c in _children(child)
                         if _zero_arg(c, 'kind') in ('identifier', 'type_identifier', 'scoped_type_identifier')), None)
            if base is not None:
                class_name = get_text(base).strip()
                if class_name:
                    return f"new {class_name}"
    return None
