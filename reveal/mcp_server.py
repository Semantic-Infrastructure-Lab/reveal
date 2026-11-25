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
import inspect
import io
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

try:
    from mcp.server import MCPServer
    from mcp.server.mcpserver.exceptions import ToolError
    from mcp.types import ToolAnnotations
    from pydantic import Field, StrictBool, StrictInt, StrictStr, TypeAdapter, ValidationError
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
from .utils.results import NavSourceFailure
from .errors import ConfigLoadError, ConfigValidationError, NavRequestValidationError, TestLayoutValidationError

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
        "0. reveal_run(['overview', '<dir>']) — orient in an unfamiliar "
        "codebase first: a compact map of scope, components and import "
        "relationships, one screen. This is reveal's own best answer to \"what is this repo\" — "
        "start here before structure/element/nav on unfamiliar code.\n"
        "1. reveal_structure(dir) — understand what's in a directory (~100-3,000 tokens, by size)\n"
        "2. reveal_structure(file) — see all functions/classes (~150-750 tokens; ~1,300 for a 1,000-line module)\n"
        "3. reveal_element(file, fn) — read one function's implementation (~100-600 tokens)\n"
        "4. reveal_nav(file, fn, view='boundary') — deep-dive analysis without reading source:\n"
        "   view='boundary'  — INPUTS + ENVIRONMENT + EFFECTS in one report\n"
        "   view='effects'   — ordinary calls, loop groups (mode='loops'), persistent writes (mode='state')\n"
        "   view='flow'      — recognized structural skeleton; kind=['if', 'loop', 'try'] selects\n"
        "   view='exits'     — static exit sites with recorded syntactic gates\n"
        "   flag='inputs'    — candidate undefined reads, with builtins distinguished\n"
        "   flag='outputs'   — variables written in a range and read later\n"
        "   flag='callsites' — call sites within the selected element or range\n"
        "   flag='varflow', flag_value='VAR' — trace one variable's reads and writes\n"
        "5. reveal_grep(path, pattern) — \"where is X used?\" cross-file "
        "search grouped by enclosing function (use instead of shell grep).\n"
        "6. reveal_run(['calls', '<dir>', '--callees', 'FN', '--depth', '2', '--detail', 'full']) — \"what "
        "happens when X runs?\" level-by-level callee walk with params and side "
        "effects (reveal_trace(dir, entry_point) renders the same walk as a "
        "depth-indented narrative).\n"
        "7. reveal_query('help://quick') — lost, or need an adapter outside "
        "this workflow (git, imports, sqlite, env, infra adapters like ssl/"
        "domain/mysql/cpanel, ...)? Start here for an orientation map of "
        "everything else reveal://* can do — it's the full escape hatch, not "
        "just these named tools.\n"
        "8. reveal_run(['calls', 'src', '--callers', 'FN']) — any reveal command line, one list "
        "item per word: the CLI's grammar, answer and exit meaning (flags, not query strings).\n\n"
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
    captured = _capture(fn, *args, **kwargs)
    raised = _raised_failure(captured)
    if raised is not None:
        return raised
    out, err, exit_code = captured.out, captured.err, captured.exit_code
    if out.strip():
        return _with_stderr(out, err) if capture_stderr else out
    if exit_code not in (0, None):
        msg = f"[reveal exited with code {exit_code}]"
        return f"{msg}: {err}" if err else msg
    if capture_stderr and err:
        return f"[stderr: {err}]"
    return out


@dataclass
class _Captured:
    """What one in-process run printed and how it ended: its stdout, its stripped stderr, the code it exited with
    (None when it returned) and what it raised."""
    out: str
    err: str
    exit_code: object = None
    exception: Optional[Exception] = None
    source_failure: Optional[NavSourceFailure] = None


def _capture(fn, *args, **kwargs) -> _Captured:
    """Run fn with stdout and stderr captured, under _capture_lock (they are process globals)."""
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    captured = _Captured('', '')
    with _capture_lock:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = out_buf
        sys.stderr = err_buf
        try:
            fn(*args, **kwargs)
        except NavSourceFailure as exc:
            captured.source_failure = exc
        except SystemExit as e:
            captured.exit_code = e.code
        except Exception as exc:  # boundary-ok: broad-except -- arbitrary adapter code; preserve origin for the registered boundary to mask crashes
            captured.exception = exc
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
    captured.out = out_buf.getvalue()
    captured.err = err_buf.getvalue().strip()
    return captured


