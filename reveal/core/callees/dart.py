"""Dart flat type-then-arguments call shapes (shared by analyzer and nav)."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, List, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .generic import CHAIN_FULL
from .sites import CallSite


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


# `.member` / `?.member` selector kinds; after `this`/`super` they are BARE siblings
# with no `selector` wrapper.
MEMBER_SELECTORS = ('unconditional_assignable_selector', 'conditional_assignable_selector')


def _extend_receiver(parts: List[str], member_node: Any, get_text: Callable[[Any], str]) -> List[str]:
    """Append a `.member` selector to the callee text so far; an index selector (`a[0]`) ends the chain."""
    inner = _children(member_node)
    if inner and _zero_arg(inner[0], 'kind') == 'index_selector':
        return []
    member = get_text(inner[-1]).strip() if inner else ''
    if not member:
        return []
    return parts + [f'.{member}'] if parts else [f'.{member}']


def _site(node: Any, args: Any, parts: List[str]) -> CallSite:
    dotted = ''.join(parts)
    return CallSite(node=node, member=dotted.rsplit('.', 1)[-1], receiver='', dotted=dotted, args=args)


def selector_sites(children: List[Any], get_text: Callable[[Any], str]) -> List[CallSite]:
    """Call sites in Dart's flat `identifier selector selector ...` sibling run.

    `obj.method(x, y).other()` has no node naming "the call": walk left to right,
    accumulating the callee through `.member` selectors, one site per `argument_part`.
    A call after a call restarts the chain, so it is `.member` (chain collapse). The
    receiver may be `identifier`, `this` or `super`.
    """
    sites: List[CallSite] = []
    parts: List[str] = []
    for child in children:
        kind = _zero_arg(child, 'kind')
        if kind in ('identifier', 'this', 'super'):
            parts = [get_text(child)]
            continue
        if kind in MEMBER_SELECTORS:
            parts = _extend_receiver(parts, child, get_text)
            continue
        if kind != 'selector':
            parts = []
            continue
        sel = _children(child)
        if not sel:
            continue
        if len(sel) == 1 and _zero_arg(sel[0], 'kind') == '!':
            continue  # null-assertion `x!.foo()`: carries no name, the receiver survives it
        inner = sel[0]
        inner_kind = _zero_arg(inner, 'kind')
        if inner_kind == 'argument_part':
            sites.append(_site(child, inner, parts))
            parts = []
        elif inner_kind in MEMBER_SELECTORS:
            parts = _extend_receiver(parts, inner, get_text)
        else:
            parts = []
    return sites


def cascade_sites(section: Any, get_text: Callable[[Any], str]) -> List[CallSite]:
    """Call sites in one `cascade_section` (`..foo()`, `..setup().finish()`).

    Each cascaded operation is its own sibling section: `..`, a `cascade_selector`
    (the member), then an `argument_part` directly, or a run of
    `assignable_selector`/`argument_part` for a chained continuation. A cascaded
    field write (`..field = 3`) has no `argument_part` and emits nothing.
    """
    sites: List[CallSite] = []
    parts: List[str] = []
    for child in _children(section):
        kind = _zero_arg(child, 'kind')
        if kind == 'cascade_selector':
            name = next((c for c in _children(child) if _zero_arg(c, 'kind') == 'identifier'), None)
            member = get_text(name).strip() if name else ''
            parts = [f'.{member}'] if member else []
        elif kind == 'argument_part':
            sites.append(_site(child, child, parts))
            parts = []
        elif kind in MEMBER_SELECTORS:
            sub = _children(child)
            if sub and _zero_arg(sub[0], 'kind') == 'index_selector':
                parts = []
            else:
                member = get_text(sub[-1]).strip() if sub else ''
                parts = (parts + [f'.{member}']) if parts and member else ([f'.{member}'] if member else [])
        elif kind != '..':
            parts = []
    return sites


def site_at(sites: List[CallSite], start_byte: int) -> Optional[CallSite]:
    """The site whose argument list starts at `start_byte` (node identity is unreliable, BACK-573)."""
    return next((s for s in sites if _zero_arg(s.arg_node, 'start_byte') == start_byte), None)
