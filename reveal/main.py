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
from argparse import Namespace
from contextlib import contextmanager
from typing import Optional, Tuple, Any, List, TextIO, cast
from collections.abc import Callable, Iterator, Sequence


from .logging_setup import configure_stderr_logging
from .registry import FALLBACK_SUPPORT_NOTE, display_name_for_extension, fallback_languages, get_all_analyzers
from . import __version__
from .utils import copy_to_clipboard, check_for_updates
from .cli.global_flags import apply_global_flags
from .cli.invocation import COMMANDS, Invocation, invocation_scope
from .config import disable_breadcrumbs_permanently


PERF_LOG_PATH = Path(os.environ.get('REVEAL_PERF_LOG_PATH', str(Path.home() / '.reveal' / 'perf.jsonl')))


# BACK-1231: moved to reveal/logging_setup.py so pool workers can call it
# without importing the CLI. Re-exported here for any caller using the old name.
_configure_stderr_logging = configure_stderr_logging


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


def _require_subcommand_format(name: str, args: Any) -> None:
    """A subcommand renders what its adapter (or its COMMANDS entry) declares;
    any other --format is rejected, not printed as text (BACK-1425)."""
    from . import adapters as _adapters  # noqa: F401 -- registers every adapter
    from .adapters.base import get_adapter_class
    from .cli.routing.formats import (
        declared_output_formats, reject_unhonored_also_json, require_supported_format,
    )
    adapter_class = get_adapter_class(name)
    supported = (declared_output_formats(adapter_class) if adapter_class is not None
                 else COMMANDS[name].formats)
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


@contextmanager
def _copy_scope(enabled: bool) -> Iterator[None]:
    """--copy: tee stdout while the command runs, then copy what it printed."""
    if not enabled:
        yield
        return
    captured_output = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = cast(TextIO, TeeWriter(original_stdout, captured_output))  # duck-typed stream
    try:
        yield
    finally:
        _handle_clipboard_copy(captured_output, original_stdout)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Main CLI entry point. ``argv`` defaults to the process's own (``argv[0]`` is the program)."""
    _configure_stderr_logging()
    _setup_console()
    invocation = Invocation.parse(sys.argv if argv is None else argv)

    perf_enabled = invocation.perf or os.environ.get('REVEAL_PERF_LOG') == '1'
    start = time.perf_counter()
    exit_code = 0
    try:
        with invocation_scope(invocation):
            _dispatch_and_run(invocation)
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        raise
    except BaseException:
        exit_code = 1
        raise
    finally:
        if perf_enabled:
            _log_perf(start, list(invocation.argv), exit_code)


def _dispatch_and_run(invocation: Invocation) -> None:
    """Parse the invocation once, apply its global flags, and run it (BACK-1058).

    The subcommand and path/URI forms differ only in which parser reads the command line
    and what runs the result. Everything else is applied here, once, for both.
    """
    args, run = _prepare(invocation)
    apply_global_flags(args)
    # --copy comes from the parsed args, so every spelling argparse accepts (-c, -qc,
    # --copy) is honored. A raw scan of argv missed the combined short form.
    with _copy_scope(bool(getattr(args, 'copy', False))):
        try:
            run()
            # Flush here so a reader that closed early (`| head`) raises inside this
            # try: output smaller than the buffer otherwise failed at interpreter exit
            # with "Exception ignored ... BrokenPipeError" and exit 120 (BACK-1510).
            sys.stdout.flush()
        except BrokenPipeError:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            sys.exit(0)


def _prepare(invocation: Invocation) -> Tuple[Namespace, Callable[[], None]]:
    """Parse ``invocation`` with its command's parser; return the args and what runs them."""
    name = invocation.command
    if name is None:
        _check_ghost_flags(invocation)
        parser = create_argument_parser(__version__, full_help=invocation.typed('--help-all'))
        args = parser.parse_args(invocation.argv)
        validate_navigation_args(args)
        return args, lambda: _main_impl(invocation, parser, args)

    _warn_if_subcommand_shadows_path(name)
    sub_parser, runner = COMMANDS[name].load()
    sub_args = sub_parser.parse_args(invocation.command_argv)
    _require_subcommand_format(name, sub_args)
    # BACK-1539: the flag ledger and the REVEAL_IGNORE/--exclude walk scope, once for all.
    from .cli.routing.subcommand import dispatch_subcommand
    return sub_args, lambda: dispatch_subcommand(name, sub_parser, runner, sub_args)


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

    # `reveal @list` is `reveal --stdin < list`: one path for both, so a URI that fails
    # is reported and counted the same way (BACK-1556; this had its own copy that
    # skipped a failure and exited 0).
    old_stdin = sys.stdin
    sys.stdin = io.StringIO('\n'.join(lines))
    try:
        handle_stdin_mode(args, handle_file)
    finally:
        sys.stdin = old_stdin


def _check_ghost_flags(invocation: Invocation) -> None:
    """Intercept unsupported flags before argparse to emit targeted suggestions."""
    argv = invocation.argv
    lines_pattern = re.compile(r'^--lines(?:=\S+)?$')
    for i, arg in enumerate(argv):
        if lines_pattern.match(arg):
            # Extract the range value if present (--lines=N-M or --lines N-M)
            range_val = None
            if '=' in arg:
                range_val = arg.split('=', 1)[1]
            elif i < len(argv) - 1 and not argv[i + 1].startswith('-'):
                range_val = argv[i + 1]
            hint = f" {range_val}" if range_val else " N-M"
            path_hint = argv[0] if argv and not argv[0].startswith('-') else "file.py"
            print(
                f"reveal: unknown flag --lines. Did you mean:\n"
                f"  reveal {path_hint}:{hint.strip()}    (line range extraction)\n"
                f"  reveal {path_hint} --range {hint.strip()}  (structure range)",
                file=sys.stderr,
            )
            sys.exit(2)


def _main_impl(invocation: Invocation, parser: Any, args: Namespace) -> None:
    """Run the path/URI form with its parsed ``args``."""
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
        if invocation.bare:
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
