"""Variable flow tracking: var_flow, _walk_var, all_var_flow, render_var_flow."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


def var_flow(
    func_node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Return all reads and writes of var_name within a line range.

    Each event is a dict:
        kind  -- 'WRITE', 'READ/COND', or 'READ'
        line  -- 1-indexed line number of the identifier
        node  -- the identifier tree-sitter node
    """
    events: List[Dict[str, Any]] = []
    _walk_var(func_node, var_name, from_line, to_line, get_text, events, ctx='READ')
    events.sort(key=lambda e: (e['line'], e['node'].start_point[1]))
    seen: set = set()
    unique = []
    for ev in events:
        key = (ev['line'], ev['node'].start_point[1], ev['kind'])
        if key not in seen:
            seen.add(key)
            unique.append(ev)
    return unique


def _walk_var(
    node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
    events: List[Dict[str, Any]],
    ctx: str,
) -> None:
    """Recursive var-flow walker with write/condition context propagation."""

    def walk(n: Any, c: str) -> None:
        ntype = n.type
        line = n.start_point[0] + 1

        if n.end_point[0] + 1 < from_line or line > to_line:
            return

        if ntype == 'identifier' and get_text(n) == var_name:
            if from_line <= line <= to_line:
                events.append({'kind': c, 'line': line, 'node': n})
            return

        if ntype in ('assignment', 'augmented_assignment'):
            _walk_assignment(n, ntype, c)
        elif ntype == 'named_expression':
            _walk_named_expression(n)
        elif ntype == 'for_statement':
            _walk_for(n, c)
        elif ntype == 'with_statement':
            _walk_with(n, c)
        elif ntype in ('if_statement', 'elif_clause', 'while_statement'):
            _walk_if_while(n, c)
        else:
            for child in n.children:
                walk(child, c)

    def _walk_assignment(n: Any, ntype: str, c: str) -> None:
        left = n.child_by_field_name('left')
        right = n.child_by_field_name('right')
        if left:
            if ntype == 'augmented_assignment':
                walk(left, 'READ')
            walk(left, 'WRITE')
        if right:
            walk(right, 'READ')
        processed = {
            (left.start_byte, left.end_byte) if left else None,
            (right.start_byte, right.end_byte) if right else None,
        }
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                walk(child, c)

    def _walk_named_expression(n: Any) -> None:
        if n.children:
            walk(n.children[0], 'WRITE')
            for child in n.children[1:]:
                walk(child, 'READ')

    def _walk_for(n: Any, c: str) -> None:
        left = n.child_by_field_name('left')
        right = n.child_by_field_name('right')
        body = n.child_by_field_name('body')
        processed: set = set()
        if left:
            processed.add((left.start_byte, left.end_byte))
            walk(left, 'WRITE')
        if right:
            processed.add((right.start_byte, right.end_byte))
            walk(right, 'READ')
        if body:
            processed.add((body.start_byte, body.end_byte))
            walk(body, 'READ')
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                walk(child, c)

    def _walk_with(n: Any, c: str) -> None:
        for child in n.children:
            if child.type == 'with_clause':
                for item in child.children:
                    if item.type == 'with_item':
                        value = item.child_by_field_name('value')
                        alias = item.child_by_field_name('alias')
                        if value:
                            walk(value, 'READ')
                        if alias:
                            walk(alias, 'WRITE')
                    else:
                        walk(item, c)
            elif child.type == 'as_pattern':
                children = child.children
                if children:
                    walk(children[0], 'READ')
                    if len(children) > 2:
                        walk(children[-1], 'WRITE')
            else:
                walk(child, c)

    def _walk_if_while(n: Any, c: str) -> None:
        cond = n.child_by_field_name('condition')
        processed: set = set()
        if cond:
            processed.add((cond.start_byte, cond.end_byte))
            walk(cond, 'READ/COND')
        for child in n.children:
            if (child.start_byte, child.end_byte) not in processed:
                walk(child, c)

    walk(node, ctx)


def render_var_flow(
    var_name: str,
    events: List[Dict[str, Any]],
    content_lines: List[str],
) -> str:
    """Render a var_flow result as text."""
    if not events:
        return f'No references to {var_name!r} found in range'

    lines = []
    for ev in events:
        kind = ev['kind']
        lineno = ev['line']
        snippet = content_lines[lineno - 1].strip() if lineno <= len(content_lines) else ''
        if len(snippet) > 80:
            snippet = snippet[:77] + '...'
        lines.append(f'{kind:<10}L{lineno}:  {snippet}')
    return '\n'.join(lines)


def _collect_identifier_names(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> frozenset:
    """Return the set of identifier names that appear in a line range."""
    names: set = set()
    stack = list(reversed(scope_node.children))
    while stack:
        node = stack.pop()
        line = node.start_point[0] + 1
        if node.end_point[0] + 1 < from_line or line > to_line:
            continue
        if node.type == 'identifier' and from_line <= line <= to_line:
            text = get_text(node)
            if text:
                names.add(text)
        stack.extend(reversed(node.children))
    return frozenset(names)


def all_var_flow(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    full_from: int = 1,
    full_to: Optional[int] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Collect var_flow events for every identifier that appears in a line range."""
    if full_to is None:
        full_to = scope_node.end_point[0] + 1

    names = _collect_identifier_names(scope_node, from_line, to_line, get_text)
    result: Dict[str, List[Dict[str, Any]]] = {}
    for name in sorted(names):
        events = var_flow(scope_node, name, full_from, full_to, get_text)
        if events:
            result[name] = events
    return result
