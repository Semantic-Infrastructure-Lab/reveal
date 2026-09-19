"""Language-neutral callee naming: the tail shared by every call path.

Given the node in a call's callee position, produce the callee string. Language
specific call shapes (PHP `new`, Java `method_invocation`, Dart selectors, ...)
are handled before this point; this covers what remains: identifiers, member
access, splats, turbofish, parenthesized callees, Swift prefix expressions,
chained/IIFE calls.

`chain_receiver` is the one intentional difference between the two consumers
(BACK-415): for `a.b().c()` the analyzer index keeps the full receiver text
(`a.b().c`), while ast:// nav collapses it to `.c` because the inner call is
already its own edge and a whole multi-line chain would pollute the effect
taxonomy.
"""

from __future__ import annotations

from typing import AbstractSet, Any, Callable, Optional

from .. import node_children as _children
from ..node_taxonomy import MEMBER_ACCESS_NODES as _MEMBER_ACCESS_KINDS
from ..treesitter_compat import _zero_arg

CHAIN_FULL = 'full'
CHAIN_COLLAPSE = 'collapse'

# Callee expressions that have no name of their own: `(a = b)(x)`, an inline
# function/IIFE, a ternary. Emitting their raw text produced junk callees like
# `_malloc = wasmExports["O"]` (BACK-1305); any calls inside an IIFE body are
# captured by the tree walk separately.
_UNNAMEABLE_CALLEE_KINDS = frozenset({
    'assignment_expression', 'augmented_assignment_expression', 'named_expression',
    'function_expression', 'function', 'generator_function', 'arrow_function', 'lambda',
    'class', 'conditional_expression', 'ternary_expression', 'await_expression',
    'binary_expression',
})


def unwrap_parenthesized_callee(node: Any) -> Optional[Any]:
    """Resolve a parenthesized callee to the node that names the call, or None.

    `(f)(x)` -> f; `(0, obj.fn)(x)` (the transpiler idiom that drops `this`) ->
    the LAST comma operand; `(a = b)(x)`, an inline function or a ternary have
    no nameable callee -> None (BACK-1305).
    """
    while _zero_arg(node, 'kind') in ('parenthesized_expression', 'sequence_expression'):
        operands = [c for c in _children(node) if _zero_arg(c, 'kind') not in ('(', ')', ',')]
        if not operands:
            return None
        node = operands[-1] if _zero_arg(node, 'kind') == 'sequence_expression' else operands[0]
    return None if _zero_arg(node, 'kind') in _UNNAMEABLE_CALLEE_KINDS else node


def _receiver_contains_call(member_node: Any, call_node_types: AbstractSet[str]) -> bool:
    """True if a member-access node's receiver subtree contains a nested call.

    The trailing property child (e.g. `.catch`) is skipped — we only care whether
    the *object* being accessed is itself a call result (chained/fluent call).
    """
    named = [c for c in _children(member_node) if _zero_arg(c, 'is_named')]
    # The last named child is the property/field being accessed; the receiver is
    # everything before it. Only scan the receiver for nested calls.
    for child in named[:-1] if len(named) > 1 else named:
        stack = [child]
        while stack:
            node = stack.pop()
            if _zero_arg(node, 'kind') in call_node_types:
                return True
            stack.extend(_children(node))
    return False


def _trailing_property_name(member_node: Any, get_text: Callable[[Any], str]) -> Optional[str]:
    """Return the trailing property/field identifier text of a member-access node."""
    named = [c for c in _children(member_node) if _zero_arg(c, 'is_named')]
    if not named:
        return None
    trailing = named[-1]
    # Kotlin/Swift's navigation_expression wraps the name in its own
    # 'navigation_suffix' node (['.', simple_identifier]) rather than exposing
    # the identifier as a direct child — using its text as-is doubles the
    # leading dot the caller already prepends (BACK-478 move 1 step 2).
    if _zero_arg(trailing, 'kind') == 'navigation_suffix':
        suffix_named = [c for c in _children(trailing) if _zero_arg(c, 'is_named')]
        if not suffix_named:
            return None
        trailing = suffix_named[-1]
    prop = get_text(trailing).strip()
    # Guard against a multi-line / call-bearing trailing node (shouldn't happen
    # for a plain property, but keep the output a clean single token).
    if not prop or '\n' in prop or '(' in prop:
        return None
    return prop


def callee_name_from_node(
    callee_node: Any,
    get_text: Callable[[Any], str],
    *,
    call_node_types: Optional[AbstractSet[str]] = None,
    chain_receiver: str = CHAIN_FULL,
) -> Optional[str]:
    """Name the callee held in `callee_node` (a call's callee-position child).

    `call_node_types` enables the two checks that need to recognise a call node:
    a callee that is itself a call (`f(...)()`, IIFE) has no name of its own
    (BACK-732), and the `chain_receiver='collapse'` policy. Pass None to skip both.
    """
    kind = _zero_arg(callee_node, 'kind')

    # `f(...)()`: the inner call is already its own edge from the tree walk, so
    # emitting its raw text would add a second, un-normalized entry (BACK-732).
    if call_node_types and kind in call_node_types:
        return None

    # Rust turbofish (`size_of::<u32>()`, `x.remap_types::<T>()`) parses as
    # generic_function(path, '::', type_arguments): the path is the real callee
    # (BACK-733). Recurse into just the path.
    if kind == 'generic_function':
        path_node = callee_node.child(0)
        if path_node is not None:
            name = callee_name_from_node(
                path_node, get_text, call_node_types=call_node_types, chain_receiver=chain_receiver)
            if name:
                return name

    # `(f)(args)`: raw text would be the unmatchable literal "(f)" (BACK-733).
    if kind == 'parenthesized_expression':
        inner = unwrap_parenthesized_callee(callee_node)
        if inner is None:
            return None  # no nameable callee (BACK-1305)
        name = callee_name_from_node(
            inner, get_text, call_node_types=call_node_types, chain_receiver=chain_receiver)
        if name:
            return name

    # Swift `!isRunning(x)` parses the callee as prefix_expression(bang,
    # simple_identifier); the operand is always last, after the operator token
    # (BACK-730). Also covers the implicit-member `.foo(...)` shape.
    if kind == 'prefix_expression':
        kids = _children(callee_node)
        if kids:
            name = callee_name_from_node(
                kids[-1], get_text, call_node_types=call_node_types, chain_receiver=chain_receiver)
            if name:
                return name

    # Fluent chain `fetch(x).then(...).catch(...)`: the callee is a member
    # access whose *receiver* is itself a call, so its raw text folds the whole
    # chain into one bogus name (BACK-415). Nav collapses to the trailing
    # `.<property>`; non-chained member calls stay receiver-qualified because
    # the effect taxonomy needs `obj.method`.
    if (
        chain_receiver == CHAIN_COLLAPSE
        and call_node_types
        and kind in _MEMBER_ACCESS_KINDS
        and _receiver_contains_call(callee_node, call_node_types)
    ):
        prop = _trailing_property_name(callee_node, get_text)
        if prop:
            return f".{prop}"
        # No clean property: fall back to a sanitized single-line form.
        first_line = get_text(callee_node).lstrip('*').strip().splitlines()[0].strip()
        return first_line or None

    # tree-sitter parses `*foo(args)` as call(list_splat(*foo), args).
    if kind == 'list_splat':
        for child in _children(callee_node):
            text = get_text(child).lstrip('*').strip()
            if text:
                return text

    text = get_text(callee_node).strip().lstrip('*').strip()
    return text or None
