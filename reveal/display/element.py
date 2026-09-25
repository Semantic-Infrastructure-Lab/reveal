"""Element extraction display."""

from ..reveal_types import StructureItem
import difflib
import sys
from typing import Optional, cast

from reveal.base import FileAnalyzer
from reveal.element_resolve import (
    TYPE_TIER, Resolution, ambiguity_note, describe_candidates, resolve_bare_name, resolve_path,
)
from reveal.treesitter import ELEMENT_TYPE_MAP, ALL_ELEMENT_NODE_TYPES
from reveal.core.treesitter_compat import _zero_arg
from reveal.utils import safe_json_dumps, get_file_type_from_analyzer, print_breadcrumbs

# Dominant category priority by file type
_DOMINANT_CATEGORY_PRIORITY = [
    'functions', 'classes', 'structs',  # Code
    'headings', 'sections',              # Markdown
    'queries', 'mutations', 'types',     # GraphQL
    'messages', 'services',              # Protobuf
    'resources', 'variables',            # Terraform
    'keys', 'tables',                    # Config
    'cells',                             # Jupyter
    'schema',                            # CSV columns
]

# Map element type names to category names
_TYPE_TO_CATEGORY = {
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


_HIERARCHICAL_PATH = (
    r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*'
    r'\.(?:#?[A-Za-z_]\w*|~[A-Za-z_]\w*|operator(?:\(\)|\[\]|[^\w\s.()\[\]]+))$'
)


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
            assert typed_ordinal_match is not None
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

    # Check for bare integer (treat as line reference — editor/grep convention)
    if re.match(r'^\d+$', element):
        return {
            'type': 'line',
            'start_line': int(element),
            'end_line': None
        }

    # Check for hierarchical extraction (Class.method, Outer.Inner.method)
    # Require identifier(.identifier)+: every part a bare identifier (no spaces),
    # not version strings like [0.50.0] or v1.2.3, and not headings like "rr.php sentinel locking".
    # The last part may also be a C++ destructor or operator (`Vec.~Vec`,
    # `Vec.operator+`, `Vec.operator()`; no overloadable operator contains '.')
    # or a JS/TS private member (`Svc.#normalize`).
    if '.' in element and re.match(_HIERARCHICAL_PATH, element):
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
            # Bare integer (not an explicit ":N") on an analyzer whose own
            # get_element() gives numeric args a different meaning (e.g. CSV
            # row lookup) — prefer that over line-number semantics.
            if not element.startswith(':') and hasattr(analyzer, 'get_element'):
                result = analyzer.get_element(element)
                if result is not None:
                    return result

            result = _extract_element_at_line(analyzer, syntax['start_line'])
            if result is not None:
                return result
            # Line not inside any named element (e.g., imports, module-level code).
            # Fall back to a context window so bare integers always show something useful.
            target = syntax['start_line']
            context = 10
            window = _extract_line_range(analyzer, max(1, target - context), target + context)
            # A line past EOF is an error, not a window onto the file's start.
            if window is not None and target > window['line_end']:
                return None
            return window

    elif syntax_type == 'hierarchical':
        from ..treesitter import TreeSitterAnalyzer
        if isinstance(analyzer, TreeSitterAnalyzer) and analyzer.tree:
            result = _extract_hierarchical_element(analyzer, element)
            if result:
                return result
        # Not a member path after all: a dotted name the analyzer knows as-is
        # (a markdown heading `setup.py`, a JSON key `a.b`).
        return _extract_by_name(analyzer, element)

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
    is_treesitter = isinstance(analyzer, TreeSitterAnalyzer) and analyzer.tree
    if is_treesitter:
        result = _try_treesitter_extraction(analyzer, element)
        if result:
            return result

    # Fallback to the analyzer's own extract_element (markdown sections, ...)
    result = _try_grep_extraction(analyzer, element)
    if result:
        return result
    # Last: anything the outline lists by this name. After the analyzer's own
    # extractor, never before it -- a markdown heading's outline item spans
    # only the heading line, while its section extractor returns the section.
    # Every analyzer, not just tree-sitter ones (BACK-1411: INI sections,
    # JSONL records and notebook cells were listed but "not found").
    return _extract_listed_item(analyzer, element)


# Bare-name tiers for display extraction, first tier with a match wins (see
# element_resolve.resolve_bare_name). Types before functions, so `reveal
# A.java Foo` is the class, not its constructor; structs after functions, so
# C's `stat` is the function, not `struct stat`.
_DISPLAY_NAME_TIERS = (
    TYPE_TIER,
    ELEMENT_TYPE_MAP['function'],
    ELEMENT_TYPE_MAP['struct'],
    ('section',), ('server',), ('location',), ('upstream',),
)


def _element_from_resolution(analyzer, resolution: Resolution, element: str):
    """Element dict for a resolved node, carrying every candidate when the name
    was ambiguous (BACK-1400) so each surface can say so."""
    node = getattr(analyzer, '_extraction_node', lambda n: n)(resolution.node)
    # Dart: node may be a function_signature whose body lives in a disjoint
    # sibling (TreeSitterAnalyzer._function_end_node); every other language's
    # node already spans its own body.
    end_node = getattr(analyzer, '_function_end_node', lambda n: n)(node)
    source = (
        analyzer._get_node_text(node) if end_node is node
        else analyzer._get_text_span(
            _zero_arg(node, 'start_byte'), _zero_arg(end_node, 'end_byte')
        )
    )
    result = {
        'name': element,
        'line_start': _zero_arg(node, 'start_position').row + 1,
        'line_end': _zero_arg(end_node, 'end_position').row + 1,
        'source': source,
    }
    if resolution.ambiguous:
        result['candidates'] = describe_candidates(analyzer, resolution, element)
    return result


def _try_treesitter_extraction(analyzer, element: str):
    """Try extracting element using tree-sitter.

    Args:
        analyzer: TreeSitterAnalyzer instance
        element: Element name to find

    Returns:
        Element dict or None if not found
    """
    # Named node kinds, then JS-family `const f = (...) => {}` values and
    # test-callback labels (element_resolve._unnamed_kind_matches).
    resolution = resolve_bare_name(analyzer, element, _DISPLAY_NAME_TIERS)
    if resolution is None:
        return None
    return _element_from_resolution(analyzer, resolution, element)


def listed_item_line(item) -> Optional[int]:
    """The first line of an outline item, or None when it has no location.

    An item without a positive line (JSONL's record-count summary at line 0,
    a properties file's '(no section)') is outline metadata, not an
    addressable span -- neither advertised as extractable nor extracted.
    """
    line = item.get('line', item.get('line_start'))
    return line if isinstance(line, int) and line > 0 else None


def _extract_listed_item(analyzer, element: str):
    """Last resort: an item the outline lists under this exact name.

    BACK-1400: the outline is the addressing contract -- if `reveal file`
    lists it, `reveal file NAME` must return it. Analyzer-specific categories
    have no node kind in the tiers above (Go `interfaces`, a `type_spec`'s
    sibling-named `interface_type`), so `reveal fifo.go Queue` answered "not
    found" for an interface printed one command earlier.
    """
    structure = _get_analyzer_structure(analyzer)
    if not structure:
        return None
    matches = [
        (category, item)
        for category, items in structure.items()
        if category != 'imports' and isinstance(items, list)
        for item in items
        if isinstance(item, dict) and item.get('name') == element and listed_item_line(item)
    ]
    if not matches:
        return None
    matches.sort(key=lambda m: listed_item_line(m[1]))
    category, item = matches[0]
    result = _build_element_from_item(analyzer, item, category, 1)
    if len(matches) > 1:
        candidates = []
        for _, m_item in matches:
            start = m_item.get('line', m_item.get('line_start', 1))
            end = m_item.get('line_end', start)
            candidates.append({
                'name': m_item['name'], 'line_start': start, 'line_end': end,
                'address': f':{start}-{end}', 'selected': m_item is item,
            })
        result['candidates'] = candidates
    return result


def _try_grep_extraction(analyzer, element: str):
    """Try extracting element using an analyzer's own extract_element().

    Args:
        analyzer: File analyzer instance
        element: Element name to find

    Returns:
        Element dict or None if not found
    """
    # Selector/tag-based analyzers (BACK-481: HTML) match a single target
    # string — a CSS selector, id, or tag — rather than the base
    # `(element_type, name)` pair. They expose `extract_by_selector()`;
    # capability-check for it and hand the raw target straight through.
    #
    # This used to be a probe — `extract_element(element, '')`, target in the
    # *type* slot, empty name — which markdown's `extract_element` answered
    # with an empty-pattern = match-all result, shadowing the correct
    # `extract_element('section', element)` loop below and dumping the whole
    # file instead of the requested `--section`. Dispatching on an honest
    # capability instead of a swapped-argument shape removes that footgun.
    extract_by_selector = getattr(analyzer, 'extract_by_selector', None)
    if extract_by_selector is not None:
        result = extract_by_selector(element)
        if result:
            return result

    for element_type in ['function', 'class', 'struct', 'section', 'server', 'location', 'upstream', 'record']:
        result = analyzer.extract_element(element_type, element)
        if result:
            return result
    return None


def _available_names(analyzer) -> list:
    """Distinct element names from the analyzer's structure, in outline order."""
    structure = analyzer.get_structure()
    if not structure or not isinstance(structure, dict):
        return []
    names: list = []
    for category in ('functions', 'classes', 'methods'):
        items = structure.get(category, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get('name')
            # An overload set or same-named methods list once: the name is the address.
            if name and name not in names:
                names.append(name)
    return names


def _print_available_names(analyzer):
    """Print available element names from the analyzer's structure to stderr."""
    try:
        available = _available_names(analyzer)
        if available:
            max_names = 10
            suffix = f" (and {len(available) - max_names} more)" if len(available) > max_names else ""
            print(f"Available: {', '.join(available[:max_names])}{suffix}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: could not list available names: {e}", file=sys.stderr)


def _print_did_you_mean(analyzer, element: str):
    """Suggest the closest element names for a mistyped one (stderr)."""
    try:
        close = difflib.get_close_matches(element, _available_names(analyzer), n=3, cutoff=0.6)
    except Exception as e:
        print(f"Warning: could not suggest similar names: {e}", file=sys.stderr)
        return
    if close:
        print(f"Did you mean: {', '.join(close)}?", file=sys.stderr)


def _count_lines(path) -> Optional[int]:
    """Number of lines in a file, or None when it cannot be read as text."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return sum(1 for _ in f)
    except (OSError, UnicodeDecodeError, TypeError):
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
        end_line = syntax['end_line']
        total = _count_lines(analyzer.path)
        span = f"{target_line}-{end_line}" if end_line else str(target_line)
        if total is not None and target_line > total:
            print(f"Error: Line {span} is past the end of {analyzer.path} ({total} lines)", file=sys.stderr)
        elif end_line:
            print(f"Error: Invalid line range {span} in {analyzer.path}", file=sys.stderr)
        else:
            print(f"Error: No element found at line {target_line} in {analyzer.path}", file=sys.stderr)

    elif syntax_type == 'hierarchical':
        parent, child = element.rsplit('.', 1)
        print(f"Error: Element '{element}' not found in {analyzer.path}", file=sys.stderr)
        print(f"Hint: Looking for '{child}' within '{parent}'", file=sys.stderr)

    else:
        print(f"Error: Element '{element}' not found in {analyzer.path}", file=sys.stderr)
        if '|' in element:
            print(
                "Hint: '|' pattern matches headings only. "
                f"For table or body content, use: reveal {analyzer.path} --grep '{element.split('|')[0].strip()}'",
                file=sys.stderr
            )
        else:
            print(
                f"Hint: Code extraction matches exact names. "
                f"For content search, use: reveal {analyzer.path} --grep '{element}'",
                file=sys.stderr
            )
        _print_did_you_mean(analyzer, element)
        _print_available_names(analyzer)


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
    """Extract an element using hierarchical syntax (Class.method, Outer.Inner.method).

    Args:
        analyzer: TreeSitterAnalyzer instance
        element: Hierarchical element name like "MyClass.my_method"

    Returns:
        Element dict with name, line_start, line_end, source (and candidates
        when several definitions match) or None if not found
    """
    resolution = resolve_path(analyzer, element)
    if resolution is None:
        return None
    return _element_from_resolution(analyzer, resolution, element)


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
        for node in analyzer._find_nodes_by_type(node_type):
            start = _zero_arg(node, 'start_position').row + 1  # 1-indexed
            end = _zero_arg(node, 'end_position').row + 1
            if not (start <= target_line <= end):
                continue
            span = end - start
            if span < smallest_span:
                smallest_span = span
                best_match = node

    if not best_match:
        return None

    name = analyzer._get_node_name(best_match) or f"element@{target_line}"
    return {
        'name': name,
        'line_start': _zero_arg(best_match, 'start_position').row + 1,
        'line_end': _zero_arg(best_match, 'end_position').row + 1,
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
    # The analyzer's heading index: ATX and setext, never a `# comment` in a code fence
    headings: list[dict[str, int | str]] = [
        {'line': line, 'level': level, 'name': title}
        for line, level, title in analyzer._heading_index()
    ]

    if not headings:
        return None

    # Find the heading that contains the target line
    # (last heading whose line <= target_line)
    containing_heading = None
    for h in headings:
        if cast(int, h['line']) <= target_line:
            containing_heading = h
        else:
            break

    if not containing_heading:
        return None

    # Find the end of this section (next heading of same or higher level)
    start_line = cast(int, containing_heading['line'])
    heading_level = cast(int, containing_heading['level'])
    end_line = len(analyzer.lines)

    for h in headings:
        if cast(int, h['line']) > start_line and cast(int, h['level']) <= heading_level:
            end_line = cast(int, h['line']) - 1
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
        with open(analyzer.path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Validate range; clamp end_line to actual file length
        if start_line < 1 or start_line > len(lines) or start_line > end_line:
            return None
        end_line = min(end_line, len(lines))

        # Extract lines (convert to 0-indexed)
        extracted = lines[start_line - 1:end_line]
        source = ''.join(extracted).rstrip('\n')

        return {
            'name': f'lines:{start_line}-{end_line}',
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }
    except Exception as e:
        print(f"Warning: could not extract lines {start_line}-{end_line} from {analyzer.path}: {e}",
              file=sys.stderr)
        return None


def _extract_ordinal_element(analyzer, ordinal: int, element_type: Optional[str] = None):
    """Extract the Nth element of a given type (or dominant category).

    Args:
        analyzer: File analyzer instance
        ordinal: 1-indexed position (e.g., 3 for "3rd function")
        element_type: Optional element type (e.g., "function", "class").
                      If None, uses the file's dominant category.

    Returns:
        Element dict with name, line_start, line_end, source, or None
    """
    if ordinal < 1:
        return None

    # Get structure from analyzer
    structure = _get_analyzer_structure(analyzer)
    if not structure:
        return None

    # Determine target category
    category = _determine_target_category(structure, element_type)
    if not category:
        return None

    # Get and validate items
    items = _get_category_items(structure, category)
    if not items or ordinal > len(items):
        return None

    # Extract item at ordinal position
    item = items[ordinal - 1]
    return _build_element_from_item(analyzer, item, category, ordinal)


def _get_analyzer_structure(analyzer):
    """Get structure from analyzer, return None on failure."""
    try:
        structure = analyzer.get_structure()
        return structure if structure else None
    except Exception as e:
        print(f"Warning: could not get structure for {getattr(analyzer, 'path', '<unknown>')}: {e}",
              file=sys.stderr)
        return None


def _determine_target_category(structure, element_type: Optional[str] = None):
    """Determine which category to extract from.

    Args:
        structure: File structure dict
        element_type: Optional explicit type (e.g., "function")

    Returns:
        Category name or None
    """
    if element_type:
        # User specified type explicitly
        category = _TYPE_TO_CATEGORY.get(element_type)
        if not category:
            # Try using element_type directly as category
            category = element_type if element_type in structure else None
        return category if (category and category in structure) else None

    # Find dominant category (first non-empty category in priority order)
    for cat in _DOMINANT_CATEGORY_PRIORITY:
        if cat in structure and structure[cat]:
            return cat

    # Fallback: use any category with items, skipping ones that aren't a
    # list of dicts (e.g. CSV's 'columns' is a bare list of strings) — those
    # have no ordinal-extractable shape and would crash downstream.
    for cat in structure:
        items = structure[cat]
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return cat

    return None


def _get_category_items(structure, category: str):
    """Get and sort items from category.

    Args:
        structure: File structure dict
        category: Category name

    Returns:
        Sorted list of items or None
    """
    items = structure.get(category, [])
    if not items or not isinstance(items, list):
        return None

    # Skip non-dict entries (e.g. CSV's 'columns' is a bare list of strings) —
    # they have no 'line'/'line_start' to sort by and no ordinal-extractable shape.
    items = [item for item in items if isinstance(item, dict)]
    if not items:
        return None

    # Sort by line number to ensure consistent ordering
    return sorted(items, key=lambda x: x.get('line', x.get('line_start', 0)))


def _build_element_from_item(analyzer, item: StructureItem, category: str, ordinal: int):
    """Build element dict from structure item.

    Args:
        analyzer: File analyzer instance
        item: Structure item dict
        category: Category name
        ordinal: Ordinal position

    Returns:
        Element dict with name, line_start, line_end, source
    """
    from ..treesitter import TreeSitterAnalyzer

    # Extract metadata
    name = item.get('name') or item.get('text') or item.get('title') or f'{category}@{ordinal}'
    line_start = item.get('line', item.get('line_start', 1))
    line_end = item.get('line_end', line_start)

    # Get source code
    if isinstance(analyzer, TreeSitterAnalyzer) and analyzer.tree:
        source = _get_source_for_item(analyzer, item, line_start, line_end)
    else:
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
            start = _zero_arg(node, 'start_position').row + 1
            if start == line_start:
                return analyzer._get_node_text(node)

    # Fallback to reading lines
    return _read_lines(analyzer.path, line_start, line_end)


def _read_lines(path, start_line, end_line):
    """Read lines from a file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if start_line < 1 or end_line > len(lines):
            return None
        return ''.join(lines[start_line - 1:end_line]).rstrip('\n')
    except Exception as e:
        print(f"Warning: could not read lines {start_line}-{end_line} from {path}: {e}", file=sys.stderr)
        return None


def _next_element_line(analyzer, after_line: int) -> Optional[int]:
    """First line of the nearest outline item that starts after `after_line`.

    The "Nearby" breadcrumb points here so the suggested `:N` lands on a real
    element -- not on blank space between elements or past the end of the file.
    None when nothing follows (the last element of the file).
    """
    try:
        structure = _get_analyzer_structure(analyzer)
        if not structure:
            return None
        starts = [
            line
            for category, items in structure.items()
            if category != 'imports' and isinstance(items, list)
            for item in items
            if isinstance(item, dict)
            for line in [listed_item_line(item)]
            if line and line > after_line
        ]
    except Exception as e:
        print(f"Warning: could not find the next element: {e}", file=sys.stderr)
        return None
    return min(starts) if starts else None


def _output_sections(analyzer, path, name: str, sections, output_format: str, config=None):
    """Render several non-contiguous sections, each numbered from its own start line."""
    for i, section in enumerate(sections):
        start, end, source = section['line_start'], section['line_end'], section['source']
        if output_format == 'grep':
            for offset, line in enumerate(source.split('\n')):
                print(f"{path}:{start + offset}:{line}")
            continue
        if i:
            print()
        print(f"{path}:{start}-{end} | {name}\n")
        print(analyzer.format_with_lines(source, start))
    if output_format != 'grep':
        line_count = sum(s['line_end'] - s['line_start'] + 1 for s in sections)
        file_type = get_file_type_from_analyzer(analyzer)
        print_breadcrumbs('element', path, file_type=file_type, config=config,
                          element_name=name, line_count=line_count,
                          line_start=sections[0]['line_start'],
                          next_line=_next_element_line(analyzer, sections[-1]['line_end']))


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

    # get_element()-style results (e.g. CSV row lookup via BACK-666) are a flat
    # data dict, not an extracted code span -- no 'source'/'line_start' to render.
    if 'source' not in result and 'data' in result:
        row_number = result.get('row_number')
        label = f"row {row_number}" if row_number is not None else element
        print(f"{path} | {label}\n")
        for key, value in result['data'].items():
            print(f"  {key}: {value}")
        return

    line_start = result.get('line_start', 1)
    line_end = result.get('line_end', line_start)
    source = result.get('source', '')
    name = result.get('name', element)
    match_count = result.get('match_count')

    # BACK-1400: an ambiguous name used to return the first definition
    # silently. stderr keeps stdout the unchanged extracted source.
    if result.get('candidates'):
        for line in ambiguity_note(path, element, result['candidates']):
            print(line, file=sys.stderr)

    # Match count prefix for multi-section results
    if match_count and match_count > 1 and output_format not in ('json', 'grep'):
        print(f"# {match_count} sections matched \"{name}\" — showing all\n")

    sections = result.get('sections')
    if sections:
        _output_sections(analyzer, path, name, sections, output_format, config)
        return

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

        # Short-result hint for single-section extractions that look like label-only sections
        line_count = line_end - line_start + 1
        next_section = result.get('next_section')
        if next_section and line_count <= 5 and output_format not in ('json', 'grep'):
            print(f"\n⚠ Short result ({line_count} lines) — this section may be a label only.",
                  file=sys.stderr)
            print(f"   Next section: {next_section['name']} (line {next_section['line']})",
                  file=sys.stderr)

        # Navigation hints
        file_type = get_file_type_from_analyzer(analyzer)
        print_breadcrumbs('element', path, file_type=file_type, config=config,
                         element_name=name, line_count=line_count, line_start=line_start,
                         next_line=_next_element_line(analyzer, line_end))