def _raised_failure(captured: _Captured) -> str | None:
    """The tool failure for a run that raised: a failed navigation source, or an exception (public when it is an
    invalid request or an unusable input the caller can act on, masked otherwise)."""
    from .utils.results import execution_failed
    source_failure, exc = captured.source_failure, captured.exception
    if source_failure is not None and execution_failed(source_failure.execution_facts):
        return _tool_failure(source_failure.public_diagnostic)
    if exc is None:
        return None
    from .cli.invocation import RetiredSpellingError
    return _tool_failure(str(exc), public=isinstance(exc, (OSError, NavRequestValidationError, TestLayoutValidationError,
                                                          ConfigValidationError, ConfigLoadError, RetiredSpellingError)),
                         exception=exc)


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
    """Consume owner facts and diagnostic origin, never rendered result text. A failed analysis (exit 3) with no
    authored public diagnostic is given in reveal's own words, the text the Python API raises for the same answer
    (``analysis_failure_text``, BACK-2786); a failure with no authored text stays masked."""
    from .utils.results import FailureCause, analysis_failure_text, execution_exit_code, execution_failed
    facts = answer.execution_facts
    if facts is None:
        return None
    if FailureCause.OUTPUT not in facts.failures and _trace_absence_compatibility(answer):
        return None
    if not execution_failed(facts):
        return None
    if answer.exception is not None:
        exc = answer.exception
        if isinstance(exc, OSError) and answer.public_diagnostic is not None:
            # The owner's own line for a file it could not read ("Error: cannot read F: Permission denied"), as the
            # CLI prints it; str(OSError) is a Python spelling with the path in it (BACK-2249).
            return _tool_failure(answer.public_diagnostic, exception=exc)
        return _tool_failure(str(exc), public=isinstance(exc, (OSError, ConfigLoadError)), exception=exc)
    if answer.public_diagnostic is not None:
        return _tool_failure(answer.public_diagnostic)
    authored = analysis_failure_text(answer.result) if execution_exit_code(facts) == 3 else None
    if authored is not None:
        return _tool_failure(authored)
    return _tool_failure(answer.private_diagnostic or 'Required analysis or output failed', public=False)


def _is_json_document(text: str) -> bool:
    """True when the tool text is one JSON object: the CLI's JSON answer, which must reach the
    client exactly as the CLI prints it (COMMAND_MODEL 'Transports')."""
    if not text.lstrip().startswith('{'):
        return False
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def _with_stderr(out: str, err: str) -> str:
    """The CLI's stdout followed by its stderr, as a terminal shows them. A JSON answer is the CLI's JSON
    exactly and the whole answer (COMMAND_MODEL 'Transports'): every diagnostic is in it (config and plugin
    warnings, per-file failures; BACK-2659), so a JSON answer has no stderr beside it, and anything that
    still reaches stderr is a defect, logged for the server's operator rather than sent to the client."""
    if not err:
        return out
    if _is_json_document(out):
        logging.getLogger(__name__).warning('stderr beside a JSON answer, not sent to the client: %s', err)
        return out
    return f"{out}\n[stderr: {err}]"


def _with_invocation_notes(output: str) -> str:
    """Append what this call recorded for its answer to a text result: each retired spelling's note
    (ground rule 7) and each configuration warning (BACK-2659), as a terminal would show them after
    the answer. The MCP server never prints them to stderr; a JSON result carries them in
    ``meta.warnings`` already."""
    from .cli.invocation import noted_retirements
    from .utils.invocation_log import unreported_warnings
    lines = ([f'[note: {entry.text}]' for entry in noted_retirements().values()]
             + [f"[warning: {entry['message']}]" for entry in unreported_warnings()])
    if not lines or not isinstance(output, str) or isinstance(output, _ToolFailure) or _is_json_document(output):
        return output
    return output.rstrip('\n') + ''.join(f'\n{line}' for line in lines) + '\n'


