"""JS/TS/TSX `new_expression` callee naming (shared by analyzer and nav)."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .generic import CHAIN_FULL


def new_expression(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """JS/TS/TSX `new ClassName(args)` / `new ns.ClassName(args)` -> "new <name>".

    Same node kind as C++'s `new_expression` but a different grammar shape: the
    callee sits in a 'constructor' field (identifier, or member_expression for a
    dotted form), not C++'s 'type' field (BACK-730, 13th language).
    """
    ctor_node = node.child_by_field_name('constructor')
    if ctor_node is None:
        return None
    kind = _zero_arg(ctor_node, 'kind')
    if kind == 'identifier':
        name = get_text(ctor_node).strip()
        return f"new {name}" if name else None
    if kind == 'member_expression':
        prop = None
        for child in _children(ctor_node):
            if _zero_arg(child, 'kind') == 'property_identifier':
                prop = child
        if prop is not None:
            name = get_text(prop).strip()
            return f"new {name}" if name else None
    return None
