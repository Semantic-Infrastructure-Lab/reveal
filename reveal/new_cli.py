"""Clean, simple CLI for reveal."""

import sys
import argparse
from pathlib import Path
from typing import Optional
from .base import get_analyzer, FileAnalyzer
from .tree_view import show_directory_tree


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Reveal: Explore code semantically',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  reveal src/                    # Show directory tree
  reveal app.py                  # Show file structure
  reveal app.py load_config      # Extract function
  reveal app.py --meta           # Show metadata only
  reveal app.py --format=json    # JSON output
        '''
    )

    parser.add_argument('path', help='File or directory to reveal')
    parser.add_argument('element', nargs='?', help='Element to extract (function, class, etc.)')

    # Optional flags
    parser.add_argument('--meta', action='store_true', help='Show metadata only')
    parser.add_argument('--format', choices=['text', 'json', 'grep'], default='text',
                        help='Output format')
    parser.add_argument('--depth', type=int, default=3, help='Directory tree depth (default: 3)')

    args = parser.parse_args()

    # Check if path exists
    path = Path(args.path)
    if not path.exists():
        print(f"Error: {args.path} not found", file=sys.stderr)
        sys.exit(1)

    # Route based on path type
    if path.is_dir():
        # Directory → show tree
        output = show_directory_tree(str(path), depth=args.depth)
        print(output)

    elif path.is_file():
        # File → show structure or extract element
        handle_file(str(path), args.element, args.meta, args.format)

    else:
        print(f"Error: {args.path} is neither file nor directory", file=sys.stderr)
        sys.exit(1)


def handle_file(path: str, element: Optional[str], show_meta: bool, output_format: str):
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
    """
    # Get analyzer
    analyzer_class = get_analyzer(path)
    if not analyzer_class:
        print(f"Error: No analyzer found for {path}", file=sys.stderr)
        print("Hint: File type not supported yet", file=sys.stderr)
        sys.exit(1)

    analyzer = analyzer_class(path)

    # Show metadata only?
    if show_meta:
        show_metadata(analyzer, output_format)
        return

    # Extract specific element?
    if element:
        extract_element(analyzer, element, output_format)
        return

    # Default: show structure
    show_structure(analyzer, output_format)


def show_metadata(analyzer: FileAnalyzer, output_format: str):
    """Show file metadata."""
    meta = analyzer.get_metadata()

    if output_format == 'json':
        import json
        print(json.dumps(meta, indent=2))
    else:
        print(f"📄 {meta['name']}\n")
        print(f"Path:     {meta['path']}")
        print(f"Size:     {meta['size_human']}")
        print(f"Lines:    {meta['lines']}")
        print(f"Encoding: {meta['encoding']}")
        print(f"\n→ reveal {meta['path']}")


def show_structure(analyzer: FileAnalyzer, output_format: str):
    """Show file structure."""
    structure = analyzer.get_structure()
    path = analyzer.path

    if output_format == 'json':
        import json
        print(json.dumps(structure, indent=2))
        return

    if not structure:
        print(f"📄 {path.name}\n")
        print("No structure available for this file type")
        return

    print(f"📄 {path.name}\n")

    # Show each category
    for category, items in structure.items():
        if not items:
            continue

        # Format category name (e.g., 'functions' → 'Functions')
        category_name = category.capitalize()
        print(f"{category_name} ({len(items)}):")

        for item in items:
            line = item.get('line', '?')
            name = item.get('name', '')
            signature = item.get('signature', '')
            content = item.get('content', '')

            # Format based on what's available
            if signature and name:
                # Function with signature
                if output_format == 'grep':
                    print(f"{path}:{line}:{name}{signature}")
                else:
                    print(f"  {path}:{line:<6} {name}{signature}")
            elif name:
                # Just name (class, struct, etc.)
                if output_format == 'grep':
                    print(f"{path}:{line}:{name}")
                else:
                    print(f"  {path}:{line:<6} {name}")
            elif content:
                # Just content (import, etc.)
                if output_format == 'grep':
                    print(f"{path}:{line}:{content}")
                else:
                    print(f"  {path}:{line:<6} {content}")

        print()  # Blank line between categories

    # Navigation hints
    if output_format == 'text':
        print(f"→ reveal {path} <element>")
        print(f"→ vim {path}:<line>")


def extract_element(analyzer: FileAnalyzer, element: str, output_format: str):
    """Extract a specific element.

    Args:
        analyzer: File analyzer
        element: Element name to extract
        output_format: Output format
    """
    # Try common element types
    for element_type in ['function', 'class', 'struct', 'section']:
        result = analyzer.extract_element(element_type, element)
        if result:
            break
    else:
        # Not found
        print(f"Error: Element '{element}' not found in {analyzer.path}", file=sys.stderr)
        sys.exit(1)

    # Format output
    if output_format == 'json':
        import json
        print(json.dumps(result, indent=2))
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
        print(f"\n→ vim {path}:{line_start}")
        print(f"→ reveal {path}")


if __name__ == '__main__':
    main()
