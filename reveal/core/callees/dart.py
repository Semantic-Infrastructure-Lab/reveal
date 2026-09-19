"""Dart flat type-then-arguments call shapes (shared by analyzer and nav)."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .generic import CHAIN_FULL


def flat_type_call(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """Dart `new Foo(..)` / `const Foo(..)` / `List<int>.from(..)`.

    'constructor_invocation', 'const_object_expression' and Dart's field-less
    'new_expression' share a flat layout: `[new|const]? type_identifier
    type_arguments? ('.' identifier)? arguments`. Returns `Foo` or `Foo.named`;
    generic arguments are dropped (BACK-760, BACK-1279).
    """
    base = named = None
    seen_dot = False
    for child in _children(node):
        kind = _zero_arg(child, 'kind')
        if kind == 'type_identifier' and base is None:
            base = get_text(child).strip()
        elif kind == '.':
            seen_dot = True
        elif kind == 'identifier' and seen_dot and named is None:
            named = get_text(child).strip()
    if not base:
        return None
    return f"{base}.{named}" if named else base
