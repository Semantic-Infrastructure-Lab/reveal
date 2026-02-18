"""Renderer for ast:// code query adapter."""

import sys
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
            name = elem.get('name', '')
            line = elem.get('line', 0)
            line_count = elem.get('line_count', 0)
            complexity = elem.get('complexity')

            # Format output - path already shown in "File:" header above
            if complexity:
                print(f"  :{line:>4}  {name} [{line_count} lines, complexity: {complexity}]")
            else:
                print(f"  :{line:>4}  {name} [{line_count} lines]")

        print()


def _suggest_filter_correction(query: str) -> None:
    """If the query looks like a known shorthand, suggest the correct syntax."""
    if not query or query == 'none':
        return
    import re
    # format_query produces "field op value" — bare existence filters look like "field??"
    fields = re.findall(r'^(\w+)', query)
    for field in fields:
        correction = _FILTER_SHORTHANDS.get(field.lower())
        if correction:
            print()
            print(f"Hint: '{field}' is not a valid filter. Did you mean '{correction}'?")
            print(f"  reveal 'ast://path/{correction}'")
            return
