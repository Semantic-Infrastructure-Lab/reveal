"""
Type-narrowing path display for a named variable within a function.

Walk a function body tracking how a variable's type-set changes as guards
fire. Starting type-set comes from the parameter annotation; isinstance(),
is None, is not None, assert forms, and else-by-exhaustion are all handled.

Usage: reveal file.py func_name --narrow x
"""

from __future__ import annotations

from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple


# ─────────────────────────── public API ──────────────────────────────────────

def collect_narrowing(
    func_node: Any,
    var_name: str,
    get_text: Callable,
) -> Optional[List[Dict[str, Any]]]:
    """Return type-narrowing events for var_name, or None if no annotation."""
    initial = _extract_param_types(func_node, var_name, get_text)
    if initial is None:
        return None

    events: List[Dict[str, Any]] = []
    body = _get_body(func_node)
    if body is None:
        return events

    entry_line = func_node.start_point[0] + 1
    events.append({
        'line': entry_line,
        'kind': 'ENTRY',
        'label': _fmt_types(initial),
        'type_set': initial,
        'depth': 0,
    })

    _walk_stmts(body, var_name, initial, 0, get_text, events)
    return events


def render_narrowing(
    var_name: str,
    events: Optional[List[Dict[str, Any]]],
    content_lines: List[str],
) -> str:
    if events is None:
        return f'No annotation for {var_name!r} — cannot narrow'
    if len(events) <= 1:
        return f'{var_name}  →  {_fmt_types(events[0]["type_set"] if events else frozenset())}\n(no narrowing guards found)'

    lines = []
    entry = events[0]
    lines.append(f'{var_name}  →  {_fmt_types(entry["type_set"])}')
    lines.append('')

    for ev in events[1:]:
        depth = ev['depth']
        indent = '  ' * depth
        kind = ev['kind']
        lineno = ev['line']
        type_str = _fmt_types(ev['type_set'])

        if kind == 'NARROW':
            lines.append(f'{indent}     ↓  {type_str}')
            continue

        snippet = content_lines[lineno - 1].strip() if lineno <= len(content_lines) else ''
        if len(snippet) > 58:
            snippet = snippet[:55] + '...'

        prefix = {
            'IF': 'if  ',
            'ELIF': 'elif',
            'ELSE': 'else',
            'ASSERT': 'asrt',
        }.get(kind, '    ')

        lines.append(f'{indent}L{lineno:<5} {prefix}  {snippet:<58}  → {type_str}')

    return '\n'.join(lines)


# ─────────────────────────── annotation parsing ──────────────────────────────

def _extract_param_types(
    func_node: Any, var_name: str, get_text: Callable
) -> Optional[FrozenSet[str]]:
    params = None
    for c in func_node.children:
        if c.type == 'parameters':
            params = c
            break
    if params is None:
        return None

    for child in params.children:
        if child.type == 'typed_parameter':
            name_node = next(
                (c for c in child.children if c.type == 'identifier'), None
            )
            if name_node is None or get_text(name_node) != var_name:
                continue
            type_node = next(
                (c for c in child.children if c.type == 'type'), None
            )
            if type_node is None:
                return None
            inner = type_node.children[0] if type_node.child_count == 1 else type_node
            return _parse_type_node(inner, get_text)
    return None


def _parse_type_node(node: Any, get_text: Callable) -> FrozenSet[str]:
    if node.type == 'type':
        inner = node.children[0] if node.child_count == 1 else node
        return _parse_type_node(inner, get_text)

    if node.type in ('identifier',):
        name = get_text(node)
        return frozenset({'None'} if name == 'None' else {name})

    if node.type == 'none':
        return frozenset({'None'})

    if node.type == 'generic_type':
        name = get_text(node.children[0])
        params = next((c for c in node.children if c.type == 'type_parameter'), None)
        if params is None:
            return frozenset({name})
        inner_types = _collect_type_params(params, get_text)
        if name == 'Optional':
            return inner_types | frozenset({'None'})
        if name == 'Union':
            return inner_types
        return frozenset({get_text(node)})

    if node.type == 'binary_operator':
        # X | Y syntax (PEP 604)
        result: FrozenSet[str] = frozenset()
        for child in node.children:
            if child.type != '|':
                result = result | _parse_type_node(child, get_text)
        return result

    return frozenset({get_text(node)})


