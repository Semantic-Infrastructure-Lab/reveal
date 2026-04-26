"""AST-level surface extraction — env vars, FS writes, HTTP routes, CLI, MCP, imports."""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    aliases: Dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _process_import(node, file_path, aliases, surfaces)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _process_function_def(node, file_path, surfaces)
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
) -> None:
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
        elif _is_cli_command(deco_str):
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


def _is_http_route(deco: str) -> bool:
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


def _is_cli_command(deco: str) -> bool:
    return '.command(' in deco.lower() or deco.lower() in ('command', 'click.command')


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


def _extract_first_arg(node: ast.Call) -> Optional[str]:
    if node.args:
        arg = node.args[0]
        if isinstance(arg, ast.Constant):
            return str(arg.value)
        return _unparse_expr(arg)
    return None


def _extract_kwarg(node: ast.Call, key: str) -> Optional[str]:
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


def _add_once(lst: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    key = (entry.get('name', ''), entry.get('file', ''), entry.get('line', 0))
    for existing in lst:
        if (existing.get('name', ''), existing.get('file', ''), existing.get('line', 0)) == key:
            return
    lst.append(entry)
