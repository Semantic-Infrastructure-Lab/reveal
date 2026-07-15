"""Tree-sitter surface extraction for Rust — env vars, FS writes, HTTP routes, CLI, imports.

BACK-403 pt 2 (surface breadth). Mirrors nav_surface_go.py's categorised-dict
shape but walks Rust's grammar:

- **HTTP routes**, two dominant idioms:
    * Actix-web / Rocket **attribute macros**: `#[get("/path")]`,
      `#[post("/path")]`, … — an `attribute_item` whose `attribute` identifier
      is an HTTP verb and whose `token_tree` holds a leading-`/` string.
    * Axum / Actix builder: `.route("/path", get(handler))` — a `.route(...)`
      call whose first argument is a leading-`/` string and whose second
      argument is a `verb(handler)` call (the verb is read from that nested
      call; unrecognised → method `ANY`).
    * Actix programmatic routing: `web::resource("/path")` / `web::scope("/path")`
      — the verb lives on a chained `.route(web::get()…)` (and a resource may
      bind several), so method is reported `ANY`; the surfaced value is the path.
      Without this, `surface` returns a misleading blank on a real actix app
      (e.g. Meilisearch), which reads as "no HTTP surface".
  As with the Go/Ruby scanners the **leading-`/` guard** keeps a stray `.route`
  or a lookalike attribute off non-route call sites.

- **env access**: `env::var("KEY")` / `std::env::var("KEY")` (and `*_os`) —
  reads only.

- **filesystem writes**: `std::fs::write` / `fs::write` and `File::create`.

- **CLI entrypoint**: a top-level `fn main` (a `function_item` that is a direct
  child of the source file — a method named `main` inside an `impl` is not the
  crate entrypoint and is excluded).

- **network/db/sdk egress**: `use`-path crate-root taxonomy (Rust crate roots
  are the first `::` segment; underscore form, e.g. `aws_sdk_s3`).

Still ❌ (no shared node shape with the languages above): C++.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

_NET_CRATES: frozenset = frozenset({
    'reqwest', 'hyper', 'isahc', 'ureq', 'tonic', 'tungstenite',
    'tokio_tungstenite', 'awc',
})

_DB_CRATES: frozenset = frozenset({
    'sqlx', 'diesel', 'tokio_postgres', 'postgres', 'mysql', 'mysql_async',
    'redis', 'mongodb', 'rusqlite', 'sea_orm', 'deadpool_postgres',
})

_SDK_CRATES: frozenset = frozenset({
    'stripe', 'rusoto_core', 'rusoto_s3', 'twilio', 'google_cloud_storage',
    'azure_core', 'octocrab',
})

# aws-sdk crates share a common `aws_sdk_*` prefix; handled as a prefix rule.
_SDK_PREFIXES: tuple = ('aws_sdk_', 'aws_config', 'azure_', 'google_cloud_')

_CRATE_TAXONOMY: tuple = (
    (_NET_CRATES, 'network'),
    (_DB_CRATES, 'db'),
    (_SDK_CRATES, 'sdk'),
)

_HTTP_VERBS: frozenset = frozenset({
    'get', 'post', 'put', 'delete', 'patch', 'head', 'options',
})

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')


def scan_file_surface_rust(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Rust file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('rust')
        tree = ts_parse(parser, source)
    except Exception:
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    root = tree_root(tree)

    # CLI: only a top-level `fn main` is the crate entrypoint.
    for child in _children(root):
        if _zero_arg(child, 'kind') == 'function_item' and _function_item_name(child, content_bytes) == 'main':
            surfaces['cli'].append({
                'type': 'main', 'name': 'main', 'file': file_path, 'line': _get_line(child),
            })

    stack = [root]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind == 'use_declaration':
            _process_use(node, file_path, content_bytes, surfaces)
        elif kind == 'attribute_item':
            _process_attribute(node, file_path, content_bytes, surfaces)
        elif kind == 'call_expression':
            _process_call(node, file_path, content_bytes, surfaces)
        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


def _function_item_name(node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _string_content(node: Any, content_bytes: bytes) -> Optional[str]:
    """Text inside a string_literal (its string_content child), quotes stripped."""
    if _zero_arg(node, 'kind') != 'string_literal':
        return None
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'string_content':
            return _get_text(ch, content_bytes)
    return _get_text(node, content_bytes).strip('"')


def _crate_root(node: Any, content_bytes: bytes) -> Optional[str]:
    """First `::` segment of a use path (the crate root)."""
    if _zero_arg(node, 'kind') == 'use_as_clause':
        node = next((c for c in _children(node) if _zero_arg(c, 'kind') in ('scoped_identifier', 'identifier')), node)
    if _zero_arg(node, 'kind') == 'scoped_identifier':
        for ch in _children(node):
            if _zero_arg(ch, 'kind') == 'identifier':
                return _get_text(ch, content_bytes)
            if _zero_arg(ch, 'kind') == 'scoped_identifier':
                return _crate_root(ch, content_bytes)
    if _zero_arg(node, 'kind') == 'identifier':
        return _get_text(node, content_bytes)
    return None


def _process_use(node: Any, file_path: str, content_bytes: bytes,
                 surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    target = next((c for c in _children(node)
                   if _zero_arg(c, 'kind') in ('scoped_identifier', 'use_as_clause', 'identifier',
                                   'scoped_use_list', 'use_list')), None)
    if target is None:
        return
    crate = _crate_root(target, content_bytes)
    if crate is None:
        return
    line = _get_line(node)
    full = _get_text(target, content_bytes).split(' as ')[0].strip()
    _categorize_crate(crate, full, file_path, line, surfaces)


def _categorize_crate(crate: str, full: str, file_path: str, line: int,
                      surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for prefix in _SDK_PREFIXES:
        if crate.startswith(prefix):
            _add_once(surfaces['sdk'], {'type': 'import', 'name': full, 'file': file_path, 'line': line})
            return
    for crates, category in _CRATE_TAXONOMY:
        if crate in crates:
            _add_once(surfaces[category], {'type': 'import', 'name': full, 'file': file_path, 'line': line})
            return


def _attribute_verb_and_path(attr_item: Any, content_bytes: bytes):
    """(verb, path) for an `#[get("/x")]`-style route attribute, or (None, None)."""
    attribute = next((c for c in _children(attr_item) if _zero_arg(c, 'kind') == 'attribute'), None)
    if attribute is None:
        return None, None
    verb = None
    token_tree = None
    for ch in _children(attribute):
        if _zero_arg(ch, 'kind') == 'identifier':
            verb = _get_text(ch, content_bytes)
        elif _zero_arg(ch, 'kind') == 'token_tree':
            token_tree = ch
    if verb is None or verb.lower() not in _HTTP_VERBS or token_tree is None:
        return None, None
    for ch in _children(token_tree):
        if _zero_arg(ch, 'kind') == 'string_literal':
            path = _string_content(ch, content_bytes)
            if path and path.startswith('/'):
                return verb.upper(), path
    return None, None


def _process_attribute(node: Any, file_path: str, content_bytes: bytes,
                       surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    verb, path = _attribute_verb_and_path(node, content_bytes)
    if verb is None:
        return
    surfaces['http'].append({
        'type': 'route', 'name': '?', 'path': path, 'methods': verb,
        'decorator': f'#[{verb.lower()}]', 'file': file_path, 'line': _get_line(node),
    })


def _call_function_child(node: Any):
    return next((c for c in _children(node) if _zero_arg(c, 'kind') in ('scoped_identifier', 'field_expression', 'identifier')), None)


def _first_string_arg(call_node: Any, content_bytes: bytes) -> Optional[str]:
    args = next((c for c in _children(call_node) if _zero_arg(c, 'kind') == 'arguments'), None)
    if args is None:
        return None
    for arg in _children(args):
        if _zero_arg(arg, 'kind') == 'string_literal':
            return _string_content(arg, content_bytes)
    return None


def _route_call_verb(call_node: Any, content_bytes: bytes) -> str:
    """Verb from an Axum `.route(path, get(handler))` — the 2nd arg's call
    identifier if it names an HTTP verb, else ANY."""
    args = next((c for c in _children(call_node) if _zero_arg(c, 'kind') == 'arguments'), None)
    if args is None:
        return 'ANY'
    call_args = [a for a in _children(args) if _zero_arg(a, 'kind') == 'call_expression']
    for ca in call_args:
        fn = _call_function_child(ca)
        if fn is not None and _zero_arg(fn, 'kind') == 'identifier':
            verb = _get_text(fn, content_bytes)
            if verb.lower() in _HTTP_VERBS:
                return verb.upper()
    return 'ANY'


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                  surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    fn = _call_function_child(node)
    if fn is None:
        return
    line = _get_line(node)

    if _zero_arg(fn, 'kind') == 'scoped_identifier':
        path_text = _get_text(fn, content_bytes)
        if path_text.endswith('env::var') or path_text.endswith('env::var_os'):
            key = _first_string_arg(node, content_bytes)
            if key:
                surfaces['env'].append({
                    'type': 'env_var', 'name': key, 'expr': path_text,
                    'file': file_path, 'line': line,
                })
            return
        if path_text.endswith('fs::write') or path_text.endswith('File::create'):
            surfaces['fs'].append({
                'type': 'fs_write', 'name': path_text, 'file': file_path, 'line': line,
            })
            return
        # Actix-web programmatic routing: web::resource("/path") / web::scope("/path").
        # The verb lives on a chained `.route(web::get()...)` and a resource may
        # bind several, so method is reported as ANY; the DD value is the path.
        if path_text.endswith('::resource') or path_text.endswith('::scope'):
            route_path = _first_string_arg(node, content_bytes)
            if route_path and route_path.startswith('/'):
                surfaces['http'].append({
                    'type': 'route', 'name': '?', 'path': route_path, 'methods': 'ANY',
                    'decorator': f'{path_text}()', 'file': file_path, 'line': line,
                })
            return

    if _zero_arg(fn, 'kind') == 'field_expression':
        field = next((c for c in _children(fn) if _zero_arg(c, 'kind') == 'field_identifier'), None)
        if field is not None and _get_text(field, content_bytes) == 'route':
            path = _first_string_arg(node, content_bytes)
            if path and path.startswith('/'):
                surfaces['http'].append({
                    'type': 'route', 'name': '?', 'path': path,
                    'methods': _route_call_verb(node, content_bytes),
                    'decorator': '.route()', 'file': file_path, 'line': line,
                })
