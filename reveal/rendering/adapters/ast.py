"""Renderer for ast:// code query adapter."""


from pathlib import Path
from typing import Any, Dict, List

from reveal.utils import safe_json_dumps

# Maps bare shorthand names users commonly try to the correct filter syntax
_FILTER_SHORTHANDS = {
    'functions': '?type=function',
    'function': '?type=function',
    'classes': '?type=class',
    'class': '?type=class',
    'methods': '?type=method',
    'method': '?type=method',
    'imports': '?type=import',
}

# All keys that ast:// actually understands
_KNOWN_FILTER_KEYS = {'type', 'name', 'complexity', 'size', 'lines', 'decorator', 'calls', 'callee_of'}


def render_ast_structure(data: Dict[str, Any], output_format: str) -> None:
    """Render AST query results.

    Args:
        data: AST query results from adapter
        output_format: Output format (text, json, grep)
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    # Text/grep format
    query = data.get('query', 'none')
    total_files = data.get('total_files', 0)
    total_results = data.get('total_results', 0)
    results = data.get('results', [])

    if output_format == 'grep':
        # grep format: file:line:name
        for result in results:
            file_path = result.get('file', '')
            line = result.get('line', 0)
            name = result.get('name', '')
            print(f"{file_path}:{line}:{name}")
        return

    # Text format
    print(f"AST Query: {data.get('path', '.')}")
    if query != 'none':
        print(f"Filter: {query}")
    print(f"Files scanned: {total_files}")
    print(f"Results: {total_results}")
    print()

    if not results:
        print("No matches found.")
        # Detect common shorthand filters and suggest corrections
        _suggest_filter_correction(query)
        return

    # show=calls → call graph view
    show_mode = data.get('show_mode')
    if show_mode == 'calls':
        _render_call_graph(data)
        return

    # Group by file
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        file_path = result.get('file', '')
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(result)

    # Render grouped results
    for file_path, elements in sorted(by_file.items()):
        print(f"File: {file_path}")
        for elem in elements:
            _render_ast_element(elem)
        print()


def _render_ast_element(elem: Dict[str, Any]) -> None:
    """Render a single AST element line."""
    name = elem.get('name', '')
    line = elem.get('line', 0)
    line_count = elem.get('line_count', 0)
    complexity = elem.get('complexity')
    if complexity:
        print(f"  :{line:>4}  {name} [{line_count} lines, complexity: {complexity}]")
    else:
        print(f"  :{line:>4}  {name} [{line_count} lines]")

    calls = elem.get('calls', [])
    called_by = elem.get('called_by', [])
    resolved_calls = elem.get('resolved_calls')
    if calls:
        if resolved_calls:
            # Show resolved info for entries that could be resolved
            resolved_map = {e['name']: e for e in resolved_calls if 'resolved_file' in e}
            parts = []
            for name in calls:
                if name in resolved_map:
                    e = resolved_map[name]
                    short_file = Path(e['resolved_file']).name
                    parts.append(f"{name} (→ {short_file}::{e['resolved_name']})")
                else:
                    parts.append(name)
            print(f"           calls:     {', '.join(parts)}")
        else:
            print(f"           calls:     {', '.join(calls)}")
    if called_by:
        print(f"           called by: {', '.join(called_by)}")


def _render_call_graph(data: Dict[str, Any]) -> None:
    """Render compact call graph view (show=calls)."""
    results = data.get('results', [])

    # Only show functions and methods — imports, classes, etc. have no call data
    callable_results = [
        e for e in results
        if e.get('category') in ('functions', 'methods')
    ]

    if not callable_results:
        print("No functions or methods found.")
        return

    # Group by file
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for elem in callable_results:
        fp = elem.get('file', '')
        by_file.setdefault(fp, []).append(elem)

    for file_path, elements in sorted(by_file.items()):
        print(f"Call Graph: {file_path}")
        print()
        for elem in elements:
            name = elem.get('name', '')
            calls = elem.get('calls', [])
            called_by = elem.get('called_by', [])
            print(f"{name}")
            if calls:
                print(f"  └─calls──▶ {', '.join(calls)}")
            if called_by:
                print(f"  ◀─called─  {', '.join(called_by)}")
            if not calls and not called_by:
                print(f"  (no calls or callers within this file)")
            print()
        print()


def _suggest_filter_correction(query: str) -> None:
    """Emit hints when the query contains known shorthands or unrecognized filter keys."""
    if not query or query == 'none':
        return
    import re
    # format_query produces "key op value" parts joined by " AND "
    # Extract the leading identifier from each part to get the field names used.
    parts = [p.strip() for p in query.split(' AND ')]
    fields = [m.group(1) for p in parts for m in [re.match(r'^(\w+)', p)] if m]

    for field in fields:
        correction = _FILTER_SHORTHANDS.get(field.lower())
        if correction:
            print()
            print(f"Hint: '{field}' is not a valid filter. Did you mean '{correction}'?")
            print(f"  reveal 'ast://path/{correction}'")
            return

    # Check for unknown keys not in any known set
    unknown = [f for f in fields if f.lower() not in _KNOWN_FILTER_KEYS and f.lower() not in _FILTER_SHORTHANDS]
    if unknown:
        valid = ', '.join(sorted(_KNOWN_FILTER_KEYS))
        print()
        for key in unknown:
            print(f"Hint: '{key}' is not a recognized filter key.")
        print(f"  Valid keys: {valid}")
        print(f"  Run `reveal help://ast` for filter reference.")
