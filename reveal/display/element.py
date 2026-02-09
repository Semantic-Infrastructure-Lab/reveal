"""Element extraction display."""

import sys

from reveal.base import FileAnalyzer
from reveal.treesitter import (
    ELEMENT_TYPE_MAP, PARENT_NODE_TYPES, CHILD_NODE_TYPES, ALL_ELEMENT_NODE_TYPES
)
from reveal.utils import safe_json_dumps, get_file_type_from_analyzer, print_breadcrumbs


def _parse_element_syntax(element: str):
    """Parse element syntax to determine extraction type.

    Args:
        element: Element string to parse

    Returns:
        Dict with 'type' and parsed values:
        - ordinal: {'type': 'ordinal', 'ordinal': int, 'element_type': str or None}
        - line: {'type': 'line', 'start_line': int, 'end_line': int or None}
        - hierarchical: {'type': 'hierarchical'}
        - name: {'type': 'name'} (default)
    """
    import re

    # Check for @N ordinal extraction syntax (e.g., "@3" or "function:3")
    ordinal_match = re.match(r'^@(\d+)$', element)
    typed_ordinal_match = re.match(r'^(\w+):(\d+)$', element)
    if ordinal_match or typed_ordinal_match:
        if ordinal_match:
            return {
                'type': 'ordinal',
                'ordinal': int(ordinal_match.group(1)),
                'element_type': None
            }
        else:
            return {
                'type': 'ordinal',
                'ordinal': int(typed_ordinal_match.group(2)),
                'element_type': typed_ordinal_match.group(1)
            }

    # Check for :LINE extraction syntax (e.g., ":73" or ":73-91")
    line_match = re.match(r'^:(\d+)(?:-(\d+))?$', element)
    if line_match:
        return {
            'type': 'line',
            'start_line': int(line_match.group(1)),
            'end_line': int(line_match.group(2)) if line_match.group(2) else None
        }

    # Check for hierarchical extraction (Class.method syntax)
    if '.' in element:
        return {'type': 'hierarchical'}

    # Default: name-based extraction
    return {'type': 'name'}


def _extract_by_syntax(analyzer, element: str, syntax: dict):
    """Extract element based on parsed syntax.

    Args:
        analyzer: File analyzer instance
        element: Original element string
        syntax: Parsed syntax dict from _parse_element_syntax

    Returns:
        Element dict or None if not found
    """
    syntax_type = syntax['type']

    if syntax_type == 'ordinal':
        return _extract_ordinal_element(analyzer, syntax['ordinal'], syntax['element_type'])

    elif syntax_type == 'line':
        if syntax['end_line']:
            return _extract_line_range(analyzer, syntax['start_line'], syntax['end_line'])
        else:
            return _extract_element_at_line(analyzer, syntax['start_line'])

    elif syntax_type == 'hierarchical':
        from ..treesitter import TreeSitterAnalyzer
        if isinstance(analyzer, TreeSitterAnalyzer) and analyzer.tree:
            return _extract_hierarchical_element(analyzer, element)
        return None

    else:  # name-based extraction
        return _extract_by_name(analyzer, element)


def _extract_by_name(analyzer, element: str):
    """Extract element by name using tree-sitter or grep.

    Args:
        analyzer: File analyzer instance
        element: Element name to find

    Returns:
        Element dict or None if not found
    """
    from ..treesitter import TreeSitterAnalyzer

    # Try tree-sitter first if available
    if isinstance(analyzer, TreeSitterAnalyzer) and analyzer.tree:
        result = _try_treesitter_extraction(analyzer, element)
        if result:
            return result

    # Fallback to grep-based extraction
    return _try_grep_extraction(analyzer, element)


def _try_treesitter_extraction(analyzer, element: str):
    """Try extracting element using tree-sitter.

    Args:
        analyzer: TreeSitterAnalyzer instance
        element: Element name to find

    Returns:
        Element dict or None if not found
    """
    for element_type in ['class', 'function', 'struct', 'section', 'server', 'location', 'upstream']:
        node_types = ELEMENT_TYPE_MAP.get(element_type, [element_type])

        for node_type in node_types:
            nodes = analyzer._find_nodes_by_type(node_type)
            for node in nodes:
                node_name = analyzer._get_node_name(node)
                if node_name == element:
                    return {
                        'name': element,
                        'line_start': node.start_point[0] + 1,
                        'line_end': node.end_point[0] + 1,
                        'source': analyzer._get_node_text(node),
                    }
    return None


