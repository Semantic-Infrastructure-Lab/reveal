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

import io
import os
import sys
from argparse import Namespace

from mcp.server.fastmcp import FastMCP

# Suppress update-check prints that would corrupt MCP tool responses.
os.environ.setdefault('REVEAL_NO_UPDATE_CHECK', '1')

mcp = FastMCP(
    "reveal",
    instructions=(
        "Reveal is a progressive disclosure tool for exploring codebases, "
        "infrastructure, and data sources.\n\n"
        "Core workflow:\n"
        "1. reveal_structure(dir) — understand what's in a directory (50-200 tokens)\n"
        "2. reveal_structure(file) — see all functions/classes (200-500 tokens)\n"
        "3. reveal_element(file, fn) — read one function's implementation (100-300 tokens)\n\n"
        "This is 3-33x more token-efficient than reading files directly. "
        "Use reveal_structure before reveal_element — always progressive disclosure."
    ),
)

def _run_and_capture(fn, *args, **kwargs) -> str:
    """Run fn with stdout+stderr captured; return captured text.

    Used only for tools where the underlying display layer prints rather than
    returning strings.  No global lock — MCP tool calls are sequential.
    Swallows SystemExit(0) (reveal uses it for clean exit on some paths).
    Stderr is appended so MCP clients see error messages instead of silence.
    """
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = out_buf
    sys.stderr = err_buf
    exit_code = None
    exc_msg = None
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
    if exit_code not in (0, None):
        detail = err or out.strip()
        msg = f"[reveal exited with code {exit_code}]"
        return f"{msg}: {detail}" if detail else msg
    if err and not out.strip():
        return f"[stderr: {err}]"
    if err:
        return f"{out}\n[stderr: {err}]"
    return out


def _default_args(**overrides) -> Namespace:
    """Return a Namespace with all reveal CLI defaults for internal routing functions."""
    defaults = dict(
        path=None,
        element=None,
        format='text',
        copy=False,
        verbose=False,
        no_breadcrumbs=False,
        disable_breadcrumbs=False,
        stdin=False,
        meta=False,
        list_supported=False,
        languages=False,
        adapters=False,
        explain_file=False,
        capabilities=False,
        show_ast=False,
        language_info=None,
        agent_help=False,
        agent_help_full=False,
        discover=False,
        head=None,
        tail=None,
        range=None,
        search=None,
        sort=None,
        desc=False,
        asc=False,
        type=None,
        all=False,
        since=None,
        base_path=None,
        no_fallback=False,
        depth=3,
        max_entries=200,
        dir_limit=50,
        fast=False,
        respect_gitignore=True,
        exclude=None,
        ext=None,
        files=False,
        outline=False,
        hotspots=False,
        code_only=False,
        typed=False,
        filter=None,
        decorator_stats=False,
        check=False,
        config=None,
        select=None,
        ignore=None,
        no_group=False,
        recursive=False,
        rules=False,
        schema=False,
        explain=None,
        severity=None,
        advanced=False,
        only_failures=False,
        batch=False,
        fields=None,
        max_items=None,
        max_snippet_chars=None,
        links=False,
        link_type=None,
        domain=None,
        code=False,
        language=None,
        inline=False,
        frontmatter=False,
        related=False,
        related_depth=1,
        related_all=False,
        related_flat=False,
        related_limit=100,
        section=None,
        metadata=False,
        semantic=None,
        scripts=None,
        styles=None,
        validate_schema=None,
        list_schemas=False,
        summary=False,
        expiring_within=None,
        validate_nginx=False,
        local_certs=False,
        extract=None,
        canonical_only=False,
        check_acl=False,
        validate_nginx_acme=False,
        check_conflicts=False,
        cpanel_certs=False,
        diagnose=False,
        log_path=None,
        dns_verified=False,
        check_live=False,
        user=None,
        # pack-specific
        content=False,
        focus=None,
        budget='2000',
    )
    defaults.update(overrides)
    return Namespace(**defaults)


