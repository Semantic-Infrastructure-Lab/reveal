"""Cross-function varflow: --varflow VAR --cross-calls (BACK-220).

Extends --varflow to follow a variable across function call boundaries within
the same module. When the tracked variable is passed to a callee defined in the
same file, recursively runs var_flow in that callee with the mapped param name.

Output: list of frame dicts
    {
        'depth': int,            # 0 = root function
        'function': str,         # function name
        'var': str,              # variable name at this level
        'from_line': int,
        'to_line': int,
        'events': List[Dict],    # var_flow events
        'callouts': List[Dict],  # {callee: str, var: str, line: int} — where we followed
    }

Usage (from file_handler):
    frames = cross_var_flow(analyzer, func_node, var_name, from_line, to_line,
                            get_text, max_depth=3)
    print(render_cross_var_flow(var_name, frames, content_lines))
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set

from .nav_varflow import var_flow, render_var_flow

_MAX_DEPTH = 3


# ─────────────────────────── public entry point ──────────────────────────────

def cross_var_flow(
    analyzer: Any,
    func_node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
    max_depth: int = _MAX_DEPTH,
) -> List[Dict[str, Any]]:
    """Run var_flow and follow into callees defined in the same module.

    Returns a list of frame dicts in DFS order (root first, then callees).
    """
    frames: List[Dict[str, Any]] = []
    visited: Set[tuple] = set()  # (func_name, var_name) to prevent loops
    _collect_frames(analyzer, func_node, var_name, from_line, to_line,
                    get_text, depth=0, max_depth=max_depth,
                    frames=frames, visited=visited)
    return frames


def _collect_frames(
    analyzer: Any,
    func_node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
    depth: int,
    max_depth: int,
    frames: List[Dict[str, Any]],
    visited: Set[tuple],
) -> None:
    func_name = _get_func_name(func_node, get_text)
    key = (func_name, var_name)
    if key in visited:
        return
    visited.add(key)

    events = var_flow(func_node, var_name, from_line, to_line, get_text)

    # Find where var_name is passed into local callees
    callouts = _find_callouts(func_node, var_name, from_line, to_line, get_text)

    frames.append({
        'depth': depth,
        'function': func_name,
        'var': var_name,
        'from_line': from_line,
        'to_line': to_line,
        'events': events,
        'callouts': callouts,
    })

    if depth >= max_depth:
        return

    # Recurse into callees
    for callout in callouts:
        callee_name = callout['callee']
        callee_node = _find_function_node(analyzer, callee_name)
        if callee_node is None:
            continue
        # Resolve calling-var to callee's actual param name before recursing
        kw_name = callout['param'] if callout['arg_pos'] == -1 else ''
        mapped_param = _resolve_param_name(callee_node, callout['arg_pos'], get_text, kw_name)
        callout['param'] = mapped_param  # update so renderer sees resolved name
        callee_start = callee_node.start_point[0] + 1
        callee_end = callee_node.end_point[0] + 1
        _collect_frames(
            analyzer, callee_node, mapped_param,
            callee_start, callee_end, get_text,
            depth + 1, max_depth, frames, visited,
        )


# ─────────────────────────── callout detection ───────────────────────────────

def _find_callouts(
    func_node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
) -> List[Dict[str, Any]]:
    """Find call sites where var_name is passed as an argument.

    Returns list of {callee: str, param: str, arg_pos: int, line: int}.
    Starts from the function body so the function_definition guard in
    _scan_for_callouts only fires for actual nested function definitions.
    """
    callouts: List[Dict[str, Any]] = []
    body = func_node.child_by_field_name('body')
    if body:
        _scan_for_callouts(body, var_name, from_line, to_line, get_text, callouts)
    return callouts


def _scan_for_callouts(
    node: Any,
    var_name: str,
    from_line: int,
    to_line: int,
    get_text: Callable,
    callouts: List[Dict[str, Any]],
) -> None:
    ntype = node.type
    line = node.start_point[0] + 1

    if line > to_line or node.end_point[0] + 1 < from_line:
        return

    if ntype in ('function_definition', 'async_function_definition'):
        # Don't recurse into nested function definitions
        return

    if ntype == 'call':
        func_part = node.child_by_field_name('function')
        args_part = node.child_by_field_name('arguments')
        if func_part and args_part:
            callee_name = _extract_callee_name(func_part, get_text)
            if callee_name:
                _check_args_for_var(callee_name, args_part, var_name, line, get_text, callouts)
        # Still recurse into arguments (could have nested calls)
        for child in node.children:
            _scan_for_callouts(child, var_name, from_line, to_line, get_text, callouts)
        return

    for child in node.children:
        _scan_for_callouts(child, var_name, from_line, to_line, get_text, callouts)


def _extract_callee_name(func_node: Any, get_text: Callable) -> Optional[str]:
    if func_node.type == 'identifier':
        name = get_text(func_node)
        return name if name else None
    if func_node.type == 'attribute':
        attr = func_node.child_by_field_name('attribute')
        return get_text(attr) if attr else None
    return None


def _check_args_for_var(
    callee_name: str,
    args_node: Any,
    var_name: str,
    line: int,
    get_text: Callable,
    callouts: List[Dict[str, Any]],
) -> None:
    arg_pos = 0
    for child in args_node.children:
        if child.type in (',', '(', ')'):
            continue
        if child.type == 'keyword_argument':
            # keyword_argument: name=value
            key_node = child.child_by_field_name('name')
            val_node = child.child_by_field_name('value')
            if val_node and _node_is_var(val_node, var_name, get_text):
                kw_name = get_text(key_node) if key_node else ''
                callouts.append({
                    'callee': callee_name,
                    'param': kw_name or var_name,
                    'arg_pos': -1,  # keyword
                    'line': line,
                })
        else:
            if _node_is_var(child, var_name, get_text):
                callouts.append({
                    'callee': callee_name,
                    'param': var_name,  # resolved to actual param name later
                    'arg_pos': arg_pos,
                    'line': line,
                })
            arg_pos += 1


def _node_is_var(node: Any, var_name: str, get_text: Callable) -> bool:
    return node.type == 'identifier' and get_text(node) == var_name


# ─────────────────────────── callee lookup ───────────────────────────────────

def _find_function_node(analyzer: Any, func_name: str) -> Optional[Any]:
    """Find a function definition node by name in the analyzer's AST."""
    from ...treesitter import ELEMENT_TYPE_MAP
    for node_type in ELEMENT_TYPE_MAP.get('function', []):
        for node in analyzer._find_nodes_by_type(node_type):
            if analyzer._get_node_name(node) == func_name:
                return node
    return None