def _run_declared_tool(fn, *args, quiet_usage: bool = False, render=None, **kwargs) -> str:
    """Capture one qualified consumer while retaining canonical outcome evidence.

    ``render`` replaces the answer's own emission for a tool with a specialized text layout;
    the outcome policy above it is unchanged."""
    answers = []
    rendered: list[str] = []

    def consume(answer):
        from .utils.results import AnalysisCompleteness, note_incomplete
        answers.append(answer)
        if _declared_failure(answer) is not None:
            return
        partial = answer.execution_facts.completeness is AnalysisCompleteness.INCOMPLETE
        if render is not None:
            # A specialized layout skips the emit boundary that marks an incomplete answer, so mark it here.
            note_incomplete(answer.result, answer.execution_facts)
            rendered.append(render(answer.result))
        elif partial or (quiet_usage and _trace_absence_compatibility(answer)):
            answer.emit(announce_error=False)
        else:
            answer.emit()

    output = _run_and_capture(fn, *args, answer_consumer=consume, **kwargs)
    if answers:
        failure = _declared_failure(answers[-1])
        if failure is not None:
            return failure
    if rendered:
        return rendered[-1]
    return output


def mcp_tool(*, annotations: ToolAnnotations | None = None, title: str | None = None):
    """Register failures with explicit origin; retain direct Python strings."""

    def decorator(fn):
        @functools.wraps(fn)
        def request(*args, **kwargs):
            from .utils.request_cache import host_request
            from .utils.invocation_log import log_scope
            # Direct Python callers and registered tools have the same evidence
            # lifetime, while retaining their distinct error-sentinel contracts.
            # One invocation log per call: what it records rides in the result, never on stderr.
            with _capture_lock, host_request(), log_scope(to_stderr=False):
                return _with_invocation_notes(fn(*args, **kwargs))

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
    # `path` is a filesystem path, never a URI or a command word: the existence check keeps a missing name from being
    # read as either, and `--` below keeps a path named like a subcommand (`check/`) a path.
    if not Path(path).exists():
        return _tool_failure(f"path not found: {path}")
    return _run_command(_structure_command(path, depth, ext, exclude, files))


def _structure_command(path: str, depth: int, ext: str, exclude: str, files: bool) -> list[str]:
    """The CLI command line reveal_structure answers: ``reveal PATH`` in text, plus the directory controls on a
    directory (a file view reads none of them; the tool ignores them there, as it always did). The file route then
    gives the answer and the outcome: a file that failed to parse is a tool error naming the cause, a directory under
    a missing ``REVEAL_CONFIG`` the invalid request (BACK-2762)."""
    options = ['--format', 'text']
    if Path(path).is_dir():
        options += ['--files'] if files else ['--depth', str(depth)]
        if ext:
            options += ['--ext', ext]
        for pattern in (e.strip() for e in exclude.split(',')):
            if pattern:
                options += ['--exclude', pattern]
    return [*options, '--', path]


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Extract Function/Class')
def reveal_element(path: str, element: str) -> str:
    """Extract a specific function or class from a file.

    Use after reveal_structure to drill into the exact code you need.
    Returns the full implementation — more token-efficient than reading
    the whole file when you only need one function.

    The answer is ``reveal PATH ELEMENT``'s: the element as the CLI prints it, any element spelling the CLI takes
    (``Class.method``, ``:LINE``, ``:A-B``, ``function:2``, ``@2``), and the CLI's outcome: a miss is a tool error
    naming the miss and what the file holds, a file that failed to parse a tool error naming the cause (BACK-2775).

    Args:
        path: File path containing the element
        element: Function or class name to extract (e.g., 'validate_token')
    """
    # As reveal_structure: `path` is a filesystem path, never a URI or a command word, and `--` keeps an element
    # spelled like a flag (`-x`) an element.
    if not Path(path).exists():
        return _tool_failure(f"path not found: {path}")
    return _run_command(['--format', 'text', '--', path, element])


# reveal_nav's mode is the MCP spelling of the effects view's two switches (D10; P1 ruling 6 keeps it): each mode
# names the declared switch it turns on, ``ordinary`` none.
_NAV_MODES = {'ordinary': None, 'loops': 'in-loops', 'state': 'state'}
# A declared control's value type as the MCP schema states it (strict: a direct call is judged as a registered one).
_NAV_VALUE_TYPES: dict[str, Any] = {'boolean': StrictBool, 'integer': StrictInt, 'string': StrictStr}


def _nav_view_specs() -> tuple:
    """The element views' declared controls reveal_nav takes as typed parameters: the view and every control an
    element view reads (``answers`` names ``view`` or ``view=V``), less the switches ``mode`` spells."""
    from .nav_params import ELEMENT_VIEW_SPECS, VIEW
    switches = {name for name in _NAV_MODES.values() if name}
    return tuple(spec for spec in ELEMENT_VIEW_SPECS if spec.name not in switches and (
        spec is VIEW or any(answer == 'view' or answer.startswith('view=') for answer in spec.answers)))


