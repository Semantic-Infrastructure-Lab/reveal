"""reveal MCP server — exposes reveal's capabilities via Model Context Protocol.

Allows Claude Code, Cursor, Windsurf, and any MCP-compatible agent framework to
use reveal as a first-class tool without subprocess overhead.

Usage:
    reveal-mcp                     # stdio transport (default, for Claude Code)
    reveal-mcp --transport sse     # SSE transport (for HTTP clients)

Configuration example (Claude Code settings.json):
    {
        "mcpServers": {
            "reveal": {
                "command": "reveal-mcp"
            }
        }
    }
"""

import functools
import io
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path

try:
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations
except ImportError:
    # BACK-1247: `mcp` lives in its own dedicated extra (reveal-cli[mcp]),
    # not reveal-cli's base dependencies -- a plain `pip install reveal-cli`
    # ships this reveal-mcp entry point without what it needs to import,
    # and the resulting raw ModuleNotFoundError traceback gives no hint
    # toward the fix. Confirmed live: reproduces at 0.124.0/0.125.0.
    print(
        "reveal-mcp requires the 'mcp' package, which is not installed.\n"
        'Fix: pip install "reveal-cli[mcp]"',
        file=sys.stderr,
    )
    sys.exit(1)

from .cli.defaults import _default_args
from .cli.global_flags import apply_global_flags
from .utils.path_utils import failure_of
from .errors import NavRequestValidationError

# All reveal-mcp tools are read-only (no writes, no side effects) and
# idempotent (same args -> same result, modulo underlying files changing).
# reveal_query is the exception for openWorldHint: several of its adapters
# (ssl://, domain://, mysql://) reach external network services, while the
# rest of the tools only ever touch the local filesystem/git repo.
_LOCAL_READONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
_OPEN_WORLD_READONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

# Suppress update-check prints that would corrupt MCP tool responses.
os.environ.setdefault('REVEAL_NO_UPDATE_CHECK', '1')

# Access logging (BACK-1144): reveal-mcp has no root-confinement -- every
# path/uri argument is trusted as-is, so an LLM driven by a malicious doc or
# webpage (prompt injection) could ask a tool to read anything the server
# process can see (~/.ssh/id_rsa, another user's repo, ...) with no warning
# and no record. This does not confine access -- it just gives a post-hoc
# audit trail of what every tool call actually touched. Opt-in and
# best-effort, mirroring the REVEAL_PERF_LOG convention in main.py.
_MCP_ACCESS_LOG_ENABLED = os.environ.get('REVEAL_MCP_ACCESS_LOG') == '1'
_MCP_ACCESS_LOG_PATH = Path(
    os.environ.get('REVEAL_MCP_ACCESS_LOG_PATH', str(Path.home() / '.reveal' / 'mcp_access.jsonl'))
)


def _log_mcp_access(tool_name: str, kwargs: dict) -> None:
    """Append one JSON line recording an MCP tool call's arguments.

    Never raises -- access logging must not break a tool call.
    """
    if not _MCP_ACCESS_LOG_ENABLED:
        return
    try:
        record = {
            'ts': time.time(),
            'pid': os.getpid(),
            'tool': tool_name,
            'args': kwargs,
        }
        _MCP_ACCESS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_MCP_ACCESS_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, default=str) + '\n')
    except (OSError, ValueError):  # unwritable log dir, or a circular kwarg json.dumps rejects
        pass

mcp = MCPServer(
    "reveal",
    instructions=(
        "Reveal is a progressive disclosure tool for exploring codebases, "
        "infrastructure, and data sources. On measured tasks it takes typically "
        "3.9-15x fewer tokens than reading files directly — always prefer the narrowest tool below "
        "over reading a whole file or dumping a whole repo.\n\n"
        "Param convention: `path` = local filesystem path only. `uri` = a "
        "reveal URI (scheme://...) only. `target` = either, tool-dependent "
        "(reveal_health: path or URI; reveal_review: path or git range).\n\n"
        "Core workflow:\n"
        "0. reveal_query('overview://<dir>') — orient in an unfamiliar "
        "codebase first: quality score, ranked hotspots, git activity, one "
        "screen. This is reveal's own best answer to \"what is this repo\" — "
        "start here before structure/element/nav on unfamiliar code.\n"
        "1. reveal_structure(dir) — understand what's in a directory (~100-3,000 tokens, by size)\n"
        "2. reveal_structure(file) — see all functions/classes (~150-750 tokens; ~1,300 for a 1,000-line module)\n"
        "3. reveal_element(file, fn) — read one function's implementation (~100-600 tokens)\n"
        "4. reveal_nav(file, fn, flag) — deep-dive analysis without reading source:\n"
        "   boundary    — INPUTS + ENVIRONMENT + EFFECTS in one report\n"
        "   inputs      — candidate undefined reads, with builtins distinguished\n"
        "   outputs     — variables written in a range and read later\n"
        "   callsites   — call sites within the selected element or range\n"
        "   sideeffects — db/http/cache/log/file/sleep/hard_stop calls\n"
        "   returns     — exit paths with gate conditions\n"
        "   varflow     — trace one variable's reads and writes\n"
        "5. reveal_grep(path, pattern) — \"where is X used?\" cross-file "
        "search grouped by enclosing function (use instead of shell grep).\n"
        "6. reveal_query('calls://<dir>?callees=FN&depth=2&detail') — \"what "
        "happens when X runs?\" level-by-level callee walk with params and side "
        "effects (reveal_trace(dir, entry_point) renders the same walk as a "
        "depth-indented narrative).\n"
        "7. reveal_query('help://quick') — lost, or need an adapter outside "
        "this workflow (git, imports, sqlite, env, infra adapters like ssl/"
        "domain/mysql/cpanel, ...)? Start here for an orientation map of "
        "everything else reveal://* can do — it's the full escape hatch, not "
        "just these 10 named tools.\n\n"
        "Quality tools — pick one, they answer different questions and CAN "
        "DISAGREE (a coarse PASS from one and real issues from another on the "
        "same path is expected, not a bug):\n"
        "  reveal_health(target)  — fast go/no-go verdict; also probes "
        "ssl:///mysql:///domain:// targets, not just code\n"
        "  reveal_check(path)     — itemized rule violations for a file/dir, "
        "supports select/ignore to target specific rule codes\n"
        "  reveal_review(target)  — pre-merge assessment; pass a git range "
        "(e.g. 'main..feature') to scope to changed files only\n\n"
        "reveal_pack(path) — picks the most important files that fit a token "
        "budget (default 8000, counted on the files' raw size) and returns "
        "their names plus the structure of the key ones, not raw file "
        "content: a few hundred to a few thousand tokens. With `since`, "
        "changed files come first and are shown raw (up to 500 lines each). "
        "Use it for breadth (PR review via `since`, an unfamiliar repo, a "
        "one-shot handoff); for one file or function, reveal_structure + "
        "reveal_element answer directly."
    ),
)