@mcp.tool()
def reveal_structure(path: str) -> str:
    """Get the semantic structure of a file or directory.

    For **directories**: returns the file tree with sizes and language types.
    For **files**: returns imports, functions, and classes with their signatures.

    This is the first step of progressive disclosure — understand the shape
    before drilling into implementation. Costs 50-500 tokens vs thousands for
    reading files directly.

    Args:
        path: File or directory path to inspect (absolute or relative to cwd)
    """
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return f"[reveal error: path not found: {path}]"

    args = _default_args(path=str(p))

    if p.is_dir():
        from .tree_view import show_directory_tree
        return show_directory_tree(
            str(p),
            depth=args.depth,
            max_entries=args.max_entries,
            dir_limit=args.dir_limit,
            fast=args.fast,
            respect_gitignore=args.respect_gitignore,
            exclude_patterns=args.exclude,
        )

    from .registry import get_analyzer
    from .display.structure import show_structure

    analyzer_class = get_analyzer(str(p), allow_fallback=True)
    if not analyzer_class:
        return f"[reveal error: no analyzer found for {path}]"

    analyzer = analyzer_class(str(p))
    return _run_and_capture(show_structure, analyzer, 'text', args)


@mcp.tool()
def reveal_element(path: str, element: str) -> str:
    """Extract a specific function or class from a file.

    Use after reveal_structure to drill into the exact code you need.
    Returns the full implementation — more token-efficient than reading
    the whole file when you only need one function.

    Args:
        path: File path containing the element
        element: Function or class name to extract (e.g., 'validate_token')
    """
    from .registry import get_analyzer
    from .display.element import _parse_element_syntax, _extract_by_syntax

    analyzer_class = get_analyzer(path, allow_fallback=True)
    if not analyzer_class:
        return f"[reveal error: no analyzer found for {path}]"

    analyzer = analyzer_class(path)
    syntax = _parse_element_syntax(element)
    result = _extract_by_syntax(analyzer, element, syntax)

    if not result:
        return f"[reveal error: element '{element}' not found in {path}]"

    line_start = result.get('line_start', 1)
    line_end = result.get('line_end', line_start)
    source = result.get('source', '')
    name = result.get('name', element)

    header = f"{path}:{line_start}-{line_end} | {name}\n"
    return f"{header}\n{analyzer.format_with_lines(source, line_start)}"


@mcp.tool()
def reveal_query(uri: str) -> str:
    """Run a reveal URI query across any of 23 adapters.

    Full access to all reveal adapters using the ``scheme://resource?query`` syntax.
    Same operators, same output format across all adapters.

    Common patterns:
      ``ast://src/?complexity>10&sort=-complexity``   high-complexity code
      ``calls://src/?target=my_fn&depth=3``           call graph analysis
      ``calls://src/?uncalled``                       dead code detection
      ``calls://src/?rank=callers&top=20``            most-coupled functions
      ``imports://src/?unused``                       unused imports
      ``diff://git://main/.:git://HEAD/.``            PR structural diff
      ``ssl://api.example.com``                       certificate status
      ``domain://example.com``                        DNS/WHOIS/email health
      ``mysql://db/?type=replication``                database replication
      ``sqlite://path/to/db``                         SQLite schema
      ``nginx://nginx.conf``                          nginx config analysis
      ``markdown://docs/?aggregate=type``             doc taxonomy
      ``claude://sessions/``                          AI session history

    Args:
        uri: Full reveal URI (scheme://resource or scheme://resource?query)
    """
    from .cli.routing import handle_uri

    args = _default_args(path=uri)
    return _run_and_capture(handle_uri, uri, None, args)


