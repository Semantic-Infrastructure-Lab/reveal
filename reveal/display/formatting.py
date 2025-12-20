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


def _format_links(items: List[Dict[str, Any]], path: Path, output_format: str) -> None:
    """Format and display link items grouped by type."""
    by_type = {}
    for item in items:
        link_type = item.get('type', 'unknown')
        by_type.setdefault(link_type, []).append(item)

    for link_type in ['external', 'internal', 'email']:
        if link_type not in by_type:
            continue

        type_items = by_type[link_type]
        print(f"\n  {link_type.capitalize()} ({len(type_items)}):")

        for item in type_items:
            line = item.get('line', '?')
            text = item.get('text', '')
            url = item.get('url', '')
            broken = item.get('broken', False)

            if output_format == 'grep':
                print(f"{path}:{line}:{url}")
            else:
                if broken:
                    print(f"    X Line {line:<4} [{text}]({url}) [BROKEN]")
                else:
                    if link_type == 'external':
                        domain = item.get('domain', '')
                        print(f"    Line {line:<4} [{text}]({url})")
                        if domain:
                            print(f"             -> {domain}")
                    else:
                        print(f"    Line {line:<4} [{text}]({url})")


def _format_code_blocks(items: List[Dict[str, Any]], path: Path, output_format: str) -> None:
    """Format and display code block items grouped by language."""
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
            line_start = item.get('line_start', '?')
            line_end = item.get('line_end', '?')
            line_count = item.get('line_count', 0)
            source = item.get('source', '')

            if output_format == 'grep':
                first_line = source.split('\n')[0] if source else ''
                print(f"{path}:{line_start}:{first_line}")
            else:
                print(f"    Lines {line_start}-{line_end} ({line_count} lines)")
                preview_lines = source.split('\n')[:3]
                for preview_line in preview_lines:
                    print(f"      {preview_line}")
                if line_count > 3:
                    print(f"      ... ({line_count - 3} more lines)")

    # Show inline code if present
    if 'inline' in by_lang:
        inline_items = by_lang['inline']
        print(f"\n  Inline code ({len(inline_items)} snippets):")
        for item in inline_items[:10]:
            line = item.get('line', '?')
            source = item.get('source', '')
            if output_format == 'grep':
                print(f"{path}:{line}:{source}")
            else:
                print(f"    Line {line:<4} `{source}`")
        if len(inline_items) > 10:
            print(f"    ... and {len(inline_items) - 10} more")


def _format_standard_items(items: List[Dict[str, Any]], path: Path, output_format: str) -> None:
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
        if signature and name:
            if output_format == 'grep':
                print(f"{path}:{line}:{name}{signature}")
            else:
                print(f"  {path}:{line:<6} {name}{signature}{metrics}")
        elif name:
            if output_format == 'grep':
                print(f"{path}:{line}:{name}")
            else:
                print(f"  {path}:{line:<6} {name}{metrics}")
        elif content:
            if output_format == 'grep':
                print(f"{path}:{line}:{content}")
            else:
                print(f"  {path}:{line:<6} {content}")


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

    return kwargs