# Sync MCP tools are dispatched via anyio.to_thread.run_sync under the
# sse/streamable-http transports (concurrent clients), not just stdio
# (serialized by construction). _run_and_capture mutates process-global
# sys.stdout/sys.stderr, so concurrent calls must be serialized here or
# they race and cross-attribute output between callers. BACK-898.
# Reentrant (not plain Lock): reveal_query's provenance param (BACK-1135)
# also mutates a process-global (utils.json_utils's provenance-enabled
# flag) and needs to hold this same lock across its own call into
# _run_and_capture, which re-acquires it internally.
_capture_lock = threading.RLock()


def _run_and_capture(fn, *args, capture_stderr: bool = True, **kwargs) -> str:
    """Run fn with stdout+stderr captured; return captured text.

    Used only for tools where the underlying display layer prints rather than
    returning strings. Serialized via _capture_lock since this mutates
    process-global sys.stdout/sys.stderr and tool calls are not guaranteed
    sequential under sse/streamable-http transports.
    Swallows SystemExit(0) (reveal uses it for clean exit on some paths).
    Stderr is appended so MCP clients see error messages instead of silence,
    unless the caller passes capture_stderr=False (e.g. reveal_review, whose
    stderr is pure progress/duplicate-header noise once captured to a buffer
    instead of a live TTY -- BACK-REVEAL-3).

    Nonzero exit is reveal's normal convention for "the target has a negative
    verdict" (reveal_health FAIL, reveal_review violations found), not just a
    crash -- real stdout content always wins over the exit-code sentinel, even
    on nonzero exit; the sentinel is only a fallback when there is no stdout
    at all (a genuine crash with nothing rendered).
    """
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    exit_code = None
    captured_exception = None
    with _capture_lock:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = out_buf
        sys.stderr = err_buf
        try:
            fn(*args, **kwargs)
        except SystemExit as e:
            exit_code = e.code
        except Exception as exc:  # boundary-ok: broad-except -- arbitrary adapter code; preserve origin for the registered boundary to mask crashes
            captured_exception = exc
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    out = out_buf.getvalue()
    err = err_buf.getvalue().strip()

    if captured_exception is not None:
        return _tool_failure(str(captured_exception),
                             public=isinstance(captured_exception, (OSError, NavRequestValidationError)),
                             exception=captured_exception)
    if out.strip():
        if capture_stderr and err:
            return f"{out}\n[stderr: {err}]"
        return out
    if exit_code not in (0, None):
        msg = f"[reveal exited with code {exit_code}]"
        return f"{msg}: {err}" if err else msg
    if capture_stderr and err:
        return f"[stderr: {err}]"
    return out


# Error origin belongs to this owner, never to rendered/source text. Keep the
# direct Python string contract while marking only failures authored here.
class _ToolFailure(str):
    public: bool
    exception: Exception | None

    def __new__(cls, message: str, *, public: bool = True,
                exception: Exception | None = None):
        result = super().__new__(cls, f"[reveal error: {message}]")
        result.public = public
        result.exception = exception
        return result


def _tool_failure(message: str, *, public: bool = True,
                  exception: Exception | None = None) -> str:
    return _ToolFailure(message, public=public, exception=exception)


def _raise_if_tool_failure(result: str, tool_name: str) -> str:
    if isinstance(result, _ToolFailure):
        if result.public:
            raise ToolError(result[1:-1])
        exc = result.exception
        if exc is not None:
            logging.getLogger(__name__).error(
                "Unexpected failure in MCP tool %s", tool_name,
                exc_info=(type(exc), exc, exc.__traceback__))
        else:
            logging.getLogger(__name__).error("Failure in MCP tool %s: %s", tool_name, result)
        raise ToolError(f"Internal error executing tool {tool_name}")
    return result


