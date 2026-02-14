"""Argument parsing and validation for reveal CLI."""

import sys
import argparse
import shutil


def _build_core_examples() -> str:
    """Build core usage examples."""
    return '''
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


def _build_jq_examples() -> str:
    """Build jq integration examples."""
    return '''
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


def _build_adapter_examples() -> str:
    """Build URI adapter and file-specific examples."""
    return '''
  # Markdown-specific features
  reveal doc.md --links                       # Extract all links
  reveal doc.md --links --link-type external  # Only external links
  reveal doc.md --code                        # Extract all code blocks
  reveal doc.md --code --language python      # Only Python code blocks
  reveal doc.md --frontmatter                 # Extract YAML front matter

  # HTML-specific features
  reveal page.html --metadata                 # Extract SEO/social metadata
  reveal page.html --semantic navigation      # Extract nav elements
  reveal page.html --semantic content         # Extract main/article/section
  reveal page.html --scripts all              # Extract all script tags
  reveal page.html --styles external          # Extract external stylesheets
  reveal page.html --links                    # Extract all HTML links

  # URI adapters - explore ANY resource!
  reveal help://                              # Discover all help topics
  reveal help://ast                           # Learn about ast:// queries
  reveal help://tricks                        # Cool tricks and hidden features
  reveal help://adapters                      # Summary of all adapters

  reveal env://                               # Show all environment variables
  reveal env://PATH                           # Get specific variable

  reveal reveal://config                      # Show configuration sources and values
  reveal reveal://config --format json        # Config as JSON for scripts

  reveal 'ast://./src?complexity>10'          # Find complex functions
  reveal 'ast://app.py?lines>50'              # Find long functions
  reveal 'ast://.?type=function' --format=json  # All functions as JSON

  # Universal operation flags (work across all adapters with --check)
  reveal ssl://example.com --check --advanced        # SSL deep health check
  reveal domain://example.com --check --advanced     # Domain + DNS validation
  reveal mysql://localhost --check --only-failures   # Show only MySQL problems

  # Batch processing (works with any adapter)
  cat domains.txt | reveal --stdin --batch --check   # Batch health checks
  echo -e "ssl://a.com\\nssl://b.com" | reveal --stdin --batch --check --only-failures
  cat mixed-uris.txt | reveal --stdin --batch --format=json  # Mix SSL, domain, mysql

File-type specific features:
  • Markdown: --links, --code, --frontmatter (extract links/code/metadata)
  • HTML: --metadata, --semantic, --scripts, --styles (extract SEO/elements/scripts)
  • Code files: --check, --outline, --typed (quality checks, hierarchy, containment)
  • URI adapters: help:// (docs), env:// (env vars), reveal://config (config), ast:// (code queries)

  # Type-aware output (shows parent/child relationships!)
  reveal app.py --typed            # See containment hierarchy
  reveal app.py --typed --format=json  # Full typed structure as JSON

Perfect filename:line format - works with vim, git, grep, sed, awk!
Metrics: All code files show [X lines, depth:Y] for complexity analysis
stdin: Reads file paths from stdin (one per line) - works with find, git, ls, etc.
'''


def build_help_epilog() -> str:
    """Build dynamic help with conditional jq examples."""
    has_jq = shutil.which('jq') is not None

    help_text = _build_core_examples()
    if has_jq:
        help_text += _build_jq_examples()
    help_text += _build_adapter_examples()

    return help_text


def _add_basic_arguments(parser: argparse.ArgumentParser, version: str) -> None:
    """Add positional arguments and basic flags."""
    # Positional arguments
    parser.add_argument('path', nargs='?', help='File or directory to reveal')
    parser.add_argument('element', nargs='?', help='Element to extract (function, class, etc.)')

    # Basic flags
    parser.add_argument('--version', action='version', version=f'reveal {version}')
    parser.add_argument('--list-supported', '-l', action='store_true',
                        help='List all supported file types')
    parser.add_argument('--languages', action='store_true',
                        help='List all supported languages with explicit vs fallback analyzers')
    parser.add_argument('--adapters', action='store_true',
                        help='List all URI adapters (env://, ast://, git://, etc.)')
    parser.add_argument('--explain-file', action='store_true',
                        help='Explain how reveal will analyze a file (shows analyzer, fallback status, capabilities)')
    parser.add_argument('--capabilities', action='store_true',
                        help='Show file capabilities as JSON (for agents: what can be extracted, what rules apply)')
    parser.add_argument('--show-ast', action='store_true',
                        help='Show tree-sitter AST for a file (for tree-sitter based analyzers)')
    parser.add_argument('--language-info', type=str, metavar='LANG',
                        help='Show detailed information about a language (e.g., --language-info python or --language-info .py)')
    parser.add_argument('--agent-help', action='store_true',
                        help='Show agent usage guide (llms.txt-style brief reference)')
    parser.add_argument('--agent-help-full', action='store_true',
                        help='Show comprehensive agent guide (complete examples, patterns, troubleshooting)')


