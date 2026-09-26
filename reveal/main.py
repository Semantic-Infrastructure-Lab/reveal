"""Clean, simple CLI for reveal."""

import sys
import os
import io
import re
import json
import time
try:
    import resource  # POSIX-only; used for --perf RSS reporting
except ImportError:  # Windows CPython has no `resource` module
    resource = None  # type: ignore[assignment]
from pathlib import Path
from typing import Optional, Tuple, Any, List
from collections.abc import Callable


from .logging_setup import configure_stderr_logging
from .registry import FALLBACK_SUPPORT_NOTE, display_name_for_extension, fallback_languages, get_all_analyzers
from . import __version__
from .utils import copy_to_clipboard, check_for_updates
from .cli.global_flags import apply_global_flags
from .config import disable_breadcrumbs_permanently


PERF_LOG_PATH = Path(os.environ.get('REVEAL_PERF_LOG_PATH', str(Path.home() / '.reveal' / 'perf.jsonl')))


# BACK-1231: moved to reveal/logging_setup.py so pool workers can call it
# without importing the CLI. Re-exported here for any caller using the old name.
_configure_stderr_logging = configure_stderr_logging


def _perf_flag_present() -> bool:
    """Check for --perf without going through argparse (must work before
    subcommand dispatch, which uses its own per-command parsers)."""
    return '--perf' in sys.argv or os.environ.get('REVEAL_PERF_LOG') == '1'


def _strip_perf_flag() -> None:
    if '--perf' in sys.argv:
        sys.argv.remove('--perf')


def _log_perf(start: float, argv_snapshot: List[str], exit_code: int) -> None:
    """Append one JSON line describing this invocation to PERF_LOG_PATH.

    Never raises — perf logging must not break normal operation.
    """
    try:
        if resource is None:
            peak_rss_kb = None  # Windows: no resource-usage API
        else:
            ru_self = resource.getrusage(resource.RUSAGE_SELF)
            ru_children = resource.getrusage(resource.RUSAGE_CHILDREN)
            peak_rss_kb = ru_self.ru_maxrss + ru_children.ru_maxrss
            if sys.platform == 'darwin':
                peak_rss_kb //= 1024  # macOS reports ru_maxrss in bytes, not KB
    except Exception:
        peak_rss_kb = None

    record = {
        'ts': time.time(),
        'pid': os.getpid(),
        'argv': argv_snapshot,
        'elapsed_s': round(time.perf_counter() - start, 3),
        'peak_rss_kb': peak_rss_kb,
        'exit_code': exit_code,
        'max_workers_env': os.environ.get('REVEAL_MAX_WORKERS'),
    }

    try:
        PERF_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PERF_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record) + '\n')
    except Exception:
        # Perf log is a best-effort diagnostic sidecar — disk full, permission
        # denied, or a read-only filesystem must never fail the actual command.
        pass


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
        self.capture.flush()

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
    handle_rules_list,
    handle_profiles_list,
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


# Module-level (not just local to _dispatch_subcommand) so other layers —
# e.g. help.py's help://schemas/<name> lookup, BACK-1028 — can tell a
# CLI-only subcommand apart from an unknown name without re-deriving this
# table. Each entry: subcommand name -> (module_path, parser_factory, runner).
_SUBCOMMANDS = {
    'architecture': ('reveal.cli.commands.architecture', 'create_architecture_parser', 'run_architecture'),
    'check':        ('reveal.cli.commands.check',        'create_check_parser',        'run_check'),
    'contracts':    ('reveal.cli.commands.contracts',    'create_contracts_parser',    'run_contracts'),
    'deps':         ('reveal.cli.commands.deps',         'create_deps_parser',         'run_deps'),
    'dev':          ('reveal.cli.commands.dev',          'create_dev_parser',          'run_dev'),
    'health':       ('reveal.cli.commands.health',       'create_health_parser',       'run_health'),
    'hotspots':     ('reveal.cli.commands.hotspots',     'create_hotspots_parser',     'run_hotspots'),
    'offline':      ('reveal.cli.commands.offline',      'create_offline_parser',      'run_offline'),
    'overview':     ('reveal.cli.commands.overview',     'create_overview_parser',     'run_overview'),
    'pack':         ('reveal.cli.commands.pack',         'create_pack_parser',         'run_pack'),
    'review':       ('reveal.cli.commands.review',       'create_review_parser',       'run_review'),
    'scaffold':     ('reveal.cli.commands.scaffold',     'create_scaffold_parser',     'run_scaffold'),
    'surface':      ('reveal.cli.commands.surface',      'create_surface_parser',      'run_surface'),
    'testability':  ('reveal.cli.commands.testability',  'create_testability_parser',  'run_testability'),
    'trace':        ('reveal.cli.commands.trace',         'create_trace_parser',         'run_trace'),
}


