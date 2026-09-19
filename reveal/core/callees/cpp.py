"""C++ call shapes: `new T(args)`, direct-initialization, and the mfp-declaration misparse."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .generic import CHAIN_FULL

_NEW_TYPE_KINDS = ('type_identifier', 'qualified_identifier', 'template_type')


def _constructor_name(type_node: Any, get_text: Callable[[Any], str]) -> Optional[str]:
    """Trailing `::` segment of a (possibly qualified, possibly templated) type, generics dropped."""
    text = get_text(type_node).strip().split('<')[0].strip()
    return text.split('::')[-1].strip() or None if text else None


def new_expression(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """C++ `new ClassName(args)` / `new NS::ClassName<T>(args)` -> "new <name>".

    Qualified types collapse to their trailing segment and generics are dropped,
    like the other `new <name>` shapes. Non-class types (`new int[8]`) are not calls.
    """
    type_node = node.child_by_field_name('type')
    if type_node is None or _zero_arg(type_node, 'kind') not in _NEW_TYPE_KINDS:
        return None
    name = _constructor_name(type_node, get_text)
    return f"new {name}" if name else None


def direct_init(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """C++ direct-initialization `ClassName obj(args);` / `std::vector<int> v(10);` (BACK-744).

    An `init_declarator` whose 'value' field is a bare `argument_list`. Copy-init
    (`Foo o = Foo(3, 4)`, a call_expression value) and plain declarations
    (`int x = 5`, also plain C/ObjC) are not this shape. The callee is the TYPE on
    the parent `declaration`'s 'type' field; no "new " prefix (no `new` in source).
    """
    value_node = node.child_by_field_name('value')
    if value_node is None or _zero_arg(value_node, 'kind') != 'argument_list':
        return None
    decl_node = _zero_arg(node, 'parent')
    if decl_node is None:
        return None
    type_node = decl_node.child_by_field_name('type')
    if type_node is None:
        return None
    kind = _zero_arg(type_node, 'kind')
    if kind not in ('type_identifier', 'qualified_identifier'):
        return None
    text = get_text(type_node).strip()
    if not text:
        return None
    return text.split('::')[-1] if kind == 'qualified_identifier' else text


def is_member_function_pointer_misparse(call_node: Any) -> bool:
    """True if `call_node` is a member-function-pointer declaration misparsed as a call (BACK-745).

    `void (Base::*mfp)() = &Base::plain;` parses as nested call_expression nodes
    with `Base::*mfp` (a `pointer_type_declarator`, never a valid call argument)
    inside the inner call's argument list. `pointer_type_declarator` is a C/C++-only
    kind, so this scan is a no-op for other languages.
    """
    args = call_node.child_by_field_name('arguments')
    if args is None:
        return False
    stack = _children(args)
    while stack:
        n = stack.pop()
        if _zero_arg(n, 'kind') == 'pointer_type_declarator':
            return True
        stack.extend(_children(n))
    return False
