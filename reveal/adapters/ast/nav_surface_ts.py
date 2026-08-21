"""Tree-sitter surface extraction for TypeScript/TSX/JavaScript/JSX — env vars, FS writes, HTTP routes, CLI, imports."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once

logger = logging.getLogger(__name__)

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

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

# BACK-785: mirrors BACK-786's Python mcp provenance fix — a bare `.tool()`
# call is not evidence of MCP registration on its own (many objects expose a
# `tool` method); it must resolve to an instance constructed from the
# official MCP TypeScript SDK's `McpServer`, tracked through import aliasing.
_MCP_PACKAGE_ROOTS: frozenset = frozenset({'@modelcontextprotocol/sdk'})
_MCP_CONSTRUCTORS: frozenset = frozenset({'McpServer'})
_MCP_METHODS: frozenset = frozenset({'tool', 'registerTool'})

# BACK-790: same discipline as BACK-785's MCP fix — an `obj.get()`/`.post()`/
# etc call is not evidence of an HTTP route on its own; `obj` must resolve to
# an Express app/router. CommonJS `require('express')` is out of scope, same
# precedent as the MCP collector (ESM import only).
_EXPRESS_PACKAGE: str = 'express'
_EXPRESS_INSTANCE_TYPES: frozenset = frozenset({'Application', 'Express', 'Router'})

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess', 'mcp')


def scan_file_surface_ts(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one TypeScript/TSX/JavaScript/JSX file and return categorised surface entries.

    BACK-631: plain JS/JSX share this scanner — the extraction below is generic
    tree-walking (env vars, HTTP routes, FS writes, ...) with no type-annotation
    dependency, so TS's grammar (a JS superset) parses plain .js fine; .jsx
    needs the JSX-aware 'tsx' grammar just like .tsx does.
    """
    try:
        from tree_sitter_language_pack import get_parser
        path = Path(file_path)
        source = path.read_text(errors='replace')
        lang = 'tsx' if path.suffix in ('.tsx', '.jsx') else 'typescript'
        parser = get_parser(lang)
        tree = ts_parse(parser, source)
    except Exception as e:
        logger.warning("surface scan (TS/JS) failed to parse %s: %s", file_path, e)
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(
    tree: Any,
    file_path: str,
    content_bytes: bytes,
) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}

    mcp_ctor_names = _collect_mcp_constructor_aliases(tree, content_bytes)
    mcp_instances = _collect_mcp_instances(tree, content_bytes, mcp_ctor_names)
    express_instances = _collect_express_instances(tree, content_bytes)

    # Walk all nodes
    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')

        if kind == 'import_statement':
            _process_import(node, file_path, content_bytes, surfaces)
        elif kind == 'call_expression':
            _process_call(node, file_path, content_bytes, surfaces, mcp_instances, express_instances)
        elif kind in ('member_expression', 'subscript_expression'):
            _process_member(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


def _is_mcp_module(module: str) -> bool:
    return module in _MCP_PACKAGE_ROOTS or any(
        module.startswith(root + '/') for root in _MCP_PACKAGE_ROOTS
    )


def _get_import_clause_specifiers(node: Any, content_bytes: bytes) -> List[tuple]:
    """Return (imported_name, local_name) pairs for an import_statement's clause —
    named imports (`{ McpServer }`, `{ McpServer as Server2 }`) and default imports."""
    specifiers: List[tuple] = []
    for ch in _children(node):
        if _zero_arg(ch, 'kind') != 'import_clause':
            continue
        for clause_ch in _children(ch):
            if _zero_arg(clause_ch, 'kind') == 'named_imports':
                for spec in _children(clause_ch):
                    if _zero_arg(spec, 'kind') != 'import_specifier':
                        continue
                    idents = [c for c in _children(spec) if _zero_arg(c, 'kind') == 'identifier']
                    if len(idents) == 1:
                        name = _get_text(idents[0], content_bytes)
                        specifiers.append((name, name))
                    elif len(idents) == 2:
                        imported = _get_text(idents[0], content_bytes)
                        local = _get_text(idents[1], content_bytes)
                        specifiers.append((imported, local))
            elif _zero_arg(clause_ch, 'kind') == 'identifier':
                specifiers.append(('default', _get_text(clause_ch, content_bytes)))
    return specifiers


def _collect_mcp_constructor_aliases(tree: Any, content_bytes: bytes) -> set:
    """Local names bound to the MCP SDK's `McpServer` export via import
    (alias-aware — `McpServer as Server2` resolves to `Server2`)."""
    aliases: set = set()
    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') == 'import_statement':
            module = _get_import_source(node, content_bytes)
            if module and _is_mcp_module(module):
                for imported, local in _get_import_clause_specifiers(node, content_bytes):
                    if imported in _MCP_CONSTRUCTORS:
                        aliases.add(local)
        for ch in _children(node):
            stack.append(ch)
    return aliases


def _collect_mcp_instances(tree: Any, content_bytes: bytes, mcp_ctor_names: set) -> set:
    """Variable/parameter names bound to an `McpServer` — either a local
    constructed via `new McpServer(...)`, or a function/arrow-function
    parameter typed `: McpServer` (the dominant real-world shape: modular
    servers pass the instance into per-tool `register(server: McpServer)`
    functions rather than constructing it inline — see BACK-785 follow-up)."""
    instances: set = set()
    if not mcp_ctor_names:
        return instances
    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind == 'variable_declarator':
            children = _children(node)
            if children and _zero_arg(children[0], 'kind') == 'identifier':
                value = children[-1]
                if (
                    _zero_arg(value, 'kind') == 'new_expression'
                    and any(
                        _zero_arg(ch, 'kind') == 'identifier' and _get_text(ch, content_bytes) in mcp_ctor_names
                        for ch in _children(value)
                    )
                ):
                    instances.add(_get_text(children[0], content_bytes))
        elif kind in ('required_parameter', 'optional_parameter'):
            children = _children(node)
            if children and _zero_arg(children[0], 'kind') == 'identifier':
                for ch in children:
                    if _zero_arg(ch, 'kind') != 'type_annotation':
                        continue
                    if any(
                        _zero_arg(tch, 'kind') == 'type_identifier'
                        and _get_text(tch, content_bytes) in mcp_ctor_names
                        for tch in _children(ch)
                    ):
                        instances.add(_get_text(children[0], content_bytes))
        for ch in _children(node):
            stack.append(ch)
    return instances


def _get_require_call_module(node: Any, content_bytes: bytes) -> Optional[str]:
    """`require('express')` → 'express'; None if `node` isn't a require call
    with a string-literal argument."""
    children = _children(node)
    if not children or _zero_arg(children[0], 'kind') != 'identifier':
        return None
    if _get_text(children[0], content_bytes) != 'require':
        return None
    for ch in children[1:]:
        if _zero_arg(ch, 'kind') != 'arguments':
            continue
        for arg in _children(ch):
            if _zero_arg(arg, 'kind') == 'string':
                for sch in _children(arg):
                    if _zero_arg(sch, 'kind') == 'string_fragment':
                        return _get_text(sch, content_bytes)
    return None


def _collect_express_import_names(tree: Any, content_bytes: bytes) -> tuple:
    """`(default_local_name, router_named_import_locals)` — covers ESM
    (`import express from 'express'`, `import { Router } from 'express'`)
    and CommonJS (`const express = require('express')`,
    `const { Router } = require('express')`), the still-dominant real-world
    shape (BACK-790 recall verification against expressjs/express's own
    examples/, which are 100% CommonJS, showed 100%→25% recall without this)."""
    default_name: Optional[str] = None
    router_names: set = set()
    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind == 'import_statement':
            module = _get_import_source(node, content_bytes)
            if module == _EXPRESS_PACKAGE:
                for imported, local in _get_import_clause_specifiers(node, content_bytes):
                    if imported == 'default':
                        default_name = local
                    elif imported == 'Router':
                        router_names.add(local)
        elif kind == 'variable_declarator':
            children = _children(node)
            if children and _zero_arg(children[-1], 'kind') == 'call_expression':
                if _get_require_call_module(children[-1], content_bytes) == _EXPRESS_PACKAGE:
                    target = children[0]
                    if _zero_arg(target, 'kind') == 'identifier':
                        default_name = _get_text(target, content_bytes)
                    elif _zero_arg(target, 'kind') == 'object_pattern':
                        for pch in _children(target):
                            if _zero_arg(pch, 'kind') == 'shorthand_property_identifier_pattern':
                                if _get_text(pch, content_bytes) == 'Router':
                                    router_names.add('Router')
        for ch in _children(node):
            stack.append(ch)
    return default_name, router_names


def _is_express_constructor_call(call_node: Any, content_bytes: bytes, default_name: Optional[str], router_names: set) -> bool:
    """`express(...)` / `express.Router(...)` / a bare `Router(...)` bound to
    a named `Router` import from express."""
    children = _children(call_node)
    if not children:
        return False
    callee = children[0]
    ck = _zero_arg(callee, 'kind')
    if ck == 'identifier':
        name = _get_text(callee, content_bytes)
        return name == default_name or name in router_names
    if ck == 'member_expression':
        parts = _children(callee)
        if len(parts) >= 2 and _zero_arg(parts[0], 'kind') == 'identifier':
            obj_name = _get_text(parts[0], content_bytes)
            prop_name = _get_text(parts[-1], content_bytes)
            return obj_name == default_name and prop_name == 'Router'
    return False


def _type_node_is_express_instance(type_node: Any, content_bytes: bytes) -> bool:
    """True if `type_node` (the value inside a `type_annotation`, e.g. the
    `Application` in `: Application` or the `express.Application` in
    `: express.Application`) names one of `_EXPRESS_INSTANCE_TYPES` — either
    a bare `type_identifier` or the rightmost segment of a qualified
    `nested_type_identifier` (BACK-831: `express.Application` is the
    dominant real-world shape once `express` is imported as a namespace
    rather than destructuring `Application` by name)."""
    kind = _zero_arg(type_node, 'kind')
    if kind == 'type_identifier':
        return _get_text(type_node, content_bytes) in _EXPRESS_INSTANCE_TYPES
    if kind == 'nested_type_identifier':
        children = _children(type_node)
        return bool(children) and _type_node_is_express_instance(children[-1], content_bytes)
    return False


def _annotation_is_express_instance(type_annotation_node: Any, content_bytes: bytes) -> bool:
    """True if a `type_annotation` node's contained type resolves to an
    Express instance type."""
    return any(
        _type_node_is_express_instance(tch, content_bytes)
        for tch in _children(type_annotation_node)
    )


def _destructured_express_names(param_node: Any, content_bytes: bytes) -> set:
    """BACK-831: a destructured parameter with an inline object-type
    annotation — `({ app }: { app: express.Application }) => ...` — binds
    `app` to the Express instance, but the type lives on a
    `property_signature` inside the annotation's `object_type`, one level
    removed from the identifier itself (unlike the plain `(app: Application)`
    shape). Match each destructured property name against its sibling
    `property_signature`'s type and return the bound local names whose type
    resolves to an Express instance."""
    names: set = set()
    children = _children(param_node)
    if not children or _zero_arg(children[0], 'kind') != 'object_pattern':
        return names
    pattern_node = children[0]
    annotation_node = next(
        (ch for ch in children if _zero_arg(ch, 'kind') == 'type_annotation'), None
    )
    if annotation_node is None:
        return names
    object_type_node = next(
        (ch for ch in _children(annotation_node) if _zero_arg(ch, 'kind') == 'object_type'), None
    )
    if object_type_node is None:
        return names

    # property name -> its declared type (property_signature's type_annotation)
    declared_types: Dict[str, Any] = {}
    for prop in _children(object_type_node):
        if _zero_arg(prop, 'kind') != 'property_signature':
            continue
        prop_children = _children(prop)
        if not prop_children or _zero_arg(prop_children[0], 'kind') != 'property_identifier':
            continue
        prop_name = _get_text(prop_children[0], content_bytes)
        prop_annotation = next(
            (pch for pch in prop_children if _zero_arg(pch, 'kind') == 'type_annotation'), None
        )
        if prop_annotation is not None:
            declared_types[prop_name] = prop_annotation

    for pch in _children(pattern_node):
        pk = _zero_arg(pch, 'kind')
        if pk == 'shorthand_property_identifier_pattern':
            # `{ app }` — bound local name is the same as the property name
            source_name = local_name = _get_text(pch, content_bytes)
        elif pk == 'pair_pattern':
            # `{ app: theApp }` — renamed binding
            pair_children = _children(pch)
            if len(pair_children) < 2 or _zero_arg(pair_children[0], 'kind') != 'property_identifier':
                continue
            source_name = _get_text(pair_children[0], content_bytes)
            local_name = _get_text(pair_children[-1], content_bytes)
        else:
            continue
        prop_annotation = declared_types.get(source_name)
        if prop_annotation is not None and _annotation_is_express_instance(prop_annotation, content_bytes):
            names.add(local_name)
    return names


def _collect_express_instances(tree: Any, content_bytes: bytes) -> set:
    """Variable names bound to an Express app/router — `express()`,
    `express.Router()`, a bare `Router()` (named import, the dominant
    modular-router shape — see node-express-realworld-example-app) — plus
    function parameters typed `Application`/`Express`/`Router` (bare or
    `express.`-qualified), including destructured parameters with an inline
    object-type annotation (BACK-831)."""
    default_name, router_names = _collect_express_import_names(tree, content_bytes)
    instances: set = set()
    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind == 'variable_declarator' and (default_name or router_names):
            children = _children(node)
            if children and _zero_arg(children[0], 'kind') == 'identifier':
                value = children[-1]
                if _zero_arg(value, 'kind') == 'call_expression' and _is_express_constructor_call(
                    value, content_bytes, default_name, router_names
                ):
                    instances.add(_get_text(children[0], content_bytes))
        elif kind in ('required_parameter', 'optional_parameter'):
            children = _children(node)
            if children and _zero_arg(children[0], 'kind') == 'identifier':
                for ch in children:
                    if _zero_arg(ch, 'kind') != 'type_annotation':
                        continue
                    if _annotation_is_express_instance(ch, content_bytes):
                        instances.add(_get_text(children[0], content_bytes))
            else:
                instances |= _destructured_express_names(node, content_bytes)
        for ch in _children(node):
            stack.append(ch)
    return instances


def _get_import_source(node, content_bytes: bytes) -> Optional[str]:
    """Extract the module path string from an import_statement node."""
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'string':
            # string node: first string_fragment child
            for sch in _children(ch):
                if _zero_arg(sch, 'kind') == 'string_fragment':
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
    if _zero_arg(callee, 'kind') != 'member_expression':
        return False
    parts = _children(callee)
    return bool(parts) and _zero_arg(parts[0], 'kind') == 'call_expression'


def _get_callee_parts(node: Any, content_bytes: bytes):
    """For a call_expression node, return (obj, method) or (None, callee_name)."""
    children = _children(node)
    if not children:
        return None, None
    callee = children[0]
    if _zero_arg(callee, 'kind') == 'member_expression':
        parts = _children(callee)
        if len(parts) >= 3:
            obj = _get_text(parts[0], content_bytes)
            method = _get_text(parts[-1], content_bytes)
            return obj, method
    elif _zero_arg(callee, 'kind') == 'identifier':
        return None, _get_text(callee, content_bytes)
    return None, None


def _get_call_first_arg_string(node: Any, content_bytes: bytes) -> Optional[str]:
    """Extract first string argument from a call_expression."""
    children = _children(node)
    for ch in children:
        if _zero_arg(ch, 'kind') == 'arguments':
            arg_children = [c for c in _children(ch) if _zero_arg(c, 'kind') not in ('(', ')', ',')]
            if arg_children:
                first = arg_children[0]
                if _zero_arg(first, 'kind') == 'string':
                    for sch in _children(first):
                        if _zero_arg(sch, 'kind') == 'string_fragment':
                            return _get_text(sch, content_bytes)
                    return _get_text(first, content_bytes).strip("'\"`")
    return None


def _process_call(
    node: Any,
    file_path: str,
    content_bytes: bytes,
    surfaces: Dict[str, List[Dict[str, Any]]],
    mcp_instances: set,
    express_instances: set,
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
    # BACK-790: obj must resolve to an Express app/router, not just any
    # object exposing a same-named method.
    if method in _HTTP_METHODS and not _callee_obj_is_call(node) and obj in express_instances:
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

    # MCP tool registration: server.tool(name, schema, handler) (legacy v1 API)
    # or server.registerTool(name, config, handler) (current v2 API) — only
    # when `server` was constructed from the MCP SDK's McpServer (see BACK-785).
    if method in _MCP_METHODS and obj in mcp_instances:
        arg = _get_call_first_arg_string(node, content_bytes)
        _add_once(surfaces['mcp'], {
            'type': 'tool',
            'name': arg or '?',
            'expr': f'{obj}.{method}',
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

    if _zero_arg(node, 'kind') == 'member_expression':
        # process.env.VAR_NAME → member_expression(member_expression(process, env), VAR_NAME)
        children = _children(node)
        if len(children) >= 3:
            obj_node = children[0]
            prop_node = children[-1]
            if _zero_arg(obj_node, 'kind') == 'member_expression':
                obj_text = _get_text(obj_node, content_bytes)
                if obj_text == 'process.env':
                    var_name = _get_text(prop_node, content_bytes)
                    _add_once(surfaces['env'], {
                        'type': 'env_var', 'name': var_name,
                        'expr': 'process.env', 'file': file_path, 'line': line,
                    })

    elif _zero_arg(node, 'kind') == 'subscript_expression':
        # process.env['VAR_NAME']
        children = _children(node)
        if len(children) >= 2:
            obj_node = children[0]
            if _zero_arg(obj_node, 'kind') == 'member_expression':
                obj_text = _get_text(obj_node, content_bytes)
                if obj_text == 'process.env':
                    # find string child
                    for ch in children[1:]:
                        if _zero_arg(ch, 'kind') == 'string':
                            for sch in _children(ch):
                                if _zero_arg(sch, 'kind') == 'string_fragment':
                                    var_name = _get_text(sch, content_bytes)
                                    _add_once(surfaces['env'], {
                                        'type': 'env_var', 'name': var_name,
                                        'expr': 'process.env', 'file': file_path, 'line': line,
                                    })
                                    return
