"""Clean, simple CLI for reveal."""

import sys
import os
import argparse
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta, date
from .base import get_analyzer, get_all_analyzers, FileAnalyzer
from .tree_view import show_directory_tree
from . import __version__
import json

# Import utilities from utils module
from .utils import (
    copy_to_clipboard,
    DateTimeEncoder,
    safe_json_dumps,
    get_element_placeholder,
    get_file_type_from_analyzer,
    print_breadcrumbs,
    check_for_updates,
)

# Import renderers from rendering package
from .rendering import (
    render_reveal_structure,
    render_json_result,
    render_env_structure,
    render_env_variable,
    render_ast_structure,
    render_help,
    render_python_structure,
    render_python_element,
)

# Import display functions from display package
from .display import (
    show_structure,
    show_metadata,
    extract_element,
    build_hierarchy,
    build_heading_hierarchy,
    render_outline,
)


def main():
    """Main CLI entry point."""
    import io

    # Fix Windows console encoding for emoji/unicode support
    if sys.platform == 'win32':
        # Set environment variable for subprocess compatibility
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
        # Reconfigure stdout/stderr to use UTF-8 with error handling
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    # Check for --copy flag early (before full parsing)
    copy_mode = '--copy' in sys.argv or '-c' in sys.argv

    if copy_mode:
        # Capture stdout while still displaying it (tee behavior)
        captured_output = io.StringIO()
        original_stdout = sys.stdout

        class TeeWriter:
            """Write to both original stdout and capture buffer."""
            def __init__(self, original, capture):
                self.original = original
                self.capture = capture

            def write(self, data):
                self.original.write(data)
                self.capture.write(data)

            def flush(self):
                self.original.flush()

            # Support attributes like encoding, isatty, etc.
            def __getattr__(self, name):
                return getattr(self.original, name)

        sys.stdout = TeeWriter(original_stdout, captured_output)

    try:
        _main_impl()
    except BrokenPipeError:
        # Python flushes standard streams on exit; redirect remaining output
        # to devnull to avoid another BrokenPipeError at shutdown
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)  # Exit cleanly
    finally:
        if copy_mode:
            sys.stdout = original_stdout
            output_text = captured_output.getvalue()
            if output_text:
                if copy_to_clipboard(output_text):
                    print(f"\n📋 Copied {len(output_text)} chars to clipboard", file=sys.stderr)
                else:
                    print("\n⚠️  Could not copy to clipboard (no clipboard utility found)", file=sys.stderr)
                    print("   Install xclip, xsel (Linux), or use pbcopy (macOS)", file=sys.stderr)


def handle_uri(uri: str, element: Optional[str], args) -> None:
    """Handle URI-based resources (env://, https://, etc.).

    Args:
        uri: Full URI (e.g., env://, env://PATH)
        element: Optional element to extract
        args: Parsed command line arguments
    """
    # Parse URI
    if '://' not in uri:
        print(f"Error: Invalid URI format: {uri}", file=sys.stderr)
        sys.exit(1)

    scheme, resource = uri.split('://', 1)

    # Look up adapter from registry (pluggable!)
    from .adapters.base import get_adapter_class, list_supported_schemes
    from .adapters import env, ast, help, python, json_adapter, reveal  # Import to trigger registration

    adapter_class = get_adapter_class(scheme)
    if not adapter_class:
        print(f"Error: Unsupported URI scheme: {scheme}://", file=sys.stderr)
        schemes = ', '.join(f"{s}://" for s in list_supported_schemes())
        print(f"Supported schemes: {schemes}", file=sys.stderr)
        sys.exit(1)

    # Dispatch to adapter-specific handler
    _handle_adapter(adapter_class, scheme, resource, element, args)


