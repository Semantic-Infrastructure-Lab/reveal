"""AST-level surface extraction — env vars, FS writes, HTTP routes, CLI, MCP, imports."""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _add_once

_NET_PACKAGES: frozenset = frozenset({
    'requests', 'httpx', 'httpcore', 'aiohttp', 'urllib', 'urllib3', 'socket',
    'http', 'ftplib', 'smtplib', 'imaplib', 'poplib', 'xmlrpc',
    'grpc', 'websocket', 'websockets',
})

_DB_PACKAGES: frozenset = frozenset({
    'psycopg2', 'psycopg', 'pymysql', 'MySQLdb', 'sqlite3',
    'pymongo', 'motor', 'redis', 'aioredis', 'elasticsearch',
    'sqlalchemy', 'databases', 'asyncpg',
    'aiomysql', 'cx_Oracle', 'pyodbc', 'cassandra', 'pika',
    'clickhouse_driver', 'confluent_kafka', 'supabase', 'minio',
})

_SDK_PACKAGES: frozenset = frozenset({
    'anthropic', 'openai', 'cohere', 'google.cloud', 'azure',
    'stripe', 'twilio', 'sendgrid', 'slack_sdk', 'github',
    'atlassian', 'jira', 'pagerduty',
    'boto3', 'botocore', 'litellm', 'anthropic_bedrock',
})

_WRITE_MODES: frozenset = frozenset({'w', 'wb', 'a', 'ab', 'x', 'xb'})