def _try_grep_extraction(analyzer, element: str):
    """Try extracting element using grep fallback.

    Args:
        analyzer: File analyzer instance
        element: Element name to find

    Returns:
        Element dict or None if not found
    """
    for element_type in ['function', 'class', 'struct', 'section', 'server', 'location', 'upstream']:
        result = analyzer.extract_element(element_type, element)
        if result:
            return result
    return None


def _handle_extraction_error(analyzer, element: str, syntax: dict):
    """Print appropriate error message based on extraction type.

    Args:
        analyzer: File analyzer instance
        element: Element string that failed
        syntax: Parsed syntax dict
    """
    syntax_type = syntax['type']

    if syntax_type == 'ordinal':
        element_type = syntax['element_type']
        ordinal = syntax['ordinal']
        if element_type:
            print(f"Error: No {element_type} #{ordinal} found in {analyzer.path}", file=sys.stderr)
        else:
            print(f"Error: No element #{ordinal} found in {analyzer.path}", file=sys.stderr)

    elif syntax_type == 'line':
        target_line = syntax['start_line']
        print(f"Error: No element found at line {target_line} in {analyzer.path}", file=sys.stderr)

    elif syntax_type == 'hierarchical':
        parent, child = element.rsplit('.', 1)
        print(f"Error: Element '{element}' not found in {analyzer.path}", file=sys.stderr)
        print(f"Hint: Looking for '{child}' within '{parent}'", file=sys.stderr)

    else:
        print(f"Error: Element '{element}' not found in {analyzer.path}", file=sys.stderr)


def extract_element(analyzer: FileAnalyzer, element: str, output_format: str, config=None):
    """Extract a specific element.

    Args:
        analyzer: File analyzer
        element: Element name to extract (supports "Class.method" hierarchy, ":LINE" syntax)
        output_format: Output format
        config: Optional RevealConfig instance
    """
    # Parse element syntax to determine extraction strategy
    syntax = _parse_element_syntax(element)

    # Route to appropriate extraction handler
    result = _extract_by_syntax(analyzer, element, syntax)

    # Handle extraction failure
    if not result:
        _handle_extraction_error(analyzer, element, syntax)
        sys.exit(1)

    # Output result in requested format
    _output_result(analyzer, result, element, output_format, config)


def _extract_hierarchical_element(analyzer, element: str):
    """Extract an element using hierarchical syntax (Class.method).

    Args:
        analyzer: TreeSitterAnalyzer instance
        element: Hierarchical element name like "MyClass.my_method"

    Returns:
        Element dict with name, line_start, line_end, source
        or None if not found
    """
    parts = element.split('.')
    if len(parts) != 2:
        # Only support single-level hierarchy for now (Class.method)
        return None

    parent_name, child_name = parts

    # Find the parent node
    parent_node = None
    for node_type in PARENT_NODE_TYPES:
        nodes = analyzer._find_nodes_by_type(node_type)
        for node in nodes:
            if analyzer._get_node_name(node) == parent_name:
                parent_node = node
                break
        if parent_node:
            break

    if not parent_node:
        return None

    # Search for child within parent's subtree
    def find_child_in_subtree(node, target_name):
        """Recursively search for child node within subtree."""
        for child in node.children:
            if child.type in CHILD_NODE_TYPES:
                name = analyzer._get_node_name(child)
                if name == target_name:
                    return child
            # Recurse into child nodes (for nested blocks)
            result = find_child_in_subtree(child, target_name)
            if result:
                return result
        return None

    child_node = find_child_in_subtree(parent_node, child_name)

    if not child_node:
        return None

    return {
        'name': element,
        'line_start': child_node.start_point[0] + 1,
        'line_end': child_node.end_point[0] + 1,
        'source': analyzer._get_node_text(child_node),
    }


