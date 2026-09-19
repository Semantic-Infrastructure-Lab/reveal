"""Zig call sites: `foo(x)`, `a.b.c(x)`, `@import("std")`, `.fixed(&buf)`.

Zig has no call-expression node. A call is a `SuffixExpr`: a base (`IDENTIFIER`,
`BUILTINIDENTIFIER`, or a `.name` enum-literal pair) followed by `FnCallArguments` (bare
call) and/or `FieldOrFnCall` segments, each optionally carrying its own arguments.
The analyzer already projects from nav's `range_calls` (BACK-660), so this enumerator
is the single decoder for both.
"""

from __future__ import annotations

from typing import Any, Callable, List

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