_EMPTY: Dict[str, List] = {k: [] for k in ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs')}

# mock.patch / mocker.patch / unittest.mock.patch decorators contain ".patch("
# which would otherwise be mistaken for an HTTP PATCH route.
_MOCK_PATCH_PREFIXES: tuple = ('mock.patch(', 'mocker.patch(', 'patch(')
_MOCK_PATCH_SUBSTRINGS: tuple = ('unittest.mock.patch(',)


def scan_file_surface(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Python file and return categorised surface entries."""
    try:
        source = Path(file_path).read_text(errors='replace')
        tree = ast.parse(source, filename=file_path)
    except (SyntaxError, OSError):
        return {k: [] for k in _EMPTY}
    return _scan_tree(tree, file_path)


def _scan_tree(
    tree: ast.Module,
    file_path: str,
) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY}
    # BACK-534: resolve @command decorators against real click/typer provenance,
    # not the decorator name alone (which mistakes any project's own @command
    # for a CLI surface). Both maps are collected in a full pre-pass so a group
    # object or import defined after its first use still resolves.
    aliases: Dict[str, str] = {}
    _collect_aliases(tree, aliases)
    cli_groups = _collect_cli_groups(tree, aliases)
    # BACK-786: same treatment for @x.tool() — a bare decorator-name match
    # mistakes any unrelated `.tool()`-shaped decorator (e.g. LangChain's
    # `@tool`) for an MCP tool.
    mcp_instances = _collect_mcp_instances(tree, aliases)
    # BACK-790: same treatment for @x.route()/@x.get()/etc — a bare
    # decorator-name match mistakes any object with a same-named method for
    # an HTTP surface.
    http_apps = _collect_http_apps(tree, aliases)

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _process_import(node, file_path, aliases, surfaces)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _process_function_def(node, file_path, surfaces, aliases, cli_groups, mcp_instances, http_apps)
        elif isinstance(node, ast.Call):
            _process_call(node, file_path, aliases, surfaces)
        elif isinstance(node, ast.Subscript):
            # BACK-777: os.environ['X'] (read or write) is ast.Subscript, not
            # ast.Call — _process_call's dispatch never sees it.
            _process_subscript(node, file_path, surfaces)

    return surfaces


def _process_import(
    node: ast.stmt,
    file_path: str,
    aliases: Dict[str, str],
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            name = alias.name
            asname = alias.asname or name.split('.')[0]
            aliases[asname] = name
            _check_network_import(name, file_path, node.lineno, surfaces)
    elif isinstance(node, ast.ImportFrom):
        mod = node.module or ''
        for alias in node.names:
            full = f"{mod}.{alias.name}" if mod else alias.name
            asname = alias.asname or alias.name
            aliases[asname] = full
            _check_network_import(mod, file_path, node.lineno, surfaces)


def _check_network_import(
    name: str,
    file_path: str,
    line: int,
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    root = name.split('.')[0]
    if root in _NET_PACKAGES:
        _add_once(surfaces['network'], {'type': 'import', 'name': name, 'file': file_path, 'line': line})
    elif root in _DB_PACKAGES:
        _add_once(surfaces['db'], {'type': 'import', 'name': name, 'file': file_path, 'line': line})
    elif root in _SDK_PACKAGES:
        _add_once(surfaces['sdk'], {'type': 'import', 'name': name, 'file': file_path, 'line': line})


def _process_function_def(
    node: ast.FunctionDef,
    file_path: str,
    surfaces: Dict[str, List[Dict[str, Any]]],
    aliases: Optional[Dict[str, str]] = None,
    cli_groups: Optional[set] = None,
    mcp_instances: Optional[set] = None,
    http_apps: Optional[set] = None,
) -> None:
    aliases = aliases or {}
    cli_groups = cli_groups or set()
    mcp_instances = mcp_instances or set()
    http_apps = http_apps or set()
    for decorator in node.decorator_list:
        deco_str = _unparse_expr(decorator)

        if _is_http_route(deco_str) and _http_route_has_provenance(decorator, aliases, http_apps):
            path_arg = _extract_first_arg(decorator)
            methods = _extract_kwarg(decorator, 'methods')
            surfaces['http'].append({
                'type': 'route',
                'name': node.name,
                'path': path_arg or '?',
                'methods': methods or _infer_http_method(deco_str),
                'decorator': deco_str,
                'file': file_path,
                'line': node.lineno,
            })
        elif _cli_command_has_provenance(decorator, aliases, cli_groups):
            name_arg = _extract_kwarg(decorator, 'name') or node.name
            surfaces['cli'].append({
                'type': 'command',
                'name': name_arg,
                'decorator': deco_str,
                'file': file_path,
                'line': node.lineno,
            })
        elif _mcp_tool_has_provenance(decorator, aliases, mcp_instances):
            surfaces['mcp'].append({
                'type': 'tool',
                'name': node.name,
                'decorator': deco_str,
                'file': file_path,
                'line': node.lineno,
            })


def _process_call(
    node: ast.Call,
    file_path: str,
    aliases: Dict[str, str],
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    func_str = _unparse_expr(node.func)

    if _is_env_access(func_str):
        key = _extract_first_arg(node)
        if key and not key.startswith('{'):
            surfaces['env'].append({
                'type': 'env_var',
                'name': key,
                'expr': func_str,
                'file': file_path,
                'line': node.lineno,
            })
    elif _is_fs_write(func_str, node):
        target = _extract_first_arg(node) or '?'
        surfaces['fs'].append({
            'type': 'fs_write',
            'name': func_str,
            'target': target,
            'file': file_path,
            'line': node.lineno,
        })
    elif func_str.endswith('.add_argument'):
        key = _extract_first_arg(node)
        if key and key.startswith('-'):
            surfaces['cli'].append({
                'type': 'argument',
                'name': key,
                'expr': func_str,
                'file': file_path,
                'line': node.lineno,
            })
    elif func_str.endswith('.add_parser'):
        key = _extract_first_arg(node)
        if key:
            surfaces['cli'].append({
                'type': 'subcommand',
                'name': key,
                'expr': func_str,
                'file': file_path,
                'line': node.lineno,
            })


def _is_mock_patch_decorator(deco: str) -> bool:
    deco_lower = deco.lower()
    return (
        any(deco_lower.startswith(p) for p in _MOCK_PATCH_PREFIXES)
        or any(s in deco_lower for s in _MOCK_PATCH_SUBSTRINGS)
    )


def _is_http_route(deco: str) -> bool:
    if _is_mock_patch_decorator(deco):
        return False
    deco_lower = deco.lower()
    for method in ('.route(', '.get(', '.post(', '.put(', '.delete(', '.patch(', '.head(', '.options('):
        if method in deco_lower:
            return True
    return False


def _infer_http_method(deco: str) -> str:
    for m in ('get', 'post', 'put', 'delete', 'patch', 'head', 'options'):
        if f'.{m}(' in deco.lower():
            return m.upper()
    return 'ANY'


# BACK-534: a decorator only names a real CLI surface when it resolves to the
# click or typer frameworks — either imported directly, or invoked on a group
# object those frameworks construct (`typer.Typer()`, a `@click.group()`-
# decorated function). Anything else (`@command` from an entity API, a
# same-named local decorator) is not a command-line entry point.
_CLI_FRAMEWORK_ROOTS: frozenset = frozenset({'click', 'typer'})
_GROUP_CONSTRUCTORS: frozenset = frozenset({'Group', 'group', 'Typer'})


def _collect_aliases(tree: ast.Module, aliases: Dict[str, str]) -> None:
    """Full import map (asname → dotted source) for provenance resolution."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split('.')[0]] = alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ''
            for alias in node.names:
                full = f"{mod}.{alias.name}" if mod else alias.name
                aliases[alias.asname or alias.name] = full


def _leftmost_name(node: ast.expr) -> Optional[str]:
    """Root identifier of an attribute/call chain (`click.testing.foo` → 'click')."""
    while isinstance(node, ast.Attribute):
        node = node.value
    if isinstance(node, ast.Call):
        return _leftmost_name(node.func)
    return node.id if isinstance(node, ast.Name) else None


def _resolves_to_cli_framework(name: Optional[str], aliases: Dict[str, str]) -> bool:
    if not name:
        return False
    return aliases.get(name, name).split('.')[0] in _CLI_FRAMEWORK_ROOTS


def _is_group_constructor(call: ast.expr, aliases: Dict[str, str]) -> bool:
    """`click.Group(...)` / `click.group(...)` / `typer.Typer(...)` (or the
    bare form of each when imported directly)."""
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in _GROUP_CONSTRUCTORS:
        return _resolves_to_cli_framework(_leftmost_name(func.value), aliases)
    if isinstance(func, ast.Name) and func.id in _GROUP_CONSTRUCTORS:
        return _resolves_to_cli_framework(func.id, aliases)
    return False


def _is_group_decorator(deco: ast.expr, aliases: Dict[str, str], cli_groups: set) -> bool:
    """`@click.group()`, `@typer_app.group()`, or `@existing_group.group()`."""
    func = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(func, ast.Attribute) and func.attr == 'group':
        base = func.value
        if isinstance(base, ast.Name) and base.id in cli_groups:
            return True
        return _resolves_to_cli_framework(_leftmost_name(base), aliases)
    if isinstance(func, ast.Name) and func.id == 'group':
        return _resolves_to_cli_framework(func.id, aliases)
    return False


def _collect_cli_groups(tree: ast.Module, aliases: Dict[str, str]) -> set:
    """Variable names bound to a click/typer command group — the base of the
    common `@cli.command()` / `@app.command()` pattern. Iterated to a fixpoint
    so sub-groups (`@cli.group()` def sub → `@sub.command()`) resolve regardless
    of definition order."""
    groups: set = set()
    for _ in range(6):  # bounded fixpoint; deeper nesting is vanishingly rare
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and _is_group_constructor(node.value, aliases):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in groups:
                        groups.add(target.id)
                        changed = True
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in groups:
                    continue
                if any(_is_group_decorator(d, aliases, groups) for d in node.decorator_list):
                    groups.add(node.name)
                    changed = True
        if not changed:
            break
    return groups


def _cli_command_has_provenance(deco: ast.expr, aliases: Dict[str, str], cli_groups: set) -> bool:
    """True when a command-shaped decorator actually resolves to click/typer."""
    func = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(func, ast.Name):
        # bare @command / @cmd (e.g. `from click import command as cmd`)
        return _resolves_to_cli_framework(func.id, aliases)
    if isinstance(func, ast.Attribute) and func.attr == 'command':
        base = func.value
        if isinstance(base, ast.Name) and base.id in cli_groups:
            return True
        return _resolves_to_cli_framework(_leftmost_name(base), aliases)
    return False


# BACK-790: same discipline as BACK-534 (CLI) and BACK-786 (MCP) — an
# `@x.route()`/`@x.get()`/etc decorator only names a real HTTP surface when
# `x` resolves to a Flask/FastAPI app, blueprint, or router, not just any
# object that happens to expose a same-named method.
_HTTP_FRAMEWORK_ROOTS: frozenset = frozenset({'flask', 'fastapi'})
_APP_CONSTRUCTORS: frozenset = frozenset({'Flask', 'FastAPI', 'Blueprint', 'APIRouter'})


def _resolves_to_http_framework(name: Optional[str], aliases: Dict[str, str]) -> bool:
    if not name:
        return False
    return aliases.get(name, name).split('.')[0] in _HTTP_FRAMEWORK_ROOTS


def _is_app_constructor(call: ast.expr, aliases: Dict[str, str]) -> bool:
    """`Flask(...)` / `FastAPI(...)` / `Blueprint(...)` / `APIRouter(...)`,
    qualified (`flask.Flask(...)`) or imported directly."""
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in _APP_CONSTRUCTORS:
        return _resolves_to_http_framework(_leftmost_name(func.value), aliases)
    if isinstance(func, ast.Name):
        # resolve aliases first: `from flask import Flask as F` maps F ->
        # 'flask.Flask', so the constructor name lives in the resolved tail,
        # not in func.id itself.
        resolved = aliases.get(func.id, func.id).split('.')
        if resolved[-1] in _APP_CONSTRUCTORS and resolved[0] in _HTTP_FRAMEWORK_ROOTS:
            return True
    return False


def _collect_http_apps(tree: ast.Module, aliases: Dict[str, str]) -> set:
    """Variable names bound to a Flask/FastAPI app, blueprint, or router —
    the base of the `@app.route()` / `@app.get()` / `@router.post()` pattern."""
    apps: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_app_constructor(node.value, aliases):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    apps.add(target.id)
    return apps


def _http_route_has_provenance(deco: ast.expr, aliases: Dict[str, str], http_apps: set) -> bool:
    """True when an http-method-shaped decorator's base actually resolves to
    a Flask/FastAPI app, blueprint, or router — including a sub-router
    attribute reached off one (`@app.webhooks.post(...)`, FastAPI's webhooks
    router), not just a directly-decorated app/router variable."""
    func = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(func, ast.Attribute):
        base = func.value
        if isinstance(base, ast.Name) and base.id in http_apps:
            return True
        leftmost = _leftmost_name(base)
        if leftmost and leftmost in http_apps:
            return True
        return _resolves_to_http_framework(leftmost, aliases)
    return False


# BACK-786: same shape as BACK-534 (CLI provenance) — a `.tool()`/bare `tool`
# decorator name alone is not evidence of MCP; it must resolve to `mcp`/
# `fastmcp` (import root or an instance those packages construct), or it
# mistakes any unrelated `.tool()`-shaped decorator — e.g. LangChain's
# `@tool` — for an MCP tool registration.
_MCP_FRAMEWORK_ROOTS: frozenset = frozenset({'mcp', 'fastmcp'})
_MCP_CONSTRUCTORS: frozenset = frozenset({'FastMCP'})


def _resolves_to_mcp_framework(name: Optional[str], aliases: Dict[str, str]) -> bool:
    if not name:
        return False
    return aliases.get(name, name).split('.')[0] in _MCP_FRAMEWORK_ROOTS


def _is_mcp_constructor(call: ast.expr, aliases: Dict[str, str]) -> bool:
    """`FastMCP(...)` (or `mcp.server.fastmcp.FastMCP(...)`), the server object
    whose `.tool()` method registers MCP tools."""
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in _MCP_CONSTRUCTORS:
        return _resolves_to_mcp_framework(_leftmost_name(func.value), aliases)
    if isinstance(func, ast.Name):
        # resolve through the import alias map first — `FastMCP as MCPServer`
        # must not require the local name to literally read "FastMCP".
        resolved = aliases.get(func.id, func.id)
        return (
            resolved.split('.')[-1] in _MCP_CONSTRUCTORS
            and resolved.split('.')[0] in _MCP_FRAMEWORK_ROOTS
        )
    return False


def _collect_mcp_instances(tree: ast.Module, aliases: Dict[str, str]) -> set:
    """Variable names bound to an MCP server instance (`mcp = FastMCP(...)`) —
    the base of the `@mcp.tool()` pattern."""
    instances: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_mcp_constructor(node.value, aliases):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    instances.add(target.id)
    return instances


def _mcp_tool_has_provenance(deco: ast.expr, aliases: Dict[str, str], mcp_instances: set) -> bool:
    """True when a `tool`-shaped decorator actually resolves to mcp/fastmcp."""
    func = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(func, ast.Name):
        # bare @tool (e.g. `from mcp.server.fastmcp import tool`)
        return _resolves_to_mcp_framework(func.id, aliases)
    if isinstance(func, ast.Attribute) and func.attr == 'tool':
        base = func.value
        if isinstance(base, ast.Name) and base.id in mcp_instances:
            return True
        return _resolves_to_mcp_framework(_leftmost_name(base), aliases)
    return False


def _is_env_access(func_str: str) -> bool:
    return func_str in (
        'os.environ.get', 'os.getenv', 'environ.get', 'getenv', 'os.environ.__getitem__',
        'os.environ.setdefault', 'environ.setdefault', 'os.environ.pop', 'environ.pop',
        'os.putenv',
    )


def _process_subscript(node: ast.Subscript, file_path: str, surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    # BACK-777: os.environ['X'] read or write — the subscript form is
    # structurally invisible to _process_call's ast.Call dispatch.
    receiver = _unparse_expr(node.value)
    if receiver not in ('os.environ', 'environ'):
        return
    key = None
    if isinstance(node.slice, ast.Constant):
        key = str(node.slice.value)
    if key is None or key.startswith('{'):
        return
    surfaces['env'].append({
        'type': 'env_var',
        'name': key,
        'expr': f'{receiver}[...]',
        'file': file_path,
        'line': node.lineno,
    })


def _is_fs_write(func_str: str, node: ast.Call) -> bool:
    if func_str == 'open':
        return _get_open_mode(node) in _WRITE_MODES
    tail = func_str.split('.')[-1]
    if tail not in ('write_text', 'write_bytes', 'write', 'writelines') or len(func_str) <= len(tail):
        return False
    # BACK-778: a bare `.write`/`.writelines` matches any receiver, including
    # sys.stdout/sys.stderr and io.StringIO()/io.BytesIO() — none of which
    # touch the filesystem.
    if any(func_str.startswith(p) for p in _NON_FILE_WRITE_PREFIXES):
        return False
    if _is_chained_open_write(node):
        # open(...).write(...) is already counted via the inner open() call
        # (which reports the real path as target, not the data written).
        return False
    return True


_NON_FILE_WRITE_PREFIXES: tuple = (
    'sys.stdout.', 'sys.stderr.', 'stdout.', 'stderr.',
    'io.StringIO(', 'io.BytesIO(', 'StringIO(', 'BytesIO(',
)


def _is_chained_open_write(node: ast.Call) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Call):
        return False
    return _unparse_expr(func.value.func) == 'open'


def _get_open_mode(node: ast.Call) -> str:
    if len(node.args) >= 2:
        arg = node.args[1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    for kw in node.keywords:
        if kw.arg == 'mode' and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return 'r'


def _extract_first_arg(node: ast.expr) -> Optional[str]:
    if not isinstance(node, ast.Call):
        return None
    if node.args:
        arg = node.args[0]
        if isinstance(arg, ast.Constant):
            return str(arg.value)
        return _unparse_expr(arg)
    return None


def _extract_kwarg(node: ast.expr, key: str) -> Optional[str]:
    if not isinstance(node, ast.Call):
        return None
    for kw in node.keywords:
        if kw.arg == key:
            if isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
            return _unparse_expr(kw.value)
    return None


def _unparse_expr(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{_unparse_expr(node.value)}.{node.attr}"
        return '?'
