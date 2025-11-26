"""Clean, simple CLI for reveal."""

import sys
import os
import argparse
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from .base import get_analyzer, get_all_analyzers, FileAnalyzer
from .tree_view import show_directory_tree
from . import __version__


def check_for_updates():
    """Check PyPI for newer version (once per day, non-blocking).

    - Checks at most once per day (cached in ~/.config/reveal/last_update_check)
    - 1-second timeout (doesn't slow down CLI)
    - Fails silently (no errors shown to user)
    - Opt-out: Set REVEAL_NO_UPDATE_CHECK=1 environment variable
    """
    # Opt-out check
    if os.environ.get('REVEAL_NO_UPDATE_CHECK'):
        return

    try:
        # Setup cache directory
        cache_dir = Path.home() / '.config' / 'reveal'
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / 'last_update_check'

        # Check if we should update (once per day)
        if cache_file.exists():
            last_check_str = cache_file.read_text().strip()
            try:
                last_check = datetime.fromisoformat(last_check_str)
                if datetime.now() - last_check < timedelta(days=1):
                    return  # Checked recently, skip
            except (ValueError, OSError):
                pass  # Invalid cache, continue with check

        # Check PyPI (using urllib to avoid new dependencies)
        import urllib.request
        import json

        req = urllib.request.Request(
            'https://pypi.org/pypi/reveal-cli/json',
            headers={'User-Agent': f'reveal-cli/{__version__}'}
        )

        with urllib.request.urlopen(req, timeout=1) as response:
            data = json.loads(response.read().decode('utf-8'))
            latest_version = data['info']['version']

        # Update cache file
        cache_file.write_text(datetime.now().isoformat())

        # Compare versions (simple string comparison works for semver)
        if latest_version != __version__:
            # Parse versions for proper comparison
            def parse_version(v):
                return tuple(map(int, v.split('.')))

            try:
                if parse_version(latest_version) > parse_version(__version__):
                    print(f"⚠️  Update available: reveal {latest_version} (you have {__version__})")
                    print(f"Update available: pip install --upgrade reveal-cli\n")
            except (ValueError, AttributeError):
                pass  # Version comparison failed, ignore

    except Exception:
        # Fail silently - don't interrupt user's workflow
        pass


def main():
    """Main CLI entry point."""
    # Fix Windows console encoding for emoji/unicode support
    if sys.platform == 'win32':
        # Set environment variable for subprocess compatibility
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
        # Reconfigure stdout/stderr to use UTF-8 with error handling
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    _main_impl()


def _build_help_epilog() -> str:
    """Build dynamic help with conditional jq examples."""
    import shutil

    has_jq = shutil.which('jq') is not None

    base_help = '''
Examples:
  # Basic structure exploration
  reveal src/                    # Directory tree
  reveal app.py                  # Show structure with metrics
  reveal app.py --meta           # File metadata

  # God function detection (find complex code!)
  reveal main.py --god           # Show only god functions (>50 lines or >4 depth)
  reveal src/**/*.py --god       # Find all god functions in project

  # Hierarchical outline (see structure as a tree!)
  reveal app.py --outline        # Classes with methods, nested structures
  reveal app.py --outline --god  # Outline showing only complex functions

  # Element extraction
  reveal app.py load_config      # Extract specific function
  reveal app.py Database         # Extract class definition

  # Output formats
  reveal app.py --format=json    # JSON for scripting
  reveal app.py --format=grep    # Pipeable format

  # Pipeline workflows (Unix composability!)
  find src/ -name "*.py" | reveal --stdin --god
  git diff --name-only | reveal --stdin --outline
  git ls-files "*.ts" | reveal --stdin --format=json
  ls src/*.py | reveal --stdin
'''

    if has_jq:
        base_help += '''
  # Advanced filtering with jq (powerful!)
  reveal app.py --format=json | jq '.functions[] | select(.line_count > 100)'
  reveal app.py --format=json | jq '.functions[] | select(.depth > 3)'
  reveal app.py --format=json | jq '.functions[] | select(.line_count > 50 and .depth > 2)'
  reveal src/**/*.py --format=json | jq -r '.functions[] | "\\(.file):\\(.line) \\(.name) [\\(.line_count) lines]"'

  # Pipeline + jq (combine the power!)
  find . -name "*.py" | reveal --stdin --format=json | jq '.functions[] | select(.line_count > 100)'
  git diff --name-only | grep "\\.py$" | reveal --stdin --god --format=grep
'''

    base_help += '''
Perfect filename:line format - works with vim, git, grep, sed, awk!
Metrics: All code files show [X lines, depth:Y] for complexity analysis
stdin: Reads file paths from stdin (one per line) - works with find, git, ls, etc.
'''

    return base_help


