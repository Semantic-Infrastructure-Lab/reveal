"""Tree-sitter surface extraction for TypeScript/TSX — env vars, FS writes, HTTP routes, CLI, imports."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse

_NET_PACKAGES: frozenset = frozenset({
    'axios', 'fetch', 'node-fetch', 'got', 'ky', 'undici', 'ws', 'http', 'https', 'net',
})

_DB_PACKAGES: frozenset = frozenset({
    'pg', 'mysql', 'mysql2', 'prisma', '@prisma/client', 'knex', 'typeorm', 'sequelize',
    'mongodb', 'mongoose', 'ioredis', 'redis', 'better-sqlite3', 'drizzle-orm',
})

_SDK_PACKAGES: frozenset = frozenset({
    '@anthropic-ai/sdk', 'openai', 'stripe', 'twilio', '@slack/web-api', '@sendgrid/mail',
})

_FS_WRITE_METHODS: frozenset = frozenset({
    'writeFile', 'writeFileSync', 'appendFile', 'appendFileSync', 'createWriteStream',
})

_FS_WRITE_GLOBAL: Dict[str, frozenset] = {
    'Bun': frozenset({'write'}),
    'Deno': frozenset({'writeTextFile', 'writeFile'}),
}

_HTTP_METHODS: frozenset = frozenset({'get', 'post', 'put', 'delete', 'patch', 'head', 'options', 'route', 'all'})

_SUBPROCESS_OBJECTS: frozenset = frozenset({'child_process', 'exec', 'spawn', 'execFile', 'fork'})
_SUBPROCESS_METHODS: frozenset = frozenset({'exec', 'spawn', 'execFile', 'fork', 'execSync', 'spawnSync'})
_SUBPROCESS_CALLEE_NAMES: frozenset = frozenset({'execa', 'execaSync', 'execaCommand'})

_CLI_METHODS: frozenset = frozenset({'command', 'option'})

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')


def scan_file_surface_ts(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one TypeScript/TSX file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        path = Path(file_path)
        source = path.read_text(errors='replace')
        lang = 'tsx' if path.suffix == '.tsx' else 'typescript'
        parser = get_parser(lang)
        tree = ts_parse(parser, source)
    except Exception:
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(
    tree: Any,
    file_path: str,
    content_bytes: bytes,
) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}

    # Walk all nodes
    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = node.kind()

        if kind == 'import_statement':
            _process_import(node, file_path, content_bytes, surfaces)
        elif kind == 'call_expression':
            _process_call(node, file_path, content_bytes, surfaces)
        elif kind in ('member_expression', 'subscript_expression'):
            _process_member(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


def _get_import_source(node, content_bytes: bytes) -> Optional[str]:
    """Extract the module path string from an import_statement node."""
    for ch in _children(node):
        if ch.kind() == 'string':
            # string node: first string_fragment child
            for sch in _children(ch):
                if sch.kind() == 'string_fragment':
                    return _get_text(sch, content_bytes)
            # fallback: strip quotes
            raw = _get_text(ch, content_bytes)
            return raw.strip("'\"`")
    return None


def _process_import(
    node: Any,
    file_path: str,
    content_bytes: bytes,
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    module = _get_import_source(node, content_bytes)
    if not module:
        return
    line = _get_line(node)
    _categorize_module(module, file_path, line, surfaces)


def _categorize_module(
    module: str,
    file_path: str,
    line: int,
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    # Check exact match first (for scoped packages like @prisma/client)
    if module in _NET_PACKAGES:
        _add_once(surfaces['network'], {'type': 'import', 'name': module, 'file': file_path, 'line': line})
        return
    if module in _DB_PACKAGES:
        _add_once(surfaces['db'], {'type': 'import', 'name': module, 'file': file_path, 'line': line})
        return
    if module in _SDK_PACKAGES:
        _add_once(surfaces['sdk'], {'type': 'import', 'name': module, 'file': file_path, 'line': line})
        return
    # Check root package name (strip scope for @org/pkg → check @org/pkg and pkg)
    root = module.split('/')[0]
    if root in _NET_PACKAGES:
        _add_once(surfaces['network'], {'type': 'import', 'name': module, 'file': file_path, 'line': line})
    elif root in _DB_PACKAGES:
        _add_once(surfaces['db'], {'type': 'import', 'name': module, 'file': file_path, 'line': line})
    elif root in _SDK_PACKAGES:
        _add_once(surfaces['sdk'], {'type': 'import', 'name': module, 'file': file_path, 'line': line})


def _callee_obj_is_call(node: Any) -> bool:
    """Return True if the callee object is itself a call_expression (e.g. request(app).get)."""
    children = _children(node)
    if not children:
        return False
    callee = children[0]
    if callee.kind() != 'member_expression':
        return False
    parts = _children(callee)
    return bool(parts) and parts[0].kind() == 'call_expression'


def _get_callee_parts(node: Any, content_bytes: bytes):
    """For a call_expression node, return (obj, method) or (None, callee_name)."""
    children = _children(node)
    if not children:
        return None, None
    callee = children[0]
    if callee.kind() == 'member_expression':
        parts = _children(callee)
        if len(parts) >= 3:
            obj = _get_text(parts[0], content_bytes)
            method = _get_text(parts[-1], content_bytes)
            return obj, method
    elif callee.kind() == 'identifier':
        return None, _get_text(callee, content_bytes)
    return None, None


def _get_call_first_arg_string(node: Any, content_bytes: bytes) -> Optional[str]:
    """Extract first string argument from a call_expression."""
    children = _children(node)
    for ch in children:
        if ch.kind() == 'arguments':
            arg_children = [c for c in _children(ch) if c.kind() not in ('(', ')', ',')]
            if arg_children:
                first = arg_children[0]
                if first.kind() == 'string':
                    for sch in _children(first):
                        if sch.kind() == 'string_fragment':
                            return _get_text(sch, content_bytes)
                    return _get_text(first, content_bytes).strip("'\"`")
    return None


def _process_call(
    node: Any,
    file_path: str,
    content_bytes: bytes,
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    line = _get_line(node)
    obj, method = _get_callee_parts(node, content_bytes)

    if obj is None and method is None:
        return

    # standalone call: execa(...), fetch(...), etc.
    if obj is None and method is not None:
        if method in _SUBPROCESS_CALLEE_NAMES:
            _add_once(surfaces['subprocess'], {
                'type': 'subprocess', 'name': method, 'file': file_path, 'line': line,
            })
        elif method == 'fetch':
            _add_once(surfaces['network'], {
                'type': 'call', 'name': 'fetch', 'file': file_path, 'line': line,
            })
        return

    # obj.method(...) forms
    if method is None:
        return

    # subprocess: child_process.exec/spawn/execFile/fork
    if obj == 'child_process' and method in _SUBPROCESS_METHODS:
        _add_once(surfaces['subprocess'], {
            'type': 'subprocess', 'name': f'child_process.{method}', 'file': file_path, 'line': line,
        })
        return

    # fs writes: fs.writeFile, fs.appendFile, fs.createWriteStream
    if obj == 'fs' and method in _FS_WRITE_METHODS:
        _add_once(surfaces['fs'], {
            'type': 'fs_write', 'name': f'fs.{method}', 'file': file_path, 'line': line,
        })
        return

    # Bun.write / Deno.writeTextFile / Deno.writeFile
    if obj in _FS_WRITE_GLOBAL and method in _FS_WRITE_GLOBAL[obj]:
        _add_once(surfaces['fs'], {
            'type': 'fs_write', 'name': f'{obj}.{method}', 'file': file_path, 'line': line,
        })
        return

    # HTTP routes: app.get/post/put/delete/patch, router.get/post/...
    # Exclude supertest-style `request(app).get(...)` — obj_node is a call_expression, not an identifier
    if method in _HTTP_METHODS and not _callee_obj_is_call(node):
        path_arg = _get_call_first_arg_string(node, content_bytes)
        if path_arg and path_arg.startswith('/'):
            _add_once(surfaces['http'], {
                'type': 'route',
                'name': f'{obj}.{method}',
                'path': path_arg,
                'methods': method.upper(),
                'file': file_path,
                'line': line,
            })
            return

    # CLI: yargs.command / commander.command / yargs.option / commander.option
    if method in _CLI_METHODS:
        arg = _get_call_first_arg_string(node, content_bytes)
        _add_once(surfaces['cli'], {
            'type': 'command' if method == 'command' else 'option',
            'name': arg or '?',
            'expr': f'{obj}.{method}',
            'file': file_path,
            'line': line,
        })
        return


def _process_member(
    node: Any,
    file_path: str,
    content_bytes: bytes,
    surfaces: Dict[str, List[Dict[str, Any]]],
) -> None:
    """Detect process.env.VAR_NAME and process.env['VAR_NAME'] accesses."""
    line = _get_line(node)

    if node.kind() == 'member_expression':
        # process.env.VAR_NAME → member_expression(member_expression(process, env), VAR_NAME)
        children = _children(node)
        if len(children) >= 3:
            obj_node = children[0]
            prop_node = children[-1]
            if obj_node.kind() == 'member_expression':
                obj_text = _get_text(obj_node, content_bytes)
                if obj_text == 'process.env':
                    var_name = _get_text(prop_node, content_bytes)
                    _add_once(surfaces['env'], {
                        'type': 'env_var', 'name': var_name,
                        'expr': 'process.env', 'file': file_path, 'line': line,
                    })

    elif node.kind() == 'subscript_expression':
        # process.env['VAR_NAME']
        children = _children(node)
        if len(children) >= 2:
            obj_node = children[0]
            if obj_node.kind() == 'member_expression':
                obj_text = _get_text(obj_node, content_bytes)
                if obj_text == 'process.env':
                    # find string child
                    for ch in children[1:]:
                        if ch.kind() == 'string':
                            for sch in _children(ch):
                                if sch.kind() == 'string_fragment':
                                    var_name = _get_text(sch, content_bytes)
                                    _add_once(surfaces['env'], {
                                        'type': 'env_var', 'name': var_name,
                                        'expr': 'process.env', 'file': file_path, 'line': line,
                                    })
                                    return
