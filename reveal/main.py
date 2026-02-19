"""Clean, simple CLI for reveal."""

import sys
import os
import logging
import io
from typing import Optional, Tuple, Any, List
from collections.abc import Callable


from .registry import get_all_analyzers
from . import __version__
from .utils import copy_to_clipboard, check_for_updates
from .config import disable_breadcrumbs_permanently

from .cli import (
    create_argument_parser,
    validate_navigation_args,
    handle_list_supported,
    handle_languages,
    handle_adapters,
    handle_explain_file,
    handle_capabilities,
    handle_show_ast,
    handle_language_info,
    handle_agent_help,
    handle_agent_help_full,
    handle_rules_list,
    handle_schema,
    handle_explain_rule,
    handle_list_schemas,
    handle_stdin_mode,
    handle_decorator_stats,
    handle_scaffold_adapter,
    handle_scaffold_analyzer,
    handle_scaffold_rule,
    handle_uri,
    handle_file_or_directory,
    handle_file,
)


def _handle_scaffold_command() -> bool:
    """Handle 'reveal scaffold' subcommands.

    Returns:
        bool: True if scaffold command was handled, False otherwise
    """
    import argparse

    if len(sys.argv) < 2 or sys.argv[1] != 'scaffold':
        return False

    # Create scaffold subcommand parser
    parser = argparse.ArgumentParser(
        prog='reveal scaffold',
        description='Scaffold new reveal components (adapters, analyzers, rules)',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='component', help='Component type to scaffold')
    subparsers.required = True

    # Adapter subcommand
    adapter_parser = subparsers.add_parser('adapter', help='Scaffold a new adapter')
    adapter_parser.add_argument('name', help='Adapter name (e.g., github, docker)')
    adapter_parser.add_argument('uri', help='URI scheme (e.g., github://, docker://)')
    adapter_parser.add_argument('--force', action='store_true', help='Overwrite existing files')

    # Analyzer subcommand
    analyzer_parser = subparsers.add_parser('analyzer', help='Scaffold a new analyzer')
    analyzer_parser.add_argument('name', help='Analyzer name (e.g., kotlin, dart)')
    analyzer_parser.add_argument('extension', help='File extension (e.g., .kt, .dart)')
    analyzer_parser.add_argument('--force', action='store_true', help='Overwrite existing files')

    # Rule subcommand
    rule_parser = subparsers.add_parser('rule', help='Scaffold a new quality rule')
    rule_parser.add_argument('code', help='Rule code (e.g., C001, X001)')
    rule_parser.add_argument('name', help='Rule name (e.g., "custom-pattern-check")')
    rule_parser.add_argument('--category', default='custom', help='Rule category (default: custom)')
    rule_parser.add_argument('--force', action='store_true', help='Overwrite existing files')

    # Parse scaffold subcommand args (skip 'reveal scaffold' from argv)
    args = parser.parse_args(sys.argv[2:])

    # Dispatch to appropriate handler
    if args.component == 'adapter':
        handle_scaffold_adapter(args.name, args.uri, args.force)
    elif args.component == 'analyzer':
        handle_scaffold_analyzer(args.name, args.extension, args.force)
    elif args.component == 'rule':
        handle_scaffold_rule(args.code, args.name, args.category, args.force)

    return True


def _setup_windows_console() -> None:
    """Configure Windows console for UTF-8/emoji support."""
    if sys.platform != 'win32':
        return

    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def _setup_copy_mode() -> Optional[Tuple[Any, io.StringIO, Any]]:
    """Setup output capture for copy mode.

    Returns:
        Optional[Tuple[Any, io.StringIO, Any]]: (tee_writer, captured_output, original_stdout)
            or None if not copy mode
    """
    copy_mode = '--copy' in sys.argv or '-c' in sys.argv
    if not copy_mode:
        return None

    captured_output = io.StringIO()
    original_stdout = sys.stdout

    class TeeWriter:
        """Write to both original stdout and capture buffer."""
        def __init__(self, original: Any, capture: io.StringIO) -> None:
            self.original = original
            self.capture = capture

        def write(self, data: str) -> None:
            self.original.write(data)
            self.capture.write(data)

        def flush(self) -> None:
            self.original.flush()

        def __getattr__(self, name: str) -> Any:
            return getattr(self.original, name)

    return TeeWriter(original_stdout, captured_output), captured_output, original_stdout


def _handle_clipboard_copy(captured_output: io.StringIO, original_stdout: Any) -> None:
    """Handle clipboard copy after command execution.

    Args:
        captured_output: StringIO buffer containing captured stdout
        original_stdout: Original stdout stream
    """
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