def _handle_adapter(adapter_class: type, scheme: str, resource: str,
                    element: Optional[str], args) -> None:
    """Handle adapter-specific logic for different URI schemes.

    Args:
        adapter_class: The adapter class to instantiate
        scheme: URI scheme (env, ast, etc.)
        resource: Resource part of URI
        element: Optional element to extract
        args: CLI arguments
    """
    # Adapter-specific initialization and rendering
    if scheme == 'env':
        adapter = adapter_class()

        if element or resource:
            # Get specific variable (element takes precedence)
            var_name = element if element else resource
            result = adapter.get_element(var_name, show_secrets=False)

            if result is None:
                print(f"Error: Environment variable '{var_name}' not found", file=sys.stderr)
                sys.exit(1)

            render_env_variable(result, args.format)
        else:
            # Get all variables
            result = adapter.get_structure(show_secrets=False)
            render_env_structure(result, args.format)

    elif scheme == 'ast':
        # Parse path and query from resource
        if '?' in resource:
            path, query = resource.split('?', 1)
        else:
            path = resource
            query = None

        # Default to current directory if no path
        if not path:
            path = '.'

        adapter = adapter_class(path, query)
        result = adapter.get_structure()
        render_ast_structure(result, args.format)

    elif scheme == 'help':
        adapter = adapter_class(resource)

        if element or resource:
            # Get specific help topic (element takes precedence)
            topic = element if element else resource
            result = adapter.get_element(topic)

            if result is None:
                print(f"Error: Help topic '{topic}' not found", file=sys.stderr)
                available = adapter.get_structure()
                print(f"\nAvailable topics: {', '.join(available['available_topics'])}", file=sys.stderr)
                sys.exit(1)

            render_help(result, args.format)
        else:
            # List all help topics
            result = adapter.get_structure()
            render_help(result, args.format, list_mode=True)

    elif scheme == 'python':
        adapter = adapter_class()

        if element or resource:
            # Get specific Python runtime element (element takes precedence)
            element_name = element if element else resource
            result = adapter.get_element(element_name)

            if result is None:
                print(f"Error: Python element '{element_name}' not found", file=sys.stderr)
                print(f"\nAvailable elements: version, env, venv, packages, imports, debug/bytecode", file=sys.stderr)
                sys.exit(1)

            render_python_element(result, args.format)
        else:
            # Get overview
            result = adapter.get_structure()
            render_python_structure(result, args.format)

    elif scheme == 'json':
        # Parse path and query from resource
        if '?' in resource:
            path, query = resource.split('?', 1)
        else:
            path = resource
            query = None

        try:
            adapter = adapter_class(path, query)
            result = adapter.get_structure()
            render_json_result(result, args.format)
        except ValueError as e:
            # User error (e.g., wrong file type) - show friendly message without traceback
            print(str(e), file=sys.stderr)
            sys.exit(1)

    elif scheme == 'reveal':
        # reveal:// - Self-inspection
        adapter = adapter_class(resource if resource else None)
        result = adapter.get_structure()
        render_reveal_structure(result, args.format)

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

  # Semantic navigation - iterative deepening! (NEW in v0.12!)
  reveal conversation.jsonl --head 10    # First 10 records
  reveal conversation.jsonl --tail 5     # Last 5 records
  reveal conversation.jsonl --range 48-52 # Records 48-52 (1-indexed)
  reveal app.py --head 5                 # First 5 functions
  reveal doc.md --tail 3                 # Last 3 headings

  # Code quality checks (pattern detectors)
  reveal main.py --check         # Run all quality checks
  reveal main.py --check --select=B,S  # Select specific categories
  reveal Dockerfile --check      # Docker best practices

  # Hierarchical outline (see structure as a tree!)
  reveal app.py --outline        # Classes with methods, nested structures
  reveal app.py --outline --check    # Outline with quality checks

  # Element extraction
  reveal app.py load_config      # Extract specific function
  reveal app.py Database         # Extract class definition
  reveal conversation.jsonl 42   # Extract record #42

  # Output formats
  reveal app.py --format=json    # JSON for scripting
  reveal app.py --format=grep    # Pipeable format
  reveal app.py --copy           # Copy output to clipboard

  # Pipeline workflows (Unix composability!)
  find src/ -name "*.py" | reveal --stdin --check
  git diff --name-only | reveal --stdin --outline
  git ls-files "*.ts" | reveal --stdin --format=json
  ls src/*.py | reveal --stdin
'''

    if has_jq:
        base_help += '''
  # Semantic navigation + jq (token-efficient exploration!)
  reveal conversation.jsonl --tail 10 --format=json | jq '.structure.records[] | select(.name | contains("user"))'
  reveal app.py --head 20 --format=json | jq '.structure.functions[] | select(.line_count > 30)'
  reveal log.jsonl --range 100-150 --format=json | jq '.structure.records[] | select(.name | contains("error"))'

  # Advanced filtering with jq (powerful!)
  reveal app.py --format=json | jq '.structure.functions[] | select(.line_count > 100)'
  reveal app.py --format=json | jq '.structure.functions[] | select(.depth > 3)'
  reveal app.py --format=json | jq '.structure.functions[] | select(.line_count > 50 and .depth > 2)'
  reveal src/**/*.py --format=json | jq -r '.structure.functions[] | "\\(.file):\\(.line) \\(.name) [\\(.line_count) lines]"'

  # Pipeline + jq (combine the power!)
  find . -name "*.py" | reveal --stdin --format=json | jq '.structure.functions[] | select(.line_count > 100)'
  git diff --name-only | grep "\\.py$" | reveal --stdin --check --format=grep
