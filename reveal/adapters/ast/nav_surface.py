"""AST-level surface extraction — env vars, FS writes, HTTP routes, CLI, MCP, imports."""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .surface_rules import apply_ast_rules
from ...utils.pyparse import parse_python
from .surface_matrix import UNPARSED_KEY

# network/db/sdk imports are rule-driven (surface_rules_imports.py, BACK-1334 c).

_WRITE_MODES: frozenset = frozenset({'w', 'wb', 'a', 'ab', 'x', 'xb'})

# BACK-1338: a `.write` target longer than this is an expression (the data
# being written), not a path; cap it so one entry cannot be a whole call tree.
_MAX_TARGET_LEN = 60

_EMPTY: Dict[str, List] = {k: [] for k in ('cli', 'http', 'mcp', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')}

# mock.patch / mocker.patch / unittest.mock.patch decorators contain ".patch("
# which would otherwise be mistaken for an HTTP PATCH route.
_MOCK_PATCH_PREFIXES: tuple = ('mock.patch(', 'mocker.patch(', 'patch(')
_MOCK_PATCH_SUBSTRINGS: tuple = ('unittest.mock.patch(',)


def scan_file_surface(file_path: str) -> Dict[str, List[Any]]:
    """Parse one Python file and return categorised surface entries (plus
    UNPARSED_KEY: [file_path] when it cannot be parsed, BACK-1394)."""
    try:
        source = Path(file_path).read_text(errors='replace', encoding='utf-8')
        tree = parse_python(source, file_path)
    except (SyntaxError, ValueError, OSError):
        return {**{k: [] for k in _EMPTY}, UNPARSED_KEY: [file_path]}
    return _scan_tree(tree, file_path, source)


def _scan_tree(
    tree: ast.Module,
    file_path: str,
    source: Optional[str] = None,
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
    # BACK-1339: tools registered through a project decorator factory that
    # calls `<mcp>.tool(...)(fn)` internally are still MCP tools.
    mcp_registrars = _collect_mcp_registrars(tree, mcp_instances)
    # BACK-1338: `.write` calls inside a stream wrapper's own write() method.
    delegating_writes = _collect_delegating_writes(tree)
    # BACK-2268: which file a handle's `.write` writes to; fed by this walk, resolved after it.
    handles = _HandleTrace(aliases)

    for node in ast.walk(tree):
        handles.visit(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _process_function_def(node, file_path, surfaces, aliases, cli_groups, mcp_instances, http_apps,
                                  mcp_registrars)
        elif isinstance(node, ast.Call):
            fs_row = _process_call(node, file_path, surfaces, delegating_writes, aliases)
            if fs_row is not None:
                handles.note_write(node, fs_row)
        elif isinstance(node, ast.Subscript):
            # BACK-777: os.environ['X'] (read or write) is ast.Subscript, not
            # ast.Call — _process_call's dispatch never sees it.
            _process_subscript(node, file_path, surfaces)

    handles.resolve()
    apply_ast_rules(surfaces, tree, file_path, source)
    return surfaces


def _process_function_def(
    node: ast.FunctionDef,
    file_path: str,
    surfaces: Dict[str, List[Dict[str, Any]]],
    aliases: Optional[Dict[str, str]] = None,
    cli_groups: Optional[set] = None,
    mcp_instances: Optional[set] = None,
    http_apps: Optional[set] = None,
    mcp_registrars: Optional[set] = None,
) -> None:
    aliases = aliases or {}
    cli_groups = cli_groups or set()
    mcp_instances = mcp_instances or set()
    http_apps = http_apps or set()
    mcp_registrars = mcp_registrars or set()
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
        elif _mcp_tool_has_provenance(decorator, aliases, mcp_instances, mcp_registrars):
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
    surfaces: Dict[str, List[Dict[str, Any]]],
    delegating_writes: Optional[set] = None,
    aliases: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Record the surface entry `node` makes; return it when it is an fs row (BACK-2268)."""
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
    elif (target := _fs_write_target(func_str, node, delegating_writes or set(), aliases or {})) is not None:
        row: Dict[str, Any] = {
            'type': 'fs_write',
            'name': func_str,
            'target': _truncate(target),
            'file': file_path,
            'line': node.lineno,
        }
        surfaces['fs'].append(row)
        return row
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
    return None


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
# `MCPServer` is the official SDK's low-level server class (reveal's own).
_MCP_CONSTRUCTORS: frozenset = frozenset({'FastMCP', 'MCPServer'})


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


def _mcp_tool_has_provenance(
    deco: ast.expr, aliases: Dict[str, str], mcp_instances: set, mcp_registrars: Optional[set] = None,
) -> bool:
    """True when a `tool`-shaped decorator actually resolves to mcp/fastmcp."""
    func = deco.func if isinstance(deco, ast.Call) else deco
    if isinstance(func, ast.Name) and func.id in (mcp_registrars or ()):
        return True
    if isinstance(func, ast.Name):
        # bare @tool (e.g. `from mcp.server.fastmcp import tool`)
        return _resolves_to_mcp_framework(func.id, aliases)
    if isinstance(func, ast.Attribute) and func.attr == 'tool':
        base = func.value
        if isinstance(base, ast.Name) and base.id in mcp_instances:
            return True
        return _resolves_to_mcp_framework(_leftmost_name(base), aliases)
    return False


def _collect_mcp_registrars(tree: ast.Module, mcp_instances: set) -> set:
    """Module-level functions that register a tool on an MCP instance via
    `<mcp>.tool(...)(fn)` — a decorator factory wrapping `@mcp.tool()` (BACK-1339).
    Only the outermost function is named, so an inner helper called `decorator`
    elsewhere in the file is not swept in."""
    registrars: set = set()
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(node):
            inner = call.func if isinstance(call, ast.Call) else None
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == 'tool'
                    and isinstance(inner.func.value, ast.Name)
                    and inner.func.value.id in mcp_instances):
                registrars.add(node.name)
                break
    return registrars


def _collect_delegating_writes(tree: ast.Module) -> set:
    """ids of `.write`/`.writelines` calls made inside a method that is itself
    named write/writelines — a stream wrapper forwarding to another writer,
    whose real sink is elsewhere (BACK-1338)."""
    ids: set = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in ('write', 'writelines'):
            ids.update(id(c) for c in ast.walk(node) if isinstance(c, ast.Call))
    return ids


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_TARGET_LEN else text[:_MAX_TARGET_LEN - 1] + '…'


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


def _fs_write_target(func_str: str, node: ast.Call, delegating_writes: set,
                     aliases: Dict[str, str]) -> Optional[str]:
    """What a filesystem write writes to, or None when `node` is not one."""
    if _is_fs_write(func_str, node):
        return None if id(node) in delegating_writes else _written_path(node) or '?'
    return _shutil_destination(func_str, node, aliases)


# BACK-1697: pathlib's writers are methods of the path they write, so the target is the
# receiver, like open(path, 'w')'s path; `Path('a.txt')` reports 'a.txt' as open('a.txt')
# does. A handle's `.write(data)` reports the handle, never the data (BACK-2268), and
# _HandleTrace replaces it with the path the handle was opened on when it can.
_PATH_WRITERS: frozenset = frozenset({'write_text', 'write_bytes'})
_HANDLE_WRITERS: frozenset = frozenset({'write', 'writelines'})
_PATH_CONSTRUCTORS: frozenset = frozenset({
    'Path', 'PosixPath', 'WindowsPath', 'pathlib.Path', 'pathlib.PosixPath', 'pathlib.WindowsPath',
})


def _written_path(node: ast.Call) -> Optional[str]:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in _HANDLE_WRITERS:
        return _unparse_expr(func.value)
    if not (isinstance(func, ast.Attribute) and func.attr in _PATH_WRITERS):
        return _extract_first_arg(node)
    return _receiver_path(func.value)


def _receiver_path(receiver: ast.expr) -> str:
    """The path a pathlib method's receiver names: `Path('a.txt')` → 'a.txt', `p` → 'p'."""
    if (isinstance(receiver, ast.Call) and len(receiver.args) == 1 and not receiver.keywords
            and _unparse_expr(receiver.func) in _PATH_CONSTRUCTORS):
        return _arg_text(receiver.args[0])
    return _unparse_expr(receiver)


# BACK-1697: shutil calls that create or replace a file or tree at their destination
# (second positional argument or `dst=`), resolved through the file's imports. Not fs
# rows: rmtree (a delete; no language's fs row counts deletes), copymode/copystat
# (metadata only), make_archive/unpack_archive (the written path is not one argument).
_SHUTIL_WRITES: frozenset = frozenset({'copy', 'copy2', 'copyfile', 'copytree', 'move'})


def _resolved_name(func_str: str, aliases: Dict[str, str]) -> str:
    """`func_str` with its first segment resolved through the file's imports (`sh.copy`)."""
    head, dot, rest = func_str.partition('.')
    return f'{aliases.get(head, head)}{dot}{rest}'


def _shutil_destination(func_str: str, node: ast.Call, aliases: Dict[str, str]) -> Optional[str]:
    module, _, name = _resolved_name(func_str, aliases).rpartition('.')
    if module != 'shutil' or name not in _SHUTIL_WRITES:
        return None
    if len(node.args) >= 2:
        return _arg_text(node.args[1])
    return _extract_kwarg(node, 'dst') or '?'


# BACK-2268: calls that return a file handle, resolved through the file's imports. The first
# group takes the path first, so the handle's writes report it as the open() row prints it; a
# temporary file has no path argument, so its writes report the call that made it. A pathlib
# `p.open('w')` reports its receiver as `p.write_text` does; it is told apart from other
# `.open(path, mode)` methods (sftp, zip, a project's own) by a literal writing mode as its
# first argument or `mode=`.
_PATH_OPENERS: frozenset = frozenset({
    'open', 'io.open', 'codecs.open', 'gzip.open', 'bz2.open', 'lzma.open',
})
_TEMP_OPENERS: frozenset = frozenset({
    'tempfile.NamedTemporaryFile', 'tempfile.TemporaryFile', 'tempfile.SpooledTemporaryFile',
})
_SCOPE_NODES: tuple = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)
_TRACED_KINDS: frozenset = frozenset({
    ast.arg, *_SCOPE_NODES, ast.With, ast.AsyncWith, ast.Assign, ast.AnnAssign,
    ast.Global, ast.Nonlocal, ast.ExceptHandler,
})

_Pos = Tuple[int, int]


def _handle_origin(value: Optional[ast.expr], aliases: Dict[str, str]) -> Optional[str]:
    """What a handle made by `value` writes to; None when `value` opens no file handle."""
    if not (isinstance(value, ast.Call) and isinstance(value.func, (ast.Name, ast.Attribute))):
        return None
    func_str = _unparse_expr(value.func)
    name = _resolved_name(func_str, aliases)
    if name in _PATH_OPENERS:
        return _written_path(value) or '?'
    if name in _TEMP_OPENERS:
        return f'{func_str}(...)'
    func = value.func
    if isinstance(func, ast.Attribute) and func.attr == 'open' and _pathlib_write_mode(value):
        return _receiver_path(func.value)
    return None


_MODE_CHARS: frozenset = frozenset('rwaxbt+')


def _pathlib_write_mode(call: ast.Call) -> bool:
    """True when `call`'s first argument or `mode=` is a literal writing mode ('w', 'ab', 'r+')."""
    mode: Optional[ast.expr] = call.args[0] if call.args else None
    for kw in call.keywords:
        if mode is None and kw.arg == 'mode':
            mode = kw.value
    if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str) and mode.value):
        return False
    return set(mode.value) <= _MODE_CHARS and bool(set(mode.value) & set('wax+'))


def _start(node: ast.AST) -> _Pos:
    return (getattr(node, 'lineno', 0), getattr(node, 'col_offset', 0))


def _end(node: ast.AST) -> _Pos:
    return (getattr(node, 'end_lineno', None) or 0, getattr(node, 'end_col_offset', None) or 0)


class _HandleTrace:
    """One def-use step over `_scan_tree`'s walk (BACK-2268): a handle's `.write(data)` row
    reports the path the handle was opened on when a single binding in the same scope opened it.

    The walk feeds scopes, every binding of a name (store/del targets, parameters, `except ... as`,
    `global`/`nonlocal`) and the bindings made by an opening call. A write inside the body of a
    `with <opener> as f` reports that opener's path unless `f` is bound again in that body; a
    write after `f = <opener>` reports it only when that is the scope's one binding of `f`.
    Anything else keeps the handle expression the row already carries. Flow-insensitive on
    purpose: a name bound twice is reported as the name, never as the wrong path."""

    def __init__(self, aliases: Dict[str, str]) -> None:
        self._aliases = aliases
        self._nodes: List[ast.AST] = []
        self._scopes: List[Tuple[_Pos, _Pos]] = []
        self._bindings: List[Tuple[str, _Pos, int]] = []
        # id() of the Name an opening call binds -> its target, plus the with-body's span.
        self._with_binders: Dict[int, Tuple[str, _Pos, _Pos]] = {}
        self._assign_binders: Dict[int, str] = {}
        self._writes: List[Tuple[Dict[str, Any], str, _Pos]] = []

    def visit(self, node: ast.AST) -> None:
        """Keep the nodes the trace may need; they are read only if the file has a handle write."""
        kind = type(node)
        if kind is ast.Name:
            if type(node.ctx) is not ast.Load:  # type: ignore[attr-defined]
                self._nodes.append(node)
        elif kind in _TRACED_KINDS:
            self._nodes.append(node)

    def _index(self, node: Any) -> None:
        if isinstance(node, ast.Name):
            self._bindings.append((node.id, _start(node), id(node)))
        elif isinstance(node, ast.arg):
            self._bindings.append((node.arg, _start(node), id(node)))
        elif isinstance(node, _SCOPE_NODES):
            self._scopes.append((_start(node), _end(node)))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            self._note_with(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            self._note_assign(node)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            self._bindings.extend((name, _start(node), id(node)) for name in node.names)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            self._bindings.append((node.name, _start(node), id(node)))

    def _note_with(self, node: Any) -> None:
        body = (_start(node.body[0]), _end(node))
        for item in node.items:
            if isinstance(item.optional_vars, ast.Name):
                origin = _handle_origin(item.context_expr, self._aliases)
                if origin is not None:
                    self._with_binders[id(item.optional_vars)] = (origin, *body)

    def _note_assign(self, node: Any) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if len(targets) == 1 and isinstance(targets[0], ast.Name):
            origin = _handle_origin(node.value, self._aliases)
            if origin is not None:
                self._assign_binders[id(targets[0])] = origin

    def note_write(self, node: ast.Call, row: Dict[str, Any]) -> None:
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr in _HANDLE_WRITERS
                and isinstance(func.value, ast.Name)):
            self._writes.append((row, func.value.id, _start(node)))

    def resolve(self) -> None:
        if not self._writes:
            return
        for node in self._nodes:
            self._index(node)
        names = {name for _, name, _ in self._writes}
        by_scope: Dict[Tuple[Optional[_Pos], str], List[Tuple[_Pos, int]]] = {}
        for name, pos, node_id in self._bindings:
            if name in names:
                by_scope.setdefault((self._scope_of(pos), name), []).append((pos, node_id))
        for row, name, pos in self._writes:
            origin = self._origin(by_scope.get((self._scope_of(pos), name), []), pos)
            if origin is not None:
                row['target'] = _truncate(origin)

    def _scope_of(self, pos: _Pos) -> Optional[_Pos]:
        """Start of the innermost function, lambda or class holding `pos`; None for the module."""
        starts = [start for start, end in self._scopes if start <= pos <= end]
        return max(starts) if starts else None

    def _origin(self, bindings: List[Tuple[_Pos, int]], pos: _Pos) -> Optional[str]:
        binders = [self._with_binders[node_id] for _, node_id in bindings
                   if node_id in self._with_binders]
        enclosing = [(start, end, origin) for origin, start, end in binders if start <= pos <= end]
        if enclosing:
            start, end, origin = max(enclosing)
            return None if any(start <= bpos <= end for bpos, _ in bindings) else origin
        if len(bindings) == 1 and bindings[0][0] < pos:
            return self._assign_binders.get(bindings[0][1])
        return None


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
        return _arg_text(node.args[0])
    return None


def _arg_text(arg: ast.expr) -> str:
    if isinstance(arg, ast.Constant):
        return str(arg.value)
    return _unparse_expr(arg)


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
    except (ValueError, TypeError, RecursionError):
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{_unparse_expr(node.value)}.{node.attr}"
        return '?'
