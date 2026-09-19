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

from . import cpp, dart, java, js, php, ruby, scala, swift
from .generic import (
    CHAIN_COLLAPSE,
    CHAIN_FULL,
    callee_name_from_node,
    unwrap_parenthesized_callee,
)

# (node, get_text, *, call_node_types, chain_receiver) -> callee or None
Extractor = Callable[..., Optional[str]]

def _new_expression(node: Any, get_text: Callable[[Any], str], **kw: Any) -> Optional[str]:
    """`new_expression` is shared by JS/TS ('constructor' field), C++ ('type' field) and
    Dart (no fields); dispatch on which field is populated, not on the language, so
    grammars with no dedicated analyzer class still resolve (BACK-730, BACK-760)."""
    if node.child_by_field_name('constructor') is not None:
        return js.new_expression(node, get_text, **kw)
    if node.child_by_field_name('type') is not None:
        return cpp.new_expression(node, get_text, **kw)
    return dart.flat_type_call(node, get_text, **kw)


# Kinds whose call nodes are misparses of non-call syntax and name nothing.
_MISPARSE_CHECKS: Dict[str, Callable[[Any], bool]] = {
    'call_expression': cpp.is_member_function_pointer_misparse,
}


def is_misparsed_call(kind: str, node: Any) -> bool:
    """True when a call-shaped node is really something else (e.g. C++ mfp declaration)."""
    check = _MISPARSE_CHECKS.get(kind)
    return bool(check and check(node))


# Kinds shared with another language: the extractor only owns nodes the predicate
# accepts, the rest fall through to the generic tail (Ruby `call` vs Python `call`).
_CLAIMS: Dict[str, Callable[[Any], bool]] = {
    'call': ruby.is_ruby_call,
}

KIND_EXTRACTORS: Dict[str, Extractor] = {
    'method_invocation': java.method_invocation,             # Java
    'member_call_expression': php.member_call,               # PHP $obj->m()
    'scoped_call_expression': php.scoped_call,               # PHP self::m() / Class::m()
    'object_creation_expression': php.object_creation,       # PHP / C# / Java `new`
    'instance_expression': scala.instance,                   # Scala new Foo[T](...)
    'infix_expression': scala.infix,                         # Scala a :: b (Swift ops -> None)
    'constructor_expression': swift.constructor,             # Swift Foo<T>(...)
    'call': ruby.call,                                       # Ruby (claimed by _CLAIMS)
    'new_expression': _new_expression,                       # JS/TS, C++, Dart `new`
    'init_declarator': cpp.direct_init,                      # C++ `Foo obj(args);`
    'constructor_invocation': dart.flat_type_call,           # Dart List<int>.from(...)
    'const_object_expression': dart.flat_type_call,          # Dart const Foo(...)
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
    claim = _CLAIMS.get(kind)
    if claim is not None and not claim(node):
        return False, None
    return True, handler(node, get_text, call_node_types=call_node_types, chain_receiver=chain_receiver)


__all__ = [
    'CHAIN_COLLAPSE',
    'CHAIN_FULL',
    'KIND_EXTRACTORS',
    'callee_name_from_node',
    'extract_by_kind',
    'is_misparsed_call',
    'unwrap_parenthesized_callee',
]
