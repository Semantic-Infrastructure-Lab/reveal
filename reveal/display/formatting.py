"""Formatting helpers for display output."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.base import FileAnalyzer


def _format_frontmatter(fm: Optional[Dict[str, Any]]) -> None:
    """Format and display YAML front matter."""
    if fm is None:
        print("  (No front matter found)")
        return

    data = fm.get('data', {})
    lines = f"{fm.get('line_start', '?')}-{fm.get('line_end', '?')}"

    # Display key fields
    if not data:
        print("  (Empty front matter)")
        return

    print(f"  Lines {lines}:")
    for key, value in data.items():
        # Format value based on type
        if isinstance(value, list):
            print(f"    {key}:")
            for item in value:
                print(f"      - {item}")
        elif isinstance(value, dict):
            print(f"    {key}:")
            for sub_key, sub_value in value.items():
                print(f"      {sub_key}: {sub_value}")
        else:
            print(f"    {key}: {value}")


def _format_single_link(
    item: Dict[str, Any],
    link_type: str,
    path: Path,
    output_format: str
) -> None:
    """Format and display a single link.

    Args:
        item: Link item dict
        link_type: Type of link (external, internal, email)
        path: File path (for grep output)
        output_format: Output format ('grep' or default)
    """
    line = item.get('line', '?')
    text = item.get('text', '')
    url = item.get('url', '')
    broken = item.get('broken', False)

    if output_format == 'grep':
        print(f"{path}:{line}:{url}")
        return

    if broken:
        print(f"    X Line {line:<4} [{text}]({url}) [BROKEN]")
        return

    # Normal link display
    print(f"    Line {line:<4} [{text}]({url})")

    # Show domain for external links
    if link_type == 'external':
        domain = item.get('domain', '')
        if domain:
            print(f"             -> {domain}")


def _format_links(
    items: List[Dict[str, Any]], path: Path, output_format: str
) -> None:
    """Format and display link items grouped by type."""
    # Group by type
    by_type = {}
    for item in items:
        link_type = item.get('type', 'unknown')
        by_type.setdefault(link_type, []).append(item)

    # Display each type
    for link_type in ['external', 'internal', 'email']:
        if link_type not in by_type:
            continue

        type_items = by_type[link_type]
        print(f"\n  {link_type.capitalize()} ({len(type_items)}):")

        for item in type_items:
            _format_single_link(item, link_type, path, output_format)


def _format_fenced_block(
    item: Dict[str, Any], path: Path, output_format: str
) -> None:
    """Format and display a single fenced code block.

    Args:
        item: Code block item dict
        path: File path (for grep output)
        output_format: Output format ('grep' or default)
    """
    line_start = item.get('line_start', '?')
    line_end = item.get('line_end', '?')
    line_count = item.get('line_count', 0)
    source = item.get('source', '')

    if output_format == 'grep':
        first_line = source.split('\n')[0] if source else ''
        print(f"{path}:{line_start}:{first_line}")
        return

    print(f"    Lines {line_start}-{line_end} ({line_count} lines)")
    preview_lines = source.split('\n')[:3]
    for preview_line in preview_lines:
        print(f"      {preview_line}")
    if line_count > 3:
        print(f"      ... ({line_count - 3} more lines)")


def _format_inline_code_items(
    items: List[Dict[str, Any]], path: Path, output_format: str
) -> None:
    """Format and display inline code items.

    Args:
        items: List of inline code items
        path: File path (for grep output)
        output_format: Output format ('grep' or default)
    """
    print(f"\n  Inline code ({len(items)} snippets):")

    for item in items[:10]:
        line = item.get('line', '?')
        source = item.get('source', '')

        if output_format == 'grep':
            print(f"{path}:{line}:{source}")
        else:
            print(f"    Line {line:<4} `{source}`")

    if len(items) > 10:
        print(f"    ... and {len(items) - 10} more")


def _format_code_blocks(
    items: List[Dict[str, Any]], path: Path, output_format: str
) -> None:
    """Format and display code block items grouped by language."""
    # Group by language
    by_lang = {}
    for item in items:
        lang = item.get('language', 'unknown')
        by_lang.setdefault(lang, []).append(item)

    # Show fenced blocks grouped by language
    for lang in sorted(by_lang.keys()):
        if lang == 'inline':
            continue

        lang_items = by_lang[lang]
        print(f"\n  {lang.capitalize()} ({len(lang_items)} blocks):")

        for item in lang_items:
            _format_fenced_block(item, path, output_format)

    # Show inline code if present
    if 'inline' in by_lang:
        _format_inline_code_items(by_lang['inline'], path, output_format)


def _format_related_item(
    item: Dict[str, Any],
    indent: str = "  ",
    output_format: str = "text"
) -> None:
    """Format and display a single related document.

    Args:
        item: Related document info dict
        indent: Indentation prefix
        output_format: Output format ('grep' or default)
    """
    path = item.get('path', '?')
    exists = item.get('exists', False)
    headings = item.get('headings', [])
    error = item.get('error')
    nested_related = item.get('related', [])

    # Status indicator
    if not exists:
        status = "✗ NOT FOUND"
    elif error:
        status = f"⚠ {error}"
    else:
        status = "✓"

    print(f"{indent}{path} {status}")

    # Show headings if available
    if headings and exists and not error:
        print(f"{indent}  Headings ({len(headings)}):")
        for heading in headings[:5]:
            print(f"{indent}    - {heading}")
        if len(headings) > 5:
            print(f"{indent}    ... and {len(headings) - 5} more")

    # Show nested related docs (for depth=2)
    if nested_related:
        print(f"{indent}  Related ({len(nested_related)}):")
        for nested in nested_related:
            _format_related_item(nested, indent=indent + "    ", output_format=output_format)


def _count_related_stats(items: List[Dict[str, Any]], depth: int = 1) -> Dict[str, int]:
    """Count total docs and max depth in related tree.

    Args:
        items: List of related document info dicts
        depth: Current depth level

    Returns:
        Dict with 'total' count and 'max_depth'
    """
    total = len(items)
    max_depth = depth if items else 0

    for item in items:
        nested = item.get('related', [])
        if nested:
            nested_stats = _count_related_stats(nested, depth + 1)
            total += nested_stats['total']
            max_depth = max(max_depth, nested_stats['max_depth'])

    return {'total': total, 'max_depth': max_depth}


def _format_related_flat(
    items: List[Dict[str, Any]], seen: Optional[set] = None
) -> List[str]:
    """Extract flat list of paths from related tree (grep-friendly).

    Args:
        items: List of related document info dicts
        seen: Set of already-seen paths (for deduplication)

    Returns:
        List of unique resolved paths
    """
    if seen is None:
        seen = set()

    paths = []
    for item in items:
        resolved = item.get('resolved_path') or item.get('path', '')
        if resolved and resolved not in seen:
            seen.add(resolved)
            paths.append(resolved)
            nested = item.get('related', [])
            if nested:
                paths.extend(_format_related_flat(nested, seen))

    return paths


def _format_related(
    items: List[Dict[str, Any]], path: Path, output_format: str,
    flat: bool = False, show_summary: bool = True
) -> None:
    """Format and display related documents from front matter.

    Args:
        items: List of related document info dicts
        path: Source file path
        output_format: Output format ('grep', 'json', or default)
        flat: If True, output only paths (grep-friendly)
        show_summary: If True, show summary header for multi-level trees
    """
    if not items:
        print("  (No related documents found in front matter)")
        return

    # Flat output mode - just paths
    if flat:
        paths = _format_related_flat(items)
        for p in paths:
            print(p)
        return

    if output_format == 'grep':
        for item in items:
            rel_path = item.get('path', '?')
            exists = "EXISTS" if item.get('exists', False) else "MISSING"
            print(f"{path}:related:{rel_path}:{exists}")
        return

    # Show summary header for deep traversals
    stats = _count_related_stats(items)
    if show_summary and stats['max_depth'] > 1:
        print(f"  ({stats['total']} docs across {stats['max_depth']} levels)")

    # Default text format
    for i, item in enumerate(items, 1):
        print(f"\n  {i}. ", end="")
        _format_related_item(item, indent="     ", output_format=output_format)


def _format_script_summary(script: Dict[str, Any]) -> None:
    """Format and display a single script summary.

    Args:
        script: Script dict with type, src, and preview
    """
    if script['type'] == 'external':
        print(f"    [external] {script['src']}")
        return

    preview = script.get('preview', '')
    if preview:
        print(f"    [inline] {preview[:60]}...")
    else:
        print(f"    [inline]")


def _format_html_metadata(
    metadata: Dict[str, Any], path: Path, output_format: str
) -> None:
    """Format and display HTML metadata (SEO, social, etc.)."""
    # Title
    if 'title' in metadata:
        print(f"  Title: {metadata['title']}")

    # Meta tags
    if 'meta' in metadata:
        print(f"\n  Meta Tags ({len(metadata['meta'])}):")
        for name, content in metadata['meta'].items():
            if len(content) > 80:
                print(f"    {name}: {content[:77]}...")
            else:
                print(f"    {name}: {content}")

    # Canonical URL
    if 'canonical' in metadata:
        print(f"\n  Canonical: {metadata['canonical']}")

    # Stylesheets
    if 'stylesheets' in metadata:
        print(f"\n  Stylesheets ({len(metadata['stylesheets'])}):")
        for stylesheet in metadata['stylesheets']:
            print(f"    {stylesheet}")

    # Scripts
    if 'scripts' in metadata:
        print(f"\n  Scripts ({len(metadata['scripts'])}):")
        for script in metadata['scripts']:
            _format_script_summary(script)


def _format_script_element(
    elem: Dict[str, Any], path: Path, line: int
) -> None:
    """Format and display a script element.

    Args:
        elem: Script element dict
        path: File path (kept for API compatibility, not displayed - shown in header)
        line: Line number
    """
    if elem['type'] == 'external':
        print(f"  :{line:<6} [external] {elem['src']}")
        return

    preview = elem.get('preview', '')
    if preview:
        print(f"  :{line:<6} [inline] {preview[:60]}...")
    else:
        print(f"  :{line:<6} [inline]")


def _format_style_element(
    elem: Dict[str, Any], path: Path, line: int
) -> None:
    """Format and display a style element.

    Args:
        elem: Style element dict
        path: File path (kept for API compatibility, not displayed - shown in header)
        line: Line number
    """
    if elem['type'] == 'external':
        print(f"  :{line:<6} [external] {elem['href']}")
        return

    preview = elem.get('preview', '')
    if preview:
        print(f"  :{line:<6} [inline] {preview[:60]}...")
    else:
        print(f"  :{line:<6} [inline]")


def _format_semantic_element(
    elem: Dict[str, Any], path: Path, line: int
) -> None:
    """Format and display a semantic element.

    Args:
        elem: Semantic element dict
        path: File path (kept for API compatibility, not displayed - shown in header)
        line: Line number
    """
    tag = elem.get('tag', '')
    attrs = elem.get('attributes', {})
    elem_id = attrs.get('id', '')
    elem_class_attr = attrs.get('class', '')

    # Build class string
    if isinstance(elem_class_attr, list):
        elem_class = ' '.join(elem_class_attr)
    else:
        elem_class = elem_class_attr

    # Build label
    label = f"<{tag}>"
    if elem_id:
        label += f" #{elem_id}"
    elif elem_class:
        first_class = elem_class.split()[0] if elem_class else ''
        label += f" .{first_class}"

    print(f"  :{line:<6} {label}")


def _format_html_elements(
    elements: List[Dict[str, Any]],
    path: Path,
    output_format: str,
    category: str
) -> None:
    """Format and display HTML elements (scripts, styles, semantic)."""
    for elem in elements:
        line = elem.get('line', '?')

        if category == 'scripts':
            _format_script_element(elem, path, line)
        elif category == 'styles':
            _format_style_element(elem, path, line)
        elif category == 'semantic':
            _format_semantic_element(elem, path, line)


def _format_standard_items(
    items: List[Dict[str, Any]], path: Path, output_format: str
) -> None:
    """Format and display standard items (functions, classes, etc.)."""
    for item in items:
        line = item.get('line', '?')
        name = item.get('name', '')
        signature = item.get('signature', '')
        content = item.get('content', '')

        # Build metrics display (if available)
        metrics = ''
        if 'line_count' in item or 'depth' in item:
            parts = []
            if 'line_count' in item:
                parts.append(f"{item['line_count']} lines")
            if 'depth' in item:
                parts.append(f"depth:{item['depth']}")
            if parts:
                metrics = f" [{', '.join(parts)}]"

        # Format based on what's available
        # Note: path is already shown in file header, so text format omits it
        if signature and name:
            if output_format == 'grep':
                print(f"{path}:{line}:{name}{signature}")
            else:
                print(f"  :{line:<6} {name}{signature}{metrics}")
        elif name:
            if output_format == 'grep':
                print(f"{path}:{line}:{name}")
            else:
                print(f"  :{line:<6} {name}{metrics}")
        elif content:
            if output_format == 'grep':
                print(f"{path}:{line}:{content}")
            else:
                print(f"  :{line:<6} {content}")


def _format_csv_schema(items: List[Dict[str, Any]]) -> None:
    """Format CSV schema with column types and stats."""
    for item in items:
        name = item.get('name', '?')
        dtype = item.get('type', 'unknown')
        missing_pct = item.get('missing_pct', 0)
        unique = item.get('unique_count', '?')

        # Build info string
        info_parts = [dtype]
        if missing_pct > 0:
            info_parts.append(f"{missing_pct}% missing")
        info_parts.append(f"{unique} unique")

        samples = item.get('sample_values', [])
        sample_str = ''
        if samples:
            # Truncate long sample values
            truncated = [s[:20] + '...' if len(str(s)) > 20 else str(s) for s in samples[:3]]
            sample_str = f" → {', '.join(truncated)}"

        print(f"  {name:<20} ({', '.join(info_parts)}){sample_str}")


def _format_xml_children(items: List[Dict[str, Any]], indent: int = 1) -> None:
    """Format XML children with nested structure."""
    for item in items:
        tag = item.get('tag', '?')
        attrs = item.get('attributes', {})
        text = item.get('text', '')
        children = item.get('children', [])
        child_count = item.get('child_count', 0)

        # Build attribute string
        attr_str = ''
        if attrs:
            attr_parts = [f'{k}="{v}"' for k, v in list(attrs.items())[:3]]
            if len(attrs) > 3:
                attr_parts.append('...')
            attr_str = ' ' + ' '.join(attr_parts)

        # Build content hint
        content_hint = ''
        if text:
            # Show truncated text content
            text_preview = text[:30] + '...' if len(text) > 30 else text
            content_hint = f' → "{text_preview}"'
        elif child_count > 0:
            content_hint = f' ({child_count} children)'

        prefix = '  ' * indent
        print(f"{prefix}<{tag}{attr_str}>{content_hint}")

        # Recursively show nested children (limit depth)
        if children and indent < 3:
            _format_xml_children(children, indent + 1)


def _add_navigation_kwargs(kwargs: Dict[str, Any], args) -> None:
    """Add navigation/slicing arguments to kwargs.

    Args:
        kwargs: Dict to update with navigation args
        args: Command-line arguments
    """
    if not args:
        return

    if getattr(args, 'head', None):
        kwargs['head'] = args.head
    if getattr(args, 'tail', None):
        kwargs['tail'] = args.tail
    if getattr(args, 'range', None):
        kwargs['range'] = args.range


def _add_markdown_link_kwargs(kwargs: Dict[str, Any], args) -> None:
    """Add markdown link extraction arguments to kwargs.

    Args:
        kwargs: Dict to update with link args
        args: Command-line arguments
    """
    if not (args.links or args.link_type or args.domain):
        return

    kwargs['extract_links'] = True
    if args.link_type:
        kwargs['link_type'] = args.link_type
    if args.domain:
        kwargs['domain'] = args.domain


def _add_markdown_code_kwargs(kwargs: Dict[str, Any], args) -> None:
    """Add markdown code extraction arguments to kwargs.

    Args:
        kwargs: Dict to update with code args
        args: Command-line arguments
    """
    if not (args.code or args.language or args.inline):
        return

    kwargs['extract_code'] = True
    if args.language:
        kwargs['language'] = args.language
    if args.inline:
        kwargs['inline_code'] = args.inline


def _add_html_kwargs(kwargs: Dict[str, Any], args) -> None:
    """Add HTML-specific arguments to kwargs.

    Args:
        kwargs: Dict to update with HTML args
        args: Command-line arguments
    """
    if not (args.metadata or args.semantic or args.scripts or args.styles):
        return

    if args.metadata:
        kwargs['metadata'] = True
    if args.semantic:
        kwargs['semantic'] = args.semantic
    if args.scripts:
        kwargs['scripts'] = args.scripts
    if args.styles:
        kwargs['styles'] = args.styles


def _build_analyzer_kwargs(analyzer: FileAnalyzer, args) -> Dict[str, Any]:
    """Build kwargs for get_structure() based on analyzer type and args.

    Refactored to reduce complexity from 40 → ~10 by extracting helpers.

    Args:
        analyzer: File analyzer instance
        args: Command-line arguments

    Returns:
        Dict of kwargs for get_structure()
    """
    kwargs = {}

    # Navigation/slicing arguments (apply to all analyzers)
    _add_navigation_kwargs(kwargs, args)

    # Markdown-specific filters
    if args and hasattr(analyzer, '_extract_links'):
        _add_markdown_link_kwargs(kwargs, args)
        _add_markdown_code_kwargs(kwargs, args)

        if args.frontmatter:
            kwargs['extract_frontmatter'] = True

        # Handle --related-all shorthand
        if getattr(args, 'related_all', False):
            kwargs['extract_related'] = True
            kwargs['related_depth'] = 0  # unlimited
            kwargs['related_limit'] = getattr(args, 'related_limit', 100)
        elif getattr(args, 'related', False):
            kwargs['extract_related'] = True
            kwargs['related_depth'] = getattr(args, 'related_depth', 1)
            kwargs['related_limit'] = getattr(args, 'related_limit', 100)

    # HTML-specific filters
    if args and hasattr(analyzer, '_extract_metadata'):
        _add_html_kwargs(kwargs, args)

        # HTML also supports --links (reuse from markdown)
        if args.links or args.link_type or args.domain:
            kwargs['links'] = True
            if args.link_type:
                kwargs['link_type'] = args.link_type
            if args.domain:
                kwargs['domain'] = args.domain

    return kwargs
