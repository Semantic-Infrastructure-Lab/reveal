"""Renderer for ast:// code query adapter."""

from typing import Any, Dict

from reveal.utils import safe_json_dumps


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
        return

    # Group by file
    by_file = {}
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