def _nav_view_parameter(spec) -> inspect.Parameter:
    """One declared control as a keyword parameter: its name with ``-`` as ``_``, its type (a list when it repeats),
    its description; absent by default (a switch off), so only what the caller gives reaches the command line."""
    value = _NAV_VALUE_TYPES[spec.type]
    if spec.repeatable:
        value = list[value]  # type: ignore[valid-type]
    if spec.type == 'boolean':
        return inspect.Parameter(spec.name.replace('-', '_'), inspect.Parameter.KEYWORD_ONLY, default=False,
                                 annotation=Annotated[value, Field(description=spec.description)])
    return inspect.Parameter(spec.name.replace('-', '_'), inspect.Parameter.KEYWORD_ONLY, default=None,
                             annotation=Annotated[Optional[value], Field(description=spec.description)])


def _with_nav_view_parameters(fn):
    """*fn*'s signature with its ``**controls`` replaced by the element views' declared controls (before ``mode``):
    the SDK builds reveal_nav's input schema from it, so the schema is the declarations (BACK-2627 X13)."""
    signature = inspect.signature(fn, eval_str=True)
    own = [param for param in signature.parameters.values() if param.kind is not inspect.Parameter.VAR_KEYWORD]
    at = next(index for index, param in enumerate(own) if param.name == 'mode')
    fn.__signature__ = signature.replace(
        parameters=[*own[:at], *(_nav_view_parameter(spec) for spec in _nav_view_specs()), *own[at:]])
    fn.nav_types = {param.name: TypeAdapter(param.annotation) for param in fn.__signature__.parameters.values()
                    if param.name not in ('path', 'element')}
    return fn


def _nav_flag_words(flag: str, flag_value: str, options) -> list[str]:
    """``flag`` as the CLI flag it names (every spelling of an element control, ``ELEMENT_KEYS``), with ``flag_value``
    as its value: ``--FLAG`` for a flag that takes none, ``--FLAG=VALUE`` otherwise (an optional value may be left
    out). Raises NavRequestValidationError for what the flag parameter cannot carry; the CLI judges the rest."""
    from .nav_params import ELEMENT_KEYS
    if flag not in ELEMENT_KEYS:
        raise NavRequestValidationError(f"unknown nav flag '{flag}'. Valid flags: {sorted(ELEMENT_KEYS)}")
    option, action = options[flag.replace('-', '_')]
    if action.nargs == 0 and flag_value:
        raise NavRequestValidationError(f'{flag} takes no flag_value')
    if action.nargs == 0 or (action.nargs == '?' and not flag_value):
        return [option]
    return [f'{option}={flag_value}']


def _nav_words(flag: str, flag_value: str, mode, controls: dict) -> list[str]:
    """reveal_nav's request as the CLI's words: ``flag`` first, then ``mode``'s switch and the typed controls, each
    the flag of its declaration, spelled by the element read's one keyword-to-flag mapping (``path_read_words``, as
    ``api.element``). Raises NavRequestValidationError for a value of the wrong type or an unknown parameter."""
    from .version import __version__
    from .cli.parser import create_argument_parser
    from .cli.routing.typed import path_read_options, path_read_words
    types = reveal_nav.nav_types
    unknown = sorted(set(controls) - set(types))
    if unknown:
        raise NavRequestValidationError(f"reveal_nav has no parameter {', '.join(map(repr, unknown))}; "
                                        f"its parameters: path, element, {', '.join(types)}")
    for name, value in {'flag': flag, 'flag_value': flag_value, 'mode': mode, **controls}.items():
        try:
            types[name].validate_python(value)
        except ValidationError as exc:
            raise NavRequestValidationError(f"{name}: {exc.errors()[0]['msg']}, got {value!r}") from None
    parser = create_argument_parser(__version__)
    words = _nav_flag_words(flag, flag_value, path_read_options(parser, element=True)) if flag else []
    switch = _NAV_MODES.get(mode)
    given = {switch.replace('-', '_'): True} if switch else {}
    given.update((name, value) for name, value in controls.items() if value is not None and value is not False)
    return words + path_read_words(parser, given, element=True)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Deep-Dive Nav Analysis')
