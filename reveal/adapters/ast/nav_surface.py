"""AST-level surface extraction — env vars, FS writes, HTTP routes, CLI, MCP, imports."""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _add_once

_NET_PACKAGES: frozenset = frozenset({
    'requests', 'httpx', 'aiohttp', 'urllib', 'urllib3', 'socket',
    'http', 'ftplib', 'smtplib', 'imaplib', 'poplib', 'xmlrpc',
    'grpc', 'websocket', 'websockets',
})

_DB_PACKAGES: frozenset = frozenset({
    'psycopg2', 'psycopg', 'pymysql', 'MySQLdb', 'sqlite3',
    'pymongo', 'motor', 'redis', 'aioredis', 'elasticsearch',
    'boto3', 'botocore', 'sqlalchemy', 'databases', 'asyncpg',
    'aiomysql', 'cx_Oracle', 'pyodbc', 'cassandra', 'pika',
})

_SDK_PACKAGES: frozenset = frozenset({
    'anthropic', 'openai', 'cohere', 'google.cloud', 'azure',
    'stripe', 'twilio', 'sendgrid', 'slack_sdk', 'github',
    'atlassian', 'jira', 'pagerduty',
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

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _process_import(node, file_path, aliases, surfaces)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _process_function_def(node, file_path, surfaces, aliases, cli_groups)
        elif isinstance(node, ast.Call):
            _process_call(node, file_path, aliases, surfaces)

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
) -> None:
    aliases = aliases or {}
    cli_groups = cli_groups or set()
    for decorator in node.decorator_list:
        deco_str = _unparse_expr(decorator)

        if _is_http_route(deco_str):
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
        elif _is_mcp_tool(deco_str):
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


def _is_mcp_tool(deco: str) -> bool:
    return '.tool(' in deco.lower() or deco.lower() in ('tool', 'mcp.tool')


def _is_env_access(func_str: str) -> bool:
    return func_str in ('os.environ.get', 'os.getenv', 'environ.get', 'getenv', 'os.environ.__getitem__')


def _is_fs_write(func_str: str, node: ast.Call) -> bool:
    if func_str == 'open':
        return _get_open_mode(node) in _WRITE_MODES
    tail = func_str.split('.')[-1]
    return tail in ('write_text', 'write_bytes', 'write', 'writelines') and len(func_str) > len(tail)


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