def _get_func_name(func_node: Any, get_text: Callable) -> str:
    name_node = func_node.child_by_field_name('name')
    return get_text(name_node) if name_node else '?'


def _resolve_param_name(callee_node: Any, arg_pos: int, get_text: Callable, kw_name: str) -> str:
    """Given arg_pos (0-based) or kw_name, resolve to the callee's param name."""
    if kw_name:
        return kw_name
    params = callee_node.child_by_field_name('parameters')
    if not params:
        return str(arg_pos)
    pos = 0
    for child in params.children:
        if child.type in (',', '(', ')'):
            continue
        if child.type == 'identifier':
            name = get_text(child)
            if name in ('self', 'cls'):
                continue
            if pos == arg_pos:
                return name
            pos += 1
        elif child.type in ('typed_parameter', 'default_parameter', 'typed_default_parameter'):
            ident = None
            for sub in child.children:
                if sub.type == 'identifier':
                    ident = sub
                    break
            if ident:
                name = get_text(ident)
                if name in ('self', 'cls'):
                    continue
                if pos == arg_pos:
                    return name
                pos += 1
    return str(arg_pos)


# ─────────────────────────── renderer ────────────────────────────────────────

def render_cross_var_flow(
    var_name: str,
    frames: List[Dict[str, Any]],
    content_lines: List[str],
) -> str:
    if not frames:
        return f'No frames for {var_name}'

    lines = []
    for frame in frames:
        depth = frame['depth']
        func_name = frame['function']
        frame_var = frame['var']
        events = frame['events']
        indent = '  ' * depth

        if depth == 0:
            lines.append(f"─── {func_name}  var: {frame_var} ───")
        else:
            lines.append(f"\n{indent}↳ {func_name}({frame_var})  [from caller above]")

        if events:
            rendered = render_var_flow(frame_var, events, content_lines)
            for rline in rendered.splitlines():
                lines.append(f"{indent}  {rline}" if depth > 0 else f"  {rline}")
        else:
            lines.append(f"{indent}  (no {frame_var} events in {func_name})")

    return '\n'.join(lines)
