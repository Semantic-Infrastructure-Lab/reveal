"""Renderer for markdown:// query results."""

from typing import Any, Dict

from reveal.utils import safe_json_dumps


def render_markdown_query(data: Dict[str, Any], output_format: str,
                          single_file: bool = False) -> None:
    """Render markdown query results.

    Args:
        data: Query results from MarkdownQueryAdapter
        output_format: Output format (text, json, grep)
        single_file: True if rendering a single file's details
    """
    if output_format == 'json':
        print(safe_json_dumps(data))
        return

    if single_file:
        _render_single_file(data, output_format)
    else:
        _render_query_results(data, output_format)


def _render_single_file(data: Dict[str, Any], output_format: str) -> None:
    """Render single file frontmatter details.

    Args:
        data: File data with frontmatter
        output_format: Output format
    """
    if output_format == 'grep':
        path = data.get('path', '?')
        if data.get('frontmatter'):
            for key, value in data['frontmatter'].items():
                print(f"{path}:{key}:{value}")
        else:
            print(f"{path}:NO_FRONTMATTER")
        return

    # Text format
    print(f"File: {data.get('path', '?')}")
    print()

    if data.get('frontmatter'):
        print("Front Matter:")
        for key, value in data['frontmatter'].items():
            if isinstance(value, list):
                print(f"  {key}:")
                for item in value:
                    print(f"    - {item}")
            else:
                print(f"  {key}: {value}")
    else:
        print("No front matter found")


def _render_result_row(result: Dict[str, Any]) -> None:
    """Print a single markdown query result row with tags/topics."""
    path = result.get('relative_path', result.get('path', '?'))
    parts = [path]
    if result.get('type'):
        parts.append(f"[{result['type']}]")
    if result.get('status'):
        parts.append(f"({result['status']})")
    if result.get('title'):
        parts.append(f"- {result['title']}")
    print("  " + " ".join(parts))

    for field in ['tags', 'topics']:
        if field in result:
            values = result[field]
            if isinstance(values, list):
                print(f"      {field}: {', '.join(str(v) for v in values)}")
            else:
                print(f"      {field}: {values}")


def _render_query_results(data: Dict[str, Any], output_format: str) -> None:
    """Render query results."""
    results = data.get('results', [])

    if output_format == 'grep':
        for result in results:
            print(result.get('relative_path', result.get('path', '?')))
        return

    print(f"Markdown Query: {data.get('base_path', '.')}/")
    if data.get('query'):
        print(f"Filter: ?{data['query']}")
    print(f"Matched: {data.get('matched_files', 0)} of {data.get('total_files', 0)} files")
    print()

    if not results:
        print("No matching files found.")
        return

    for result in results:
        _render_result_row(result)