def _trace_absence_compatibility(answer) -> bool:
    """Only owner-qualified trace absence retains the historical MCP nonerror; so does a calls
    name answer's (exit 2 on the CLI, BACK-2066), which reveal_query returned as an empty answer."""
    from .utils.results import AnalysisCompleteness, FailureCause
    return (answer.result.get('type') in ('trace', 'calls_query', 'calls_callees')
            and answer.public_diagnostic is not None
            and answer.execution_facts.completeness is AnalysisCompleteness.COMPLETE
            and answer.execution_facts.failures == frozenset({FailureCause.INVALID_REQUEST}))


def _declared_failure(answer) -> str | None:
    """Consume owner facts and diagnostic origin, never rendered result text."""
    from .utils.results import AnalysisCompleteness, FailureCause
    facts = answer.execution_facts
    if facts is None:
        return None
    if FailureCause.OUTPUT not in facts.failures and _trace_absence_compatibility(answer):
        return None
    failed = (facts.completeness in (AnalysisCompleteness.FAILED, AnalysisCompleteness.NOT_STARTED)
              or FailureCause.OUTPUT in facts.failures or FailureCause.INVALID_REQUEST in facts.failures)
    if not failed:
        return None
    if answer.exception is not None:
        exc = answer.exception
        return _tool_failure(str(exc), public=isinstance(exc, OSError), exception=exc)
    if answer.public_diagnostic is not None:
        return _tool_failure(answer.public_diagnostic)
    return _tool_failure(answer.private_diagnostic or 'Required analysis or output failed', public=False)


def _with_retirement_notes(output: str) -> str:
    """Append the retired-spelling notes this call used to a text result (ground rule 7). The MCP
    server never prints them to stderr; a JSON result carries them as ``meta.warnings`` already."""
    from .cli.invocation import noted_retirements
    notes = noted_retirements()
    if not notes or isinstance(output, _ToolFailure):
        return output
    try:
        if isinstance(json.loads(output), dict):
            return output
    except ValueError:
        pass
    return output.rstrip('\n') + ''.join(f'\n[note: {entry.text}]' for entry in notes.values()) + '\n'


def _run_declared_tool(fn, *args, quiet_usage: bool = False, render=None, **kwargs) -> str:
    """Capture one qualified consumer while retaining canonical outcome evidence.

    ``render`` replaces the answer's own emission for a tool with a specialized text layout;
    the outcome policy above it is unchanged."""
    answers = []
    rendered: list[str] = []

    def consume(answer):
        from .utils.results import AnalysisCompleteness
        answers.append(answer)
        if _declared_failure(answer) is not None:
            return
        if answer.execution_facts.completeness is AnalysisCompleteness.INCOMPLETE:
            answer.result.setdefault('meta', {}).setdefault('warnings', []).append(
                {'type': 'analysis_incomplete', 'message': 'Required analysis is incomplete; usable evidence follows.'})
        if render is not None:
            rendered.append(render(answer.result))
        elif quiet_usage and _trace_absence_compatibility(answer):
            answer.emit(announce_error=False)
        else:
            answer.emit()

    output = _run_and_capture(fn, *args, answer_consumer=consume, **kwargs)
    if answers:
        failure = _declared_failure(answers[-1])
        if failure is not None:
            return failure
    if rendered:
        return _with_retirement_notes(rendered[-1])
    return _with_retirement_notes(output)