def _collect_type_params(
    type_params_node: Any, get_text: Callable
) -> FrozenSet[str]:
    result: FrozenSet[str] = frozenset()
    for child in type_params_node.children:
        if child.type == 'type':
            result = result | _parse_type_node(child, get_text)
    return result


# ─────────────────────────── guard classification ────────────────────────────

def _classify_guard(
    cond_node: Any, var_name: str, get_text: Callable
) -> Optional[Dict[str, Any]]:
    """Classify a condition node as a type guard for var_name, or None."""
    node = cond_node
    negated = False

    if node.type == 'not_operator':
        negated = True
        node = next((c for c in node.children if c.type == 'call'), None)
        if node is None:
            return None

    if node.type == 'call':
        callee = node.children[0] if node.children else None
        if callee is None or callee.type != 'identifier':
            return None
        if get_text(callee) != 'isinstance':
            return None
        args = next((c for c in node.children if c.type == 'argument_list'), None)
        if args is None:
            return None
        arg_ids = [c for c in args.children if c.type == 'identifier']
        if len(arg_ids) < 2 or get_text(arg_ids[0]) != var_name:
            return None
        return {'kind': 'isinstance', 'type': get_text(arg_ids[1]), 'negated': negated}

    if node.type == 'comparison_operator' and not negated:
        children = node.children
        if len(children) < 3:
            return None
        subj = children[0]
        if subj.type != 'identifier' or get_text(subj) != var_name:
            return None
        op_type = children[1].type  # 'is' or 'is not'
        rhs = children[-1]
        if rhs.type != 'none':
            return None
        if op_type == 'is':
            return {'kind': 'is_none', 'negated': False}
        if op_type == 'is not':
            return {'kind': 'is_none', 'negated': True}

    return None


def _apply_guard(
    guard: Dict[str, Any], type_set: FrozenSet[str]
) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """Return (if_branch_types, else_branch_types) given a guard and current type_set."""
    if guard['kind'] == 'isinstance':
        g_type = guard['type']
        if guard['negated']:
            return type_set - {g_type}, type_set & {g_type}
        return type_set & {g_type}, type_set - {g_type}

    # is_none
    if guard['negated']:
        return type_set - {'None'}, type_set & {'None'}
    return type_set & {'None'}, type_set - {'None'}


# ─────────────────────────── statement walker ────────────────────────────────

def _walk_stmts(
    block_node: Any,
    var_name: str,
    type_set: FrozenSet[str],
    depth: int,
    get_text: Callable,
    events: List[Dict[str, Any]],
) -> FrozenSet[str]:
    """Walk statements in block_node; return exit type_set."""
    for stmt in block_node.children:
        if stmt.type == 'if_statement':
            type_set = _handle_if(stmt, var_name, type_set, depth, get_text, events)
        elif stmt.type == 'assert_statement':
            type_set = _handle_assert(stmt, var_name, type_set, depth, get_text, events)
    return type_set