@_with_nav_view_parameters
def reveal_nav(path: str, element: str, flag: str = '', flag_value: str = '', *,
               mode: Optional[Literal['ordinary', 'loops', 'state']] = None, **controls: Any) -> str:
    """Run an element view on a function or line range — the deep-dive layer.

    Use after reveal_structure + reveal_element to analyse the internals of
    a specific function without reading its full source. The answer is
    ``reveal PATH ELEMENT --view VIEW``'s, with the CLI's outcome: views are
    boundary (inputs+environment+effects), effects (db/http/cache/log/file
    calls; mode=loops groups them per loop, mode=state lists persistent
    writes), flow (structural skeleton; kind=['if', 'loop'] selects) and
    exits (exit sites with their gates).

    The operations outside the views go in ``flag``: inputs (candidate reads),
    outputs (read-after-write hazards), callsites (calls within the element),
    varflow, keys and narrow (flag_value names the variable), scope and
    around (a :LINE element). ``flag`` is the CLI's flag without its dashes
    and answers as that flag does, a retiring one with its replacement note.

    Full catalog + examples: reveal_query('help://nav')

    Args:
        path:        File containing the element (absolute or relative to cwd)
        element:     Function/method name (e.g. 'process_order') or line ref
                     (e.g. ':120-340' for flat/procedural files)
        flag:        An operation or other element flag, without '--'
        flag_value:  The flag's value (a variable name for varflow, keys and narrow)
        mode:        Effects view: ordinary (default), loops or state

    Example:
        reveal_nav('app.py', 'process_order', view='boundary')
    """
    try:
        words = _nav_words(flag, flag_value, mode, controls)
    except NavRequestValidationError as exc:
        return _tool_failure(str(exc))
    # As reveal_element: `path` is a filesystem path, never a URI or a command word, this tool promises text
    # (REVEAL_FORMAT sets the CLI's default only), and `--` keeps an element spelled like a flag an element.
    if not Path(path).exists():
        return _tool_failure(f"path not found: {path}")
    return _run_command(['--format', 'text', *words, '--', os.fspath(path), element])


@mcp_tool(annotations=_OPEN_WORLD_READONLY, title='Reveal: URI Query')
def reveal_query(uri: str, provenance: bool = False) -> str:
    """Read one reveal resource URI (``scheme://resource``): a help topic, a git object, a session, a table.

    A resource URI names what a path cannot: help://TOPIC, git://FILE@REF,
    claude://session/NAME, sqlite://DB/TABLE, json://FILE/KEY, ssl://HOST,
    diff://LEFT:RIGHT. Analysis (call graphs, imports, metrics, AST queries,
    the project overview) is a subcommand, and every option is a flag: use
    reveal_run, e.g. reveal_run(['imports', '.', '--unused']) or
    reveal_run(['git', '<file>', '--view', 'history', '--limit', '5']).

    Lost, or need an adapter you don't know the name of? Start with
    reveal_query('help://quick') — a map of every adapter and common task.

    This tool takes the URI alone: no CLI flags (--format, --limit, --severity)
    pass through it, since there's no argv for them to come from here;
    reveal_run takes the same command line as the CLI. A query string on a
    noun's URI still answers until 1.0, with a note naming its reveal_run
    form. Each adapter's controls are listed by reveal_query('help://schemas/<adapter>').
    For severity/select filtering, use a dedicated typed tool instead
    (reveal_check has severity/select/ignore).

    Args:
        uri: Full reveal resource URI, e.g. 'help://quick' or 'git://<file>@HEAD~1'
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
    with _capture_lock, invocation_scope(invocation, retirements_to_stderr=False, form='mcp'):
        apply_global_flags(args)
        try:
            return _run_declared_tool(handle_uri, uri, None, args, quiet_usage=provenance)
        finally:
            set_provenance_enabled(False)


class _RunRefused(Exception):
    """A reveal_run request this read-only server will not run; the message says why and what to use."""


# Commands that write files or download: a terminal's work, not a read-only tool's.
_RUN_WRITING_COMMANDS = {'dev': 'reveal dev scaffolds files', 'offline': 'reveal offline downloads grammars',
                         'scaffold': 'reveal scaffold writes files'}


def _admit_run(args, command) -> None:
    """Refuse what would write, download or read this server's own input, before anything runs."""
    from .utils.json_utils import file_sinks
    if command in _RUN_WRITING_COMMANDS:
        raise _RunRefused(f'{_RUN_WRITING_COMMANDS[command]}; reveal_run is read-only: run it in a terminal')
    if getattr(args, 'stdin', False) is True:
        raise _RunRefused("--stdin reads this server's own input; send each request as its own reveal_run call")
    if getattr(args, 'copy', False) is True:
        raise _RunRefused('--copy writes the clipboard; reveal_run is read-only and returns the answer itself')
    if file_sinks(args):
        raise _RunRefused('--output FORMAT=PATH writes a file; reveal_run is read-only: use --format FORMAT '
                          '(or --output FORMAT), and the answer comes back in this result')


