"""Clean, simple CLI for reveal."""

import sys
import os
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
    handle_stdin_mode,
    handle_decorator_stats,
    handle_uri,
    handle_file_or_directory,
    handle_file,
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


def _main_impl():
    """Main CLI implementation."""
    # Parse arguments
    parser = create_argument_parser(__version__)
    args = parser.parse_args()

    # Validate navigation arguments
    validate_navigation_args(args)

    # Check for updates (once per day, non-blocking, opt-out available)
    check_for_updates()

    # Handle special modes (exit early)
    if args.list_supported:
        handle_list_supported(list_supported_types)
    if args.agent_help:
        handle_agent_help()
    if args.agent_help_full:
        handle_agent_help_full()
    if args.rules:
        handle_rules_list(__version__)
    if args.explain:
        handle_explain_rule(args.explain)
    if getattr(args, 'decorator_stats', False):
        handle_decorator_stats(args.path)

    # Handle stdin mode
    if args.stdin:
        handle_stdin_mode(args, handle_file)

    # Path is required if not using special modes or --stdin
    if not args.path:
        parser.print_help()
        sys.exit(1)

    # Check if this is a URI (scheme://)
    if '://' in args.path:
        handle_uri(args.path, args.element, args)
        sys.exit(0)

    # Handle regular file/directory path
    handle_file_or_directory(args.path, args)


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

    print("\nUsage: reveal <file>")
    print("Help: reveal --help")


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


if __name__ == '__main__':
    main()