def _extract_element_at_line(analyzer, target_line: int):
    """Find the element containing the target line.

    Searches through the file structure to find an element (function, class, etc.)
    that contains the specified line number. For markdown files, finds the section
    containing the target line.

    Args:
        analyzer: File analyzer instance
        target_line: Line number to find element for (1-indexed)

    Returns:
        Element dict with name, line_start, line_end, source, or None
    """
    from ..treesitter import TreeSitterAnalyzer

    # Check for markdown files - find section containing line
    from ..analyzers.markdown import MarkdownAnalyzer
    if isinstance(analyzer, MarkdownAnalyzer):
        return _extract_markdown_section_at_line(analyzer, target_line)

    if not isinstance(analyzer, TreeSitterAnalyzer) or not analyzer.tree:
        return None

    best_match = None
    smallest_span = float('inf')

    for node_type in ALL_ELEMENT_NODE_TYPES:
        nodes = analyzer._find_nodes_by_type(node_type)
        for node in nodes:
            start = node.start_point[0] + 1  # 1-indexed
            end = node.end_point[0] + 1

            # Check if target line is within this element
            if start <= target_line <= end:
                span = end - start
                # Prefer smallest containing element (most specific)
                if span < smallest_span:
                    smallest_span = span
                    best_match = node

    if not best_match:
        return None

    name = analyzer._get_node_name(best_match) or f"element@{target_line}"
    return {
        'name': name,
        'line_start': best_match.start_point[0] + 1,
        'line_end': best_match.end_point[0] + 1,
        'source': analyzer._get_node_text(best_match),
    }


def _extract_markdown_section_at_line(analyzer, target_line: int):
    """Find the markdown section containing the target line.

    Searches through headings to find the section that contains the target line.

    Args:
        analyzer: MarkdownAnalyzer instance
        target_line: Line number to find section for (1-indexed)

    Returns:
        Dict with name, line_start, line_end, source, or None
    """
    import re

    # Find all headings with their line numbers and levels
    headings = []
    for i, line in enumerate(analyzer.lines, 1):
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if match:
            headings.append({
                'line': i,
                'level': len(match.group(1)),
                'name': match.group(2).strip()
            })

    if not headings:
        return None

    # Find the heading that contains the target line
    # (last heading whose line <= target_line)
    containing_heading = None
    for h in headings:
        if h['line'] <= target_line:
            containing_heading = h
        else:
            break

    if not containing_heading:
        return None

    # Find the end of this section (next heading of same or higher level)
    start_line = containing_heading['line']
    heading_level = containing_heading['level']
    end_line = len(analyzer.lines)

    for h in headings:
        if h['line'] > start_line and h['level'] <= heading_level:
            end_line = h['line'] - 1
            break

    # Extract the section content
    source = '\n'.join(analyzer.lines[start_line-1:end_line])

    return {
        'name': containing_heading['name'],
        'line_start': start_line,
        'line_end': end_line,
        'source': source,
    }


def _extract_line_range(analyzer, start_line: int, end_line: int):
    """Extract a specific line range from the file.

    Args:
        analyzer: File analyzer instance
        start_line: Start line (1-indexed, inclusive)
        end_line: End line (1-indexed, inclusive)

    Returns:
        Element dict with name, line_start, line_end, source
    """
    try:
        with open(analyzer.path, 'r') as f:
            lines = f.readlines()

        # Validate range
        if start_line < 1 or end_line > len(lines) or start_line > end_line:
            return None

        # Extract lines (convert to 0-indexed)
        extracted = lines[start_line - 1:end_line]
        source = ''.join(extracted).rstrip('\n')

        return {
            'name': f'lines:{start_line}-{end_line}',
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }
    except Exception:
        return None


