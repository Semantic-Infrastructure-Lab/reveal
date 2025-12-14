"""Element extraction display."""

import sys

from reveal.base import FileAnalyzer
from reveal.utils import safe_json_dumps, get_file_type_from_analyzer, print_breadcrumbs


def extract_element(analyzer: FileAnalyzer, element: str, output_format: str):
    """Extract a specific element.

    Args:
        analyzer: File analyzer
        element: Element name to extract
        output_format: Output format
    """
    # Try common element types
    for element_type in ['function', 'class', 'struct', 'section', 'server', 'location', 'upstream']:
        result = analyzer.extract_element(element_type, element)
        if result:
            break
    else:
        # Not found
        print(f"Error: Element '{element}' not found in {analyzer.path}", file=sys.stderr)
        sys.exit(1)

    # Format output
    if output_format == 'json':
        print(safe_json_dumps(result))
        return

    path = analyzer.path
    line_start = result.get('line_start', 1)
    line_end = result.get('line_end', line_start)
    source = result.get('source', '')
    name = result.get('name', element)

    # Header
    print(f"{path}:{line_start}-{line_end} | {name}\n")

    # Source with line numbers
    if output_format == 'grep':
        # Grep format: filename:linenum:content
        for i, line in enumerate(source.split('\n')):
            line_num = line_start + i
            print(f"{path}:{line_num}:{line}")
    else:
        # Human-readable format
        formatted = analyzer.format_with_lines(source, line_start)
        print(formatted)

        # Navigation hints
        file_type = get_file_type_from_analyzer(analyzer)
        line_count = line_end - line_start + 1
        print_breadcrumbs('element', path, file_type=file_type,
                         element_name=name, line_count=line_count, line_start=line_start)
