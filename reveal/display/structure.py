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
    _format_standard_items,
    _build_analyzer_kwargs,
)


def _render_typed_structure_output(
    analyzer: FileAnalyzer,
    structure: Dict[str, List[Dict[str, Any]]],
    output_format: str = "text",
    category_filter: str = None,
) -> None:
    """Render structure using the new Type-First Architecture.

    Converts raw analyzer output to TypedStructure with containment
    relationships, then renders in the specified format.

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
        from reveal.elements import PythonElement
        filter_lower = category_filter.lower()

        def matches_filter(el):
            """Check if element matches the category filter."""
            if isinstance(el, PythonElement):
                # Check display_category (property, staticmethod, method, etc.)
                if el.display_category.lower() == filter_lower:
                    return True
                # Also check raw category for class, function, import
                if el.category.lower() == filter_lower:
                    return True
            else:
                if el.category.lower() == filter_lower:
                    return True
            return False

        def filter_tree(elements):
            """Recursively filter elements and their children."""
            result = []
            for el in elements:
                if matches_filter(el):
                    result.append(el)
                else:
                    # Check children for matches
                    filtered_children = filter_tree(el.children)
                    if filtered_children:
                        # Include this element as container for matching children
                        result.append(el)
            return result

        # Filter roots and count matches
        filtered_roots = filter_tree(typed.roots)
        if not filtered_roots:
            print(f"No elements matching filter '{category_filter}'")
            return

        # Count total matches
        def count_matches(elements):
            count = 0
            for el in elements:
                if matches_filter(el):
                    count += 1
                count += count_matches(el.children)
            return count

        match_count = count_matches(typed.roots)

        # Print type info with filter
        if typed.reveal_type:
            print(f"Type: {typed.reveal_type.name}")
        print(f"Filter: {category_filter}")
        print(f"Matches: {match_count}")
        print()
    else:
        filtered_roots = typed.roots
        # Print type info
        if typed.reveal_type:
            print(f"Type: {typed.reveal_type.name}")
        print(f"Elements: {len(typed)} ({typed.stats.get('roots', 0)} roots)")
        print()

    # Render tree structure with rich formatting
    def render_element(el, indent=0):
        from reveal.elements import PythonElement

        prefix = "  " * indent
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

        print(f"{prefix}{' '.join(parts)}")

        for child in el.children:
            render_element(child, indent + 1)

    for root in filtered_roots:
        render_element(root)

    # Navigation hints
    print()
    file_type = get_file_type_from_analyzer(analyzer)
    print_breadcrumbs("typed", file_path, file_type=file_type)


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


def _render_typed_json_output(analyzer: FileAnalyzer, structure: Dict[str, List[Dict[str, Any]]]) -> None:
    """Render structure as typed JSON output (with types and relationships).

    This format includes:
    - Entities with explicit type fields
    - Relationships (including bidirectional)
    - Type counts
    - Rich properties

    Only available for analyzers that define types.
    Falls back to standard JSON if no types defined.
    """
    # Check if analyzer has type system
    if not hasattr(analyzer, '_type_registry') or analyzer._type_registry is None:
        # No type system - fall back to standard JSON
        _render_json_output(analyzer, structure)
        return

    is_fallback = getattr(analyzer, 'is_fallback', False)
    fallback_lang = getattr(analyzer, 'fallback_language', None)
    file_path = str(analyzer.path)

    # Build entities list with explicit types
    entities = []
    type_counts = {}

    # Map structure keys to type names (handle plural to singular)
    def normalize_type_name(structure_key: str) -> str:
        """Convert structure key to type name.

        Structure keys are often plural (functions, classes),
        but type definitions are singular (function, class).
        """
        # Check if singular form exists in type registry
        singular = structure_key.rstrip('s')  # Simple pluralization
        if analyzer._type_registry and singular in analyzer._type_registry.types:
            return singular

        # Check for exact match
        if analyzer._type_registry and structure_key in analyzer._type_registry.types:
            return structure_key

        # Fall back to structure key
        return structure_key

    for structure_key, items in structure.items():
        # Get normalized type name
        entity_type = normalize_type_name(structure_key)

        for item in items:
            # Create entity with explicit type field
            entity = {
                'type': entity_type,
                **item,  # Include all original properties
                'file': file_path  # Add file field for --stdin compatibility
            }
            entities.append(entity)

            # Count types
            type_counts[entity_type] = type_counts.get(entity_type, 0) + 1

    # Extract relationships if analyzer supports them
    relationships = {}
    if hasattr(analyzer, '_relationship_registry') and analyzer._relationship_registry is not None:
        # Call analyzer's relationship extraction
        raw_relationships = analyzer._extract_relationships(structure)

        # Build relationship index (adds bidirectional edges)
        if raw_relationships:
            relationships = analyzer._relationship_registry.build_index(raw_relationships)

    # Build result
    result = {
        'file': file_path,
        'analyzer': analyzer.__class__.__name__.replace('Analyzer', '').lower(),
        'analyzer_info': {
            'type': 'fallback' if is_fallback else 'explicit',
            'language': fallback_lang if is_fallback else None,
            'explicit': not is_fallback,
            'name': analyzer.__class__.__name__,
            'has_types': True,
            'has_relationships': len(relationships) > 0
        },
        'entities': entities,
        'type_counts': type_counts,
        'metadata': {
            'total_entities': len(entities),
            'total_relationships': sum(len(edges) for edges in relationships.values())
        }
    }

    # Add relationships if present
    if relationships:
        result['relationships'] = relationships

    print(safe_json_dumps(result))


def _render_text_categories(structure: Dict[str, List[Dict[str, Any]]],
                            path: Path, output_format: str) -> None:
    """Render each category in text format."""
    for category, items in structure.items():
        if not items:
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
        else:
            _format_standard_items(items, path, output_format)

        print()  # Blank line between categories


def show_structure(analyzer: FileAnalyzer, output_format: str, args=None):
    """Show file structure.

    Simplified using extracted helper functions.
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
        _render_typed_structure_output(analyzer, structure, json_format, category_filter)
        return

    # Handle outline mode
    if args and getattr(args, 'outline', False):
        _print_file_header(path, is_fallback, fallback_lang)
        if not structure:
            print("No structure available for this file type")
            return

        # Check if this is markdown with headings
        if 'headings' in structure and structure.get('headings'):
            # Markdown outline: use level-based hierarchy
            hierarchy = build_heading_hierarchy(structure['headings'])
        # Check if this is TOML with sections (level-based like markdown)
        elif 'sections' in structure and structure.get('sections'):
            # Check if sections have 'level' field (TOML outline mode)
            sections = structure['sections']
            if sections and 'level' in sections[0]:
                # TOML outline: use level-based hierarchy like markdown
                hierarchy = build_heading_hierarchy(sections)
            else:
                # Regular TOML: use line-range based hierarchy
                hierarchy = build_hierarchy(structure)
        else:
            # Code outline: use line-range based hierarchy
            hierarchy = build_hierarchy(structure)

        render_outline(hierarchy, path)
        return

    # Handle JSON output (standard format)
    if output_format == 'json':
        _render_json_output(analyzer, structure)
        return

    # Handle typed JSON output (with types and relationships)
    if output_format == 'typed':
        _render_typed_json_output(analyzer, structure)
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
        print_breadcrumbs('structure', path, file_type=file_type)