def mcp_tool(*, annotations: ToolAnnotations | None = None, title: str | None = None):
    """Register failures with explicit origin; retain direct Python strings."""

    def decorator(fn):
        @functools.wraps(fn)
        def request(*args, **kwargs):
            from .utils.request_cache import host_request
            # Direct Python callers and registered tools have the same evidence
            # lifetime, while retaining their distinct error-sentinel contracts.
            with _capture_lock, host_request():
                return fn(*args, **kwargs)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            with _capture_lock:
                _log_mcp_access(fn.__name__, kwargs)
                try:
                    result = request(*args, **kwargs)
                except OSError as exc:
                    raise ToolError(f"reveal error: {failure_of(exc).cause}") from None
                except Exception:  # boundary-ok: broad-except -- SDK 2.0 exposes arbitrary exception details; mask at the registered tool boundary
                    logging.getLogger(__name__).exception("Unexpected failure in MCP tool %s", fn.__name__)
                    raise ToolError(f"Internal error executing tool {fn.__name__}") from None
                except BaseException as exc:  # boundary-ok: broad-except -- a PyO3 PanicException is a BaseException, so no other handler sees it and the client would wait forever for a reply (BACK-2050); every other BaseException (exit, interrupt, cancellation) propagates
                    if type(exc).__name__ != 'PanicException':
                        raise
                    logging.getLogger(__name__).exception("Native extension panic in MCP tool %s", fn.__name__)
                    raise ToolError(f"Internal error executing tool {fn.__name__}") from None
                return _raise_if_tool_failure(result, fn.__name__)

        mcp.tool(annotations=annotations, title=title)(wrapper)
        return request

    return decorator


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: File/Directory Structure')
def reveal_structure(path: str, depth: int = 3, ext: str = '', exclude: str = '', files: bool = False) -> str:
    """Get the semantic structure of a file or directory.

    For **directories**: returns the file tree with sizes and language types.
    For **files**: returns imports, functions, and classes with their signatures.

    This is the first step of progressive disclosure — understand the shape
    before drilling into implementation. A file costs ~150-750 tokens, a
    directory ~100-3,000 by size, vs thousands for reading files directly.

    Args:
        path: File or directory path to inspect (absolute or relative to cwd)
        depth: Directory-tree recursion depth (default 3; directories only)
        ext: Comma-separated extensions to filter to, e.g. 'md' or 'py,md'
            (directories only, matches the CLI's `--ext`; doc-triage pattern:
            reveal_structure(dir, files=True, ext='md'))
        exclude: Comma-separated glob patterns to exclude, e.g. '*.log,tmp/'
            (directories only)
        files: Flat mtime-sorted file list instead of a tree — matches the
            CLI's `--files` (directories only)
    """
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return _tool_failure(f"path not found: {path}")

    args = _default_args(path=str(p))

    if p.is_dir():
        from .cli.routing.file import _parse_ext_arg
        include_extensions = _parse_ext_arg(ext or None)
        exclude_patterns = [e.strip() for e in exclude.split(',') if e.strip()] or None

        if files:
            from .tree_view import show_file_list
            return show_file_list(
                str(p),
                respect_gitignore=args.respect_gitignore,
                exclude_patterns=exclude_patterns,
                include_extensions=include_extensions,
                max_entries=args.max_entries,
            )

        from .tree_view import show_directory_tree
        return show_directory_tree(
            str(p),
            depth=depth,
            max_entries=args.max_entries,
            dir_limit=args.dir_limit,
            fast=args.fast,
            respect_gitignore=args.respect_gitignore,
            exclude_patterns=exclude_patterns,
            include_extensions=include_extensions,
        )

    from .registry import get_analyzer
    from .display.structure import show_structure

    analyzer_class = get_analyzer(str(p), allow_fallback=True)
    if not analyzer_class:
        return _tool_failure(f"no analyzer found for {path}")

    analyzer = analyzer_class(str(p))
    return _run_and_capture(show_structure, analyzer, 'text', args)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Extract Function/Class')
def reveal_element(path: str, element: str) -> str:
    """Extract a specific function or class from a file.

    Use after reveal_structure to drill into the exact code you need.
    Returns the full implementation — more token-efficient than reading
    the whole file when you only need one function.

    Args:
        path: File path containing the element
        element: Function or class name to extract (e.g., 'validate_token')
    """
    from pathlib import Path
    from .registry import get_analyzer
    from .display.element import _parse_element_syntax, _extract_by_syntax

    p = Path(path)
    if not p.exists():
        return _tool_failure(f"path not found: {path}")

    try:
        analyzer_class = get_analyzer(path, allow_fallback=True)
        if not analyzer_class:
            return _tool_failure(f"no analyzer found for {path}")

        analyzer = analyzer_class(path)
        syntax = _parse_element_syntax(element)
        result = _extract_by_syntax(analyzer, element, syntax)
    except Exception as exc:  # noqa: BLE001 -- match every sibling tool's error shape
        return _tool_failure(str(exc), public=isinstance(exc, OSError), exception=exc)

    if not result:
        return _tool_failure(f"element '{element}' not found in {path}")

    line_start = result.get('line_start', 1)
    line_end = result.get('line_end', line_start)
    source = result.get('source', '')
    name = result.get('name', element)

    # Several non-contiguous spans (markdown `A|B` or substring matches, JSONL
    # records of one type, XML elements of one tag): each numbered from its
    # own start line, as the CLI renders them -- the joined `source` numbered
    # from the first start would invent line numbers.
    spans = result.get('sections') or [
        {'line_start': line_start, 'line_end': line_end, 'source': source}
    ]
    body = "\n\n".join(
        f"{path}:{s['line_start']}-{s['line_end']} | {name}\n\n"
        f"{analyzer.format_with_lines(s['source'], s['line_start'])}"
        for s in spans
    )
    # BACK-1400: an ambiguous name must not silently return the first match;
    # the agent gets the same note (and :LINE addresses) the CLI prints.
    if result.get('candidates'):
        from .element_resolve import ambiguity_note
        body += "\n\n" + "\n".join(ambiguity_note(path, element, result['candidates']))
    return body


# Nav flags that take no value (boolean), derived from nav_handlers._NAV_DISPATCH
# (BACK-457) — new boolean nav flags are genuinely automatically supported now,
# not just documented as such: this set can no longer drift from the dispatch
# table it's describing.
from .nav_handlers import NAV_BOOLEAN_FLAG_NAMES as _NAV_BOOLEAN_FLAGS  # noqa: I006