def _main_impl():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Reveal: Explore code semantically - The simplest way to understand code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_build_help_epilog()
    )

    parser.add_argument('path', nargs='?', help='File or directory to reveal')
    parser.add_argument('element', nargs='?', help='Element to extract (function, class, etc.)')

    # Optional flags
    parser.add_argument('--version', action='version', version=f'reveal {__version__}')
    parser.add_argument('--list-supported', '-l', action='store_true',
                        help='List all supported file types')
    parser.add_argument('--stdin', action='store_true',
                        help='Read file paths from stdin (one per line) - enables Unix pipeline workflows')
    parser.add_argument('--meta', action='store_true', help='Show metadata only')
    parser.add_argument('--format', choices=['text', 'json', 'grep'], default='text',
                        help='Output format (text, json, grep)')
    parser.add_argument('--no-fallback', action='store_true',
                        help='Disable TreeSitter fallback for unknown file types')
    parser.add_argument('--depth', type=int, default=3, help='Directory tree depth (default: 3)')
    parser.add_argument('--god', action='store_true',
                        help='Show only god functions/elements (high complexity or length)')
    parser.add_argument('--outline', action='store_true',
                        help='Show hierarchical outline (classes with methods, nested structures)')

    # Markdown entity filters
    parser.add_argument('--links', action='store_true',
                        help='Extract links from markdown files')
    parser.add_argument('--link-type', choices=['internal', 'external', 'email', 'all'],
                        help='Filter links by type (requires --links)')
    parser.add_argument('--domain', type=str,
                        help='Filter links by domain (requires --links)')

    parser.add_argument('--code', action='store_true',
                        help='Extract code blocks from markdown files')
    parser.add_argument('--language', type=str,
                        help='Filter code blocks by language (requires --code)')
    parser.add_argument('--inline', action='store_true',
                        help='Include inline code snippets (requires --code)')

    args = parser.parse_args()

    # Check for updates (once per day, non-blocking, opt-out available)
    check_for_updates()

    # Handle --list-supported
    if args.list_supported:
        list_supported_types()
        sys.exit(0)

    # Handle --stdin (read file paths from stdin)
    if args.stdin:
        if args.element:
            print("Error: Cannot use element extraction with --stdin", file=sys.stderr)
            sys.exit(1)

        # Read file paths from stdin (one per line)
        for line in sys.stdin:
            file_path = line.strip()
            if not file_path:
                continue  # Skip empty lines

            path = Path(file_path)

            # Skip if path doesn't exist (graceful degradation)
            if not path.exists():
                print(f"Warning: {file_path} not found, skipping", file=sys.stderr)
                continue

            # Skip directories (only process files)
            if path.is_dir():
                print(f"Warning: {file_path} is a directory, skipping (use reveal {file_path}/ directly)", file=sys.stderr)
                continue

            # Process the file
            if path.is_file():
                handle_file(str(path), None, args.meta, args.format, args)

        sys.exit(0)

    # Path is required if not using --list-supported or --stdin
    if not args.path:
        parser.print_help()
        sys.exit(1)

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
        handle_file(str(path), args.element, args.meta, args.format, args)

    else:
        print(f"Error: {args.path} is neither file nor directory", file=sys.stderr)
        sys.exit(1)


def list_supported_types():
    """List all supported file types."""
    analyzers = get_all_analyzers()

    if not analyzers:
        print("No file types registered")
        return

    print(f"Reveal v{__version__} - Supported File Types\n")

    # Sort by name for nice display
    sorted_analyzers = sorted(analyzers.items(), key=lambda x: x[1]['name'])

    print("Built-in Analyzers:")
    for ext, info in sorted_analyzers:
        name = info['name']
        print(f"  {name:20s} {ext}")

    print(f"\nTotal: {len(analyzers)} file types with full support")

    # Probe tree-sitter for additional languages
    try:
        import warnings
        warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')

        from tree_sitter_languages import get_language

        # Common languages to check (extension -> language name mapping)
        fallback_languages = {
            '.java': ('java', 'Java'),
            '.c': ('c', 'C'),
            '.cpp': ('cpp', 'C++'),
            '.cc': ('cpp', 'C++'),
            '.cxx': ('cpp', 'C++'),
            '.h': ('c', 'C/C++ Header'),
            '.hpp': ('cpp', 'C++ Header'),
            '.cs': ('c_sharp', 'C#'),
            '.rb': ('ruby', 'Ruby'),
            '.php': ('php', 'PHP'),
            '.swift': ('swift', 'Swift'),
            '.kt': ('kotlin', 'Kotlin'),
            '.scala': ('scala', 'Scala'),
            '.lua': ('lua', 'Lua'),
            '.hs': ('haskell', 'Haskell'),
            '.elm': ('elm', 'Elm'),
            '.ocaml': ('ocaml', 'OCaml'),
            '.ml': ('ocaml', 'OCaml'),
        }

        # Filter out languages already registered
        available_fallbacks = []
        for ext, (lang, display_name) in fallback_languages.items():
            if ext not in analyzers:  # Not already registered
                try:
                    get_language(lang)
                    available_fallbacks.append((display_name, ext))
                except:
                    pass

        if available_fallbacks:
            print("\nTree-Sitter Auto-Supported (basic):")
            for name, ext in sorted(available_fallbacks):
                print(f"  {name:20s} {ext}")
            print(f"\nTotal: {len(available_fallbacks)} additional languages via fallback")
            print("Note: These work automatically but may have basic support.")
            print("Note: Contributions for full analyzers welcome!")

    except Exception:
        # tree-sitter-languages not available or probe failed
        pass

    print(f"\nUsage: reveal <file>")
    print(f"Help: reveal --help")


