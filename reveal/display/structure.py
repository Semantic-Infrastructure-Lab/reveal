"""Structure display for file analysis results."""

from pathlib import Path
from typing import Any, Dict, List

from reveal.base import FileAnalyzer
from reveal.utils import safe_json_dumps, get_file_type_from_analyzer, print_breadcrumbs

from .metadata import _print_file_header
from .outline import build_hierarchy, build_heading_hierarchy, render_outline
from .formatting import (
    _format_frontmatter,
    _format_links,
    _format_code_blocks,
    _format_related,
    _format_html_metadata,
    _format_html_elements,
    _format_standard_items,
    _build_analyzer_kwargs,
)


# Helper functions for typed structure rendering

def _matches_category_filter(el, filter_value: str) -> bool:
    """Check if element matches the category filter.

    Args:
        el: Element to check (PythonElement or base Element)
        filter_value: Filter string (lowercased)

    Returns:
        True if element matches filter
    """
    from reveal.elements import PythonElement

    if isinstance(el, PythonElement):
        # Check display_category (property, staticmethod, method, etc.)
        if el.display_category.lower() == filter_value:
            return True
        # Also check raw category for class, function, import
        if el.category.lower() == filter_value:
            return True
    else:
        if el.category.lower() == filter_value:
            return True
    return False


def _filter_element_tree(elements, filter_value: str):
    """Recursively filter elements and their children.

    Args:
        elements: List of elements to filter
        filter_value: Filter string (lowercased)

    Returns:
        Filtered list of elements
    """
    result = []
    for el in elements:
        if _matches_category_filter(el, filter_value):
            result.append(el)
        else:
            # Check children for matches
            filtered_children = _filter_element_tree(el.children, filter_value)
            if filtered_children:
                # Include this element as container for matching children
                result.append(el)
    return result


def _count_filtered_matches(elements, filter_value: str) -> int:
    """Count total elements matching filter recursively.

    Args:
        elements: List of elements to count
        filter_value: Filter string (lowercased)

    Returns:
        Count of matching elements
    """
    count = 0
    for el in elements:
        if _matches_category_filter(el, filter_value):
            count += 1
        count += _count_filtered_matches(el.children, filter_value)
    return count


def _format_element_parts(el) -> List[str]:
    """Format element display parts (name, signature, type, etc.).

    Args:
        el: Element to format

    Returns:
        List of formatted parts to join
    """
    from reveal.elements import PythonElement

    parts = []

    # For PythonElement, use enhanced display
    if isinstance(el, PythonElement):
        # Decorator prefix (e.g., @property, @classmethod)
        if el.decorator_prefix and el.category == "function":
            parts.append(el.decorator_prefix)

        # Name with optional signature
        if el.compact_signature and el.category == "function":
            parts.append(f"{el.name}{el.compact_signature}")
        else:
            parts.append(el.name)

        # Return type
        if el.return_type:
            parts.append(f"→ {el.return_type}")

        # Category (semantic: method, property, classmethod, etc.)
        parts.append(f"({el.display_category})")
    else:
        # Base element: simple format
        parts.append(el.name)
        parts.append(f"({el.category})")

    # Line range
    if el.line != el.line_end:
        parts.append(f"[{el.line}-{el.line_end}]")
    else:
        parts.append(f"[{el.line}]")

    # Line count for multi-line elements
    line_count = el.line_end - el.line + 1
    if line_count > 10:
        parts.append(f"{line_count} lines")

    # Quality warnings for functions
    if isinstance(el, PythonElement) and el.category == "function":
        depth = getattr(el, "depth", 0)
        if isinstance(depth, int) and depth > 4:
            parts.append(f"⚠ depth:{depth}")

    return parts


def _render_typed_element(el, indent=0):
    """Render a single typed element and its children recursively.

    Args:
        el: Element to render
        indent: Indentation level
    """
    prefix = "  " * indent
    parts = _format_element_parts(el)
    print(f"{prefix}{' '.join(parts)}")

    for child in el.children:
        _render_typed_element(child, indent + 1)


def _print_typed_header(typed, category_filter=None, match_count=None):
    """Print header for typed structure output.

    Args:
        typed: TypedStructure instance
        category_filter: Optional category filter string
        match_count: Optional count of filtered matches
    """
    if category_filter:
        # Filtered view
        if typed.reveal_type:
            print(f"Type: {typed.reveal_type.name}")
        print(f"Filter: {category_filter}")
        print(f"Matches: {match_count}")
        print()
    else:
        # Full view
        if typed.reveal_type:
            print(f"Type: {typed.reveal_type.name}")
        print(f"Elements: {len(typed)} ({typed.stats.get('roots', 0)} roots)")
        print()


