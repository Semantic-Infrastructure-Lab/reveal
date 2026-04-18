"""Outline and scope-chain navigation: element_outline, scope_chain, renderers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List


# ---------------------------------------------------------------------------
# Node type constants — used by outline and scope traversals
# ---------------------------------------------------------------------------

SCOPE_NODES: frozenset = frozenset({
    'if_statement', 'for_statement', 'while_statement',
    'try_statement', 'with_statement',
    'match_statement', 'case_clause',
    'elif_clause', 'else_clause', 'except_clause', 'finally_clause',
    'do_statement', 'switch_statement',
    'catch_clause',
    'if', 'for', 'while', 'try', 'switch',
})

ALTERNATIVE_NODES: frozenset = frozenset({
    'elif_clause', 'else_clause',
    'except_clause', 'finally_clause',
    'else', 'catch_clause', 'catch', 'finally',
    'switch_default', 'default',
})

FUNCTION_TYPES: frozenset = frozenset({
    'function_definition', 'function_declaration', 'function_item',
    'method_definition', 'method_declaration', 'function',
    'class_definition', 'class_declaration', 'class',
    'arrow_function', 'lambda',
})

EXIT_NODES: frozenset = frozenset({
    'return_statement', 'raise_statement', 'yield_statement',
    'return', 'raise', 'throw_statement', 'yield',
    'break_statement', 'continue_statement',
})

KEYWORD_LABEL: Dict[str, str] = {
    'if_statement': 'IF', 'if': 'IF',
    'elif_clause': 'ELIF',
    'else_clause': 'ELSE', 'else': 'ELSE',
    'for_statement': 'FOR', 'for': 'FOR',
    'while_statement': 'WHILE', 'while': 'WHILE',
    'try_statement': 'TRY', 'try': 'TRY',
    'except_clause': 'EXCEPT',
    'finally_clause': 'FINALLY', 'finally': 'FINALLY',
    'with_statement': 'WITH', 'with': 'WITH',
    'match_statement': 'MATCH',
    'case_clause': 'CASE',
    'do_statement': 'DO',
    'switch_statement': 'SWITCH', 'switch': 'SWITCH',
    'catch_clause': 'CATCH', 'catch': 'CATCH',
    'switch_case': 'CASE',
    'switch_default': 'DEFAULT', 'default': 'DEFAULT',
    'function_definition': 'DEF', 'function_declaration': 'DEF',
    'function_item': 'DEF', 'function': 'DEF',
    'method_definition': 'DEF', 'method_declaration': 'DEF',
    'arrow_function': 'DEF',
    'lambda': 'LAMBDA',
    'class_definition': 'CLASS', 'class_declaration': 'CLASS', 'class': 'CLASS',
    'return_statement': 'RETURN', 'return': 'RETURN',
    'raise_statement': 'RAISE', 'raise': 'RAISE',
    'throw_statement': 'THROW',
    'yield_statement': 'YIELD', 'yield': 'YIELD',
    'break_statement': 'BREAK', 'break': 'BREAK',
    'continue_statement': 'CONTINUE', 'continue': 'CONTINUE',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_label(node: Any, get_text: Callable) -> str:
    """Return 'KEYWORD  condition_text' for a scope or exit node."""
    keyword = KEYWORD_LABEL.get(node.type, node.type.upper())
    first_line = get_text(node).splitlines()[0].strip().rstrip(':').rstrip('{').strip()
    lower = first_line.lower()
    kw_lower = keyword.lower()
    if lower.startswith(kw_lower):
        condition = first_line[len(kw_lower):].strip()
    else:
        condition = first_line
    if len(condition) > 80:
        condition = condition[:77] + '...'
    if condition:
        return f'{keyword}  {condition}'
    return keyword


def _make_item(
    node: Any,
    depth: int,
    get_text: Callable,
    is_exit: bool = False,
) -> Dict[str, Any]:
    return {
        'type': node.type,
        'keyword': KEYWORD_LABEL.get(node.type, node.type.upper()),
        'label': _node_label(node, get_text),
        'line_start': node.start_point[0] + 1,
        'line_end': node.end_point[0] + 1,
        'depth': depth,
        'is_exit': is_exit,
    }


# ---------------------------------------------------------------------------
# Feature 1: element_outline
# ---------------------------------------------------------------------------

def element_outline(
    func_node: Any,
    get_text: Callable,
    max_depth: int = 3,
) -> List[Dict[str, Any]]:
    """Return a flat list of outline items for a function's control-flow skeleton."""
    items: List[Dict[str, Any]] = []
    _collect_outline(func_node, depth=1, items=items, get_text=get_text, max_depth=max_depth)
    return items


def _collect_outline(
    node: Any,
    depth: int,
    items: List[Dict[str, Any]],
    get_text: Callable,
    max_depth: int,
) -> None:
    """Walk node's children, appending scope/exit items at the given depth."""
    for child in node.children:
        ctype = child.type
        if not child.is_named:
            continue
        if ctype in FUNCTION_TYPES:
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                _collect_scope_interior(child, depth, items, get_text, max_depth)
            continue
        if ctype in ALTERNATIVE_NODES:
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                _collect_outline(child, depth + 1, items, get_text, max_depth)
        elif ctype in SCOPE_NODES:
            items.append(_make_item(child, depth, get_text))
            if depth < max_depth:
                _collect_scope_interior(child, depth, items, get_text, max_depth)
        elif ctype in EXIT_NODES:
            items.append(_make_item(child, depth, get_text, is_exit=True))
        else:
            if depth <= max_depth:
                _collect_outline(child, depth, items, get_text, max_depth)