@mcp.tool()
def reveal_pack(
    path: str,
    budget: int = 8000,
    since: str = '',
    content: bool = True,
    focus: str = '',
) -> str:
    """Get a token-budgeted context snapshot of a codebase — ideal for PR review.

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
    """
    from pathlib import Path
    from .cli.commands.pack import (
        _parse_budget, _get_changed_files, _collect_candidates,
        _apply_budget, _collect_file_contents,
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

    # Render text at MCP boundary
    budget_desc = f"~{budget_tokens} tokens" if budget_tokens else f"{budget_lines} lines"
    since_desc = f"  [since {since_val}]" if since_val else ""
    lines = [f"Pack: {p}  [{budget_desc} budget]{since_desc}"]
    if since_val:
        lines.append(f"Changed files:  {meta.get('changed_files_count', 0)} (boosted to top priority)")
    if since_error:
        lines.append(f"Warning: --since: {since_error}")
    lines.append(
        f"Selected {meta['selected']} of {meta['total_candidates']} files "
        f"(~{meta['used_tokens_approx']} tokens, {meta['used_lines']} lines)"
    )
    lines.append("")

    if not selected:
        lines.append("No files fit within budget.")
    else:
        def _file_line(f):
            return f"  {f['relative']:50} {f['tokens_approx']:5} tokens  {f['lines']:4} lines"

        changed_f = [f for f in selected if f.get('changed')]
        high_f = [f for f in selected if not f.get('changed') and f['priority'] >= 8]
        medium_f = [f for f in selected if not f.get('changed') and 2 <= f['priority'] < 8]
        low_f = [f for f in selected if not f.get('changed') and f['priority'] < 2]

        if changed_f:
            lines.append(f"── Changed files (since {since_val}) ──")
            lines.extend(_file_line(f) for f in changed_f)
            lines.append("")
        if high_f:
            lines.append("── Entry points / focus files ──")
            lines.extend(_file_line(f) for f in high_f)
            lines.append("")
        if medium_f:
            lines.append("── Key modules ──")
            lines.extend(_file_line(f) for f in medium_f)
            lines.append("")
        if low_f:
            lines.append("── Other files ──")
            lines.extend(_file_line(f) for f in low_f)
            lines.append("")
        if meta['skipped'] > 0:
            lines.append(f"[{meta['skipped']} files excluded — exceeded budget]")

    if content and selected:
        content_data = _collect_file_contents(selected)
        lines.append("")
        lines.append("━" * 70)
        lines.append("CONTENT  (changed=full · key files=structure · low priority=names)")
        lines.append("━" * 70)
        name_only = []
        for entry in content_data:
            if entry['content_type'] == 'name_only':
                name_only.append(entry['file'])
                continue
            marker = "  ◀ CHANGED (full content)" if entry['content_type'] == 'full' else ""
            lines.append(f"\n── {entry['file']}{marker} ──")
            lines.append(entry['content'].rstrip() if entry['content'].strip() else "[unreadable]")
        if name_only:
            lines.append("\n── Low-priority files (selected, structure omitted) ──")
            lines.extend(f"  {f}" for f in name_only)

    return "\n".join(lines)


@mcp.tool()
def reveal_check(path: str, severity: str = '') -> str:
    """Run quality checks on a file or directory.

    Detects: cyclomatic complexity hotspots, maintainability issues, style
    violations (B-series, F-series, N-series, V-series rules), broken links,
    missing documentation, and security patterns.

    Returns issues grouped by severity. Exit behavior mirrors the CLI:
    clean output means no issues found.

    Args:
        path: File or directory to check (recurses into directories)
        severity: Minimum severity to show: 'low', 'medium', 'high', or 'critical'
    """
    from pathlib import Path
    from .cli.file_checker import collect_files_to_check, load_gitignore_patterns, _check_files_json

    p = Path(path)
    if not p.exists():
        return f"[reveal error: {path}: no such file or directory]"

    severity_filter = severity or None

    if p.is_dir():
        directory = p.resolve()
        gitignore_patterns = load_gitignore_patterns(directory)
        files = collect_files_to_check(directory, gitignore_patterns)
        if not files:
            return f"No files found to check in {path}"
    else:
        directory = p.parent.resolve()
        files = [p.resolve()]

    total_issues, _, file_results = _check_files_json(
        files, directory, None, None, severity=severity_filter
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
        mcp.host = args.host
        mcp.port = args.port
        mcp.run(transport='sse')
    else:
        mcp.host = args.host
        mcp.port = args.port
        mcp.run(transport='streamable-http')


if __name__ == '__main__':
    main()
