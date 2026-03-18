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
import threading
from argparse import Namespace

from mcp.server.fastmcp import FastMCP

# Suppress update-check prints from appearing in MCP tool responses.
# reveal's check_for_updates() prints to stdout; since _capture() redirects
# sys.stdout before invoking reveal functions, the notice would be injected
# into tool output and corrupt the response seen by the MCP client.
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

# Thread-local stdout capture to support concurrent requests safely
_capture_lock = threading.Lock()


def _capture(fn, *args, **kwargs) -> str:
    """Run *fn* with stdout+stderr captured; return captured text.

    Thread-safe: acquires lock so concurrent calls don't interleave.
    Swallows SystemExit(0) (reveal uses it for clean exit on some paths).
    Stderr is appended to the result so MCP clients see error messages
    rather than a blank response or a bare exit-code string.
    """
    with _capture_lock:
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
        max_bytes=None,
        max_depth=None,
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
def reveal_structure(path: str) -> str:  # noqa: uncalled
    """Get the semantic structure of a file or directory.

    For **directories**: returns the file tree with sizes and language types.
    For **files**: returns imports, functions, and classes with their signatures.

    This is the first step of progressive disclosure — understand the shape
    before drilling into implementation. Costs 50-500 tokens vs thousands for
    reading files directly.

    Args:
        path: File or directory path to inspect (absolute or relative to cwd)
    """
    from .cli.routing import handle_file_or_directory

    args = _default_args(path=path)
    return _capture(handle_file_or_directory, path, args)


@mcp.tool()
def reveal_element(path: str, element: str) -> str:  # noqa: uncalled
    """Extract a specific function or class from a file.

    Use after reveal_structure to drill into the exact code you need.
    Returns the full implementation — more token-efficient than reading
    the whole file when you only need one function.

    Args:
        path: File path containing the element
        element: Function or class name to extract (e.g., 'validate_token')
    """
    from .file_handler import handle_file

    args = _default_args(path=path, element=element)
    return _capture(handle_file, path, element, False, 'text', args=args)


@mcp.tool()
def reveal_query(uri: str) -> str:  # noqa: uncalled
    """Run a reveal URI query across any of 22 adapters.

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
    return _capture(handle_uri, uri, None, args)


@mcp.tool()
def reveal_pack(  # noqa: uncalled
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
    from .cli.commands.pack import run_pack

    args = _default_args(
        path=path,
        budget=str(budget),
        since=since or None,
        content=content,
        focus=focus or None,
    )
    return _capture(run_pack, args)


@mcp.tool()
def reveal_check(path: str, severity: str = '') -> str:  # noqa: uncalled
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
    from .cli.commands.check import run_check

    args = _default_args(
        path=path,
        severity=severity or None,
        format='text',
        verbose=False,
        select=None,
        ignore=None,
    )
    return _capture(run_check, args)


def main() -> None:  # noqa: uncalled
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