def _render_typed_structure_output(
    analyzer: FileAnalyzer,
    structure: Dict[str, List[Dict[str, Any]]],
    output_format: str = "text",
    category_filter: str = None,
    config=None,
) -> None:
    """Render structure using the new Type-First Architecture.

    Converts raw analyzer output to TypedStructure with containment
    relationships, then renders in the specified format.

    Refactored to reduce complexity from 69 → ~20 by extracting helpers.

    Args:
        analyzer: The file analyzer
        structure: Raw structure dict from analyzer
        output_format: 'text' for human-readable, 'json' for TypedStructure JSON
        category_filter: Optional filter by display_category (property, staticmethod, etc.)
    """
    from reveal.structure import TypedStructure

    file_path = str(analyzer.path)

    # Convert to TypedStructure (auto-detects type from extension)
    typed = TypedStructure.from_analyzer_output(structure, file_path)

    if output_format == "json":
        # Output full typed structure with tree
        result = {
            "file": file_path,
            "type": typed.reveal_type.name if typed.reveal_type else None,
            "stats": typed.stats,
            "tree": typed.to_tree().get("roots", []),
        }
        print(safe_json_dumps(result))
        return

    # Text output: show hierarchical structure with containment
    is_fallback = getattr(analyzer, "is_fallback", False)
    fallback_lang = getattr(analyzer, "fallback_language", None)
    _print_file_header(Path(file_path), is_fallback, fallback_lang)

    if not typed.elements:
        print("No structure available")
        return

    # Apply category filter if specified
    if category_filter:
        filter_lower = category_filter.lower()

        # Filter roots using extracted helper
        filtered_roots = _filter_element_tree(typed.roots, filter_lower)
        if not filtered_roots:
            print(f"No elements matching filter '{category_filter}'")
            return

        # Count matches using extracted helper
        match_count = _count_filtered_matches(typed.roots, filter_lower)

        # Print header with filter info
        _print_typed_header(typed, category_filter, match_count)
    else:
        filtered_roots = typed.roots
        # Print header without filter
        _print_typed_header(typed)

    # Render tree structure using extracted helper
    for root in filtered_roots:
        _render_typed_element(root)

    # Navigation hints
    print()
    file_type = get_file_type_from_analyzer(analyzer)
    print_breadcrumbs("typed", file_path, file_type=file_type, config=config)


def _render_json_output(analyzer: FileAnalyzer, structure: Dict[str, List[Dict[str, Any]]]) -> None:
    """Render structure as JSON output (standard format)."""
    is_fallback = getattr(analyzer, 'is_fallback', False)
    fallback_lang = getattr(analyzer, 'fallback_language', None)
    file_path = str(analyzer.path)

    # Add 'file' field to each element in structure for --stdin compatibility
    enriched_structure = {}
    for category, items in structure.items():
        # Special handling for frontmatter (single dict, not a list)
        if category == 'frontmatter':
            if isinstance(items, dict):
                enriched_fm = items.copy()
                enriched_fm['file'] = file_path
                enriched_structure[category] = enriched_fm
            else:
                enriched_structure[category] = items
            continue

        enriched_items = []
        for item in items:
            # Copy item and add file field
            enriched_item = item.copy()
            enriched_item['file'] = file_path
            enriched_items.append(enriched_item)
        enriched_structure[category] = enriched_items

    result = {
        'file': file_path,
        'type': analyzer.__class__.__name__.replace('Analyzer', '').lower(),
        'analyzer': {
            'type': 'fallback' if is_fallback else 'explicit',
            'language': fallback_lang if is_fallback else None,
            'explicit': not is_fallback,
            'name': analyzer.__class__.__name__
        },
        'structure': enriched_structure
    }
    print(safe_json_dumps(result))


def _render_text_categories(structure: Dict[str, List[Dict[str, Any]]],
                            path: Path, output_format: str) -> None:
    """Render each category in text format."""
    for category, items in structure.items():
        if not items:
            continue

        # Skip HTML internal structure categories (not meant for default display)
        if category in ['type', 'document', 'head', 'body', 'stats', 'template']:
            continue

        # Format category name (e.g., 'functions' -> 'Functions')
        category_name = category.capitalize()

        # Special handling for count (frontmatter is a dict, not a list)
        if category == 'frontmatter':
            count = len(items.get('data', {})) if isinstance(items, dict) else 0
        else:
            count = len(items)

        print(f"{category_name} ({count}):")

        # Special handling for different categories
        if category == 'frontmatter':
            _format_frontmatter(items)
        elif category == 'links':
            _format_links(items, path, output_format)
        elif category == 'code_blocks':
            _format_code_blocks(items, path, output_format)
        elif category == 'related':
            _format_related(items, path, output_format)
        elif category == 'metadata':
            _format_html_metadata(items, path, output_format)
        elif category in ['scripts', 'styles', 'semantic']:
            _format_html_elements(items, path, output_format, category)
        else:
            _format_standard_items(items, path, output_format)

        print()  # Blank line between categories