# Nav flags that require a variable-name flag_value, mapped to an example name
# for the error message. Collapses what used to be three near-identical
# copy-pasted elif branches (BACK-457).
_NAV_VAR_NAME_FLAGS = {
    'varflow': 'result',
    'keys': 'config',
    'narrow': 'x',
}


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Deep-Dive Nav Analysis')
def reveal_nav(path: str, element: str, flag: str, flag_value: str = '') -> str:
    """Run a nav analysis flag on a function or line range — the deep-dive layer.

    Use after reveal_structure + reveal_element to analyse the internals of
    a specific function without reading its full source. Highest-value flags:
    boundary (inputs+environment+effects), sideeffects (db/http/cache/log/file
    calls), inputs (candidate reads), outputs (read-after-write hazards),
    callsites (calls within the element), varflow (trace one variable).

    Full flag catalog + examples: reveal_query('help://nav')

    Args:
        path:        File containing the element (absolute or relative to cwd)
        element:     Function/method name (e.g. 'process_order') or line ref
                     (e.g. ':120-340' for flat/procedural files)
        flag:        Nav analysis to run — see reveal_query('help://nav') for
                     the full list. Boolean flags need no flag_value; value
                     flags (varflow, keys, narrow) require one.
        flag_value:  Required for varflow, keys, and narrow (variable name). Optional for
                     callsites (range string) and around (integer context lines).

    Example:
        reveal_nav('app.py', 'process_order', 'boundary')
    """
    from .file_handler import handle_file  # noqa: I006
    from .cli.invocation import Invocation, RetiredSpellingError, invocation_scope, retirement_note

    if flag == 'flow':
        from .nav_handlers import parse_flow_selectors
        try:
            selectors = parse_flow_selectors(flag_value) if flag_value else ()
        except ValueError as exc:
            return _tool_failure(str(exc))
        args = _default_args(flow=selectors)
    elif flag in _NAV_BOOLEAN_FLAGS:
        args = _default_args(**{flag: True})
    elif flag in _NAV_VAR_NAME_FLAGS:
        if not flag_value:
            example = _NAV_VAR_NAME_FLAGS[flag]
            return _tool_failure(f"{flag} requires flag_value (variable name, e.g. '{example}')")
        args = _default_args(**{flag: flag_value})
    elif flag in ('callsites', 'calls'):
        args = _default_args(calls=flag_value or 'FULL')
    elif flag == 'around':
        try:
            n = int(flag_value) if flag_value else 20
        except ValueError:
            return _tool_failure(f"around requires an integer flag_value, got '{flag_value}'")
        args = _default_args(around=n)
    else:
        valid = sorted(_NAV_BOOLEAN_FLAGS | set(_NAV_VAR_NAME_FLAGS) | {'callsites', 'calls', 'around', 'flow'})
        return _tool_failure(f"unknown nav flag '{flag}'. Valid flags: {valid}")

    option = '--' + flag
    if flag_value and flag not in _NAV_BOOLEAN_FLAGS:
        option += '=' + flag_value
    invocation = Invocation.parse(['reveal', option, '--', path, element])
    with _capture_lock, invocation_scope(invocation, retirements_to_stderr=False):
        try:
            retirement_note('flag:--' + flag)
        except RetiredSpellingError as exc:
            return _tool_failure(str(exc))
        return _with_retirement_notes(_run_and_capture(handle_file, path, element, False, 'text', args))


@mcp_tool(annotations=_OPEN_WORLD_READONLY, title='Reveal: URI Query')
def reveal_query(uri: str, provenance: bool = False) -> str:
    """Run a reveal URI query across any adapter (``scheme://resource?query`` syntax).

    Use for anything outside the file/nav workflow: call graphs, import
    health, git history, SSL/domain checks, database/Excel
    inspection, doc search, and more — one URI syntax for every adapter; the
    query keys each adapter accepts are its own (see below).

    Lost, or need an adapter you don't know the name of? Start with
    reveal_query('help://quick') — a map of every adapter and common task.

    CLI-only global flags (--severity, --select, --format) do NOT pass
    through to this tool — there's no argv for them to come from here.
    '?limit=N', '?sort=field' (or '?sort=-field' for desc) and '?offset=M'
    are applied by ast://, markdown://, json://, git:// and stats:// only;
    other adapters answer "Unknown query param ... ignored" -- use their own
    key instead (hotspots://, calls://, depends:// and patches://?view=pressure take '?top=N').
    Every other per-adapter option is that adapter's own '?key=value'
    vocabulary, not a generic CLI-flag passthrough — check
    reveal_query('help://schemas/<adapter>') for what a given scheme accepts.
    For severity/select filtering, use a dedicated typed tool instead
    (reveal_check has severity/select/ignore).

    Args:
        uri: Full reveal URI, e.g. 'calls://src/?callers=my_fn' or 'help://quick'
        provenance: When true, attach a '--provenance' execution manifest
            (git state, command, timestamp) to the result, for callers that
            need to cite evidence provenance (e.g. a DD finding contract).
            Forces JSON output (provenance only attaches to dict results),
            so the response shape differs from a plain-text query — only set
            this when the caller actually needs the manifest.
    """
    from .cli.invocation import Invocation, invocation_scope
    from .cli.routing import handle_uri
    from .utils.json_utils import set_provenance_enabled

    args = _default_args(path=uri, provenance=provenance, format='json' if provenance else 'text')
    # The CLI command equivalent to this call: what a provenance manifest records as the
    # command, instead of the server's own argv (BACK-1058).
    invocation = Invocation.parse(['reveal', uri] + (['--format', 'json', '--provenance'] if provenance else []))
    # Holds _capture_lock across the whole provenance-flag lifecycle (not just
    # inside _run_and_capture) because set_provenance_enabled is a second
    # process-global, independent of the stdout/stderr one _run_and_capture
    # already serializes -- a concurrent call with provenance=False must not
    # observe this call's flag mid-flight. _capture_lock is an RLock so
    # _run_and_capture's own internal acquisition below doesn't deadlock.
    with _capture_lock, invocation_scope(invocation, retirements_to_stderr=False):
        apply_global_flags(args)
        try:
            return _run_declared_tool(handle_uri, uri, None, args, quiet_usage=provenance)
        finally:
            set_provenance_enabled(False)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Token-Budgeted Context Pack')