def _add_input_output_options(parser: argparse.ArgumentParser) -> None:
    """Add input/output and formatting options."""
    parser.add_argument('--stdin', action='store_true',
                        help='Read paths/URIs from stdin (one per line) - supports files and any URI scheme (ssl://, claude://, etc.)')
    parser.add_argument('--meta', action='store_true', help='Show metadata only')
    parser.add_argument('--format', choices=['text', 'json', 'typed', 'grep'], default='text',
                        help='Output format (text, json, typed [typed JSON with types/relationships], grep)')
    parser.add_argument('--copy', '-c', action='store_true',
                        help='Copy output to clipboard (also prints normally)')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed output (e.g., all results instead of truncated summary for imports://)')


def _add_type_aware_options(parser: argparse.ArgumentParser) -> None:
    """Add type-aware output options."""
    parser.add_argument('--typed', action='store_true',
                        help='Enable type-aware output with containment navigation (Pythonic structure)')
    parser.add_argument('--filter', type=str, metavar='CATEGORY',
                        help='Filter --typed output by category (property, staticmethod, classmethod, method, function, class)')
    parser.add_argument('--decorator-stats', action='store_true',
                        help='Show decorator usage statistics across codebase (works on directories)')


def _add_display_options(parser: argparse.ArgumentParser) -> None:
    """Add display and visualization options."""
    parser.add_argument('--no-fallback', action='store_true',
                        help='Disable TreeSitter fallback for unknown file types')
    parser.add_argument('--depth', type=int, default=3, help='Directory tree depth (default: 3)')
    parser.add_argument('--max-entries', type=int, default=200,
                        help='Maximum entries to show in directory tree (default: 200, 0=unlimited)')
    parser.add_argument('--dir-limit', type=int, default=50,
                        help='Maximum entries per directory before snipping (default: 50, 0=unlimited). '
                             'When a directory exceeds this limit, shows first entries then "[snipped N more]" '
                             'and continues with sibling directories.')
    parser.add_argument('--fast', action='store_true',
                        help='Fast mode: skip line counting for better performance')
    parser.add_argument('--respect-gitignore', action='store_true', default=True,
                        help='Respect .gitignore rules when showing directory trees (default: enabled)')
    parser.add_argument('--no-gitignore', action='store_false', dest='respect_gitignore',
                        help='Ignore .gitignore rules and show all files')
    parser.add_argument('--exclude', action='append', metavar='PATTERN',
                        help='Exclude files/directories matching pattern (e.g., --exclude "*.log" --exclude "tmp/")')
    parser.add_argument('--outline', action='store_true',
                        help='Show hierarchical outline (classes with methods, nested structures)')
    parser.add_argument('--hotspots', action='store_true',
                        help='Identify quality hotspots (requires stats:// adapter, shows worst 10 files by quality)')
    parser.add_argument('--code-only', action='store_true',
                        help='Exclude data/config files from analysis (requires stats:// adapter, filters .json>10KB, .yaml, .xml, .csv, .toml)')
    parser.add_argument('--no-breadcrumbs', '-q', '--quiet', action='store_true',
                        help='Disable breadcrumb navigation hints (scripting mode)')
    parser.add_argument('--disable-breadcrumbs', action='store_true',
                        help='Permanently disable breadcrumbs in user config')


def _add_pattern_detection_options(parser: argparse.ArgumentParser) -> None:
    """Add pattern detection (linting) options."""
    parser.add_argument('--check', '--lint', action='store_true',
                        help='Run pattern detectors (code quality, security, complexity checks)')
    parser.add_argument('--config', type=str, metavar='FILE',
                        help='Configuration file to use (.reveal.yaml or pyproject.toml)')
    parser.add_argument('--select', type=str, metavar='RULES',
                        help='Select specific rules or categories (e.g., "B,S" or "B001,S701")')
    parser.add_argument('--ignore', type=str, metavar='RULES',
                        help='Ignore specific rules or categories (e.g., "E501" or "C")')
    parser.add_argument('--recursive', '-r', action='store_true',
                        help='Process directory recursively (with --check)')
    parser.add_argument('--rules', action='store_true',
                        help='List all available pattern detection rules')
    parser.add_argument('--schema', action='store_true',
                        help='Show Output Contract v1.0 specification for stable JSON output')
    parser.add_argument('--explain', type=str, metavar='CODE',
                        help='Explain a specific rule (e.g., "B001")')


def _add_navigation_options(parser: argparse.ArgumentParser) -> None:
    """Add semantic navigation options."""
    parser.add_argument('--head', type=int, metavar='N',
                        help='Show first N semantic units (records, functions, sections)')
    parser.add_argument('--tail', type=int, metavar='N',
                        help='Show last N semantic units (records, functions, sections)')
    parser.add_argument('--range', type=str, metavar='START-END',
                        help='Show semantic units in range (e.g., 10-20, 1-indexed)')

    # Convenience flags for within-file search and filtering
    parser.add_argument('--search', type=str, metavar='PATTERN',
                        help='Search for symbols matching pattern (regex on name field)')
    parser.add_argument('--sort', type=str, metavar='FIELD',
                        help='Sort results by field (prefix with - for descending, e.g., -complexity)')
    parser.add_argument('--type', type=str, metavar='TYPE',
                        help='Filter by element type (function, class, method, etc.)')


def _add_markdown_options(parser: argparse.ArgumentParser) -> None:
    """Add markdown-specific extraction options."""
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
    parser.add_argument('--related', action='store_true',
                        help='Show related documents from front matter (related, related_docs, see_also, references)')
    parser.add_argument('--related-depth', type=int, default=1,
                        help='Depth for --related traversal (default: 1, 0=unlimited)')
    parser.add_argument('--related-all', action='store_true',
                        help='Follow all related links (sets --related --related-depth 0)')
    parser.add_argument('--related-flat', action='store_true',
                        help='Output related docs as flat path list (grep-friendly)')
    parser.add_argument('--related-limit', type=int, default=100,
                        help='Max files to traverse for --related (default: 100)')
    parser.add_argument('--section', type=str, metavar='NAME',
                        help='Extract section by heading name (e.g., --section "Installation")')


def _add_html_options(parser: argparse.ArgumentParser) -> None:
    """Add HTML-specific extraction options."""
    parser.add_argument('--metadata', action='store_true',
                        help='Extract HTML head metadata (SEO, OpenGraph, Twitter cards)')
    parser.add_argument('--semantic', type=str,
                        choices=['navigation', 'content', 'forms', 'media', 'all'],
                        help='Extract semantic HTML elements (nav, main, article, forms, etc.)')
    parser.add_argument('--scripts', type=str,
                        choices=['inline', 'external', 'all'],
                        help='Extract script tags from HTML files')
    parser.add_argument('--styles', type=str,
                        choices=['inline', 'external', 'all'],
                        help='Extract stylesheets from HTML files')


def _add_schema_validation_options(parser: argparse.ArgumentParser) -> None:
    """Add schema validation options."""
    parser.add_argument('--validate-schema', type=str, metavar='SCHEMA',
                        help='Validate front matter against schema (built-in: session, hugo, obsidian; or path to custom schema)')
    parser.add_argument('--list-schemas', action='store_true',
                        help='List all built-in schemas available for validation')


def _add_universal_operation_flags(parser: argparse.ArgumentParser) -> None:
    """Add universal operation flags that work across all adapters.

    These flags provide consistent behavior for health checks, filtering,
    and batch processing across all adapters.
    """
    parser.add_argument('--advanced', action='store_true',
                        help='Run advanced checks with --check (enables deeper validation)')
    parser.add_argument('--only-failures', action='store_true',
                        help='Only show failed/warning checks (hide healthy results)')
    parser.add_argument('--batch', action='store_true',
                        help='Batch mode: process multiple URIs from stdin with aggregated results')


def _add_universal_filter_flags(parser: argparse.ArgumentParser) -> None:
    """Add universal filtering flags for field selection and budget constraints.

    These flags enable token reduction through field selection and explicit
    budget constraints for AI agent loops.
    """
    # Field selection
    parser.add_argument('--fields', type=str, metavar='FIELDS',
                        help='Select specific fields (comma-separated, supports nested: field.subfield)')

    # Budget constraints
    parser.add_argument('--max-items', type=int, metavar='N',
                        help='Stop after N results (budget mode)')
    parser.add_argument('--max-bytes', type=int, metavar='N',
                        help='Stop after N bytes/tokens (budget mode)')
    parser.add_argument('--max-depth', type=int, metavar='N',
                        help='Limit nested structure depth to N levels')
    parser.add_argument('--max-snippet-chars', type=int, metavar='N',
                        help='Truncate long string values to N characters')


def _add_ssl_options(parser: argparse.ArgumentParser) -> None:
    """Add SSL-specific options for batch checks."""
    parser.add_argument('--summary', action='store_true',
                        help='Show aggregated summary instead of full details')
    parser.add_argument('--expiring-within', type=str, metavar='DAYS',
                        help='Only show certificates expiring within N days (e.g., 7, 30)')
    parser.add_argument('--validate-nginx', action='store_true',
                        help='Cross-validate SSL certificates against nginx configuration')


def _add_extraction_options(parser: argparse.ArgumentParser) -> None:
    """Add extraction options for composable pipelines."""
    parser.add_argument('--extract', type=str, metavar='TYPE',
                        help='Extract specific data for piping (nginx: "domains" extracts SSL domains as ssl:// URIs)')


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

    _add_basic_arguments(parser, version)
    _add_input_output_options(parser)
    _add_type_aware_options(parser)
    _add_display_options(parser)
    _add_pattern_detection_options(parser)
    _add_universal_operation_flags(parser)
    _add_universal_filter_flags(parser)
    _add_navigation_options(parser)
    _add_markdown_options(parser)
    _add_html_options(parser)
    _add_schema_validation_options(parser)
    _add_ssl_options(parser)
    _add_extraction_options(parser)

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
