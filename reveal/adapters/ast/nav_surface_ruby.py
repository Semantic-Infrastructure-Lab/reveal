"""Tree-sitter surface extraction for Ruby — env vars, HTTP routes, requires.

BACK-403 pt 2 (surface breadth). Mirrors nav_surface_php.py's categorised-dict
shape but walks Ruby's grammar for the two dominant web frameworks:

- **Sinatra** routes: ``get '/path' do ... end`` — a bare ``call`` node (no
  receiver — implicit self) whose ``identifier`` is an HTTP verb, whose first
  ``argument_list`` entry is a string starting with ``/``, and which carries a
  ``do_block`` child.
- **Rails** routes: ``get '/health', to: 'health#index'`` inside a
  ``routes.draw do ... end`` block — same bare-``call``-with-HTTP-verb shape,
  but without the ``do_block`` (the route line is itself one statement inside
  the enclosing draw block). Because Ruby's bare method-call shape is
  otherwise indistinguishable from any zero-receiver method named ``get``/
  ``post``/etc., the leading-``/`` string-literal check is load-bearing here —
  it is what keeps this from firing on an arbitrary local ``get(key)`` helper.
  ``resources :posts`` (which fans out into many CRUD routes with no explicit
  path) is deliberately not tracked, matching how the PHP scanner declines
  Laravel's ``Route::resource``/``match`` for the same "wrong path if
  surfaced" reason.

env access: ``ENV['KEY']`` (``element_reference`` on the ``ENV`` constant) and
``ENV.fetch('KEY')`` (a ``call`` on the ``ENV`` constant).

network/db/sdk egress: ``require``/``require_relative`` taxonomy of common
gems. Ruby's stdlib HTTP client (``net/http``) ships as a require, unlike
PHP's curl/PDO which are language constructs — so it's tracked here.

No CLI entrypoint category: like PHP, Ruby scripts have no standard ``main``
node (execution starts at top-of-file), so surfacing one honestly is N/A.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once

from reveal.core import node_children as _children

_NET_GEMS: frozenset = frozenset({
    'net/http', 'faraday', 'httparty', 'excon', 'typhoeus', 'rest-client',
})

_DB_GEMS: frozenset = frozenset({
    'active_record', 'activerecord', 'sequel', 'mongo', 'mongoid', 'redis',
    'pg', 'mysql2', 'sqlite3',
})

_SDK_GEMS: frozenset = frozenset({
    'aws-sdk', 'stripe', 'twilio-ruby', 'google/cloud', 'sendgrid-ruby', 'mailgun-ruby',
})

# Sinatra/Rails DSL verbs → HTTP method. 'resources'/'resource' are excluded:
# they fan out into many routes with no single explicit path, so surfacing
# them here would report a wrong (or nonexistent) path — same reasoning as
# PHP's Route::resource/match exclusion.
_ROUTE_VERBS: Dict[str, str] = {
    'get': 'GET',
    'post': 'POST',
    'put': 'PUT',
    'patch': 'PATCH',
    'delete': 'DELETE',
    'options': 'OPTIONS',
}

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')

_PACKAGE_TAXONOMY: tuple = (
    (_NET_GEMS, 'network'),
    (_DB_GEMS, 'db'),
    (_SDK_GEMS, 'sdk'),
)


def scan_file_surface_ruby(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Ruby file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('ruby')
        tree = parser.parse(source)
    except Exception:
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}

    stack = [tree.root_node()]
    while stack:
        node = stack.pop()
        kind = node.kind()

        if kind == 'call':
            _process_call(node, file_path, content_bytes, surfaces)
        elif kind == 'element_reference':
            _process_element_reference(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


def _string_content(string_node: Any, content_bytes: bytes) -> str:
    for ch in _children(string_node):
        if ch.kind() == 'string_content':
            return _get_text(ch, content_bytes)
    return _get_text(string_node, content_bytes).strip('"\'')


def _string_arg_texts(arg_list: Any, content_bytes: bytes) -> List[str]:
    """Ordered string-literal texts among an `argument_list`'s direct args."""
    out: List[str] = []
    for arg in _children(arg_list):
        if arg.kind() == 'string':
            out.append(_string_content(arg, content_bytes))
    return out