def reveal_pack(
    path: str,
    budget: int = 8000,
    since: str = '',
    content: bool = True,
    focus: str = '',
    architecture: bool = False,
) -> str:
    """Get a token-budgeted context snapshot of a codebase — ideal for PR review.

    Use for breadth: PR review (via ``since``), an unfamiliar repo, a one-shot
    handoff. For a question about a specific file or function,
    reveal_structure + reveal_element answer directly. ``budget`` bounds the
    raw size of the files selected, not the size of the answer: the answer is
    names plus structure, typically a few hundred to a few thousand tokens,
    with raw content only for changed files (``since``, first 500 lines each).

    Selects the most important files within the token budget, prioritizing:
    1. Changed files (when ``since`` is set)
    2. Entry points (main.py, app.py, index.js, etc.)
    3. Key architectural modules (api/, models/, auth/, core/)
    4. Ties broken by most recently modified

    With ``content=True`` (default), includes tiered structure output:
    - Changed files → raw content, first 500 lines (see exactly what changed)
    - Key files → reveal structure (function signatures, imports)
    - Low-priority files → names only

    Args:
        path: Directory to pack
        budget: Budget in approximate tokens of the selected files' raw size (default 8000)
        since: Git ref for PR review mode, e.g. 'main' or 'HEAD~3' (prioritizes changed files)
        content: Include file structure in output (default True)
        focus: Emphasize files matching this name pattern (e.g., 'auth', 'api')
        architecture: Prepend an architecture brief (entry points + high fan-in
            core abstractions) before the file listing
    """
    from pathlib import Path
    from .cli.routing.declared import run_declared_command
    from .cli.invocation import Invocation, invocation_scope
    from .analyzers.imports.service import edge_rule_lines
    from .rendering.adapters.pack import _format_pack_result
    from .utils.json_utils import set_provenance_enabled

    p = Path(path)
    if not p.exists():
        return _tool_failure(f"{path}: not found")

    argv = ['reveal', 'pack', str(p), '--budget', str(budget)]
    for flag, value in (('--focus', focus), ('--since', since)):
        if value:
            argv += [flag, value]
    argv += [flag for flag, on in (('--content', content), ('--architecture', architecture)) if on]
    args = _default_args(path=str(p), budget=str(budget), focus=focus or None, since=since or None,
                         content=content, architecture=architecture, format='text')

    def render(result):
        meta = result['meta']
        text = _format_pack_result(
            p, result['files'], meta, meta['budget_tokens'], meta['budget_lines'],
            since_error=meta.get('since_error'), content=content,
            architecture=result.get('architecture', False), content_data=result.get('content'),
            rule_lines=edge_rule_lines(result))
        if (focus or architecture) and meta.get('relevance_warning'):
            # A requested optional signal that could not be built; the default
            # "not requested" notice stays out of this tool's layout.
            text += f"\n  ⚠ {meta['relevance_warning']}"
        return text

    invocation = Invocation.parse(argv)
    with _capture_lock, invocation_scope(invocation, retirements_to_stderr=False):
        apply_global_flags(args)
        try:
            return _run_declared_tool(run_declared_command, 'pack', args, render=render)
        finally:
            set_provenance_enabled(False)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Quality Check')
def reveal_check(path: str, severity: str = '', select: str = '', ignore: str = '') -> str:
    """Run quality checks on a file or directory.

    Rule series: B bugs, C complexity, D duplicates, E style (line length),
    F front matter, I imports, L links, M maintainability, N nginx,
    R refactoring, S security, T types, U URLs, V reveal self-validation
    (full list: reveal_query('help://rules')).

    Returns issues grouped by file, one line each (line, rule code, message,
    severity), then the total; or "No issues found." Notes come first for
    rules skipped on a language and files that errored or didn't parse cleanly.

    Args:
        path: File or directory to check (recurses into directories)
        severity: Minimum severity to show: 'low', 'medium', 'high', or 'critical'
        select: Comma-separated rule codes/series to run, e.g. 'M' or 'B006,S701'
            (same as CLI --select; see reveal_query('help://rules') for the list)
        ignore: Comma-separated rule codes/series to exclude, e.g. 'N'
    """
    from pathlib import Path
    from .cli.file_checker import collect_files_to_check, _check_files_json

    p = Path(path)
    if not p.exists():
        return _tool_failure(f"{path}: no such file or directory")

    severity_filter = severity or None
    # BACK-1605: an unknown code is an error, as on the CLI, not a clean result.
    from .rules import parse_rule_patterns
    try:
        select_list = parse_rule_patterns(select) or None
        ignore_list = parse_rule_patterns(ignore) or None
    except ValueError as e:
        return _tool_failure(f"{e}")

    collection = None
    if p.is_dir():
        directory = p.resolve()
        collection = collect_files_to_check(directory)
        files = collection.files
        if not files and not collection.traversal_failures:
            return f"No files found to check in {path}"
    else:
        directory = p.parent.resolve()
        files = [p.resolve()]

    total_issues, _, file_results, _, _ = _check_files_json(
        files, directory, select_list, ignore_list, severity=severity_filter
    )
    notes, incomplete = _check_notes(
        files, select_list, ignore_list, file_results, collection=collection, directory=directory)

    if total_issues == 0:
        return "\n".join(notes + [_check_zero_verdict(notes, incomplete)])

    lines = list(notes)
    for fr in file_results:
        n = fr['issues']
        if not n:
            continue
        lines.append(f"\n{fr['file']}: Found {n} issue{'s' if n != 1 else ''}\n")
        for d in fr['detections']:
            loc = f"L{d['line']}"
            if d.get('column'):
                loc += f" C{d['column']}"
            lines.append(f"  {loc} [{d['rule_code']}] {d['message']} ({d['severity']})")
            if d.get('suggestion'):
                lines.append(f"  → {d['suggestion']}")

    lines.append(f"\n{total_issues} issue{'s' if total_issues != 1 else ''} found.")
    return "\n".join(lines)


