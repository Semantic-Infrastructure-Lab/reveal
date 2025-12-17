"""Argument parsing and validation for reveal CLI."""

import sys
import argparse
import shutil


def build_help_epilog() -> str:
    """Build dynamic help with conditional jq examples."""
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
  • Code files: --check, --outline, --typed (quality checks, hierarchy, containment)
  • URI adapters: help:// (documentation), env:// (environment), ast:// (code queries)

  # Type-aware output (shows parent/child relationships!)
  reveal app.py --typed            # See containment hierarchy
  reveal app.py --typed --format=json  # Full typed structure as JSON

Perfect filename:line format - works with vim, git, grep, sed, awk!
Metrics: All code files show [X lines, depth:Y] for complexity analysis
stdin: Reads file paths from stdin (one per line) - works with find, git, ls, etc.
'''

    return base_help


def create_argument_parser(version: str) -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser.

    Args:
        version: Version string to display with --version

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        description='Reveal: Explore code semantically - The simplest way to understand code',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=build_help_epilog()
    )

    # Positional arguments
    parser.add_argument('path', nargs='?', help='File or directory to reveal')
    parser.add_argument('element', nargs='?', help='Element to extract (function, class, etc.)')

    # Basic flags
    parser.add_argument('--version', action='version', version=f'reveal {version}')
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

    # Type-aware output
    parser.add_argument('--typed', action='store_true',
                        help='Enable type-aware output with containment navigation (Pythonic structure)')
    parser.add_argument('--filter', type=str, metavar='CATEGORY',
                        help='Filter --typed output by category (property, staticmethod, classmethod, method, function, class)')
    parser.add_argument('--decorator-stats', action='store_true',
                        help='Show decorator usage statistics across codebase (works on directories)')

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
    parser.add_argument('--recursive', '-r', action='store_true',
                        help='Process directory recursively (with --check)')
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


def validate_navigation_args(args):
    """Validate and parse navigation arguments (--head, --tail, --range).

    Args:
        args: Parsed argument namespace

    Raises:
        SystemExit: If validation fails
    """
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


# Backward compatibility aliases (private names)
_build_help_epilog = build_help_epilog
_create_argument_parser = lambda: create_argument_parser('')  # Will be overridden
_validate_navigation_args = validate_navigation_args