def _collect_scope_interior(
    scope_node: Any,
    scope_depth: int,
    items: List[Dict[str, Any]],
    get_text: Callable,
    max_depth: int,
) -> None:
    """Process the interior of a scope node."""
    for child in scope_node.children:
        ctype = child.type
        if not child.is_named:
            continue
        if ctype in FUNCTION_TYPES:
            items.append(_make_item(child, scope_depth + 1, get_text))
            if scope_depth + 1 < max_depth:
                _collect_scope_interior(child, scope_depth + 1, items, get_text, max_depth)
            continue
        if ctype in ALTERNATIVE_NODES:
            items.append(_make_item(child, scope_depth, get_text))
            if scope_depth < max_depth:
                _collect_outline(child, scope_depth + 1, items, get_text, max_depth)
        elif ctype in SCOPE_NODES:
            items.append(_make_item(child, scope_depth + 1, get_text))
            if scope_depth + 1 < max_depth:
                _collect_scope_interior(child, scope_depth + 1, items, get_text, max_depth)
        elif ctype in EXIT_NODES:
            items.append(_make_item(child, scope_depth + 1, get_text, is_exit=True))
        else:
            if scope_depth < max_depth:
                _collect_outline(child, scope_depth + 1, items, get_text, max_depth)


# ---------------------------------------------------------------------------
# Feature 2: scope_chain
# ---------------------------------------------------------------------------

def scope_chain(
    root_node: Any,
    line_no: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Return the ancestor scope chain for a specific line (outermost first)."""
    chain: List[Dict[str, Any]] = []
    _find_ancestors(root_node, line_no, get_text, chain, depth=0)
    return chain


def _find_ancestors(
    node: Any,
    line_no: int,
    get_text: Callable,
    chain: List[Dict[str, Any]],
    depth: int,
) -> None:
    """Recursively find scope nodes that contain line_no."""
    start = node.start_point[0] + 1
    end = node.end_point[0] + 1
    if not (start <= line_no <= end):
        return

    if node.is_named and (node.type in SCOPE_NODES or node.type in FUNCTION_TYPES):
        chain.append({
            'type': node.type,
            'keyword': KEYWORD_LABEL.get(node.type, node.type.upper()),
            'label': _node_label(node, get_text),
            'line_start': start,
            'line_end': end,
            'depth': depth,
        })
        depth += 1

    for child in node.children:
        _find_ancestors(child, line_no, get_text, chain, depth)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def render_outline(
    func_name: str,
    func_start: int,
    func_end: int,
    items: List[Dict[str, Any]],
    depth: int = 3,
) -> str:
    """Render an element_outline result as text."""
    lines = [f'DEF {func_name}  L{func_start}→L{func_end}']
    for item in items:
        if item['depth'] > depth:
            continue
        indent = '  ' * item['depth']
        lrange = f'L{item["line_start"]}→L{item["line_end"]}' if item['line_start'] != item['line_end'] else f'L{item["line_start"]}'
        lines.append(f'{indent}{item["label"]}  {lrange}')
    return '\n'.join(lines)


def render_scope_chain(line_no: int, chain: List[Dict[str, Any]], line_text: str = '') -> str:
    """Render a scope_chain result as text."""
    if not chain:
        suffix = f': {line_text}' if line_text else ' is at module/function top level (no enclosing scope blocks)'
        return f'▶ L{line_no}{suffix}'

    MAX_CHAIN = 8
    lines = []
    truncated = len(chain) > MAX_CHAIN
    if truncated:
        hidden = len(chain) - MAX_CHAIN
        outer = chain[:2]
        inner = chain[-(MAX_CHAIN - 2):]
        for item in outer:
            indent = '  ' * item['depth']
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
            lines.append(f'{indent}{item["keyword"]:<8}{lrange:<16}{item["label"]}')
        lines.append(f'  ... ({hidden} more levels)')
        for item in inner:
            indent = '  ' * item['depth']
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
            lines.append(f'{indent}{item["keyword"]:<8}{lrange:<16}{item["label"]}')
    else:
        for item in chain:
            indent = '  ' * item['depth']
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
            lines.append(f'{indent}{item["keyword"]:<8}{lrange:<16}{item["label"]}')

    innermost_depth = chain[-1]['depth'] + 1
    indent = '  ' * innermost_depth
    lines.append('')
    if line_text:
        lines.append(f'{indent}▶ L{line_no}: {line_text}')
    else:
        lines.append(f'{indent}▶ L{line_no} is here')
    return '\n'.join(lines)


def render_branchmap(
    items: List[Dict[str, Any]],
    from_line: int,
    to_line: int,
) -> str:
    """Render filtered element_outline items as a branch/exception map."""
    if not items:
        return f'No branch nodes found in L{from_line}→L{to_line}'
    lines: List[str] = []
    for item in items:
        indent = '  ' * item['depth']
        if item['line_start'] != item['line_end']:
            lrange = f'L{item["line_start"]}→L{item["line_end"]}'
        else:
            lrange = f'L{item["line_start"]}'
        lines.append(f'{indent}{item["label"]}  {lrange}')
    return '\n'.join(lines)
