"""Call navigation: range_calls, helpers, render_range_calls."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


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
    stack = list(reversed(func_node.children))
    while stack:
        node = stack.pop()
        line = node.start_point[0] + 1
        if node.end_point[0] + 1 < from_line or line > to_line:
            continue
        if node.type in call_node_types and from_line <= line <= to_line:
            callee = _extract_callee(node, get_text)
            first_arg, has_more = _extract_first_arg(node, get_text)
            results.append({'line': line, 'callee': callee, 'first_arg': first_arg, 'has_more_args': has_more})
        stack.extend(reversed(node.children))

    results.sort(key=lambda r: r['line'])
    return results


def _extract_callee(call_node: Any, get_text: Callable) -> Optional[str]:
    """Extract callee name from a call expression node."""
    if not call_node.children:
        return None

    # PHP: $obj->method(args) — emit "<receiver>-><name>" so taxonomy patterns
    # like '->execute', '->fetch', '->prepare' can match.
    if call_node.type == 'member_call_expression':
        return _extract_member_call_callee(call_node, get_text)

    # PHP: new ClassName(args) — emit "new <name>" so taxonomy patterns
    # like 'new pdo' can match.
    if call_node.type == 'object_creation_expression':
        return _extract_object_creation_callee(call_node, get_text)

    callee_node = call_node.children[0]
    text = get_text(callee_node).lstrip('*').strip()
    if callee_node.type == 'list_splat':
        for child in callee_node.children:
            t = get_text(child).lstrip('*').strip()
            if t:
                return t
    return text if text else None


def _extract_member_call_callee(node: Any, get_text: Callable) -> Optional[str]:
    """PHP member_call_expression: <receiver> (->|?->) <name> <arguments>."""
    receiver_text: Optional[str] = None
    method_name: Optional[str] = None
    seen_arrow = False
    for child in node.children:
        if child.type in ('->', '?->'):
            seen_arrow = True
            continue
        if child.type == 'arguments':
            break
        if not seen_arrow:
            if receiver_text is None:
                receiver_text = get_text(child).strip()
        else:
            if child.type == 'name':
                method_name = get_text(child).strip()
                break
    if receiver_text and method_name:
        return f"{receiver_text}->{method_name}"
    if method_name:
        return f"->{method_name}"
    return None


def _extract_object_creation_callee(node: Any, get_text: Callable) -> Optional[str]:
    """PHP object_creation_expression: new <name|qualified_name> <arguments>."""
    for child in node.children:
        if child.type in ('name', 'qualified_name'):
            class_name = get_text(child).strip()
            if class_name:
                return f"new {class_name}"
    return None


def _extract_first_arg(call_node: Any, get_text: Callable) -> tuple:
    """Extract the first argument and whether more args follow."""
    for child in call_node.children:
        if child.type in ('argument_list', 'arguments', 'call_arguments'):
            real_args = [
                c for c in child.children
                if c.type not in ('(', ')', ',', 'comment') and c.is_named
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
