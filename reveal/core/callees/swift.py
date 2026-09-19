"""Swift `constructor_expression` callee naming (shared by analyzer and nav)."""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .generic import CHAIN_FULL


def constructor(
    node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """Swift `constructor_expression`: `constructed_type<TypeArgs>` + `constructor_suffix`.

    Covers a generic function call (`identity<Int>(5)`) and a generic type
    initializer (`Array<Int>()`). Unlike Scala/PHP construction nodes this is not
    always a construction, so it emits the bare name (`identity`, `Array`) with
    no "new " prefix (BACK-730).
    """
    constructed = node.child_by_field_name('constructed_type')
    if constructed is None:
        return None
    if _zero_arg(constructed, 'kind') == 'user_type':
        base = next(
            (c for c in _children(constructed) if _zero_arg(c, 'kind') == 'type_identifier'),
            None,
        )
        if base is not None:
            name = get_text(base).strip()
            if name:
                return name
    text = get_text(constructed).strip()
    if text:
        return text.split('<')[0].strip() or None
    return None