def _extract_ordinal_element(analyzer, ordinal: int, element_type: str = None):
    """Extract the Nth element of a given type (or dominant category).

    Args:
        analyzer: File analyzer instance
        ordinal: 1-indexed position (e.g., 3 for "3rd function")
        element_type: Optional element type (e.g., "function", "class").
                      If None, uses the file's dominant category.

    Returns:
        Element dict with name, line_start, line_end, source, or None
    """
    from ..treesitter import TreeSitterAnalyzer

    if ordinal < 1:
        return None

    # Get structure from analyzer
    try:
        structure = analyzer.get_structure()
    except Exception:
        return None

    if not structure:
        return None

    # Dominant category priority by file type
    # Code files: functions > classes > structs
    # Markdown: headings > sections
    # Config: keys > tables
    dominant_priority = [
        'functions', 'classes', 'structs',  # Code
        'headings', 'sections',              # Markdown
        'queries', 'mutations', 'types',     # GraphQL
        'messages', 'services',              # Protobuf
        'resources', 'variables',            # Terraform
        'keys', 'tables',                    # Config
        'cells',                             # Jupyter
    ]

    # Map element_type to category name (reverse of category_to_type)
    type_to_category = {
        'function': 'functions',
        'class': 'classes',
        'struct': 'structs',
        'section': 'headings',
        'heading': 'headings',
        'query': 'queries',
        'mutation': 'mutations',
        'type': 'types',
        'interface': 'interfaces',
        'enum': 'enums',
        'message': 'messages',
        'service': 'services',
        'rpc': 'rpcs',
        'resource': 'resources',
        'variable': 'variables',
        'output': 'outputs',
        'module': 'modules',
        'import': 'imports',
        'test': 'tests',
        'union': 'unions',
        'cell': 'cells',
        'key': 'keys',
        'table': 'tables',
        'server': 'servers',
        'location': 'locations',
        'upstream': 'upstreams',
    }

    # Determine which category to use
    if element_type:
        # User specified type explicitly (e.g., "function:3")
        category = type_to_category.get(element_type)
        if not category:
            # Try using element_type directly as category (e.g., "functions:3")
            category = element_type if element_type in structure else None
        if not category or category not in structure:
            return None
        target_categories = [category]
    else:
        # Find dominant category (first non-empty category in priority order)
        target_categories = [cat for cat in dominant_priority if cat in structure and structure[cat]]
        if not target_categories:
            # Fallback: use any category with items
            target_categories = [cat for cat in structure if isinstance(structure[cat], list) and structure[cat]]

    if not target_categories:
        return None

    # Get elements from first matching category
    category = target_categories[0]
    items = structure.get(category, [])

    if not items or not isinstance(items, list):
        return None

    # Sort by line number to ensure consistent ordering
    items = sorted(items, key=lambda x: x.get('line', x.get('line_start', 0)))

    # Check if ordinal is valid (1-indexed)
    if ordinal > len(items):
        return None

    item = items[ordinal - 1]

    # Extract the element
    name = item.get('name') or item.get('text') or item.get('title') or f'{category}@{ordinal}'
    line_start = item.get('line', item.get('line_start', 1))
    line_end = item.get('line_end', line_start)

    # Get source code
    if isinstance(analyzer, TreeSitterAnalyzer) and analyzer.tree:
        # Try to find the actual node for better source extraction
        source = _get_source_for_item(analyzer, item, line_start, line_end)
    else:
        # Fallback: read lines directly
        source = _read_lines(analyzer.path, line_start, line_end)

    return {
        'name': name,
        'line_start': line_start,
        'line_end': line_end,
        'source': source or '',
    }


def _get_source_for_item(analyzer, item, line_start, line_end):
    """Get source code for a structure item using tree-sitter if available."""
    for node_type in ALL_ELEMENT_NODE_TYPES:
        nodes = analyzer._find_nodes_by_type(node_type)
        for node in nodes:
            start = node.start_point[0] + 1
            if start == line_start:
                return analyzer._get_node_text(node)

    # Fallback to reading lines
    return _read_lines(analyzer.path, line_start, line_end)


def _read_lines(path, start_line, end_line):
    """Read lines from a file."""
    try:
        with open(path, 'r') as f:
            lines = f.readlines()
        if start_line < 1 or end_line > len(lines):
            return None
        return ''.join(lines[start_line - 1:end_line]).rstrip('\n')
    except Exception:
        return None


def _output_result(analyzer, result, element: str, output_format: str, config=None):
    """Output extraction result in the requested format.

    Args:
        analyzer: File analyzer instance
        result: Extraction result dict
        element: Original element query string
        output_format: Output format (json, grep, or human)
        config: Optional RevealConfig instance
    """
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
        for i, line in enumerate(source.split('\n')):
            line_num = line_start + i
            print(f"{path}:{line_num}:{line}")
    else:
        formatted = analyzer.format_with_lines(source, line_start)
        print(formatted)

        # Navigation hints
        file_type = get_file_type_from_analyzer(analyzer)
        line_count = line_end - line_start + 1
        print_breadcrumbs('element', path, file_type=file_type, config=config,
                         element_name=name, line_count=line_count, line_start=line_start)
