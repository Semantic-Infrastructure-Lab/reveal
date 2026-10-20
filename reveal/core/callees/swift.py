"""Swift call shapes shared by the analyzer and nav paths.

`constructor` names a `constructor_expression` callee. `is_non_call` recognises the
`call_expression` nodes tree-sitter-swift builds for syntax that calls nothing (BACK-2074).
"""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .. import node_children as _children
from ..treesitter_compat import _zero_arg
from .generic import CHAIN_FULL


def _call_suffix(node: Any) -> Optional[Any]:
    """The `call_suffix` child of a Swift (or Kotlin) `call_expression`, else None."""
    kids = _children(node)
    if len(kids) < 2 or _zero_arg(kids[-1], 'kind') != 'call_suffix':
        return None
    return kids[-1]


def _value_arguments(suffix: Any) -> Optional[Any]:
    return next((c for c in _children(suffix) if _zero_arg(c, 'kind') == 'value_arguments'), None)


def opens_subscript(value_arguments: Any) -> bool:
    """True when a `value_arguments` node is a subscript's `[...]`, not a call's `(...)`."""
    kids = _children(value_arguments)
    return bool(kids) and _zero_arg(kids[0], 'kind') == '['


def is_subscript(node: Any) -> bool:
    """`m["k"]`, `x?[0]`, `grid[1, 2]`: a Swift subscript parsed as `call_expression`."""
    suffix = _call_suffix(node)
    if suffix is None:
        return False
    args = _value_arguments(suffix)
    return args is not None and opens_subscript(args)


def _is_function_reference(suffix: Any) -> bool:
    """`T.init(rawValue:)`, `self.f(tx:)`, `g(_:)`: argument labels and no argument values.

    The function is named, not applied; `f()` (no arguments) and `f(x: 1)` are calls.
    """
    args = _value_arguments(suffix)
    if args is None:
        return False
    arguments = [c for c in _children(args) if _zero_arg(c, 'kind') == 'value_argument']
    return bool(arguments) and all(
        _zero_arg(c, 'kind') == 'value_argument_label'
        for arg in arguments for c in _children(arg) if _zero_arg(c, 'is_named')
    )


def _is_operator_application(node: Any) -> bool:
    """`-(v + 1)`, `!(flag)`: a prefix operator on a parenthesised operand.

    The callee position holds the operator token itself (anonymous `-`, or a `bang` node),
    never an expression that names a function.
    """
    head = node.child(0)
    return head is not None and (not _zero_arg(head, 'is_named') or _zero_arg(head, 'kind') == 'bang')


def _is_defer_block(node: Any, suffix: Any, get_text: Optional[Callable[[Any], str]]) -> bool:
    """`defer { ... }`: the statement keyword followed by a bare closure.

    Kotlin parses `defer { }` the same way but wraps the closure in `annotated_lambda`; there it
    is a real call of a function named defer, and the bare `lambda_literal` test excludes it.
    A backticked `` `defer`(x) `` is an ordinary identifier and stays a call.
    """
    if get_text is None:
        return False
    head = node.child(0)
    if head is None or _zero_arg(head, 'kind') != 'simple_identifier' or get_text(head).strip() != 'defer':
        return False
    named = [c for c in _children(suffix) if _zero_arg(c, 'is_named')]
    return len(named) == 1 and _zero_arg(named[0], 'kind') == 'lambda_literal'


def is_non_call(node: Any, get_text: Optional[Callable[[Any], str]] = None) -> bool:
    """True when a Swift `call_expression` is a subscript, a function reference, an operator
    on a parenthesised operand or a `defer` block: syntax that calls nothing (BACK-2074).

    Calls nested inside (`m[key()]`, the `defer` body) are their own nodes and are still found.
    Only Swift and Kotlin build a `call_suffix`, and Kotlin has none of these shapes under it.
    """
    suffix = _call_suffix(node)
    if suffix is None:
        return False
    args = _value_arguments(suffix)
    if args is not None and opens_subscript(args):
        return True
    return (
        _is_function_reference(suffix)
        or _is_operator_application(node)
        or _is_defer_block(node, suffix, get_text)
    )


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