def _check_zero_verdict(notes, incomplete) -> str:
    """Keep discovery and rule losses distinct from a complete zero-findings answer."""
    if incomplete:
        return "No findings in the checked population; scan incomplete."
    if notes:
        return "No issues found (some rules skip these languages; see notes above)."
    return "No issues found."


def _check_notes(files, select_list, ignore_list, file_results, *,
                 collection=None, directory=None) -> tuple[list[str], bool]:
    """Request-scoped diagnostics that precede every MCP check verdict, and whether
    any of them makes the scan incomplete (the CLI's exit 3). A language gap is a
    note only (BACK-1826)."""
    from .checks import capability_disclosures
    from .rules.scan_caches import get_scan_disclosures
    disclosures = get_scan_disclosures(files, select_list, ignore_list)
    if collection is not None and directory is not None:
        from .cli.file_checker import _collection_disclosures
        disclosures = _collection_disclosures(collection, directory) + disclosures
    incomplete = bool(disclosures)
    notes = [f"⚠️  {n}" for n in
             disclosures + capability_disclosures(files, select_list, ignore_list)]
    for fr in file_results:
        incomplete = incomplete or fr.get('status') in ('error', 'warning') or bool(fr.get('rule_errors'))
        if fr.get('status') == 'error':
            notes.append(f"⚠️  {fr['file']}: could not be checked -- {fr.get('detail', 'analyzer error')}")
        elif fr.get('status') == 'warning':
            notes.append(f"⚠️  {fr['file']}: " + fr.get('detail', 'did not parse cleanly; results may be incomplete or incorrect'))
        for err in fr.get('rule_errors', []):
            notes.append(f"⚠️  {fr['file']}: rule {err['rule']} crashed and did not run -- {err['error']}")

    return notes, incomplete


@mcp_tool(annotations=_OPEN_WORLD_READONLY, title='Reveal: Health Verdict')
def reveal_health(target: str, select: str = '') -> str:
    """Run a unified health check on a path or URI resource.

    Checks code quality thresholds for a local path, or SSL/database/DNS
    health for a URI resource (ssl://, mysql://, domain://). Returns a
    PASS/WARN/FAIL/INCOMPLETE verdict per target plus a one-line summary — narrower
    and faster than reveal_check/reveal_query/reveal_review for a quick
    go/no-go read. For an itemized list of issues instead of a verdict, use
    reveal_check (a file/dir) or reveal_review (pre-merge, git-range aware).

    Args:
        target: Path or URI to check (e.g. './src', 'ssl://example.com', 'mysql://host')
        select: Rule categories to check for code targets (e.g. 'B,S,I,C')
    """
    from .cli.commands.health import run_health

    args = _default_args(targets=[target], select=select or None, health_all=False)
    return _run_and_capture(run_health, args)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Pre-Merge Review')
def reveal_review(target: str, select: str = 'B,S,I,C,M') -> str:
    """Assess code quality before a PR merge — violations, hotspots, complexity spikes.

    The CLI's `reveal review` is retired into `reveal check --changed RANGE` plus the `diff://git://A/.:git://B/.`
    adapter and prints a replaced-by note; this tool keeps its name and answer until Phase 7.

    For a git range (e.g. 'main..feature'), scopes analysis to only the
    changed files. For a directory, reviews the whole tree.

    Args:
        target: Path to review, or a git range like 'main..feature'
        select: Rule categories (default: 'B,S,I,C,M')
    """
    from .cli.commands.review import run_review

    args = _default_args(target=target, select=select)
    # BACK-REVEAL-3: run_review's progress lines + a duplicated "Review: <target>"
    # header go to stderr; captured to a buffer instead of a live TTY they're
    # pure noise -- the real report is entirely on stdout.
    return _run_and_capture(run_review, args, capture_stderr=False)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Structural Grep')
def reveal_grep(path: str, pattern: str, ignore_case: bool = False) -> str:
    """Search text or an identifier across a file or directory, grouped by enclosing function.

    Structural cross-file search: each matching line (number and text) is
    listed under the function/class/heading it falls in — prefer this over
    shell grep for finding a symbol's usages or a string across a codebase.
    Shows the first 100 hits and says how many it left out.

    Args:
        path: File or directory to search
        pattern: Regex pattern to search for
        ignore_case: Case-insensitive match (default False)
    """
    from pathlib import Path
    from .cli.routing.grep import handle_grep, handle_grep_directory

    p = Path(path)
    if not p.exists():
        return _tool_failure(f"path not found: {path}")

    args = _default_args(ignore_case=ignore_case)
    if p.is_dir():
        return _run_and_capture(handle_grep_directory, str(p), pattern, args)
    return _run_and_capture(handle_grep, str(p), pattern, args)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Call-Graph Trace')