def handle_file(path: str, element: Optional[str], show_meta: bool, output_format: str, args=None):
    """Handle file analysis.

    Args:
        path: File path
        element: Optional element to extract
        show_meta: Whether to show metadata only
        output_format: Output format ('text', 'json', 'grep')
        args: Full argument namespace (for filter options)
    """
    # Get analyzer
    # Check fallback setting
    allow_fallback = not getattr(args, 'no_fallback', False) if args else True

    analyzer_class = get_analyzer(path, allow_fallback=allow_fallback)
    if not analyzer_class:
        ext = Path(path).suffix or '(no extension)'
        print(f"Error: No analyzer found for {path} ({ext})", file=sys.stderr)
        print(f"\nError: File type '{ext}' is not supported yet", file=sys.stderr)
        print(f"Run 'reveal --list-supported' to see all supported file types", file=sys.stderr)
        print(f"Visit https://github.com/scottsen/reveal to request new file types", file=sys.stderr)
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
    show_structure(analyzer, output_format, args)


def show_metadata(analyzer: FileAnalyzer, output_format: str):
    """Show file metadata."""
    meta = analyzer.get_metadata()

    if output_format == 'json':
        import json
        print(json.dumps(meta, indent=2))
    else:
        print(f"File: {meta['name']}\n")
        print(f"Path:     {meta['path']}")
        print(f"Size:     {meta['size_human']}")
        print(f"Lines:    {meta['lines']}")
        print(f"Encoding: {meta['encoding']}")
        print(f"\n→ reveal {meta['path']}")


def is_god_element(item: dict, analyzer: FileAnalyzer) -> bool:
    """Check if element exceeds god thresholds.

    Uses analyzer-specific thresholds (each file type defines what's "too complex").
    """
    thresholds = analyzer.god_thresholds

    # Check line count threshold
    if 'line_count' in item and 'line_count' in thresholds:
        if item['line_count'] > thresholds['line_count']:
            return True

    # Check nesting depth threshold
    if 'depth' in item and 'depth' in thresholds:
        if item['depth'] > thresholds['depth']:
            return True

    return False


