"""reveal surface — external boundary map for a codebase."""

import argparse
import ast
import json
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SKIP_DIRS: frozenset = frozenset({
    '__pycache__', '.git', '.tox', '.venv', 'venv', 'env',
    'node_modules', '.mypy_cache', '.pytest_cache', 'dist', 'build',
})

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


def create_surface_parser() -> argparse.ArgumentParser:
    from reveal.cli.parser import _build_global_options_parser
    parser = argparse.ArgumentParser(
        prog='reveal surface',
        parents=[_build_global_options_parser()],
        description='Map every external surface the system touches: CLI, HTTP routes, env vars, network, filesystem writes.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  reveal surface ./src          # All surfaces in src/\n"
            "  reveal surface .              # Entire project\n"
            "  reveal surface . --format json\n"
            "  reveal surface . --type env   # Only env vars\n"
        )
    )
    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='Directory to scan (default: current directory)'
    )
    parser.add_argument(
        '--type',
        metavar='TYPE',
        default='',
        help='Filter to one surface type: cli, http, mcp, env, network, fs, db, sdk'
    )
    return parser


def run_surface(args: Namespace) -> None:
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"Error: path '{args.path}' does not exist", file=sys.stderr)
        sys.exit(1)

    type_filter = getattr(args, 'type', '')
    report = _scan_surface(path, type_filter=type_filter)

    if args.format == 'json':
        print(json.dumps(report, indent=2, default=str))
        return

    _render_report(report)


def _scan_surface(path: Path, type_filter: str = '') -> Dict[str, Any]:
    py_files = _collect_python_files(path)
    surfaces: Dict[str, List[Dict[str, Any]]] = {
        'cli': [],
        'http': [],
        'mcp': [],
        'env': [],
        'network': [],
        'db': [],
        'sdk': [],
        'fs': [],
    }

    for file_path in py_files:
        try:
            source = file_path.read_text(errors='replace')
            tree = ast.parse(source, filename=str(file_path))
        except (SyntaxError, OSError):
            continue
        _scan_file(tree, str(file_path), surfaces)

    if type_filter:
        surfaces = {k: v for k, v in surfaces.items() if k == type_filter}

    total = sum(len(v) for v in surfaces.values())
    return {
        'path': str(path),
        'total': total,
        'surfaces': surfaces,
    }


def _collect_python_files(path: Path) -> List[Path]:
    if path.is_file() and path.suffix == '.py':
        return [path]
    files: List[Path] = []
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            if fname.endswith('.py'):
                files.append(Path(os.path.join(root, fname)))
    return files


def _scan_file(
    tree: ast.Module,
    file_path: str,
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    # Track import aliases for env/network detection
    aliases: Dict[str, str] = {}  # alias → canonical

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            _process_import(node, file_path, aliases, surfaces)
        elif isinstance(node, ast.FunctionDef):
            _process_function_def(node, file_path, surfaces)
        elif isinstance(node, ast.Call):
            _process_call(node, file_path, aliases, surfaces)
        elif isinstance(node, ast.AsyncFunctionDef):
            _process_function_def(node, file_path, surfaces)


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


def _check_network_import(name: str, file_path: str, line: int, surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    root = name.split('.')[0]
    if root in _NET_PACKAGES:
        _add_once(surfaces['network'], {
            'type': 'import',
            'name': name,
            'file': file_path,
            'line': line,
        })
    elif root in _DB_PACKAGES:
        _add_once(surfaces['db'], {
            'type': 'import',
            'name': name,
            'file': file_path,
            'line': line,
        })
    elif root in _SDK_PACKAGES:
        _add_once(surfaces['sdk'], {
            'type': 'import',
            'name': name,
            'file': file_path,
            'line': line,
        })


def _process_function_def(
    node: ast.FunctionDef,
    file_path: str,
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    for decorator in node.decorator_list:
        deco_str = _unparse_expr(decorator)
        deco_lower = deco_str.lower()

        # HTTP routes: @app.route, @router.get/post/put/delete/patch, @app.get, etc.
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

        # CLI commands: @click.command, @app.command, @group.command, @cli.command
        elif _is_cli_command(deco_str):
            name_arg = _extract_kwarg(decorator, 'name') or node.name
            surfaces['cli'].append({
                'type': 'command',
                'name': name_arg,
                'decorator': deco_str,
                'file': file_path,
                'line': node.lineno,
            })

        # MCP tools: @mcp.tool, @server.tool, @app.tool
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

    # Env vars: os.environ.get('KEY'), os.getenv('KEY'), environ['KEY']
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

    # Filesystem writes: open(path, 'w'/'a'), Path.write_text, shutil.copy
    elif _is_fs_write(func_str, node):
        target = _extract_first_arg(node) or '?'
        surfaces['fs'].append({
            'type': 'fs_write',
            'name': func_str,
            'target': target,
            'file': file_path,
            'line': node.lineno,
        })

    # argparse: parser.add_argument / subparsers.add_parser
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
        mode = _get_open_mode(node)
        return mode in _WRITE_MODES
    tail = func_str.split('.')[-1]
    return tail in ('write_text', 'write_bytes', 'write', 'writelines') and len(func_str) > len(tail)


def _get_open_mode(node: ast.Call) -> str:
    # open(path, mode) — mode is 2nd positional arg or 'mode' keyword
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


_SURFACE_LABELS = {
    'cli': 'CLI commands / arguments',
    'http': 'HTTP routes',
    'mcp': 'MCP tool registrations',
    'env': 'Environment variables',
    'network': 'Network I/O (imports)',
    'db': 'Database / storage (imports)',
    'sdk': 'External SDK (imports)',
    'fs': 'Filesystem writes',
}


def _render_report(report: Dict[str, Any]) -> None:
    path = report['path']
    total = report['total']
    surfaces = report['surfaces']

    print()
    print(f"Surface: {path}")
    print("━" * 50)
    print(f"Total surface entries: {total}")
    print()

    if total == 0:
        print("  No external surfaces detected.")
        print()
        return

    for key, label in _SURFACE_LABELS.items():
        entries = surfaces.get(key, [])
        if not entries:
            continue
        print(f"{label} ({len(entries)}):")
        for entry in entries:
            _render_entry(key, entry)
        print()


def _render_entry(surface_type: str, entry: Dict[str, Any]) -> None:
    file_path = entry.get('file', '')
    line = entry.get('line', '')
    loc = f"  {file_path}:{line}" if file_path else ''

    if surface_type == 'cli':
        kind = entry.get('type', '')
        name = entry.get('name', '?')
        if kind == 'argument':
            print(f"  {name}{loc}")
        elif kind == 'subcommand':
            print(f"  subcommand: {name}{loc}")
        else:
            print(f"  @{entry.get('decorator', '?')}  {name}{loc}")

    elif surface_type == 'http':
        method = entry.get('methods', 'ANY')
        path_ = entry.get('path', '?')
        name = entry.get('name', '?')
        print(f"  {method}  {path_}  → {name}{loc}")

    elif surface_type == 'mcp':
        name = entry.get('name', '?')
        print(f"  {name}{loc}")

    elif surface_type == 'env':
        name = entry.get('name', '?')
        print(f"  {name}{loc}")

    elif surface_type in ('network', 'db', 'sdk'):
        name = entry.get('name', '?')
        print(f"  import {name}{loc}")

    elif surface_type == 'fs':
        name = entry.get('name', '?')
        target = entry.get('target', '?')
        print(f"  {name}({target}){loc}")
