"""Shared call-site (callee) extraction used by both the analyzer and nav paths.

See internal-docs/design/CALLEE_EXTRACTION_SINGLE_IMPLEMENTATION_2026-09-18.md
(BACK-1279). Everything here is a pure function of (node, get_text) so the
analyzer (`TreeSitterAnalyzer._get_callee_name`) and nav
(`nav_calls._extract_callee`) delegate to one implementation instead of keeping
paired copies that drift.

`KIND_EXTRACTORS` maps a call node kind to its language-specific extractor. Both
paths consult it first; anything not listed falls through to the language-neutral
tail in `generic.callee_name_from_node`.
"""

from typing import AbstractSet, Any, Callable, Dict, Optional, Tuple

from . import java, php, scala, swift
from .generic import (
    CHAIN_COLLAPSE,
    CHAIN_FULL,
    callee_name_from_node,
    unwrap_parenthesized_callee,
)

# (node, get_text, *, call_node_types, chain_receiver) -> callee or None
Extractor = Callable[..., Optional[str]]

KIND_EXTRACTORS: Dict[str, Extractor] = {
    'method_invocation': java.method_invocation,             # Java
    'member_call_expression': php.member_call,               # PHP $obj->m()
    'scoped_call_expression': php.scoped_call,               # PHP self::m() / Class::m()
    'object_creation_expression': php.object_creation,       # PHP / C# / Java `new`
    'instance_expression': scala.instance,                   # Scala new Foo[T](...)
    'infix_expression': scala.infix,                         # Scala a :: b (Swift ops -> None)
    'constructor_expression': swift.constructor,             # Swift Foo<T>(...)
}


def extract_by_kind(
    kind: str,
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Tuple[bool, Optional[str]]:
    """(handled, name): `handled` is False when no shared extractor owns `kind`."""
    handler = KIND_EXTRACTORS.get(kind)
    if handler is None:
        return False, None
    return True, handler(node, get_text, call_node_types=call_node_types, chain_receiver=chain_receiver)


__all__ = [
    'CHAIN_COLLAPSE',
    'CHAIN_FULL',
    'KIND_EXTRACTORS',
    'callee_name_from_node',
    'extract_by_kind',
    'unwrap_parenthesized_callee',
]