def _arg_list_child(node: Any) -> Optional[Any]:
    for ch in _children(node):
        if ch.kind() == 'argument_list':
            return ch
    return None


def _pair_string_value(arg_list: Any, key: str, content_bytes: bytes) -> Optional[str]:
    """Find `key: 'value'` among an argument_list's `pair` children."""
    for arg in _children(arg_list):
        if arg.kind() != 'pair':
            continue
        children = _children(arg)
        key_node = next((c for c in children if c.kind() in ('hash_key_symbol', 'simple_symbol')), None)
        if key_node is None:
            continue
        key_text = _get_text(key_node, content_bytes).lstrip(':')
        if key_text != key:
            continue
        value_node = next((c for c in children if c.kind() == 'string'), None)
        if value_node is not None:
            return _string_content(value_node, content_bytes)
    return None


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                   surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    children = _children(node)
    ident = next((c for c in children if c.kind() == 'identifier'), None)
    if ident is None:
        return
    name = _get_text(ident, content_bytes)

    # A receiver call (`obj.method(...)`) carries a literal `.` token child
    # between the receiver and the method identifier; a bare call (implicit
    # self, e.g. top-level DSL invocations like `get '/x' do ... end`) does
    # not. Checking child kinds directly (not `children[0] is ident`) matters
    # because a receiver can itself be an `identifier` (e.g. `http.get(url)`).
    has_receiver = any(c.kind() == '.' for c in children)

    if name in ('require', 'require_relative') and not has_receiver:
        args = _arg_list_child(node)
        strings = _string_arg_texts(args, content_bytes) if args else []
        if strings:
            _categorize_gem(strings[0], file_path, _get_line(node), surfaces)
        return

    if name == 'fetch' and children and children[0].kind() == 'constant' and \
            _get_text(children[0], content_bytes) == 'ENV':
        args = _arg_list_child(node)
        strings = _string_arg_texts(args, content_bytes) if args else []
        if strings:
            surfaces['env'].append({
                'type': 'env_var', 'name': strings[0], 'expr': 'ENV.fetch',
                'file': file_path, 'line': _get_line(node),
            })
        return

    if name in _ROUTE_VERBS and not has_receiver:
        args = _arg_list_child(node)
        strings = _string_arg_texts(args, content_bytes) if args else []
        if not strings or not strings[0].startswith('/'):
            return
        to = _pair_string_value(args, 'to', content_bytes) if args else None
        surfaces['http'].append({
            'type': 'route', 'name': name, 'path': strings[0],
            'methods': _ROUTE_VERBS[name], 'decorator': name,
            'target': to, 'file': file_path, 'line': _get_line(node),
        })


def _categorize_gem(name: str, file_path: str, line: int,
                     surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for packages, category in _PACKAGE_TAXONOMY:
        for prefix in packages:
            if name == prefix or name.startswith(prefix + '/') or name.startswith(prefix + '-'):
                entry = {'type': 'import', 'name': name, 'file': file_path, 'line': line}
                _add_once(surfaces[category], entry)
                return


def _process_element_reference(node: Any, file_path: str, content_bytes: bytes,
                                surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    # ENV['KEY'] — element_reference with a leading ENV constant and a string index.
    children = _children(node)
    if not children or children[0].kind() != 'constant' or \
            _get_text(children[0], content_bytes) != 'ENV':
        return
    key = next((c for c in children if c.kind() == 'string'), None)
    if key is None:
        return
    surfaces['env'].append({
        'type': 'env_var', 'name': _string_content(key, content_bytes), 'expr': 'ENV',
        'file': file_path, 'line': _get_line(node),
    })