def build_hierarchy(structure: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Build hierarchical tree from flat structure.

    Args:
        structure: Flat structure from analyzer (imports, functions, classes)

    Returns:
        List of root-level items with 'children' added
    """
    # Collect all items with parent info
    all_items = []

    for category, items in structure.items():
        for item in items:
            item = item.copy()  # Don't mutate original
            item['category'] = category
            item['children'] = []
            all_items.append(item)

    # Sort by line number
    all_items.sort(key=lambda x: x.get('line', 0))

    # Build parent-child relationships based on line ranges
    # An item is a child if it's within another item's line range
    for i, item in enumerate(all_items):
        item_start = item.get('line', 0)
        item_end = item.get('line_end', item_start)

        # Find potential parent (previous item that contains this one)
        parent = None
        for j in range(i - 1, -1, -1):
            candidate = all_items[j]
            candidate_start = candidate.get('line', 0)
            candidate_end = candidate.get('line_end', candidate_start)

            # Check if candidate contains this item
            if candidate_start < item_start and candidate_end >= item_end:
                # Found a containing item - use most recent (closest parent)
                parent = candidate
                break

        # Add to parent's children or mark as root
        if parent:
            parent['children'].append(item)
            item['is_child'] = True
        else:
            item['is_child'] = False

    # Return only root-level items
    return [item for item in all_items if not item.get('is_child', False)]


def render_outline(items: List[Dict[str, Any]], path: Path, indent: str = '', is_root: bool = True) -> None:
    """Render hierarchical outline with tree characters.

    Args:
        items: List of items (potentially with children)
        path: File path for line number display
        indent: Current indentation prefix
        is_root: Whether these are root-level items
    """
    if not items:
        return

    for i, item in enumerate(items):
        is_last_item = (i == len(items) - 1)

        # Format item
        line = item.get('line', '?')
        name = item.get('name', '')
        signature = item.get('signature', '')

        # Build metrics display
        metrics = ''
        if 'line_count' in item or 'depth' in item:
            parts = []
            if 'line_count' in item:
                parts.append(f"{item['line_count']} lines")
            if 'depth' in item:
                parts.append(f"depth:{item['depth']}")
            if parts:
                metrics = f" [{', '.join(parts)}]"

        # Format output
        if signature and name:
            display = f"{name}{signature}{metrics}"
        elif name:
            display = f"{name}{metrics}"
        else:
            display = item.get('content', '?')

        # Print item with appropriate prefix
        if is_root:
            # Root items - no tree chars, show full path
            print(f"{display} ({path}:{line})")
        else:
            # Child items - use tree chars
            tree_char = '└─ ' if is_last_item else '├─ '
            print(f"{indent}{tree_char}{display} (line {line})")

        # Recursively render children
        if item.get('children'):
            if is_root:
                # Children of root get minimal indent
                child_indent = '  '
            else:
                # Children of nested items continue the tree
                child_indent = indent + ('   ' if is_last_item else '│  ')
            render_outline(item['children'], path, child_indent, is_root=False)


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
                    print(f"    ❌ Line {line:<4} [{text}]({url}) [BROKEN]")
                else:
                    if link_type == 'external':
                        domain = item.get('domain', '')
                        print(f"    Line {line:<4} [{text}]({url})")
                        if domain:
                            print(f"             → {domain}")
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


def show_structure(analyzer: FileAnalyzer, output_format: str, args=None):
    """Show file structure."""
    # Build kwargs for get_structure based on analyzer type and args
    kwargs = {}

    # Check if this is a Markdown analyzer and if filters are requested
    if args and hasattr(analyzer, '_extract_links'):
        # This is a markdown analyzer
        if args.links or args.link_type or args.domain:
            kwargs['extract_links'] = True
            if args.link_type:
                kwargs['link_type'] = args.link_type
            if args.domain:
                kwargs['domain'] = args.domain

        if args.code or args.language or args.inline:
            kwargs['extract_code'] = True
            if args.language:
                kwargs['language'] = args.language
            if args.inline:
                kwargs['inline_code'] = args.inline

    structure = analyzer.get_structure(**kwargs)
    path = analyzer.path

    # Apply god filter if requested
    if args and args.god:
        filtered_structure = {}
        for category, items in structure.items():
            god_items = [item for item in items if is_god_element(item, analyzer)]
            if god_items:
                filtered_structure[category] = god_items
        structure = filtered_structure

    # Check if this is a fallback analyzer
    is_fallback = getattr(analyzer, 'is_fallback', False)
    fallback_lang = getattr(analyzer, 'fallback_language', None)

    # Handle outline mode
    if args and getattr(args, 'outline', False):
        # Show file header
        if is_fallback:
            print(f"File: {path.name} (fallback: {fallback_lang})\n")
        else:
            print(f"File: {path.name}\n")

        if not structure:
            print("No structure available for this file type")
            return

        # Build hierarchy and render as tree
        hierarchy = build_hierarchy(structure)
        render_outline(hierarchy, path)
        return

    if output_format == 'json':
        import json
        result = {
            'file': str(path),
            'type': analyzer.__class__.__name__.replace('Analyzer', '').lower(),
            'analyzer': {
                'type': 'fallback' if is_fallback else 'explicit',
                'language': fallback_lang if is_fallback else None,
                'explicit': not is_fallback,
                'name': analyzer.__class__.__name__
            },
            'structure': structure
        }
        print(json.dumps(result, indent=2))
        return

    if not structure:
        if is_fallback:
            print(f"File: {path.name} (fallback: {fallback_lang})\n")
        else:
            print(f"File: {path.name}\n")
        print("No structure available for this file type")
        return

    # Show file header with fallback indicator
    if is_fallback:
        print(f"File: {path.name} (fallback: {fallback_lang})\n")
    else:
        print(f"File: {path.name}\n")

    # Show each category
    for category, items in structure.items():
        if not items:
            continue

        # Format category name (e.g., 'functions' → 'Functions')
        category_name = category.capitalize()
        print(f"{category_name} ({len(items)}):")

        # Special handling for links
        if category == 'links':
            _format_links(items, path, output_format)

        elif category == 'code_blocks':
            _format_code_blocks(items, path, output_format)

        else:
            _format_standard_items(items, path, output_format)

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