def main() -> None:
    """Main CLI entry point."""
    _setup_windows_console()

    # Handle scaffold subcommands early (before copy mode setup)
    if _handle_scaffold_command():
        return

    copy_setup = _setup_copy_mode()
    if copy_setup:
        tee_writer, captured_output, original_stdout = copy_setup
        sys.stdout = tee_writer

    try:
        _main_impl()
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(0)
    finally:
        if copy_setup:
            _, captured_output, original_stdout = copy_setup
            _handle_clipboard_copy(captured_output, original_stdout)


def _handle_special_modes(args: Any) -> bool:
    """Handle special CLI modes that exit early.

    Args:
        args: Parsed command-line arguments

    Returns:
        bool: True if a special mode was handled (caller should exit)
    """
    # Special mode handlers (flag -> (handler, *handler_args))
    special_modes: List[Tuple[Any, Callable[..., Any], List[Any]]] = [
        (args.list_supported, handle_list_supported, [list_supported_types]),
        (getattr(args, 'languages', False), handle_languages, []),
        (getattr(args, 'adapters', False), handle_adapters, []),
        (getattr(args, 'language_info', None), handle_language_info, [args.language_info]),
        (getattr(args, 'explain_file', False), handle_explain_file, [args.path, args.verbose]),
        (getattr(args, 'capabilities', False), handle_capabilities, [args.path]),
        (getattr(args, 'show_ast', False), handle_show_ast, [args.path]),
        (args.agent_help, handle_agent_help, []),
        (args.agent_help_full, handle_agent_help_full, []),
        (args.rules, handle_rules_list, [__version__]),
        (getattr(args, 'schema', False), handle_schema, []),
        (args.explain, handle_explain_rule, [args.explain]),
        (getattr(args, 'list_schemas', False), handle_list_schemas, []),
        (getattr(args, 'decorator_stats', False), handle_decorator_stats, [args.path]),
        (args.stdin, handle_stdin_mode, [args, handle_file]),
        (getattr(args, 'disable_breadcrumbs', False), disable_breadcrumbs_permanently, []),
    ]

    for condition, handler, handler_args in special_modes:
        if condition:
            handler(*handler_args)
            return True

    return False


def _handle_at_file(file_path: str, args):
    """Handle @file syntax - read URIs/paths from a file.

    Args:
        file_path: Path to file containing URIs (one per line)
        args: Parsed CLI arguments

    Similar to --stdin but reads from a file instead of stdin.
    """
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"Error reading {file_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if not lines:
        print(f"Error: No URIs found in {file_path}", file=sys.stderr)
        sys.exit(1)

    # Process each URI/path
    for target in lines:
        if '://' in target:
            try:
                handle_uri(target, None, args)
            except SystemExit as e:
                # Only warn for actual failures (non-zero exit codes)
                if e.code != 0:
                    print(f"Warning: {target} failed, skipping", file=sys.stderr)
        else:
            # Handle as file path
            target_path = Path(target)
            if not target_path.exists():
                print(f"Warning: {target} not found, skipping", file=sys.stderr)
                continue
            if target_path.is_dir():
                print(f"Warning: {target} is a directory, skipping", file=sys.stderr)
                continue
            if target_path.is_file():
                handle_file(str(target_path), None, args.meta, args.format, args)

    sys.exit(0)


def _main_impl() -> None:
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

    # Handle @file syntax - read URIs from file
    if args.path.startswith('@'):
        _handle_at_file(args.path[1:], args)
        return

    # Dispatch based on path type
    if '://' in args.path:
        handle_uri(args.path, args.element, args)
    else:
        handle_file_or_directory(args.path, args)


def _get_tree_sitter_fallbacks(registered_analyzers: dict[str, Any]) -> List[Tuple[str, str]]:
    """Probe tree-sitter for additional language support.

    Args:
        registered_analyzers: Dict of already-registered analyzers

    Returns:
        list: Available fallback languages as (display_name, ext) tuples
    """
    try:
        import warnings
        warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')
        from tree_sitter_language_pack import get_language
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
            get_language(lang)  # type: ignore[arg-type]
            available_fallbacks.append((display_name, ext))
        except Exception as e:
            logging.debug(f"Tree-sitter language {lang} not available: {e}")

    return available_fallbacks


def _print_fallback_languages(fallbacks: List[Tuple[str, str]]) -> None:
    """Print tree-sitter fallback languages.

    Args:
        fallbacks: List of (display_name, extension) tuples
    """
    if not fallbacks:
        return

    print("\nTree-Sitter Auto-Supported (basic):")
    for name, ext in sorted(fallbacks):
        print(f"  {name:20s} {ext}")
    print(f"\nTotal: {len(fallbacks)} additional languages via fallback")
    print("Note: These work automatically but may have basic support.")
    print("Note: Contributions for full analyzers welcome!")


def list_supported_types() -> None:
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


if __name__ == '__main__':
    main()
