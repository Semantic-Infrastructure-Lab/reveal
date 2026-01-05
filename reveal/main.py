"""Clean, simple CLI for reveal."""

import sys
import os
import logging
from .base import get_all_analyzers, FileAnalyzer
from . import __version__
from .utils import copy_to_clipboard, safe_json_dumps, check_for_updates
from .cli import (
    create_argument_parser,
    validate_navigation_args,
    handle_list_supported,
    handle_agent_help,
    handle_agent_help_full,
    handle_rules_list,
    handle_explain_rule,
    handle_list_schemas,
    handle_stdin_mode,
    handle_decorator_stats,
    handle_uri,
    handle_file_or_directory,
    handle_file,
)


def _setup_windows_console():
    """Configure Windows console for UTF-8/emoji support."""
    if sys.platform != 'win32':
        return

    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def _setup_copy_mode():
    """Setup output capture for copy mode.

    Returns:
        tuple: (tee_writer, captured_output, original_stdout) or None if not copy mode
    """
    import io

    copy_mode = '--copy' in sys.argv or '-c' in sys.argv
    if not copy_mode:
        return None

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

        def __getattr__(self, name):
            return getattr(self.original, name)

    return TeeWriter(original_stdout, captured_output), captured_output, original_stdout


def _handle_clipboard_copy(captured_output, original_stdout):
    """Handle clipboard copy after command execution."""
    sys.stdout = original_stdout
    output_text = captured_output.getvalue()
    if not output_text:
        return

    if copy_to_clipboard(output_text):
        print(f"\n📋 Copied {len(output_text)} chars to clipboard", file=sys.stderr)
    else:
        msg = "Could not copy to clipboard (no clipboard utility found)"
        print(f"\n⚠️  {msg}", file=sys.stderr)
        print("   Install xclip, xsel (Linux), or use pbcopy (macOS)", file=sys.stderr)


def main():
    """Main CLI entry point."""
    _setup_windows_console()

    copy_setup = _setup_copy_mode()
    if copy_setup:
        tee_writer, captured_output, original_stdout = copy_setup
        sys.stdout = tee_writer
    else:
        captured_output = None
        original_stdout = None

    try:
        _main_impl()
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)
    finally:
        if copy_setup:
            _handle_clipboard_copy(captured_output, original_stdout)


def _handle_special_modes(args):
    """Handle special CLI modes that exit early.

    Returns:
        bool: True if a special mode was handled (caller should exit)
    """
    # Special mode handlers (flag -> (handler, *handler_args))
    special_modes = [
        (args.list_supported, handle_list_supported, [list_supported_types]),
        (args.agent_help, handle_agent_help, []),
        (args.agent_help_full, handle_agent_help_full, []),
        (args.rules, handle_rules_list, [__version__]),
        (args.explain, handle_explain_rule, [args.explain]),
        (getattr(args, 'list_schemas', False), handle_list_schemas, []),
        (getattr(args, 'decorator_stats', False), handle_decorator_stats, [args.path]),
        (args.stdin, handle_stdin_mode, [args, handle_file]),
    ]

    for condition, handler, handler_args in special_modes:
        if condition:
            handler(*handler_args)
            return True

    return False


def _main_impl():
    """Main CLI implementation."""
    # Parse and validate arguments
    parser = create_argument_parser(__version__)
    args = parser.parse_args()
    validate_navigation_args(args)

    # Check for updates (once per day, non-blocking, opt-out available)
    check_for_updates()

    # Handle special modes (exit early)
    if _handle_special_modes(args):
        return

    # Path is required for normal operation
    if not args.path:
        parser.print_help()
        sys.exit(1)

    # Dispatch based on path type
    if '://' in args.path:
        handle_uri(args.path, args.element, args)
    else:
        handle_file_or_directory(args.path, args)


def _get_tree_sitter_fallbacks(registered_analyzers):
    """Probe tree-sitter for additional language support.

    Args:
        registered_analyzers: Dict of already-registered analyzers

    Returns:
        list: Available fallback languages as (display_name, ext) tuples
    """
    try:
        import warnings
        warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')
        from tree_sitter_languages import get_language
    except ImportError:
        return []

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
        '.scala': ('scala', 'Scala'),
        '.lua': ('lua', 'Lua'),
        '.hs': ('haskell', 'Haskell'),
        '.elm': ('elm', 'Elm'),
        '.ocaml': ('ocaml', 'OCaml'),
        '.ml': ('ocaml', 'OCaml'),
    }

    available_fallbacks = []
    for ext, (lang, display_name) in fallback_languages.items():
        if ext in registered_analyzers:
            continue

        try:
            get_language(lang)
            available_fallbacks.append((display_name, ext))
        except Exception as e:
            logging.debug(f"Tree-sitter language {lang} not available: {e}")

    return available_fallbacks