def reveal_trace(path: str, entry_point: str, depth: int = 2) -> str:
    """Walk the call graph from a named entry point as a depth-indented execution narrative.

    The narrative view of the calls:// callee walk: the same walk as
    reveal_query('calls://<path>?callees=FUNC&depth=N&detail'), which replaces it (the CLI's
    `reveal trace` and `trace://` already print a replaced-by note; this tool keeps its name for
    now). Each frame shows the function's location, parameters, classified side effects
    (db/http/log/file/...), and what it calls next — useful for "walk me through what happens
    when X runs."

    Args:
        path: Source directory to analyse
        entry_point: Entry-point function name to start the trace from; use
            'path/to/file.py:name' to pick one of several same-named definitions
        depth: Call levels to expand, 1-5 (default 2)
    """
    from pathlib import Path
    from .cli.routing.declared import run_declared_command
    from .cli.invocation import Invocation, RetiredSpellingError, invocation_scope, retirement_note
    from .utils.json_utils import set_provenance_enabled

    p = Path(path)
    if not p.exists():
        return _tool_failure(f"path not found: {path}")

    args = _default_args(path=str(p), root=entry_point, depth=depth, format='text')
    invocation = Invocation.parse(['reveal', 'trace', str(p), '--from', entry_point, '--depth', str(depth)])
    with _capture_lock, invocation_scope(invocation, retirements_to_stderr=False):
        apply_global_flags(args)
        try:
            retirement_note('mcp:reveal_trace')
        except RetiredSpellingError as exc:
            return _tool_failure(f'error: {exc.entry.text}')
        try:
            return _run_declared_tool(run_declared_command, 'trace', args)
        finally:
            set_provenance_enabled(False)


# ---------------------------------------------------------------------------
# MCP Resources — self-description surface (BACK-1171)
#
# Pure static/semi-static reference data (adapter list, per-adapter schemas,
# rule catalog, quick-reference map) belongs on Resources, not Tools: it has
# no side effects, doesn't change mid-session, and a host can cache it
# (ttlMs) instead of spending a model-decided tool call every time an agent
# needs to check valid syntax. All four are thin wrappers over the same
# handle_uri() dispatch reveal_query already uses for these same 'help://'
# URIs — this just exposes them via the protocol-native primitive too.
# ---------------------------------------------------------------------------

def _read_help_uri(uri: str) -> str:
    from .cli.routing import handle_uri

    args = _default_args(path=uri, format='text')
    return _run_and_capture(handle_uri, uri, None, args)


@mcp.resource(
    'help://quick',
    name='reveal_help_quick',
    title='Reveal: Quick Reference',
    description=(
        "Router map of every reveal adapter/task with a starter query — "
        "the fastest way to find the right command for a scenario."
    ),
    mime_type='text/plain',
)
def resource_help_quick() -> str:
    return _read_help_uri('help://quick')


@mcp.resource(
    'help://adapters',
    name='reveal_help_adapters',
    title='Reveal: Adapter Catalog',
    description=(
        "Full list of every registered reveal URI adapter with one-line "
        "syntax and an example."
    ),
    mime_type='text/plain',
)
def resource_help_adapters() -> str:
    return _read_help_uri('help://adapters')


@mcp.resource(
    'help://rules',
    name='reveal_help_rules',
    title='Reveal: Quality Rule Catalog',
    description=(
        "Every reveal quality-check rule ID (B/S/I/C/M categories) with a "
        "one-line description."
    ),
    mime_type='text/plain',
)
def resource_help_rules() -> str:
    return _read_help_uri('help://rules')


@mcp.resource(
    'help://schemas/{adapter}',
    name='reveal_help_schema',
    title='Reveal: Adapter Schema',
    description=(
        "Exact query syntax (fields, operators, examples) for one reveal "
        "adapter, generated live from its own schema — check this before "
        "guessing at filter syntax for a specific scheme."
    ),
    mime_type='text/markdown',
)
def resource_help_schema(adapter: str) -> str:
    return _read_help_uri(f'help://schemas/{adapter}')


def main() -> None:
    """Entry point for the ``reveal-mcp`` command."""
    import argparse

    parser = argparse.ArgumentParser(
        prog='reveal-mcp',
        description='Reveal MCP server — progressive disclosure for AI agents',
    )
    parser.add_argument(
        '--transport',
        choices=['stdio', 'sse', 'streamable-http'],
        default='stdio',
        help='Transport to use (default: stdio for Claude Code)',
    )
    parser.add_argument(
        '--host',
        default='127.0.0.1',
        help='Host for SSE/HTTP transport (default: 127.0.0.1)',
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='Port for SSE/HTTP transport (default: 8000)',
    )
    args = parser.parse_args()

    if args.transport == 'stdio':
        mcp.run(transport='stdio')
    elif args.transport == 'sse':
        mcp.run(transport='sse', host=args.host, port=args.port)
    else:
        mcp.run(transport='streamable-http', host=args.host, port=args.port)


if __name__ == '__main__':
    main()
