"""Tree-sitter surface extraction for Go — env vars, FS writes, HTTP routes, CLI, imports.

BACK-403 pt 2 (surface breadth). Mirrors nav_surface_java.py's categorised-dict
shape but walks Go's grammar:

- **HTTP routes** for the dominant Go routers, all of which express a route as a
  method call whose selector field is an HTTP verb (or ``HandleFunc``/``Handle``)
  and whose first argument is a path string:
    * Gin / Echo (upper-case verbs): ``r.GET("/users", h)``, ``e.POST(...)``,
      ``r.Any(...)``.
    * Chi / gorilla-style (title-case verbs): ``r.Get("/users", h)``.
    * net/http and gorilla/mux: ``http.HandleFunc("/health", h)`` /
      ``r.HandleFunc("/path", h)`` — method recorded as ``ANY`` (the verb is
      constrained elsewhere, e.g. a chained ``.Methods("GET")`` this pass does
      not resolve).
  Like the Ruby/PHP scanners, the **leading-``/`` first-argument guard is
  load-bearing** — it is what keeps a title-case verb like Chi's ``Get`` from
  firing on an ordinary ``cache.Get("key")`` getter.

- **env access**: ``os.Getenv("KEY")`` and ``os.LookupEnv("KEY")`` (reads only;
  ``os.Environ`` returns everything and ``os.Setenv`` is a write — neither is a
  named-key read, so both are skipped).

- **filesystem writes**: ``os.WriteFile`` / ``os.Create`` / ``os.OpenFile`` /
  ``os.Mkdir`` / ``os.MkdirAll`` / ``ioutil.WriteFile``.

- **CLI entrypoint**: a top-level ``func main()`` — a ``function_declaration``
  (not a ``method_declaration``: a receiver method named ``main`` is neither an
  entrypoint nor the same node kind) — gated on the file declaring
  ``package main`` (a ``func main`` in any other package is an ordinary
  function, not the program entrypoint).

- **network/db/sdk egress**: import-path taxonomy of common Go modules. Go
  import paths are ``/``-separated, so matching is prefix-on-``/`` (e.g.
  ``github.com/stripe/stripe-go/v72`` matches the ``github.com/stripe/stripe-go``
  SDK prefix).

Still ❌ (no shared node shape with the languages above; each its own pass):
Rust, C++.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse

_NET_MODULES: frozenset = frozenset({
    'net/http', 'net/rpc', 'google.golang.org/grpc',
    'github.com/gorilla/websocket', 'github.com/go-resty/resty',
})

_DB_MODULES: frozenset = frozenset({
    'database/sql', 'gorm.io/gorm', 'github.com/jmoiron/sqlx',
    'go.mongodb.org/mongo-driver', 'github.com/redis/go-redis',
    'github.com/go-redis/redis', 'github.com/lib/pq',
    'github.com/go-sql-driver/mysql', 'github.com/jackc/pgx',
})

_SDK_MODULES: frozenset = frozenset({
    'github.com/stripe/stripe-go', 'github.com/aws/aws-sdk-go',
    'github.com/aws/aws-sdk-go-v2', 'cloud.google.com/go',
    'github.com/twilio/twilio-go', 'github.com/slack-go/slack',
    'github.com/Azure/azure-sdk-for-go',
})

_MODULE_TAXONOMY: tuple = (
    (_NET_MODULES, 'network'),
    (_DB_MODULES, 'db'),
    (_SDK_MODULES, 'sdk'),
)

# HTTP-verb selector fields → normalised method. Both the upper-case forms
# (Gin/Echo) and the title-case forms (Chi/gorilla) are listed explicitly
# rather than upper-casing the field, so an unrelated method whose name only
# differs in case can't sneak in; lower-case verbs are intentionally absent
# (Go's exported router methods are always capitalised).
_HTTP_VERB_FIELDS: Dict[str, str] = {
    'GET': 'GET', 'POST': 'POST', 'PUT': 'PUT', 'DELETE': 'DELETE',
    'PATCH': 'PATCH', 'HEAD': 'HEAD', 'OPTIONS': 'OPTIONS', 'Any': 'ANY',
    'Get': 'GET', 'Post': 'POST', 'Put': 'PUT', 'Delete': 'DELETE',
    'Patch': 'PATCH', 'Head': 'HEAD', 'Options': 'OPTIONS',
}

# Router registration methods that carry an explicit verb elsewhere (or match
# any) — recorded as method ANY. Same leading-`/` first-arg guard applies.
_HTTP_HANDLER_FIELDS: frozenset = frozenset({'HandleFunc', 'Handle'})

_ENV_READ_METHODS: frozenset = frozenset({'Getenv', 'LookupEnv'})

# os./ioutil. filesystem-write functions (write-capable opens included).
_FS_WRITE: Dict[str, frozenset] = {
    'os': frozenset({'WriteFile', 'Create', 'OpenFile', 'Mkdir', 'MkdirAll'}),
    'ioutil': frozenset({'WriteFile'}),
}

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')


def scan_file_surface_go(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Go file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('go')
        tree = ts_parse(parser, source)
    except Exception:
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    is_main_package = _package_name(tree, content_bytes) == 'main'

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = node.kind()

        if kind == 'import_spec':
            _process_import(node, file_path, content_bytes, surfaces)
        elif kind == 'function_declaration' and is_main_package:
            _process_function(node, file_path, content_bytes, surfaces)
        elif kind == 'call_expression':
            _process_call(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


def _package_name(tree: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(tree_root(tree)):
        if ch.kind() == 'package_clause':
            for c in _children(ch):
                if c.kind() == 'package_identifier':
                    return _get_text(c, content_bytes)
    return None


def _string_literal_text(node: Any, content_bytes: bytes) -> str:
    """Text of an interpreted_string_literal, stripping the surrounding quotes."""
    for ch in _children(node):
        if ch.kind() == 'interpreted_string_literal_content':
            return _get_text(ch, content_bytes)
    return _get_text(node, content_bytes).strip('"`')


def _process_import(node: Any, file_path: str, content_bytes: bytes,
                    surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for ch in _children(node):
        if ch.kind() == 'interpreted_string_literal':
            module = _string_literal_text(ch, content_bytes)
            _categorize_module(module, file_path, _get_line(node), surfaces)
            return


def _categorize_module(module: str, file_path: str, line: int,
                       surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for modules, category in _MODULE_TAXONOMY:
        for prefix in modules:
            if module == prefix or module.startswith(prefix + '/'):
                entry = {'type': 'import', 'name': module, 'file': file_path, 'line': line}
                _add_once(surfaces[category], entry)
                return


def _function_name(node: Any, content_bytes: bytes) -> Optional[str]:
    """Name of a function_declaration (its direct ``identifier`` child)."""
    for ch in _children(node):
        if ch.kind() == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _process_function(node: Any, file_path: str, content_bytes: bytes,
                      surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    if _function_name(node, content_bytes) == 'main':
        surfaces['cli'].append({
            'type': 'main', 'name': 'main', 'file': file_path, 'line': _get_line(node),
        })


def _selector_parts(node: Any, content_bytes: bytes):
    """(receiver_text, field) for a selector_expression, or (None, None).

    The receiver is the selector's first child (an identifier for the common
    ``os.Getenv``/``r.GET`` case; a nested expression for a chained call, whose
    text is returned as-is). The field is the trailing ``field_identifier``.
    """
    if node.kind() != 'selector_expression':
        return None, None
    kids = _children(node)
    if not kids:
        return None, None
    field = None
    for ch in kids:
        if ch.kind() == 'field_identifier':
            field = _get_text(ch, content_bytes)
    receiver = _get_text(kids[0], content_bytes)
    return receiver, field


def _first_string_arg(call_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(call_node):
        if ch.kind() != 'argument_list':
            continue
        for arg in _children(ch):
            if arg.kind() == 'interpreted_string_literal':
                return _string_literal_text(arg, content_bytes)
    return None


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                  surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    selector = next((c for c in _children(node) if c.kind() == 'selector_expression'), None)
    if selector is None:
        return
    receiver, field = _selector_parts(selector, content_bytes)
    if field is None:
        return
    line = _get_line(node)

    # env reads: os.Getenv / os.LookupEnv
    if receiver == 'os' and field in _ENV_READ_METHODS:
        key = _first_string_arg(node, content_bytes)
        if key:
            surfaces['env'].append({
                'type': 'env_var', 'name': key, 'expr': f'os.{field}',
                'file': file_path, 'line': line,
            })
        return

    # filesystem writes: os./ioutil. write functions
    if receiver in _FS_WRITE and field in _FS_WRITE[receiver]:
        surfaces['fs'].append({
            'type': 'fs_write', 'name': f'{receiver}.{field}',
            'file': file_path, 'line': line,
        })
        return

    # HTTP routes — verb (Gin/Echo/Chi) or HandleFunc/Handle (net/http, mux).
    # Leading-`/` first-arg guard keeps title-case verbs off ordinary getters.
    is_verb = field in _HTTP_VERB_FIELDS
    is_handler = field in _HTTP_HANDLER_FIELDS
    if is_verb or is_handler:
        path_arg = _first_string_arg(node, content_bytes)
        if path_arg and path_arg.startswith('/'):
            surfaces['http'].append({
                'type': 'route',
                'name': receiver or '?',
                'path': path_arg,
                'methods': _HTTP_VERB_FIELDS[field] if is_verb else 'ANY',
                'decorator': f'.{field}()',
                'file': file_path,
                'line': line,
            })