def _handle_if(
    if_node: Any,
    var_name: str,
    type_set: FrozenSet[str],
    depth: int,
    get_text: Callable,
    events: List[Dict[str, Any]],
) -> FrozenSet[str]:
    """Handle an if_statement; return type_set after the if block."""
    cond = _get_if_condition(if_node)
    if cond is None:
        return type_set

    guard = _classify_guard(cond, var_name, get_text)
    if guard is None:
        # Not a guard on var_name — recurse into bodies unchanged
        for c in if_node.children:
            if c.type == 'block':
                _walk_stmts(c, var_name, type_set, depth + 1, get_text, events)
            elif c.type in ('elif_clause', 'else_clause'):
                body = next((x for x in c.children if x.type == 'block'), None)
                if body:
                    _walk_stmts(body, var_name, type_set, depth + 1, get_text, events)
        return type_set

    if_types, else_types = _apply_guard(guard, type_set)
    if_line = if_node.start_point[0] + 1

    events.append({
        'line': if_line,
        'kind': 'IF',
        'label': get_text(cond),
        'type_set': if_types,
        'depth': depth,
    })

    if_body = next((c for c in if_node.children if c.type == 'block'), None)
    if_exits = False
    if if_body:
        _walk_stmts(if_body, var_name, if_types, depth + 1, get_text, events)
        if_exits = _block_always_exits(if_body)

    alternatives = [c for c in if_node.children if c.type in ('elif_clause', 'else_clause')]

    if not alternatives:
        if if_exits:
            after = else_types
            events.append({
                'line': if_node.end_point[0] + 2,
                'kind': 'NARROW',
                'label': '',
                'type_set': after,
                'depth': depth,
            })
            return after
        return type_set

    # Walk elif/else chain carrying the "remainder" type-set forward
    remainder = else_types
    after = type_set

    for alt in alternatives:
        alt_line = alt.start_point[0] + 1
        alt_body = next((c for c in alt.children if c.type == 'block'), None)

        if alt.type == 'else_clause':
            events.append({
                'line': alt_line,
                'kind': 'ELSE',
                'label': 'else:',
                'type_set': remainder,
                'depth': depth,
            })
            if alt_body:
                _walk_stmts(alt_body, var_name, remainder, depth + 1, get_text, events)
                alt_exits = _block_always_exits(alt_body)
                if if_exits and alt_exits:
                    after = frozenset()
                elif if_exits:
                    after = remainder
                elif alt_exits:
                    after = if_types
                else:
                    after = type_set

        elif alt.type == 'elif_clause':
            elif_cond = _get_elif_condition(alt)
            elif_guard = _classify_guard(elif_cond, var_name, get_text) if elif_cond else None

            if elif_guard:
                elif_if, elif_else = _apply_guard(elif_guard, remainder)
                events.append({
                    'line': alt_line,
                    'kind': 'ELIF',
                    'label': get_text(elif_cond),
                    'type_set': elif_if,
                    'depth': depth,
                })
                if alt_body:
                    _walk_stmts(alt_body, var_name, elif_if, depth + 1, get_text, events)
                remainder = elif_else
            else:
                events.append({
                    'line': alt_line,
                    'kind': 'ELIF',
                    'label': get_text(elif_cond) if elif_cond else 'elif ...',
                    'type_set': remainder,
                    'depth': depth,
                })
                if alt_body:
                    _walk_stmts(alt_body, var_name, remainder, depth + 1, get_text, events)

    return after


def _handle_assert(
    assert_node: Any,
    var_name: str,
    type_set: FrozenSet[str],
    depth: int,
    get_text: Callable,
    events: List[Dict[str, Any]],
) -> FrozenSet[str]:
    """Handle an assert_statement; narrow type_set if it's a guard."""
    cond = next(
        (c for c in assert_node.children if c.type not in ('assert', ',', 'comment')),
        None,
    )
    if cond is None:
        return type_set

    guard = _classify_guard(cond, var_name, get_text)
    if guard is None:
        return type_set

    if_types, _ = _apply_guard(guard, type_set)
    events.append({
        'line': assert_node.start_point[0] + 1,
        'kind': 'ASSERT',
        'label': get_text(assert_node),
        'type_set': if_types,
        'depth': depth,
    })
    return if_types


# ─────────────────────────── helpers ─────────────────────────────────────────

def _get_body(func_node: Any) -> Optional[Any]:
    return next((c for c in func_node.children if c.type == 'block'), None)


def _get_if_condition(if_node: Any) -> Optional[Any]:
    skip = {'if', ':', 'block', 'elif_clause', 'else_clause', 'comment'}
    return next((c for c in if_node.children if c.type not in skip), None)


def _get_elif_condition(elif_node: Any) -> Optional[Any]:
    skip = {'elif', ':', 'block', 'comment'}
    return next((c for c in elif_node.children if c.type not in skip), None)


def _block_always_exits(block_node: Any) -> bool:
    stmts = [
        c for c in block_node.children
        if c.type not in ('comment', 'newline', 'indent', 'dedent')
    ]
    return bool(stmts) and stmts[-1].type in ('return_statement', 'raise_statement')


def _fmt_types(type_set: FrozenSet[str]) -> str:
    if not type_set:
        return '{}'
    return '{' + ', '.join(sorted(type_set)) + '}'