def _run_outcome(captured: _Captured, answer=None) -> str:
    """The CLI's own outcome as an MCP result (COMMAND_MODEL "Transports"): the answer as the CLI prints it, or a
    tool error when the CLI's request failed. An emitted answer's execution facts decide, as reveal_query's do;
    otherwise the exit code does: 2 (an invalid request) and an exit with no answer printed are errors. In JSON
    mode a public failure's text is the CLI's JSON document exactly."""
    if isinstance(captured.exception, _RunRefused):
        return _tool_failure(str(captured.exception))
    raised = _raised_failure(captured)
    if raised is not None:
        return raised
    out, err = captured.out, captured.err
    failure = (_declared_failure(answer) if answer is not None else None) or _exit_failure(captured)
    if failure is not None:
        if isinstance(failure, _ToolFailure) and failure.public and _is_json_document(out):
            return _tool_failure(out.strip())
        return failure
    if out.strip():
        return _with_stderr(out, err)
    return f'[stderr: {err}]' if err else out


def _exit_failure(captured: _Captured) -> str | None:
    """The tool failure the CLI's exit code means when no emitted answer decided: 2, an invalid request, and any
    other non-zero exit that printed no answer (findings, exit 1, print one)."""
    code = captured.exit_code
    if code == 2 or (code not in (0, None) and not captured.out.strip()):
        return _tool_failure(captured.err or f'reveal exited with code {code}')
    return None


@mcp_tool(annotations=_OPEN_WORLD_READONLY, title='Reveal: Run')
def reveal_run(args: list[str]) -> str:
    """Run one reveal command line: ``args`` is everything after ``reveal``, one list item per word.

    The same grammar, answer and exit meaning as the CLI. A noun answers a question about a target, its options
    are flags: reveal_run(['calls', '.', '--callers', 'process_order']),
    reveal_run(['ast', '.', '--kind', 'function', '--sort=-lines', '--limit', '5']).
    A path reads a file or one element of it: reveal_run(['app.py']), reveal_run(['app.py', 'process_order']).
    A resource URI names what a path cannot (git://FILE@REF, claude://session/NAME, sqlite://DB/TABLE,
    json://FILE/KEY, help://TOPIC) and takes the same flags: reveal_run(['help://quick']).
    Verbs act on any target: reveal_run(['check', 'app.py']). Each noun lists its own flags:
    reveal_run(['calls', '--help']).

    Add '--format', 'json' for the CLI's JSON answer exactly. An invalid request (an unknown flag, a value outside
    its choices, a target that matches nothing) is a tool error whose text names what the noun accepts; findings
    (exit 1) and an incomplete answer that says so in itself are results. Read-only: --stdin, --copy, file sinks
    (--output FORMAT=PATH) and the dev/offline commands are refused.

    Args:
        args: The command line after 'reveal', e.g. ['imports', '<dir>', '--importers', '<dir>/app.py']
    """
    if not isinstance(args, list) or not all(isinstance(word, str) for word in args):
        return _tool_failure("args is the command line after 'reveal' as a list of strings, "
                             "e.g. ['calls', 'src', '--callers', 'main']")
    return _run_command(args)


