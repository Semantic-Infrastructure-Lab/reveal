"""Exit analysis: collect_exits, collect_deps, collect_mutations, renderers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .nav_calls import _extract_callee
from .nav_varflow import all_var_flow


# Language-construct names treated as hard exits even when represented as calls
_EXIT_CALL_NAMES: frozenset = frozenset({'die', 'exit'})

# Mapping from exit node type to kind label
_EXIT_KIND: Dict[str, str] = {
    'return_statement': 'RETURN', 'return': 'RETURN',
    'raise_statement': 'RAISE',   'raise': 'RAISE',
    'throw_statement': 'THROW',
    'yield_statement': 'YIELD',   'yield': 'YIELD',
    'break_statement': 'BREAK',   'break': 'BREAK',
    'continue_statement': 'CONTINUE', 'continue': 'CONTINUE',
}

_HARD_EXIT_KINDS: frozenset = frozenset({'RETURN', 'RAISE', 'THROW', 'EXIT'})

# YIELD suspends a generator — not a hard exit but transfers control.
_SOFT_EXIT_KINDS: frozenset = frozenset({'BREAK', 'CONTINUE', 'YIELD'})


def collect_exits(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
    call_node_types: Optional[frozenset] = None,
) -> List[Dict[str, Any]]:
    """Collect exit nodes within a line range.

    Each item is a dict:
        kind -- 'RETURN', 'RAISE', 'THROW', 'YIELD', 'BREAK', 'CONTINUE', or 'EXIT'
        line -- 1-indexed line number
        text -- first line of the node's source text (truncated to 80 chars)
    """
    if call_node_types is None:
        from ...treesitter import CALL_NODE_TYPES  # noqa: PLC0415
        call_node_types = CALL_NODE_TYPES

    results: List[Dict[str, Any]] = []
    stack = list(reversed(scope_node.children))
    while stack:
        node = stack.pop()
        line = node.start_point[0] + 1
        if node.end_point[0] + 1 < from_line or line > to_line:
            continue

        if from_line <= line <= to_line:
            if node.type in _EXIT_KIND:
                kind = _EXIT_KIND[node.type]
                text = get_text(node).splitlines()[0].strip()
                if len(text) > 80:
                    text = text[:77] + '...'
                results.append({'kind': kind, 'line': line, 'text': text})
                continue
            if node.type in call_node_types:
                callee = _extract_callee(node, get_text)
                if callee in _EXIT_CALL_NAMES:
                    text = get_text(node).splitlines()[0].strip()
                    if len(text) > 80:
                        text = text[:77] + '...'
                    results.append({'kind': 'EXIT', 'line': line, 'text': text})

        stack.extend(reversed(node.children))

    results.sort(key=lambda r: r['line'])
    return results


def render_exits(
    exits: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
    verdict: bool = False,
) -> str:
    """Render collect_exits results."""
    lines: List[str] = []
    if not exits:
        lines.append(f'No exits in L{from_line}→L{to_line}')
    else:
        for e in exits:
            lines.append(f'{e["kind"]:<10}L{e["line"]}:  {e["text"]}')

    if verdict:
        has_hard = any(e['kind'] in _HARD_EXIT_KINDS for e in exits)
        has_soft = any(e['kind'] in _SOFT_EXIT_KINDS for e in exits)
        if has_hard:
            v = '⚠ BLOCKED'
        elif has_soft:
            v = '~ CONDITIONAL'
        else:
            v = '✓ CLEAR'
        lines.append(f'\nflowto L{to_line}: {v}')

    return '\n'.join(lines)


def collect_deps(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Identify variables that flow INTO a line range (potential function parameters).

    A variable is a dep if its first event in the range is a READ.
    """
    all_events = all_var_flow(scope_node, from_line, to_line, get_text)
    deps: List[Dict[str, Any]] = []
    for var_name, events in all_events.items():
        in_range = [e for e in events if from_line <= e['line'] <= to_line]
        if not in_range:
            continue
        first_in_range = min(in_range, key=lambda e: e['line'])
        if first_in_range['kind'].startswith('READ'):
            first_write = next(
                (e for e in in_range if e['kind'] == 'WRITE'), None
            )
            deps.append({
                'var': var_name,
                'first_read_line': first_in_range['line'],
                'first_write_line': first_write['line'] if first_write else None,
            })
    deps.sort(key=lambda d: d['first_read_line'])
    return deps


def collect_mutations(
    scope_node: Any,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Identify variables written in a range that are read after it (potential returns)."""
    full_to = scope_node.end_point[0] + 1
    all_events = all_var_flow(
        scope_node, from_line, to_line, get_text, full_to=full_to
    )
    mutations: List[Dict[str, Any]] = []
    for var_name, events in all_events.items():
        in_range = [e for e in events if from_line <= e['line'] <= to_line]
        after_range = [e for e in events if e['line'] > to_line]
        writes_in = [e for e in in_range if e['kind'] == 'WRITE']
        if writes_in and after_range:
            last_write = max(writes_in, key=lambda e: e['line'])
            next_read = min(after_range, key=lambda e: e['line'])
            mutations.append({
                'var': var_name,
                'last_write_line': last_write['line'],
                'next_read_line': next_read['line'],
            })
    mutations.sort(key=lambda m: m['last_write_line'])
    return mutations


def render_deps(
    deps: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_deps results."""
    if not deps:
        return f'No dependencies flowing into L{from_line}→L{to_line}'
    lines: List[str] = []
    for d in deps:
        write_info = (
            f'  (first write L{d["first_write_line"]})'
            if d['first_write_line'] is not None
            else '  (never written in range)'
        )
        lines.append(
            f'PARAM  {d["var"]:<30}  first read L{d["first_read_line"]}{write_info}'
        )
    return '\n'.join(lines)


def render_mutations(
    mutations: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render collect_mutations results."""
    if not mutations:
        return f'No mutations in L{from_line}→L{to_line} that are read after'
    lines: List[str] = []
    for m in mutations:
        lines.append(
            f'RETURN {m["var"]:<30}  written L{m["last_write_line"]},'
            f' next read L{m["next_read_line"]}'
        )
    return '\n'.join(lines)