def _build_outline_hierarchy(structure: Dict[str, List[Dict[str, Any]]]):
    """Build hierarchy for outline mode based on structure type.

    Args:
        structure: Structure dict from analyzer

    Returns:
        Hierarchy suitable for render_outline()
    """
    # Check if this is markdown with headings
    if 'headings' in structure and structure.get('headings'):
        # Markdown outline: use level-based hierarchy
        return build_heading_hierarchy(structure['headings'])

    # Check if this is TOML with sections (level-based like markdown)
    if 'sections' in structure and structure.get('sections'):
        sections = structure['sections']
        # Check if sections have 'level' field (TOML outline mode)
        if sections and 'level' in sections[0]:
            # TOML outline: use level-based hierarchy like markdown
            return build_heading_hierarchy(sections)
        else:
            # Regular TOML: use line-range based hierarchy
            return build_hierarchy(structure)

    # Code outline: use line-range based hierarchy
    return build_hierarchy(structure)


def _handle_outline_mode(structure: Dict[str, List[Dict[str, Any]]],
                         path: Path, is_fallback: bool, fallback_lang: str, config=None) -> None:
    """Handle outline mode rendering.

    Args:
        structure: Structure dict from analyzer
        path: File path
        is_fallback: Whether using fallback analyzer
        fallback_lang: Fallback language if applicable
    """
    _print_file_header(path, is_fallback, fallback_lang)

    if not structure:
        print("No structure available for this file type")
        return

    hierarchy = _build_outline_hierarchy(structure)
    render_outline(hierarchy, path)

    # Navigation hints
    print()
    file_type = get_file_type_from_analyzer(None)  # TODO: pass analyzer if needed
    # Infer file type from path extension for now
    suffix = path.suffix.lstrip('.')
    type_map = {'py': 'python', 'js': 'javascript', 'ts': 'typescript',
                'rs': 'rust', 'go': 'go', 'sh': 'bash', 'md': 'markdown'}
    file_type = type_map.get(suffix, suffix)
    print_breadcrumbs("typed", str(path), file_type=file_type, config=config)


def _handle_standard_output(analyzer: FileAnalyzer, structure: Dict[str, List[Dict[str, Any]]],
                            output_format: str, is_fallback: bool, fallback_lang: str, config=None) -> None:
    """Handle standard JSON or text output.

    Args:
        analyzer: File analyzer instance
        structure: Structure dict from analyzer
        output_format: 'json' or 'text'
        is_fallback: Whether using fallback analyzer
        fallback_lang: Fallback language if applicable
    """
    path = analyzer.path

    # Handle JSON output (standard format)
    if output_format == 'json':
        _render_json_output(analyzer, structure)
        return

    # Handle typed JSON output (uses Type-First Architecture)
    if output_format == 'typed':
        _render_typed_structure_output(analyzer, structure, "json")
        return

    # Handle empty structure
    if not structure:
        _print_file_header(path, is_fallback, fallback_lang)
        print("No structure available for this file type")
        return

    # Text output: show header, categories, and navigation hints
    _print_file_header(path, is_fallback, fallback_lang)
    _render_text_categories(structure, path, output_format)

    # Navigation hints
    if output_format == 'text':
        file_type = get_file_type_from_analyzer(analyzer)
        print_breadcrumbs('structure', path, file_type=file_type, config=config,
                         structure=structure)


def show_structure(analyzer: FileAnalyzer, output_format: str, args=None, config=None):
    """Show file structure.

    Refactored to reduce complexity from 42 → ~18 by extracting mode handlers.

    Args:
        analyzer: File analyzer instance
        output_format: Output format ('text', 'json', 'typed')
        args: Optional command-line arguments
        config: Optional RevealConfig instance
    """
    # Build kwargs and get structure
    kwargs = _build_analyzer_kwargs(analyzer, args)

    # Add outline flag for markdown analyzer (Issue #3)
    if args and hasattr(args, 'outline'):
        kwargs['outline'] = args.outline

    structure = analyzer.get_structure(**kwargs)
    path = analyzer.path

    # Get fallback info
    is_fallback = getattr(analyzer, 'is_fallback', False)
    fallback_lang = getattr(analyzer, 'fallback_language', None)

    # Handle --typed flag (new Type-First Architecture)
    if args and getattr(args, 'typed', False):
        json_format = "json" if output_format == "json" else "text"
        category_filter = getattr(args, 'filter', None)
        _render_typed_structure_output(analyzer, structure, json_format, category_filter, config=config)
        return

    # Handle outline mode
    if args and getattr(args, 'outline', False):
        _handle_outline_mode(structure, path, is_fallback, fallback_lang, config=config)
        return

    # Handle standard output (JSON or text)
    _handle_standard_output(analyzer, structure, output_format, is_fallback, fallback_lang, config=config)
