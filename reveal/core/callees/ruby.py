"""Ruby `call` callee naming and the attribute-write policy (shared by analyzer and nav)."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from ..treesitter_compat import _zero_arg
from .generic import CHAIN_COLLAPSE, CHAIN_FULL, subtree_contains_call

# Receivers that would make a readable nav label too long fall back to `.method`.
_NAV_MAX_RECEIVER_LEN = 40


def is_attribute_write(call_node: Any) -> bool:
    """True for the LHS `call` of a plain assignment (`obj.attr = v`).

    tree-sitter-ruby parses a setter write as the same `call` shape as a read,
    wrapped in `assignment`. A pure write is not a call (matches Ruby's own AST
    and the recall oracle, BACK-1302); `+=`/`||=` (`operator_assignment`) reads
    first, so it is.
    """
    parent = _zero_arg(call_node, 'parent')
    if parent is None or _zero_arg(parent, 'kind') != 'assignment':
        return False
    left = parent.child_by_field_name('left')
    return left is not None and _zero_arg(left, 'start_byte') == _zero_arg(call_node, 'start_byte')


def is_ruby_call(node: Any) -> bool:
    """`call` is the same node kind as Python's; Ruby's carries a 'method' field."""
    return node.child_by_field_name('method') is not None


def call(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """Ruby `call`: fielded `receiver`/`method`/`arguments` -> `receiver.method`.

    The flat `(receiver?, '.', method, args?)` shape makes child(0) the receiver,
    which dropped the method name (`obj.baz` -> "obj", BACK-431/BACK-734). A
    receiver-less call (`puts(x)`) is just the method name. Under the nav policy a
    receiver that is itself a call, multi-line, or longer than 40 chars collapses
    to `.method` (BACK-415); the analyzer index keeps the receiver text.
    """
    if is_attribute_write(node):
        return None
    method = node.child_by_field_name('method')
    if method is None:
        return None
    name = get_text(method).strip()
    if not name:
        return None
    receiver = node.child_by_field_name('receiver')
    if receiver is None:
        return name
    if chain_receiver == CHAIN_COLLAPSE:
        if call_node_types and subtree_contains_call(receiver, call_node_types):
            return f".{name}"
        receiver_text = get_text(receiver).strip()
        if not receiver_text or '\n' in receiver_text or len(receiver_text) > _NAV_MAX_RECEIVER_LEN:
            return f".{name}"
        return f"{receiver_text}.{name}"
    receiver_text = get_text(receiver)
    return f"{receiver_text}.{name}" if receiver_text else name