def _print_fallback_languages(fallbacks):
    """Print tree-sitter fallback languages."""
    if not fallbacks:
        return

    print("\nTree-Sitter Auto-Supported (basic):")
    for name, ext in sorted(fallbacks):
        print(f"  {name:20s} {ext}")
    print(f"\nTotal: {len(fallbacks)} additional languages via fallback")
    print("Note: These work automatically but may have basic support.")
    print("Note: Contributions for full analyzers welcome!")


def list_supported_types():
    """List all supported file types."""
    analyzers = get_all_analyzers()

    if not analyzers:
        print("No file types registered")
        return

    print(f"Reveal v{__version__} - Supported File Types\n")

    # Print built-in analyzers
    sorted_analyzers = sorted(analyzers.items(), key=lambda x: x[1]['name'])
    print("Built-in Analyzers:")
    for ext, info in sorted_analyzers:
        print(f"  {info['name']:20s} {ext}")
    print(f"\nTotal: {len(analyzers)} file types with full support")

    # Check for tree-sitter fallback support
    fallbacks = _get_tree_sitter_fallbacks(analyzers)
    _print_fallback_languages(fallbacks)

    print("\nUsage: reveal <file>")
    print("Help: reveal --help")


def _format_detections_json(path, detections):
    """Format detections as JSON."""
    result = {
        'file': path,
        'detections': [d.to_dict() for d in detections],
        'total': len(detections)
    }
    print(safe_json_dumps(result))


def _format_detections_grep(detections):
    """Format detections as grep output."""
    for d in detections:
        print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")


def _format_detections_text(path, detections):
    """Format detections as human-readable text."""
    if not detections:
        print(f"{path}: ✅ No issues found")
        return

    print(f"{path}: Found {len(detections)} issues\n")
    for d in sorted(detections, key=lambda x: (x.line, x.column)):
        print(d)
        print()


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
    detections = RuleRegistry.check_file(
        path, structure, content, select=select, ignore=ignore
    )

    # Format and output results
    formatters = {
        'json': lambda: _format_detections_json(path, detections),
        'grep': lambda: _format_detections_grep(detections),
        'text': lambda: _format_detections_text(path, detections),
    }

    formatter = formatters.get(output_format, formatters['text'])
    formatter()


def run_schema_validation(analyzer: FileAnalyzer, path: str, schema_name: str, output_format: str, args):
    """Run schema validation on front matter.

    Args:
        analyzer: File analyzer instance
        path: File path
        schema_name: Schema name or path to schema file
        output_format: Output format ('text', 'json', 'grep')
        args: CLI arguments (for --select, --ignore)
    """
    from .schemas.frontmatter import load_schema
    from .rules.frontmatter import set_validation_context, clear_validation_context
    from .rules import RuleRegistry

    # Check if file is markdown (schema validation is for markdown front matter)
    if not path.lower().endswith(('.md', '.markdown')):
        print(f"Warning: Schema validation is designed for markdown files", file=sys.stderr)
        print(f"         File '{path}' does not appear to be markdown", file=sys.stderr)
        print(f"         Continuing anyway...\n", file=sys.stderr)

    # Load schema
    schema = load_schema(schema_name)
    if not schema:
        print(f"Error: Schema '{schema_name}' not found", file=sys.stderr)
        print("\nAvailable built-in schemas:", file=sys.stderr)
        from .schemas.frontmatter import list_schemas
        for name in list_schemas():
            print(f"  - {name}", file=sys.stderr)
        print("\nOr provide a path to a custom schema file", file=sys.stderr)
        sys.exit(1)

    # Get structure with frontmatter extraction enabled
    structure = analyzer.get_structure(extract_frontmatter=True)
    content = analyzer.content

    # Set schema context for F-series rules
    set_validation_context(schema)

    try:
        # Parse select/ignore options (default to F-series rules if not specified)
        select = args.select.split(',') if args.select else ['F']
        ignore = args.ignore.split(',') if args.ignore else None

        # Run rules (F003, F004, F005 will use the schema context)
        detections = RuleRegistry.check_file(
            path, structure, content, select=select, ignore=ignore
        )

        # Format and output results
        formatters = {
            'json': lambda: _format_detections_json(path, detections),
            'grep': lambda: _format_detections_grep(detections),
            'text': lambda: _format_detections_text(path, detections),
        }

        formatter = formatters.get(output_format, formatters['text'])
        formatter()

        # Exit with error code if validation failed
        if detections:
            sys.exit(1)

    finally:
        # Always clear context, even if an error occurred
        clear_validation_context()


if __name__ == '__main__':
    main()
