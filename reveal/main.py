"""Clean, simple CLI for reveal."""

import sys
import os
import logging
import io
import re
from typing import Optional, Tuple, Any, List
from collections.abc import Callable


from .registry import get_all_analyzers
from . import __version__
from .utils import copy_to_clipboard, check_for_updates
from .config import disable_breadcrumbs_permanently


class TeeWriter:
    """Write to both original stdout and a capture buffer (for --copy mode)."""
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
    handle_discover,
    handle_stdin_mode,
    handle_decorator_stats,
    handle_uri,
    handle_file_or_directory,
    handle_file,
)


def _dispatch_subcommand() -> bool:
    """Dispatch to a named subcommand using a table-driven lookup.

    Uses sys.argv inspection before argparse runs to avoid conflicts between
    optional positional args and subparsers.

    Returns:
        True if a subcommand was matched and executed.
    """
    if len(sys.argv) < 2:
        return False

    name = sys.argv[1]

    # Import lazily so startup cost is paid only when the subcommand is used.
    # Each entry: subcommand name -> (parser_factory, runner)
    _SUBCOMMANDS = {
        'check':    ('reveal.cli.commands.check',    'create_check_parser',    'run_check'),
        'dev':      ('reveal.cli.commands.dev',      'create_dev_parser',      'run_dev'),
        'health':   ('reveal.cli.commands.health',   'create_health_parser',   'run_health'),
        'hotspots': ('reveal.cli.commands.hotspots', 'create_hotspots_parser', 'run_hotspots'),
        'overview': ('reveal.cli.commands.overview', 'create_overview_parser', 'run_overview'),
        'pack':     ('reveal.cli.commands.pack',     'create_pack_parser',     'run_pack'),
        'review':   ('reveal.cli.commands.review',   'create_review_parser',   'run_review'),
        'scaffold': ('reveal.cli.commands.scaffold', 'create_scaffold_parser', 'run_scaffold'),
    }

    if name not in _SUBCOMMANDS:
        return False

    module_path, parser_fn, runner_fn = _SUBCOMMANDS[name]
    import importlib
    mod = importlib.import_module(module_path)
    args = getattr(mod, parser_fn)().parse_args(sys.argv[2:])
    getattr(mod, runner_fn)(args)
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


def _preprocess_sort_arg() -> None:
    """Allow --sort -field syntax (descending) by converting to --sort=-field.

    Argparse treats '--sort -modified' as a missing argument error because
    '-modified' looks like a flag. The '=' form '--sort=-modified' is accepted.
    This converts the space form to the = form before argparse runs.
    """
    i = 0
    while i < len(sys.argv) - 1:
        if sys.argv[i] == '--sort':
            next_arg = sys.argv[i + 1]
            # Single-dash prefix that looks like a field name (not a -- flag)
            if re.match(r'^-[a-zA-Z_][a-zA-Z0-9_]*$', next_arg):
                sys.argv[i] = f'--sort={next_arg}'
                del sys.argv[i + 1]
                break
        i += 1


def main() -> None:
    """Main CLI entry point."""
    _setup_windows_console()
    _preprocess_sort_arg()

    # Handle subcommands early (before copy mode setup and argparse)
    if _dispatch_subcommand():
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
        (getattr(args, 'discover', False), handle_discover, []),
        (getattr(args, 'decorator_stats', False), handle_decorator_stats, [args.path]),
        (args.stdin, handle_stdin_mode, [args, handle_file]),
        (getattr(args, 'disable_breadcrumbs', False), disable_breadcrumbs_permanently, []),
    ]

    for condition, handler, handler_args in special_modes:
        if condition:
            handler(*handler_args)
            return True

    return False


def _process_at_file_target(target: str, args) -> None:
    """Process a single URI or file path from an @file."""
    from pathlib import Path

    if '://' in target:
        try:
            handle_uri(target, None, args)
        except SystemExit as e:
            if e.code != 0:
                print(f"Warning: {target} failed, skipping", file=sys.stderr)
        return

    target_path = Path(target)
    if not target_path.exists():
        print(f"Warning: {target} not found, skipping", file=sys.stderr)
    elif target_path.is_dir():
        print(f"Warning: {target} is a directory, skipping", file=sys.stderr)
    elif target_path.is_file():
        handle_file(str(target_path), None, args.meta, args.format, args)


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

    # When batch or check mode is active, route through handle_stdin_mode for
    # proper aggregation (equivalent to: cat @file | reveal --stdin --batch)
    is_batch_mode = getattr(args, 'batch', False)
    is_check_mode = getattr(args, 'check', False)
    if is_batch_mode or is_check_mode:
        old_stdin = sys.stdin
        sys.stdin = io.StringIO('\n'.join(lines))
        try:
            handle_stdin_mode(args, handle_file)
        finally:
            sys.stdin = old_stdin
        return

    for target in lines:
        _process_at_file_target(target, args)

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
