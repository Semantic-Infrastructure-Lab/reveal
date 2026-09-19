"""GDScript dotted calls: `x.size()`, `self.m(1)`, `Foo.new()`, `a.b().c()`.

GDScript has no node wrapping "receiver + call". Both live in one flat `attribute`
node: a base expression, then a run of `.` tokens each paired with a bare `identifier`
(plain property, no call) or an `attribute_call` (identifier + arguments -- a call).
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .sites import CallSite


def _member_name(call_node: Any, get_text: Callable[[Any], str]) -> str:
    name_node = next((c for c in _children(call_node) if _zero_arg(c, 'kind') == 'identifier'), None)
    return get_text(name_node).strip() if name_node else ''


def _receiver_text(attribute: Any, call_node: Any, get_text: Callable[[Any], str]) -> str:
    """Source text from the start of the `attribute` up to the `.` before this call."""
    source = get_text(attribute).encode('utf-8')
    prefix = source[:_zero_arg(call_node, 'start_byte') - _zero_arg(attribute, 'start_byte')]
    text = prefix.decode('utf-8', 'replace').rstrip()
    return text[:-1].rstrip() if text.endswith('.') else text


def attribute_sites(attribute: Any, get_text: Callable[[Any], str]) -> List[CallSite]:
    """Every call in one `attribute` node, in source order."""
    children = _children(attribute)
    sites: List[CallSite] = []
    if not children:
        return sites
    dotted: List[str] = []
    if _zero_arg(children[0], 'kind') == 'identifier':
        dotted = [get_text(children[0])]
    for child in children[1:]:
        kind = _zero_arg(child, 'kind')
        if kind == 'identifier':
            member = get_text(child).strip()
            if member:
                dotted = dotted + [f'.{member}']
        elif kind == 'attribute_call':
            member = _member_name(child, get_text)
            receiver = _receiver_text(attribute, child, get_text)
            sites.append(CallSite(
                node=child,
                member=member,
                receiver=receiver,
                dotted=''.join(dotted) + f'.{member}' if dotted and member else (f'.{member}' if member else ''),
            ))
            dotted = []
    return sites


def site_for(call_node: Any, get_text: Callable[[Any], str]) -> Optional[CallSite]:
    """The `CallSite` for one `attribute_call` node, or None if it is not inside an `attribute`."""
    parent = _zero_arg(call_node, 'parent')
    if parent is None or _zero_arg(parent, 'kind') != 'attribute':
        return None
    start = _zero_arg(call_node, 'start_byte')
    return next((s for s in attribute_sites(parent, get_text)
                 if _zero_arg(s.node, 'start_byte') == start), None)
