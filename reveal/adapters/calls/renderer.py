"""Renderer for calls:// adapter output."""

from typing import Any, Dict

from reveal.utils import safe_json_dumps


def render_calls_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render calls:// adapter results.

    Args:
        data: Result dict from CallsAdapter.get_structure()
        output_format: 'text', 'json', or 'dot'
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    if data.get('query') == 'callees':
        _render_callees_text(data)
        return

    if data.get('query') == 'rank_callers':
        _render_ranking_text(data)
        return

    if output_format == 'dot':
        _render_dot(data)
        return

    _render_text(data)


def _render_text(data: Dict[str, Any]) -> None:
    if 'error' in data and 'target' not in data:
        print(f"Error: {data['error']}", file=__import__('sys').stderr)
        if 'example' in data:
            print(f"Example: {data['example']}", file=__import__('sys').stderr)
        return
    target = data.get('target', '?')
    depth = data.get('depth', 1)
    total = data.get('total_callers', 0)
    levels = data.get('levels', [])
    path = data.get('path', '.')

    print(f"Callers of: {target}")
    print(f"Project:    {path}")
    if depth > 1:
        print(f"Depth:      {depth}")
    print(f"Total:      {total}")
    print()

    if not levels:
        print(f"  No callers found for '{target}'.")
        return

    for lvl in levels:
        level_num = lvl['level']
        callers = lvl['callers']
        if depth > 1:
            label = "Direct callers" if level_num == 1 else f"Level {level_num} callers"
            print(f"{label}:")
        for rec in callers:
            file_path = rec['file']  # relative path from project root
            caller = rec['caller']
            line = rec['line']
            call_expr = rec.get('call_expr', rec.get('callee', target))
            print(f"  {file_path}:{line}  {caller}  (calls {call_expr})")
        if depth > 1:
            print()


def _render_callees_text(data: Dict[str, Any]) -> None:
    target = data.get('target', '?')
    total = data.get('total_calls', 0)
    matches = data.get('matches', [])
    path = data.get('path', '.')
    builtins_hidden = data.get('_builtins_hidden', 0)

    print(f"Callees of: {target}")
    print(f"Project:    {path}")
    print(f"Total:      {total} call(s) across {len(matches)} definition(s)")
    if builtins_hidden:
        print(f"            ({builtins_hidden} builtin(s) hidden — use ?builtins=true to include)")
    print()

    if not matches:
        print(f"  No definition of '{target}' found.")
        return

    for match in matches:
        file_path = match['file']
        line = match['line']
        calls = match.get('calls', [])
        print(f"  {file_path}:{line}  {target}")
        if calls:
            for callee in calls:
                print(f"    → {callee}")
        else:
            print(f"    (no calls detected)")
        print()


def _render_ranking_text(data: Dict[str, Any]) -> None:
    """Render rank=callers output — most-called functions sorted by in-degree."""
    path = data.get('path', '.')
    top = data.get('top', 10)
    total = data.get('total_unique_callees', 0)
    entries = data.get('entries', [])

    print(f"Most-called functions: {path}")
    print(f"Ranking by:            caller count (in-degree)")
    print(f"Showing:               top {top} of {total} unique callees")
    print()

    if not entries:
        print("  No call data found. Does the path contain Python files with function calls?")
        return

    for entry in entries:
        name = entry['name']
        count = entry['caller_count']
        callers = entry.get('callers', [])
        plural = 'caller' if count == 1 else 'callers'
        print(f"  {name}  ({count} {plural})")
        for rec in callers[:5]:  # show up to 5 callers per entry
            file_path = rec['file']
            caller = rec['caller']
            line = rec['line']
            print(f"    {file_path}:{line}  {caller}")
        if len(callers) > 5:
            print(f"    … and {len(callers) - 5} more")
        print()


def _render_dot(data: Dict[str, Any]) -> None:
    """Render call graph in Graphviz dot format."""
    target = data.get('target', '?')
    levels = data.get('levels', [])

    print("digraph calls {")
    print('  rankdir=LR;')
    print(f'  node [shape=box fontname="monospace"];')

    edges = set()
    for lvl in levels:
        for rec in lvl['callers']:
            caller = rec['caller']
            callee = rec.get('callee', target)
            edge = (caller, callee)
            if edge not in edges:
                edges.add(edge)
                print(f'  "{caller}" -> "{callee}";')

    print("}")
