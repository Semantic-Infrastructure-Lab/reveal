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

    if output_format == 'dot':
        _render_dot(data)
        return

    _render_text(data)


def _render_text(data: Dict[str, Any]) -> None:
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

    print(f"Callees of: {target}")
    print(f"Project:    {path}")
    print(f"Total:      {total} call(s) across {len(matches)} definition(s)")
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
