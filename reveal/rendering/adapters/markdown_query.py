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

    if data.get('type') == 'markdown_link_graph':
        _render_link_graph(data, output_format)
    elif data.get('type') == 'markdown_aggregate':
        _render_aggregate(data, output_format)
    elif single_file:
        _render_single_file(data, output_format)
    else:
        _render_query_results(data, output_format)


def _render_link_graph(data: Dict[str, Any], output_format: str) -> None:
    """Render markdown cross-file link graph."""
    if output_format == 'grep':
        for node in data.get('nodes', []):
            for target in node['links_to']:
                print(f"{node['file']}\t{target}")
        return

    total = data.get('total_files', 0)
    edges = data.get('total_edges', 0)
    isolated = data.get('isolated', [])
    source = data.get('source', '')
    print(f'Link graph: {source}')
    print(f'{total} files  |  {edges} edges  |  {len(isolated)} isolated')

    nodes = [n for n in data.get('nodes', []) if n['links_to'] or n['linked_by']]
    if nodes:
        print()
        for node in nodes:
            linked_by_count = len(node['linked_by'])
            linked_by_str = f'  (linked by {linked_by_count})' if linked_by_count else ''
            print(f'{node["file"]}{linked_by_str}')
            for target in node['links_to']:
                print(f'  → {target}')

    if isolated:
        print()
        print(f'Isolated ({len(isolated)} files with no links):')
        for f in isolated:
            print(f'  {f}')


def _render_aggregate(data: Dict[str, Any], output_format: str) -> None:
    """Render frontmatter field frequency table."""
    if output_format == 'grep':
        for entry in data.get('aggregate', []):
            print(f"{entry['value']}\t{entry['count']}")
        return

    field = data.get('field', '?')
    source = data.get('source', '.')
    matched = data.get('matched_files', 0)
    total = data.get('total_files', 0)
    missing = data.get('files_missing_field', 0)

    print(f"Aggregate: {field}")
    print(f"Source: {source}/")
    print(f"Files: {matched} of {total} matched")
    if missing:
        print(f"Missing field: {missing} files")
    print()

    aggregate = data.get('aggregate', [])
    if not aggregate:
        print(f"No values found for field '{field}'.")
        return

    max_count = aggregate[0]['count'] if aggregate else 1
    bar_width = 30
    for entry in aggregate:
        val = str(entry['value'])
        cnt = entry['count']
        filled = int(bar_width * cnt / max_count) if max_count else 0
        bar = '█' * filled
        print(f"  {val:<24} {cnt:>5}  {bar}")


def _print_frontmatter_item(key: str, value: Any) -> None:
    """Print a single frontmatter key/value, expanding lists."""
    if isinstance(value, list):
        print(f"  {key}:")
        for item in value:
            print(f"    - {item}")
    else:
        print(f"  {key}: {value}")


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
            _print_frontmatter_item(key, value)
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

    # Append extra_fields as key=value pairs on the same line
    extra_fields = result.get('_extra_fields') or []
    _INLINE_FIELDS = {'type', 'status', 'title', 'tags', 'topics'}
    for field in extra_fields:
        if field in _INLINE_FIELDS:
            continue
        value = result.get(field)
        if value is not None:
            if isinstance(value, list):
                parts.append(f"{field}={','.join(str(v) for v in value)}")
            else:
                parts.append(f"{field}={value}")

    print("  " + " ".join(parts))

    for field in ['tags', 'topics']:
        if field in result and field not in extra_fields:
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

    for result in results:
        _render_result_row(result)

    # Show hints (e.g. low match rate front matter warning)
    hints = data.get('hints', [])
    if hints:
        print()
        for hint in hints:
            print(f"ℹ️  {hint['message']}")