def _run_command(args: list[str]) -> str:
    """Run one CLI command line (the words after ``reveal``) through the CLI's own dispatch and return its outcome as
    an MCP result: the one entry for every tool that is a command line (reveal_run, and the path tools that build
    one), so their answer and failure meaning are the CLI's."""
    from .cli.invocation import Invocation, invocation_scope
    from .main import _dispatch_and_run
    from .utils.gitignore import set_gitignore_enabled
    from .utils.invocation_log import current_log
    from .utils.json_utils import set_provenance_enabled

    invocation = Invocation.parse(['reveal', *args])
    with _capture_lock, invocation_scope(invocation, retirements_to_stderr=False, form='mcp'):
        try:
            captured = _capture(_dispatch_and_run, invocation, _admit_run)
            log = current_log()
            answer = log.last_answer if log is not None else None
        finally:
            # The request's process-global flags end with it (reveal_query's own reset, plus --no-gitignore).
            set_provenance_enabled(False)
            set_gitignore_enabled(True)
    return _run_outcome(captured, answer)


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
    from .rendering.adapters.pack import _format_pack_result, pack_rule_lines
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
            rule_lines=pack_rule_lines(result, relevance_note=False))
        if (focus or architecture) and meta.get('relevance_warning'):
            # A requested optional signal that could not be built; the default
            # "not requested" notice stays out of this tool's layout.
            text += f"\n  ⚠ {meta['relevance_warning']}"
        return text

    invocation = Invocation.parse(argv)
    with _capture_lock, invocation_scope(invocation, retirements_to_stderr=False, form='mcp'):
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
        severity: Display threshold: 'low', 'medium' (default), 'high', or 'critical'; low findings are counted
        select: Comma-separated rule codes/series to run, e.g. 'M' or 'B006,S701'
            (same as CLI --select; see reveal_query('help://rules') for the list)
        ignore: Comma-separated rule codes/series to exclude, e.g. 'N'
    """
    from pathlib import Path
    from .cli.file_checker import _check_json, _tally, _json_file_entries

    p = Path(path)
    if not p.exists():
        return _tool_failure(f"{path}: no such file or directory")

    severity_filter = severity or 'medium'
    # BACK-1605: an unknown code is an error, as on the CLI, not a clean result.
    from .rules import parse_rule_patterns
    try:
        select_list = parse_rule_patterns(select) or None
        ignore_list = parse_rule_patterns(ignore) or None
    except ValueError as e:
        return _tool_failure(f"{e}")

    inputs = _check_inputs(p)
    if inputs is None:
        return f"No files found to check in {path}"
    directory, collection, files = inputs

    try:
        checked = _check_json(files, directory, select_list, ignore_list, severity_filter)
        tally = _tally(checked)
        total_issues = tally.total_issues
        file_results, _ = _json_file_entries(checked)
    except (TestLayoutValidationError, ConfigValidationError, ConfigLoadError) as exc:
        return _tool_failure(str(exc), exception=exc)
    notes, incomplete = _check_notes(
        files, select_list, ignore_list, file_results, collection=collection, directory=directory)

    zero_verdict = _check_zero_verdict(notes, incomplete)
    notes += _check_low_notes(tally.severity_totals)
    if total_issues == 0:
        return "\n".join(notes + [zero_verdict])

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


def _check_low_notes(counts: dict) -> list[str]:
    """One count line, separate from coverage/discovery notes used for the verdict."""
    low = counts.get('low', 0)
    return [f'Low findings: {low}'] if low else []


def _check_inputs(path) -> tuple | None:
    """The existing check inventory, retaining failed discovery even with no files."""
    from .cli.file_checker import collect_files_to_check
    if path.is_dir():
        directory = path.resolve()
        collection = collect_files_to_check(directory)
        if not collection.files and not collection.traversal_failures:
            return None
        return directory, collection, collection.files
    return path.parent.resolve(), None, [path.resolve()]


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
    disclosures = get_scan_disclosures(files, select_list, ignore_list, directory=directory)
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

    The narrative view of the calls callee walk: the same walk as
    reveal_run(['calls', '<path>', '--callees', 'FUNC', '--depth', 'N', '--detail', 'full']), which replaces it (the CLI's
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
    with _capture_lock, invocation_scope(invocation, retirements_to_stderr=False, form='mcp'):
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


def create_mcp_parser():
    """The ``reveal-mcp`` command's argument parser."""
    from .cli.argparsing import RevealArgumentParser

    parser = RevealArgumentParser(
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
    return parser


def main() -> None:
    """Entry point for the ``reveal-mcp`` command."""
    args = create_mcp_parser().parse_args()

    if args.transport == 'stdio':
        mcp.run(transport='stdio')
    elif args.transport == 'sse':
        mcp.run(transport='sse', host=args.host, port=args.port)
    else:
        mcp.run(transport='streamable-http', host=args.host, port=args.port)


if __name__ == '__main__':
    main()
