"""Zig call sites: `foo(x)`, `a.b.c(x)`, `@import("std")`, `.fixed(&buf)`.

Legacy grammar (tree-sitter-language-pack <= 1.24): Zig has no call-expression node. A
call is a `SuffixExpr`: a base (`IDENTIFIER`, `BUILTINIDENTIFIER`, or a `.name`
enum-literal pair) followed by `FnCallArguments` (bare call) and/or `FieldOrFnCall`
segments, each optionally carrying its own arguments. The analyzer already projects from
nav's `range_calls` (BACK-660), so `suffix_sites` is the single decoder for both.

Pack 1.25 grammar (BACK-2540): an ordinary `call_expression` / `builtin_function`, named
by the shared callee tail, which asks `field_callee` for a Zig member chain.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .sites import CallSite


def suffix_sites(children: List[Any], get_text: Callable[[Any], str]) -> List[CallSite]:
    """Call sites in one `SuffixExpr`'s children, in source order.

    `node` is the `FnCallArguments` node (its line and argument list).
    """
    sites: List[CallSite] = []
    if not children:
        return sites
    base_parts: List[str] = []
    rest = children[1:]
    if _zero_arg(children[0], 'kind') in ('IDENTIFIER', 'BUILTINIDENTIFIER'):
        base_parts = [get_text(children[0])]
    elif (_zero_arg(children[0], 'kind') == '.' and len(children) > 1
          and _zero_arg(children[1], 'kind') == 'IDENTIFIER'):
        # `.fixed(&buf)` -- type-inferred enum-literal call: a bare `.` then the name,
        # never wrapped in `FieldOrFnCall` (BACK-730/BACK-754, real Ghostty source).
        base_parts = [get_text(children[1])]
        rest = children[2:]
    for child in rest:
        kind = _zero_arg(child, 'kind')
        if kind == 'FnCallArguments':
            callee = ''.join(base_parts)
            sites.append(CallSite(node=child, member=callee, receiver='', dotted=callee, args=child))
            base_parts = []
        elif kind == 'FieldOrFnCall':
            seg = _children(child)
            names = [c for c in seg if _zero_arg(c, 'kind') == 'IDENTIFIER']
            args = next((c for c in seg if _zero_arg(c, 'kind') == 'FnCallArguments'), None)
            member = get_text(names[0]).strip() if names else ''
            if args is not None:
                dotted = (''.join(base_parts) + f'.{member}' if base_parts and member
                          else (f'.{member}' if member else ''))
                sites.append(CallSite(node=child, member=member, receiver=''.join(base_parts),
                                      dotted=dotted, args=args))
                base_parts = []
            elif member:
                base_parts = base_parts + [f'.{member}'] if base_parts else [f'.{member}']
    return sites


# Wrappers the pack 1.25 grammar puts around a callee or at the base of its member chain:
# `x.?(...)` (null_coercion_expression), and the prefix operators of `!a.b()` / `?*T.f()`,
# which it reads as type syntax (`!T` error union, `?T`, `*T`). The legacy grammar named
# these calls without the sigil; the operand names the call.
WRAPPER_KINDS = frozenset({'null_coercion_expression', 'error_union_type', 'nullable_type', 'pointer_type'})


# Chain links the legacy decoder read through without naming: `a[i].b` (index),
# `a.*.b` (dereference), `a.?.b` (optional unwrap). Only reached from a Zig member chain.
_THROUGH_LINKS = frozenset({'index_expression', 'dereference_expression', 'null_coercion_expression'})
# Type prefixes the 1.25 grammar puts at the base of a chain (`[]const std.ArrayList(T)`
# reads as `([]const std).ArrayList`). Not in WRAPPER_KINDS: Go's `[]byte(s)` conversion
# is a slice_type callee too, and only a Zig member chain is unwrapped through these.
_CHAIN_BASE_TYPES = frozenset({'slice_type', 'array_type'})


def unwrap_operand(node: Any) -> Any:
    """The innermost operand under WRAPPER_KINDS (`!builtin` -> `builtin`, `list[i].?` -> `list`)."""
    while _zero_arg(node, 'kind') in WRAPPER_KINDS | _THROUGH_LINKS:
        inner = node.child_by_field_name('ok') or node.child_by_field_name('object')
        if inner is None:
            named = [c for c in _children(node) if _zero_arg(c, 'is_named')]
            inner = named[0] if _zero_arg(node, 'kind') in _THROUGH_LINKS and named else (
                named[-1] if named else None)
        if inner is None:
            return node
        node = inner
    return node


def field_callee(node: Any, get_text: Callable[[Any], str]) -> Optional[str]:
    """Name a pack 1.25 member chain callee (`a.b.c`, `.fixed`), or None if `node` is not one.

    A Zig `field_expression` names its parts `object` and `member` (C, Rust and Scala name
    them argument/value and field), so this matches Zig only. The legacy decoder's naming:
    the member path, read through index/dereference/unwrap links; the base when it is a plain
    name, with any type-operator wrapper dropped (`!a.b()` -> `a.b`); `.member` when the
    receiver is no name (`(Flags{...}).cval` -> `.cval`); and a chain with no receiver
    (`.fixed(&buf)`, a type-inferred enum-literal call) names its members alone, as Swift's
    implicit `.foo(x)` does."""
    if _zero_arg(node, 'kind') != 'field_expression' or node.child_by_field_name('member') is None:
        return None
    members: List[str] = []
    current: Optional[Any] = node
    while current is not None:
        if _zero_arg(current, 'kind') == 'field_expression' and current.child_by_field_name('member') is not None:
            members.append(get_text(current.child_by_field_name('member')).strip())
            current = current.child_by_field_name('object')
        elif _zero_arg(current, 'kind') in WRAPPER_KINDS | _THROUGH_LINKS:
            inner = unwrap_operand(current)
            if inner is current:
                break
            current = inner
        elif _zero_arg(current, 'kind') in _CHAIN_BASE_TYPES:
            named = [c for c in _children(current) if _zero_arg(c, 'is_named')]
            if not named:
                break
            current = named[-1]  # the element type, after any length or sentinel
        else:
            break
    path = '.'.join(reversed(members))
    if current is None:
        return path or None
    if _zero_arg(current, 'kind') == 'identifier':
        return f'{get_text(current).strip()}.{path}'
    return f'.{path}'