'''

    base_help += '''
  # Markdown-specific features
  reveal doc.md --links                       # Extract all links
  reveal doc.md --links --link-type external  # Only external links
  reveal doc.md --code                        # Extract all code blocks
  reveal doc.md --code --language python      # Only Python code blocks
  reveal doc.md --frontmatter                 # Extract YAML front matter

  # URI adapters - explore ANY resource!
  reveal help://                              # Discover all help topics
  reveal help://ast                           # Learn about ast:// queries
  reveal help://tricks                        # Cool tricks and hidden features
  reveal help://adapters                      # Summary of all adapters

  reveal env://                               # Show all environment variables
  reveal env://PATH                           # Get specific variable

  reveal 'ast://./src?complexity>10'          # Find complex functions
  reveal 'ast://app.py?lines>50'              # Find long functions
  reveal 'ast://.?type=function' --format=json  # All functions as JSON

File-type specific features:
  • Markdown: --links, --code, --frontmatter (extract links/code/metadata)
  • Code files: --check, --outline (quality checks, show hierarchical structure)
  • URI adapters: help:// (documentation), env:// (environment), ast:// (code queries)

Perfect filename:line format - works with vim, git, grep, sed, awk!
Metrics: All code files show [X lines, depth:Y] for complexity analysis
stdin: Reads file paths from stdin (one per line) - works with find, git, ls, etc.
'''

    return base_help


def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description='Reveal: Explore code semantically - The simplest way to understand code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_build_help_epilog()
    )

    # Positional arguments
    parser.add_argument('path', nargs='?', help='File or directory to reveal')
    parser.add_argument('element', nargs='?', help='Element to extract (function, class, etc.)')

    # Basic flags
    parser.add_argument('--version', action='version', version=f'reveal {__version__}')
    parser.add_argument('--list-supported', '-l', action='store_true',
                        help='List all supported file types')
    parser.add_argument('--agent-help', action='store_true',
                        help='Show agent usage guide (llms.txt-style brief reference)')
    parser.add_argument('--agent-help-full', action='store_true',
                        help='Show comprehensive agent guide (complete examples, patterns, troubleshooting)')

    # Input/output options
    parser.add_argument('--stdin', action='store_true',
                        help='Read file paths from stdin (one per line) - enables Unix pipeline workflows')
    parser.add_argument('--meta', action='store_true', help='Show metadata only')
    parser.add_argument('--format', choices=['text', 'json', 'typed', 'grep'], default='text',
                        help='Output format (text, json, typed [typed JSON with types/relationships], grep)')
    parser.add_argument('--copy', '-c', action='store_true',
                        help='Copy output to clipboard (also prints normally)')

    # Display options
    parser.add_argument('--no-fallback', action='store_true',
                        help='Disable TreeSitter fallback for unknown file types')
    parser.add_argument('--depth', type=int, default=3, help='Directory tree depth (default: 3)')
    parser.add_argument('--max-entries', type=int, default=200,
                        help='Maximum entries to show in directory tree (default: 200, 0=unlimited)')
    parser.add_argument('--fast', action='store_true',
                        help='Fast mode: skip line counting for better performance')
    parser.add_argument('--outline', action='store_true',
                        help='Show hierarchical outline (classes with methods, nested structures)')

    # Pattern detection (linting)
    parser.add_argument('--check', '--lint', action='store_true',
                        help='Run pattern detectors (code quality, security, complexity checks)')
    parser.add_argument('--select', type=str, metavar='RULES',
                        help='Select specific rules or categories (e.g., "B,S" or "B001,S701")')
    parser.add_argument('--ignore', type=str, metavar='RULES',
                        help='Ignore specific rules or categories (e.g., "E501" or "C")')
    parser.add_argument('--rules', action='store_true',
                        help='List all available pattern detection rules')
    parser.add_argument('--explain', type=str, metavar='CODE',
                        help='Explain a specific rule (e.g., "B001")')

    # Semantic navigation
    parser.add_argument('--head', type=int, metavar='N',
                        help='Show first N semantic units (records, functions, sections)')
    parser.add_argument('--tail', type=int, metavar='N',
                        help='Show last N semantic units (records, functions, sections)')
    parser.add_argument('--range', type=str, metavar='START-END',
                        help='Show semantic units in range (e.g., 10-20, 1-indexed)')

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
    parser.add_argument('--frontmatter', action='store_true',
                        help='Extract YAML front matter from markdown files')

    return parser


def _validate_navigation_args(args):
    """Validate and parse navigation arguments (--head, --tail, --range)."""
    # Check mutual exclusivity
    nav_args = [args.head, args.tail, args.range]
    nav_count = sum(1 for arg in nav_args if arg is not None)
    if nav_count > 1:
        print("Error: --head, --tail, and --range are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    # Parse and validate range if provided
    if args.range:
        try:
            start, end = args.range.split('-')
            start, end = int(start), int(end)
            if start < 1 or end < 1:
                raise ValueError("Range must be 1-indexed (start from 1)")
            if start > end:
                raise ValueError("Range start must be <= end")
            # Store parsed range as tuple for easy access
            args.range = (start, end)
        except ValueError as e:
            print(f"Error: Invalid range format '{args.range}': {e}", file=sys.stderr)
            print("Expected format: START-END (e.g., 10-20, 1-indexed)", file=sys.stderr)
            sys.exit(1)


def _handle_list_supported():
    """Handle --list-supported flag."""
    list_supported_types()
    sys.exit(0)


def _handle_agent_help():
    """Handle --agent-help flag."""
    agent_help_path = Path(__file__).parent / 'AGENT_HELP.md'
    try:
        with open(agent_help_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP.md not found at {agent_help_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/scottsen/reveal/issues", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def _handle_agent_help_full():
    """Handle --agent-help-full flag."""
    agent_help_full_path = Path(__file__).parent / 'AGENT_HELP_FULL.md'
    try:
        with open(agent_help_full_path, 'r', encoding='utf-8') as f:
            print(f.read())
    except FileNotFoundError:
        print(f"Error: AGENT_HELP_FULL.md not found at {agent_help_full_path}", file=sys.stderr)
        print("This is a bug - please report it at https://github.com/scottsen/reveal/issues", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


def _handle_rules_list():
    """Handle --rules flag to list all pattern detection rules."""
    from .rules import RuleRegistry
    rules = RuleRegistry.list_rules()

    if not rules:
        print("No rules discovered")
        sys.exit(0)

    print(f"Reveal v{__version__} - Pattern Detection Rules\n")

    # Group by category
    by_category = {}
    for rule in rules:
        cat = rule['category']
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(rule)

    # Print by category
    for category in sorted(by_category.keys()):
        cat_rules = by_category[category]
        print(f"{category.upper()} Rules ({len(cat_rules)}):")
        for rule in sorted(cat_rules, key=lambda r: r['code']):
            status = "✓" if rule['enabled'] else "✗"
            severity_icon = {"low": "ℹ️", "medium": "⚠️", "high": "❌", "critical": "🚨"}.get(rule['severity'], "")
            print(f"  {status} {rule['code']:8s} {severity_icon} {rule['message']}")
            if rule['file_patterns'] != ['*']:
                print(f"             Files: {', '.join(rule['file_patterns'])}")
        print()

    print(f"Total: {len(rules)} rules")
    print("\nUsage: reveal <file> --check --select B,S --ignore E501")
    sys.exit(0)


def _handle_explain_rule(rule_code: str):
    """Handle --explain flag to explain a specific rule."""
    from .rules import RuleRegistry
    rule = RuleRegistry.get_rule(rule_code)

    if not rule:
        print(f"Error: Rule '{rule_code}' not found", file=sys.stderr)
        print("\nUse 'reveal --rules' to list all available rules", file=sys.stderr)
        sys.exit(1)

    print(f"Rule: {rule.code}")
    print(f"Message: {rule.message}")
    print(f"Category: {rule.category.value if rule.category else 'unknown'}")
    print(f"Severity: {rule.severity.value}")
    print(f"File Patterns: {', '.join(rule.file_patterns)}")
    if rule.uri_patterns:
        print(f"URI Patterns: {', '.join(rule.uri_patterns)}")
    print(f"Version: {rule.version}")
    print(f"Enabled: {'Yes' if rule.enabled else 'No'}")
    print(f"\nDescription:")
    print(f"  {rule.__doc__ or 'No description available.'}")
    sys.exit(0)


def _handle_stdin_mode(args):
    """Handle --stdin mode to process files from stdin."""
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


def _handle_file_or_directory(path_str: str, args):
    """Handle regular file or directory path."""
    path = Path(path_str)
    if not path.exists():
        print(f"Error: {path_str} not found", file=sys.stderr)
        sys.exit(1)

    if path.is_dir():
        # Directory → show tree
        output = show_directory_tree(str(path), depth=args.depth,
                                     max_entries=args.max_entries, fast=args.fast)
        print(output)
    elif path.is_file():
        # File → show structure or extract element
        handle_file(str(path), args.element, args.meta, args.format, args)
    else:
        print(f"Error: {path_str} is neither file nor directory", file=sys.stderr)
        sys.exit(1)


def _main_impl():
    """Main CLI entry point."""
    # Parse arguments
    parser = _create_argument_parser()
    args = parser.parse_args()

    # Validate navigation arguments
    _validate_navigation_args(args)

    # Check for updates (once per day, non-blocking, opt-out available)
    check_for_updates()

    # Handle special modes (exit early)
    if args.list_supported:
        _handle_list_supported()
    if args.agent_help:
        _handle_agent_help()
    if args.agent_help_full:
        _handle_agent_help_full()
    if args.rules:
        _handle_rules_list()
    if args.explain:
        _handle_explain_rule(args.explain)

    # Handle stdin mode
    if args.stdin:
        _handle_stdin_mode(args)

    # Path is required if not using special modes or --stdin
    if not args.path:
        parser.print_help()
        sys.exit(1)

    # Check if this is a URI (scheme://)
    if '://' in args.path:
        handle_uri(args.path, args.element, args)
        sys.exit(0)

    # Handle regular file/directory path
    _handle_file_or_directory(args.path, args)


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
                except Exception:
                    # Language not available in tree-sitter-languages, skip it
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


def run_pattern_detection(analyzer: FileAnalyzer, path: str, output_format: str, args):
    """Run pattern detection rules on a file.

    Args:
        analyzer: File analyzer instance
        path: File path
        output_format: Output format ('text', 'json', 'grep')
        args: CLI arguments (for --select, --ignore)
    """
    from .rules import RuleRegistry

    # Parse select/ignore options
    select = args.select.split(',') if args.select else None
    ignore = args.ignore.split(',') if args.ignore else None

    # Get structure and content
    structure = analyzer.get_structure()
    content = analyzer.content

    # Run rules
    detections = RuleRegistry.check_file(path, structure, content, select=select, ignore=ignore)

    # Output results
    if output_format == 'json':
        import json
        result = {
            'file': path,
            'detections': [d.to_dict() for d in detections],
            'total': len(detections)
        }
        print(safe_json_dumps(result))

    elif output_format == 'grep':
        # Grep format: file:line:column:code:message
        for d in detections:
            print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")

    else:  # text
        if not detections:
            print(f"{path}: ✅ No issues found")
        else:
            print(f"{path}: Found {len(detections)} issues\n")
            for d in sorted(detections, key=lambda x: (x.line, x.column)):
                print(d)
                print()  # Blank line between detections


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

    # Pattern detection mode (--check)?
    if args and getattr(args, 'check', False):
        run_pattern_detection(analyzer, path, output_format, args)
        return

    # Extract specific element?
    if element:
        extract_element(analyzer, element, output_format)
        return

    # Default: show structure
    show_structure(analyzer, output_format, args)


if __name__ == '__main__':
    main()
