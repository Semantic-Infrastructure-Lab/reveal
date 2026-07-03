"""Call navigation: range_calls, helpers, render_range_calls."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from ...core import node_children as _children

# Member/attribute access node kinds across the tree-sitter grammars reveal
# supports (JS/TS member_expression, C#/Java member_access, C/C++/Go field &
# selector, Python attribute, Rust scoped_identifier). A call whose callee is
# one of these is a method/attribute call like `obj.method(...)`.
_MEMBER_ACCESS_KINDS = frozenset({
    'member_expression', 'member_access_expression', 'attribute',
    'field_expression', 'selector_expression', 'scoped_identifier',
})


def range_calls(
    func_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
) -> List[Dict[str, Any]]:
    """Return call sites within a line range.

    Each item is a dict:
        line      -- 1-indexed line of the call
        callee    -- callee name string
        first_arg -- text of the first argument (or None)
    """
    if call_node_types is None:
        from ...treesitter import CALL_NODE_TYPES  # noqa: PLC0415
        call_node_types = CALL_NODE_TYPES

    results: List[Dict[str, Any]] = []
    stack = list(reversed(_children(func_node)))
    while stack:
        node = stack.pop()
        line = node.start_position().row + 1
        if node.end_position().row + 1 < from_line or line > to_line:
            continue
        if node.kind() in call_node_types and from_line <= line <= to_line:
            callee = _extract_callee(node, get_text, call_node_types)
            first_arg, has_more = _extract_first_arg(node, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
        stack.extend(reversed(_children(node)))

    results.sort(key=lambda r: r['line'])
    return results


def _extract_callee(
    call_node: Any,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
) -> Optional[str]:
    """Extract callee name from a call expression node."""
    if not call_node.child_count():
        return None

    # PHP: $obj->method(args) — emit "<receiver>-><name>" so taxonomy patterns
    # like '->execute', '->fetch', '->prepare' can match.
    if call_node.kind() == 'member_call_expression':
        return _extract_member_call_callee(call_node, get_text)

    # PHP: new ClassName(args) — emit "new <name>" so taxonomy patterns
    # like 'new pdo' can match.
    if call_node.kind() == 'object_creation_expression':
        return _extract_object_creation_callee(call_node, get_text)

    # Java: method_invocation is a flat node `[object? . name argument_list]` —
    # child(0) is only the *object* (`Files`, `path`), so the old logic dropped
    # the method name entirely (`Files.createDirectories()` → "Files",
    # `path.resolveIndex()` → "path"). Rebuild the receiver-qualified callee so
    # the effect taxonomy and calls:// see `Files.createDirectories` /
    # `path.resolveIndex` (BACK-416).
    if call_node.kind() == 'method_invocation':
        return _extract_java_method_invocation_callee(call_node, get_text, call_node_types)

    callee_node = call_node.child(0)

    # Chained/fluent call: `rimrafUnlink(x).catch(...)`, `fetch(x).then(...).catch(...)`.
    # The callee is a member-access whose *receiver* is itself a call, so its raw
    # text folds the entire (possibly multi-line, 150+ char) chain into one bogus
    # "callee" name — which then pollutes trace/calls:// and mis-fires the
    # side-effect taxonomy (BACK-415). The receiver call is already captured as
    # its own edge by the tree walk, so collapse the outer callee to just its
    # trailing `.<property>` rather than the whole chain. Non-chained member
    # calls (`obj.method`) are left receiver-qualified — the taxonomy needs that.
    if (
        call_node_types
        and callee_node.kind() in _MEMBER_ACCESS_KINDS
        and _receiver_contains_call(callee_node, call_node_types)
    ):
        prop = _trailing_property_name(callee_node, get_text)
        if prop:
            return f".{prop}"
        # Fall through to a sanitized single-line form if no clean property found.
        first_line = get_text(callee_node).lstrip('*').strip().splitlines()[0].strip()
        return first_line or None

    text = get_text(callee_node).lstrip('*').strip()
    if callee_node.kind() == 'list_splat':
        for child in _children(callee_node):
            t = get_text(child).lstrip('*').strip()
            if t:
                return t
    return text if text else None


def _receiver_contains_call(member_node: Any, call_node_types: frozenset) -> bool:
    """True if a member-access node's receiver subtree contains a nested call.

    The trailing property child (e.g. `.catch`) is skipped — we only care whether
    the *object* being accessed is itself a call result (chained/fluent call).
    """
    named = [c for c in _children(member_node) if c.is_named()]
    # The last named child is the property/field being accessed; the receiver is
    # everything before it. Only scan the receiver for nested calls.
    for child in named[:-1] if len(named) > 1 else named:
        stack = [child]
        while stack:
            node = stack.pop()
            if node.kind() in call_node_types:
                return True
            stack.extend(_children(node))
    return False


def _trailing_property_name(member_node: Any, get_text: Callable) -> Optional[str]:
    """Return the trailing property/field identifier text of a member-access node."""
    named = [c for c in _children(member_node) if c.is_named()]
    if not named:
        return None
    prop = get_text(named[-1]).strip()
    # Guard against a multi-line / call-bearing trailing node (shouldn't happen
    # for a plain property, but keep the output a clean single token).
    if not prop or '\n' in prop or '(' in prop:
        return None
    return prop


def _extract_member_call_callee(node: Any, get_text: Callable) -> Optional[str]:
    """PHP member_call_expression: <receiver> (->|?->) <name> <arguments>."""
    receiver_text: Optional[str] = None
    method_name: Optional[str] = None
    seen_arrow = False
    for child in _children(node):
        if child.kind() in ('->', '?->'):
            seen_arrow = True
            continue
        if child.kind() == 'arguments':
            break
        if not seen_arrow:
            if receiver_text is None:
                receiver_text = get_text(child).strip()
        else:
            if child.kind() == 'name':
                method_name = get_text(child).strip()
                break
    if receiver_text and method_name:
        return f"{receiver_text}->{method_name}"
    if method_name:
        return f"->{method_name}"
    return None


def _extract_object_creation_callee(node: Any, get_text: Callable) -> Optional[str]:
    """PHP object_creation_expression: new <name|qualified_name> <arguments>."""
    for child in _children(node):
        if child.kind() in ('name', 'qualified_name'):
            class_name = get_text(child).strip()
            if class_name:
                return f"new {class_name}"
    return None


def _extract_java_method_invocation_callee(
    node: Any,
    get_text: Callable,
    call_node_types: Optional[frozenset],
) -> Optional[str]:
    """Java method_invocation: `[object? . name argument_list]` → `object.name`.

    Emits the receiver-qualified callee (`Files.createDirectories`,
    `path.resolveIndex`) so the taxonomy and calls:// see the method name, not
    just the object. Chained calls (`a.b().c()`) whose object is itself a call
    collapse to `.name` (the inner call is captured separately), mirroring the
    member-access handling in _extract_callee (BACK-415/BACK-416).
    """
    children = _children(node)
    arg_idx = next(
        (i for i, c in enumerate(children) if c.kind() == 'argument_list'),
        len(children),
    )
    pre = children[:arg_idx]
    if not pre:
        return None
    name = get_text(pre[-1]).strip()
    # Qualified form: [object, '.', name]
    if len(pre) >= 3 and pre[-2].kind() in ('.', '?.'):
        obj_node = pre[0]
        if call_node_types and _subtree_contains_call(obj_node, call_node_types):
            return f".{name}" if name else None
        obj_text = get_text(obj_node).strip()
        if obj_text and name:
            return f"{obj_text}.{name}"
    return name or None


def _subtree_contains_call(node: Any, call_node_types: frozenset) -> bool:
    """True if any node in the subtree rooted at *node* is a call."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.kind() in call_node_types:
            return True
        stack.extend(_children(cur))
    return False


def _extract_first_arg(call_node: Any, get_text: Callable) -> tuple:
    """Extract the first argument and whether more args follow."""
    for child in _children(call_node):
        if child.kind() in ('argument_list', 'arguments', 'call_arguments'):
            real_args = [
                c for c in _children(child)
                if c.kind() not in ('(', ')', ',', 'comment') and c.is_named()
            ]
            if not real_args:
                return None, False
            text = get_text(real_args[0]).splitlines()[0].strip()
            if len(text) > 40:
                text = text[:37] + '...'
            return text, len(real_args) > 1
    return None, False


def render_range_calls(
    calls: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render a range_calls result as text."""
    if not calls:
        return f'No calls found in L{from_line}→L{to_line}'

    lines = []
    for call in calls:
        callee = call['callee'] or '?'
        if call['first_arg']:
            arg_part = f'({call["first_arg"]}, ...)' if call['has_more_args'] else f'({call["first_arg"]})'
        else:
            arg_part = '(...)'
        lines.append(f'L{call["line"]}:  {callee}{arg_part}')
    return '\n'.join(lines)
