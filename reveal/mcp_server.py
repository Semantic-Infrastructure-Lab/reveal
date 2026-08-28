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
import os
import sys
import threading

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from .cli.defaults import _default_args

# All reveal-mcp tools are read-only (no writes, no side effects) and
# idempotent (same args -> same result, modulo underlying files changing).
# reveal_query is the exception for openWorldHint: several of its adapters
# (ssl://, domain://, mysql://) reach external network services, while the
# rest of the tools only ever touch the local filesystem/git repo.
_LOCAL_READONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
_OPEN_WORLD_READONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

# Suppress update-check prints that would corrupt MCP tool responses.
os.environ.setdefault('REVEAL_NO_UPDATE_CHECK', '1')

mcp = MCPServer(
    "reveal",
    instructions=(
        "Reveal is a progressive disclosure tool for exploring codebases, "
        "infrastructure, and data sources. This is 3-33x more token-efficient "
        "than reading files directly — always prefer the narrowest tool below "
        "over reading a whole file or dumping a whole repo.\n\n"
        "Param convention: `path` = local filesystem path only. `uri` = a "
        "reveal URI (scheme://...) only. `target` = either, tool-dependent "
        "(reveal_health: path or URI; reveal_review: path or git range).\n\n"
        "Core workflow:\n"
        "0. reveal_query('overview://<dir>') — orient in an unfamiliar "
        "codebase first: quality score, ranked hotspots, git activity, one "
        "screen. This is reveal's own best answer to \"what is this repo\" — "
        "start here before structure/element/nav on unfamiliar code.\n"
        "1. reveal_structure(dir) — understand what's in a directory (50-200 tokens)\n"
        "2. reveal_structure(file) — see all functions/classes (200-500 tokens)\n"
        "3. reveal_element(file, fn) — read one function's implementation (100-300 tokens)\n"
        "4. reveal_nav(file, fn, flag) — deep-dive analysis without reading source:\n"
        "   boundary    — INPUTS + ENVIRONMENT + EFFECTS in one report\n"
        "   deps        — variables flowing into the function\n"
        "   mutations   — variables the function writes and the caller will read\n"
        "   sideeffects — db/http/cache/log/file/sleep/hard_stop calls\n"
        "   returns     — exit paths with gate conditions\n"
        "   varflow     — trace one variable's reads and writes\n"
        "5. reveal_grep(path, pattern) — \"where is X used?\" cross-file "
        "search grouped by enclosing function (use instead of shell grep).\n"
        "6. reveal_trace(dir, entry_point) — \"what happens when X runs?\" "
        "depth-indented call-graph narrative from one entry point.\n"
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
        "reveal_pack(path) — token-budgeted context snapshot, DEFAULTS TO "
        "~8000 TOKENS OF RAW FILE CONTENT. Use only for breadth (PR review "
        "via `since`, unfamiliar-repo handoff, one-shot context dump) — never "
        "to answer a question about one file or function, that's "
        "reveal_structure + reveal_element at a fraction of the cost."
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
    exc_msg = None
    with _capture_lock:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = out_buf
        sys.stderr = err_buf
        try:
            fn(*args, **kwargs)
        except SystemExit as e:
            exit_code = e.code
        except Exception as exc:  # noqa: BLE001
            exc_msg = str(exc)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    out = out_buf.getvalue()
    err = err_buf.getvalue().strip()

    if exc_msg is not None:
        return f"[reveal error: {exc_msg}]"
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


# BACK-REVEAL-1: every reveal_* implementation below returns "[reveal error: ...]"
# as a plain string on failure rather than raising -- kept exactly as-is so direct
# Python callers (unit tests, in-process reuse) still get a string back, never a
# raised exception. But an MCP client can't distinguish that from a successful
# result: both arrive as isError=False. mcp_tool() registers a thin wrapper around
# each function that re-raises reveal's own "[reveal error:" sentinel -- the MCP
# SDK's tool.run() converts any exception raised from a tool body into
# CallToolResult(is_error=True), which is exactly the protocol-level signal a
# client needs. "[reveal exited with code N]" (the CLI exit-code passthrough in
# _run_and_capture) is deliberately NOT covered: reveal's CLI commands use nonzero
# exit for legitimate FAIL/issues-found verdicts (e.g. reveal_health's PASS/WARN/
# FAIL), which is real tool output, not a call failure. Only "[reveal error:" is
# ever emitted for an unambiguous input/execution problem (confirmed: it's the
# exact prefix for every not-found/no-analyzer/unknown-flag/exception case across
# all 10 tools, and never appears in a verdict).
_ERROR_SENTINEL_PREFIX = "[reveal error:"


def _raise_if_error_sentinel(result: str) -> str:
    if result.startswith(_ERROR_SENTINEL_PREFIX):
        raise ValueError(result[1:-1] if result.endswith(']') else result)
    return result


def mcp_tool(*, annotations: ToolAnnotations | None = None, title: str | None = None):
    """Like @mcp.tool(), but the registered tool re-raises reveal's error
    sentinel (see above) while the module-level name stays the original,
    string-returning function."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return _raise_if_error_sentinel(fn(*args, **kwargs))

        mcp.tool(annotations=annotations, title=title)(wrapper)
        return fn

    return decorator


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: File/Directory Structure')
def reveal_structure(path: str, depth: int = 3, ext: str = '', exclude: str = '', files: bool = False) -> str:
    """Get the semantic structure of a file or directory.

    For **directories**: returns the file tree with sizes and language types.
    For **files**: returns imports, functions, and classes with their signatures.

    This is the first step of progressive disclosure — understand the shape
    before drilling into implementation. Costs 50-500 tokens vs thousands for
    reading files directly.

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
        return f"[reveal error: path not found: {path}]"

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
        return f"[reveal error: no analyzer found for {path}]"

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
        return f"[reveal error: path not found: {path}]"

    try:
        analyzer_class = get_analyzer(path, allow_fallback=True)
        if not analyzer_class:
            return f"[reveal error: no analyzer found for {path}]"

        analyzer = analyzer_class(path)
        syntax = _parse_element_syntax(element)
        result = _extract_by_syntax(analyzer, element, syntax)
    except Exception as exc:  # noqa: BLE001 -- match every sibling tool's error shape
        return f"[reveal error: {exc}]"

    if not result:
        return f"[reveal error: element '{element}' not found in {path}]"

    line_start = result.get('line_start', 1)
    line_end = result.get('line_end', line_start)
    source = result.get('source', '')
    name = result.get('name', element)

    header = f"{path}:{line_start}-{line_end} | {name}\n"
    return f"{header}\n{analyzer.format_with_lines(source, line_start)}"


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
    calls), deps (inputs), mutations (outputs), varflow (trace one variable).

    Full flag catalog + examples: reveal_query('help://nav')

    Args:
        path:        File containing the element (absolute or relative to cwd)
        element:     Function/method name (e.g. 'process_order') or line ref
                     (e.g. ':120-340' for flat/procedural files)
        flag:        Nav analysis to run — see reveal_query('help://nav') for
                     the full list. Boolean flags need no flag_value; value
                     flags (varflow, keys, narrow) require one.
        flag_value:  Required for varflow, keys, and narrow (variable name). Optional for
                     calls (range string) and around (integer context lines).

    Example:
        reveal_nav('app.py', 'process_order', 'boundary')
    """
    from .file_handler import handle_file  # noqa: I006

    if flag in _NAV_BOOLEAN_FLAGS:
        args = _default_args(**{flag: True})
    elif flag in _NAV_VAR_NAME_FLAGS:
        if not flag_value:
            example = _NAV_VAR_NAME_FLAGS[flag]
            return f"[reveal error: {flag} requires flag_value (variable name, e.g. '{example}')]"
        args = _default_args(**{flag: flag_value})
    elif flag == 'calls':
        args = _default_args(calls=flag_value or 'FULL')
    elif flag == 'around':
        try:
            n = int(flag_value) if flag_value else 20
        except ValueError:
            return f"[reveal error: around requires an integer flag_value, got '{flag_value}']"
        args = _default_args(around=n)
    else:
        valid = sorted(_NAV_BOOLEAN_FLAGS | set(_NAV_VAR_NAME_FLAGS) | {'calls', 'around'})
        return f"[reveal error: unknown nav flag '{flag}'. Valid flags: {valid}]"

    return _run_and_capture(handle_file, path, element, False, 'text', args)


@mcp_tool(annotations=_OPEN_WORLD_READONLY, title='Reveal: URI Query')
def reveal_query(uri: str, provenance: bool = False) -> str:
    """Run a reveal URI query across any adapter (``scheme://resource?query`` syntax).

    Use for anything outside the file/nav workflow: call graphs, dead-code
    detection, import health, git history, SSL/domain checks, database/Excel
    inspection, doc search, and more — same operators and output shape across
    every adapter.

    Lost, or need an adapter you don't know the name of? Start with
    reveal_query('help://quick') — a map of every adapter and common task.

    CLI-only global flags (--severity, --select, --format) do NOT pass
    through to this tool — there's no argv for them to come from here.
    Exceptions: '?limit=N', '?sort=field' (or '?sort=-field' for desc),
    and '?offset=M' work when written directly into the URI (every adapter
    reads them straight off the query string via a shared result-control
    parser, independent of any CLI flag);
    every other per-adapter option is that adapter's own '?key=value'
    vocabulary, not a generic CLI-flag passthrough — check
    reveal_query('help://schemas/<adapter>') for what a given scheme accepts.
    For severity/select filtering, use a dedicated typed tool instead
    (reveal_check has severity/select/ignore).

    Args:
        uri: Full reveal URI, e.g. 'calls://src/?target=my_fn' or 'help://quick'
        provenance: When true, attach a '--provenance' execution manifest
            (git state, command, timestamp) to the result, for callers that
            need to cite evidence provenance (e.g. a DD finding contract).
            Forces JSON output (provenance only attaches to dict results),
            so the response shape differs from a plain-text query — only set
            this when the caller actually needs the manifest.
    """
    from .cli.routing import handle_uri
    from .utils.json_utils import set_provenance_enabled

    args = _default_args(path=uri, provenance=provenance, format='json' if provenance else 'text')
    # Holds _capture_lock across the whole provenance-flag lifecycle (not just
    # inside _run_and_capture) because set_provenance_enabled is a second
    # process-global, independent of the stdout/stderr one _run_and_capture
    # already serializes -- a concurrent call with provenance=False must not
    # observe this call's flag mid-flight. _capture_lock is an RLock so
    # _run_and_capture's own internal acquisition below doesn't deadlock.
    with _capture_lock:
        set_provenance_enabled(provenance)
        try:
            return _run_and_capture(handle_uri, uri, None, args)
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
    handoff. Do NOT use to answer a question about a specific file or
    function — that's reveal_structure + reveal_element at a fraction of the
    cost (this defaults to ~8000 tokens of raw content with content=True).

    Selects the most important files within the token budget, prioritizing:
    1. Changed files (when ``since`` is set)
    2. Entry points (main.py, app.py, index.js, etc.)
    3. Key architectural modules (api/, models/, auth/, core/)
    4. Recently modified files

    With ``content=True`` (default), includes tiered structure output:
    - Changed files → full raw content (see exactly what changed)
    - Key files → reveal structure (function signatures, imports)
    - Low-priority files → names only

    Args:
        path: Directory to pack
        budget: Token budget in approximate tokens (default 8000)
        since: Git ref for PR review mode, e.g. 'main' or 'HEAD~3' (prioritizes changed files)
        content: Include file structure in output (default True)
        focus: Emphasize files matching this name pattern (e.g., 'auth', 'api')
        architecture: Prepend an architecture brief (entry points + high fan-in
            core abstractions) before the file listing
    """
    from pathlib import Path
    from .cli.commands.pack import (
        _parse_budget, _get_changed_files, _collect_candidates,
        _apply_budget, _format_pack_result,
    )

    p = Path(path)
    if not p.exists():
        return f"[reveal error: {path}: not found]"

    budget_tokens, budget_lines = _parse_budget(str(budget))
    focus_val = focus or None
    since_val = since or None

    changed_files: set = set()
    since_error = None
    if since_val:
        changed_files, since_error = _get_changed_files(p, since_val)

    candidates = _collect_candidates(p, focus_val, changed_files)
    selected, meta = _apply_budget(candidates, budget_tokens, budget_lines, p)

    if since_val:
        meta['since'] = since_val
        meta['changed_files_count'] = len(changed_files)

    return _format_pack_result(
        p, selected, meta, budget_tokens, budget_lines,
        since_error=since_error, content=content, architecture=architecture,
    )


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Quality Check')
def reveal_check(path: str, severity: str = '', select: str = '', ignore: str = '') -> str:
    """Run quality checks on a file or directory.

    Detects: cyclomatic complexity hotspots, maintainability issues, style
    violations (B-series, F-series, N-series, V-series rules), broken links,
    missing documentation, and security patterns.

    Returns issues grouped by severity. Exit behavior mirrors the CLI:
    clean output means no issues found.

    Args:
        path: File or directory to check (recurses into directories)
        severity: Minimum severity to show: 'low', 'medium', 'high', or 'critical'
        select: Comma-separated rule codes/series to run, e.g. 'M' or 'B006,S012'
            (same as CLI --select; see reveal_query('help://rules') for the list)
        ignore: Comma-separated rule codes/series to exclude, e.g. 'N'
    """
    from pathlib import Path
    from .cli.file_checker import collect_files_to_check, load_gitignore_patterns, _check_files_json

    p = Path(path)
    if not p.exists():
        return f"[reveal error: {path}: no such file or directory]"

    severity_filter = severity or None
    select_list = select.split(',') if select else None
    ignore_list = ignore.split(',') if ignore else None

    if p.is_dir():
        directory = p.resolve()
        gitignore_patterns = load_gitignore_patterns(directory)
        files = collect_files_to_check(directory, gitignore_patterns).files
        if not files:
            return f"No files found to check in {path}"
    else:
        directory = p.parent.resolve()
        files = [p.resolve()]

    total_issues, _, file_results, _, _ = _check_files_json(
        files, directory, select_list, ignore_list, severity=severity_filter
    )

    if total_issues == 0:
        return "No issues found."

    lines = []
    for fr in file_results:
        n = fr['issues']
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


@mcp_tool(annotations=_OPEN_WORLD_READONLY, title='Reveal: Health Verdict')
def reveal_health(target: str, select: str = '') -> str:
    """Run a unified health check on a path or URI resource.

    Checks code quality thresholds for a local path, or SSL/database/DNS
    health for a URI resource (ssl://, mysql://, domain://). Returns a
    PASS/WARN/FAIL verdict per target plus a one-line summary — narrower
    and faster than reveal_check/reveal_query/reveal_review for a quick
    go/no-go read. For an itemized list of issues instead of a verdict, use
    reveal_check (a file/dir) or reveal_review (pre-merge, git-range aware).

    Args:
        target: Path or URI to check (e.g. './src', 'ssl://example.com', 'mysql://host/db')
        select: Rule categories to check for code targets (e.g. 'B,S,I,C')
    """
    from .cli.commands.health import run_health

    args = _default_args(targets=[target], select=select or None, health_all=False)
    return _run_and_capture(run_health, args)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Pre-Merge Review')
def reveal_review(target: str, select: str = 'B,S,I,C,M') -> str:
    """Assess code quality before a PR merge — violations, hotspots, complexity spikes.

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

    Structural cross-file search: matches are grouped under the function/class
    they fall in, not just raw line numbers — prefer this over shell grep for
    finding a symbol's usages or a string across a codebase.

    Args:
        path: File or directory to search
        pattern: Regex pattern to search for
        ignore_case: Case-insensitive match (default False)
    """
    from pathlib import Path
    from .grep_handler import handle_grep, handle_grep_directory

    p = Path(path)
    if not p.exists():
        return f"[reveal error: path not found: {path}]"

    args = _default_args(ignore_case=ignore_case)
    if p.is_dir():
        return _run_and_capture(handle_grep_directory, str(p), pattern, args)
    return _run_and_capture(handle_grep, str(p), pattern, args)


@mcp_tool(annotations=_LOCAL_READONLY, title='Reveal: Call-Graph Trace')
def reveal_trace(path: str, entry_point: str, depth: int = 2) -> str:
    """Walk the call graph from a named entry point as a depth-indented execution narrative.

    Each frame shows the function's location, parameters, classified side
    effects (db/http/log/file/...), and what it calls next. Unlike
    reveal_query('calls://...'), which answers structural caller/callee
    queries, this renders a readable top-down trace starting from one function
    — useful for "walk me through what happens when X runs."

    Args:
        path: Source directory to analyse
        entry_point: Entry-point function name to start the trace from
        depth: Call levels to expand, 1-5 (default 2)
    """
    from pathlib import Path
    from .cli.commands.trace import run_trace

    p = Path(path)
    if not p.exists():
        return f"[reveal error: path not found: {path}]"

    args = _default_args(path=str(p), root=entry_point, depth=depth, format='text')
    return _run_and_capture(run_trace, args)


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