def _warn_if_subcommand_shadows_path(name: str) -> None:
    """Hint on stderr when a bare verb (e.g. `reveal overview`) silently
    shadows a same-named file/dir in cwd (BACK-1112).

    The precedence itself (bare word = verb, `./x` or `x/` = path) is
    intentional and correct -- this only makes the shadowing visible
    instead of silent.
    """
    if not os.path.exists(name):
        return
    target = f'./{name}/' if os.path.isdir(name) else f'./{name}'
    print(
        f"note: {target} exists — use ./{name} or {name}/ to target it",
        file=sys.stderr,
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

    if name not in _SUBCOMMANDS:
        return False

    _warn_if_subcommand_shadows_path(name)

    module_path, parser_fn, runner_fn = _SUBCOMMANDS[name]
    import importlib
    mod = importlib.import_module(module_path)
    args = getattr(mod, parser_fn)().parse_args(sys.argv[2:])
    # This path bypasses _main_impl() (table-driven dispatch before argparse's
    # positional/subparser conflicts), so it must apply the global flags itself
    # (BACK-1034: --provenance was silently dropped here).
    apply_global_flags(args)
    _require_subcommand_format(name, args)
    getattr(mod, runner_fn)(args)
    return True


# Subcommands with no same-named adapter whose runners render only these
# (measured: grep/typed output was byte-identical to text). `check` renders
# every format and is not listed.
_SUBCOMMAND_FORMATS = {
    'health': ('text', 'json'),
    'review': ('text', 'json'),
}


def _require_subcommand_format(name: str, args: Any) -> None:
    """A subcommand renders what its adapter (or _SUBCOMMAND_FORMATS)
    declares; any other --format is rejected, not printed as text (BACK-1425)."""
    from . import adapters as _adapters  # noqa: F401 -- registers every adapter
    from .adapters.base import get_adapter_class
    from .cli.routing.formats import (
        declared_output_formats, reject_unhonored_also_json, require_supported_format,
    )
    adapter_class = get_adapter_class(name)
    supported = (declared_output_formats(adapter_class) if adapter_class is not None
                 else _SUBCOMMAND_FORMATS.get(name))
    require_supported_format(args, supported, f"reveal {name}")
    if name != 'check':
        reject_unhonored_also_json(args, f"reveal {name}")


def _setup_console() -> None:
    """Make stdout/stderr unable to crash on non-ASCII output.

    Windows: force UTF-8 (emoji/box-drawing support).  Elsewhere: keep the stream's
    declared encoding but never raise on an unencodable character -- a C/POSIX locale
    or a cp1252 pipe would otherwise die with UnicodeEncodeError on '→' or '✅'
    (BACK-1351).  Unencodable characters print as '?'.
    """
    windows = sys.platform == 'win32'
    if windows:
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
    for stream in (sys.stdout, sys.stderr):
        if not hasattr(stream, 'reconfigure'):
            continue
        if windows:
            stream.reconfigure(encoding='utf-8', errors='replace')
        elif (getattr(stream, 'encoding', None) or '').lower().replace('_', '-') not in ('utf-8', 'utf8'):
            stream.reconfigure(errors='replace')


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
    _configure_stderr_logging()
    _setup_console()
    _preprocess_sort_arg()

    perf_enabled = _perf_flag_present()
    if perf_enabled:
        _strip_perf_flag()
        argv_snapshot = list(sys.argv[1:])
        start = time.perf_counter()

    exit_code = 0
    try:
        _dispatch_and_run()
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        raise
    except BaseException:
        exit_code = 1
        raise
    finally:
        if perf_enabled:
            _log_perf(start, argv_snapshot, exit_code)


def _dispatch_and_run() -> None:
    """Route to a subcommand, or fall through to the main path (URI/file/dir)."""
    # Copy mode wraps BOTH paths: it was set up after subcommand dispatch, so
    # `reveal overview . --copy` parsed the flag and copied nothing (BACK-1375).
    copy_setup = _setup_copy_mode()
    if copy_setup:
        tee_writer, captured_output, original_stdout = copy_setup
        sys.stdout = tee_writer

    try:
        if not _dispatch_subcommand():
            _main_impl()
        # Flush here so a reader that closed early (`| head`) raises inside this
        # try: output smaller than the buffer otherwise failed at interpreter exit
        # with "Exception ignored ... BrokenPipeError" and exit 120 (BACK-1510).
        sys.stdout.flush()
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
        (getattr(args, 'adapters', False), handle_adapters, [getattr(args, 'all', False)]),
        (getattr(args, 'language_info', None), handle_language_info, [args.language_info]),
        (getattr(args, 'explain_file', False), handle_explain_file, [args.path, args.verbose]),
        (getattr(args, 'capabilities', False), handle_capabilities, [args.path]),
        (getattr(args, 'show_ast', False), handle_show_ast, [args.path]),
        (args.agent_help, handle_agent_help, []),
        (args.rules, handle_rules_list, [__version__, getattr(args, 'all', False)]),
        (getattr(args, 'profiles', False), handle_profiles_list, []),
        (getattr(args, 'schema', False), handle_schema, []),
        (args.explain, handle_explain_rule, [args.explain]),
        (getattr(args, 'list_schemas', False), handle_list_schemas, []),
        (getattr(args, 'discover', False), handle_discover, [getattr(args, 'all', False)]),
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


def _check_ghost_flags() -> None:
    """Intercept unsupported flags before argparse to emit targeted suggestions."""
    import re as _re
    lines_pattern = _re.compile(r'^--lines(?:=\S+)?$')
    for i, arg in enumerate(sys.argv[1:], 1):
        if lines_pattern.match(arg):
            # Extract the range value if present (--lines=N-M or --lines N-M)
            range_val = None
            if '=' in arg:
                range_val = arg.split('=', 1)[1]
            elif i < len(sys.argv) - 1 and not sys.argv[i + 1].startswith('-'):
                range_val = sys.argv[i + 1]
            hint = f" {range_val}" if range_val else " N-M"
            path_hint = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else "file.py"
            print(
                f"reveal: unknown flag --lines. Did you mean:\n"
                f"  reveal {path_hint}:{hint.strip()}    (line range extraction)\n"
                f"  reveal {path_hint} --range {hint.strip()}  (structure range)",
                file=sys.stderr,
            )
            sys.exit(2)


def _main_impl() -> None:
    """Main CLI implementation."""
    # Intercept ghost flags before argparse to emit targeted suggestions
    _check_ghost_flags()

    # Parse and validate arguments
    parser = create_argument_parser(__version__)
    args = parser.parse_args()
    validate_navigation_args(args)
    apply_global_flags(args)

    # Check for updates (once per day, non-blocking, opt-out available)
    check_for_updates()

    # Handle special modes (exit early)
    if _handle_special_modes(args):
        return

    # Path is required for normal operation. A truly bare invocation (no args
    # at all) advertises capabilities instead of dumping argparse usage --
    # SIL agent-bootstrap-manual.md §3.1 requires a qualifying tool to
    # "advertise its own capabilities on bare invocation" (BACK-976). Any
    # other no-path case (a flag combo with nothing to act on) keeps the
    # original argparse-usage fallback.
    if not args.path:
        if len(sys.argv) == 1:
            handle_discover(False)
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
    # registry.fallback_languages() is the one answer to "what routes to a
    # fallback" (BACK-1255); only the labels are decided here. These three are
    # finer than display_name_for_extension(), which keeps .m/.mm as one name.
    labels = {'.mm': 'Objective-C++', '.sv': 'SystemVerilog', '.svh': 'SystemVerilog'}
    return [
        (labels.get(ext) or display_name_for_extension(ext) or grammar, ext)
        for ext, grammar in fallback_languages().items()
        if ext not in registered_analyzers
    ]


def _print_fallback_languages(fallbacks: List[Tuple[str, str]]) -> None:
    """Print tree-sitter fallback languages.

    Args:
        fallbacks: List of (display_name, extension) tuples
    """
    if not fallbacks:
        return

    print("\nTree-sitter fallback:")
    for name, ext in sorted(fallbacks):
        print(f"  {name:20s} {ext}")
    # Count grammars, not labels: .mm and .sv/.svh carry finer labels above but
    # route to the objc/verilog grammars, as `reveal --languages` counts them.
    grammars = fallback_languages()
    languages = len({grammars[ext] for _, ext in fallbacks})
    print(f"\nTotal: {languages} fallback languages ({len(fallbacks)} extensions)")
    print(f"Note: {FALLBACK_SUPPORT_NOTE}.")
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
        marker = " *" if info.get('content_ambiguous') else ""
        print(f"  {info['name']:20s} {ext}{marker}")
    languages = len({info['name'] for info in analyzers.values()})
    print(f"\nTotal: {len(analyzers)} extensions across {languages} explicit analyzers "
          f"(support tiers per language: reveal --languages)")

    # BACK-583: flag extensions whose actual analyzer is content-dependent —
    # the line above only shows the registry's last-registered winner.
    ambiguous = [(ext, info) for ext, info in sorted_analyzers if info.get('content_ambiguous')]
    if ambiguous:
        print("\n* Content-dependent — actual analyzer chosen per-file, not by extension alone:")
        for ext, info in ambiguous:
            print(f"  {ext}: {info['content_ambiguous']}")

    # Check for tree-sitter fallback support
    fallbacks = _get_tree_sitter_fallbacks(analyzers)
    _print_fallback_languages(fallbacks)

    print("\nUsage: reveal <file>")
    print("Help: reveal --help")


if __name__ == '__main__':
    main()
