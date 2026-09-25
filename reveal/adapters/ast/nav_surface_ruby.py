"""Tree-sitter surface extraction for Ruby — env vars, HTTP routes, requires.

BACK-403 pt 2 (surface breadth). Mirrors nav_surface_php.py's categorised-dict
shape but walks Ruby's grammar for the two dominant web frameworks:

- **Sinatra** routes: ``get '/path' do ... end`` — a bare ``call`` node (no
  receiver — implicit self) whose ``identifier`` is an HTTP verb, whose first
  ``argument_list`` entry is a string starting with ``/``, and which carries a
  ``do_block`` child.
- **Rails** routes: a ``routes.draw do ... end`` block is interpreted as the
  routing DSL it is (``nav_surface_rails.py``, BACK-1417) -- ``resources``,
  ``namespace``/``scope``, ``member``/``collection``, nesting, literal loops.
  Outside a draw block, Ruby's bare method-call shape is otherwise
  indistinguishable from any zero-receiver method named ``get``/``post``/etc.,
  so the leading-``/`` string-literal check is load-bearing for Sinatra --
  it is what keeps this from firing on an arbitrary local ``get(key)`` helper.

env access: ``ENV['KEY']`` (``element_reference`` on the ``ENV`` constant) and
``ENV.fetch('KEY')`` (a ``call`` on the ``ENV`` constant).

network/db/sdk egress: ``require``/``require_relative`` of common gems, matched by
the ``Import`` rule tables in ``surface_rules_imports.py`` (BACK-1334 b). Ruby's
stdlib HTTP client (``net/http``) ships as a require, unlike PHP's curl/PDO which
are language constructs — so it's tracked there.

No CLI entrypoint category: like PHP, Ruby scripts have no standard ``main``
node (execution starts at top-of-file), so surfacing one honestly is N/A.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import disclose_parse_recovery, _get_text, _get_line
from .nav_surface_rails import is_route_block, scan_route_block
from .surface_rules import RuleScan

logger = logging.getLogger(__name__)

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

# Sinatra DSL verbs → HTTP method (Rails draw blocks: nav_surface_rails.py).
_ROUTE_VERBS: Dict[str, str] = {
    'get': 'GET',
    'post': 'POST',
    'put': 'PUT',
    'patch': 'PATCH',
    'delete': 'DELETE',
    'options': 'OPTIONS',
}

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')


def scan_file_surface_ruby(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Ruby file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace', encoding='utf-8')
        parser = get_parser('ruby')
        tree = ts_parse(parser, source)
    except Exception as e:
        logger.warning("surface scan (Ruby) failed to parse %s: %s", file_path, e)
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return disclose_parse_recovery(tree, file_path, _scan_tree(tree, file_path, content_bytes))


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    rules = RuleScan('ruby', content_bytes)
    rule_kinds, visit = rules.kinds, rules.visit

    # Byte ranges of `routes.draw` blocks: the Rails interpreter reports their
    # routes, so a verb call inside one is not read again as a Sinatra route.
    route_blocks: List[tuple] = []

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in rule_kinds:
            visit(node, kind)

        if kind == 'call':
            start = _zero_arg(node, 'start_byte')
            in_routes = any(lo <= start < hi for lo, hi in route_blocks)
            if not in_routes and is_route_block(node, content_bytes):
                surfaces['http'].extend(scan_route_block(node, content_bytes, file_path))
                route_blocks.append((start, _zero_arg(node, 'end_byte')))
                in_routes = True
            _process_call(node, file_path, content_bytes, surfaces, in_routes)
        elif kind == 'element_reference':
            _process_element_reference(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    rules.apply(surfaces, file_path)
    return surfaces


def _string_content(string_node: Any, content_bytes: bytes) -> str:
    for ch in _children(string_node):
        if _zero_arg(ch, 'kind') == 'string_content':
            return _get_text(ch, content_bytes)
    return _get_text(string_node, content_bytes).strip('"\'')


def _string_arg_texts(arg_list: Any, content_bytes: bytes) -> List[str]:
    """Ordered string-literal texts among an `argument_list`'s direct args."""
    out: List[str] = []
    for arg in _children(arg_list):
        if _zero_arg(arg, 'kind') == 'string':
            out.append(_string_content(arg, content_bytes))
    return out


def _arg_list_child(node: Any) -> Optional[Any]:
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'argument_list':
            return ch
    return None


def _pair_string_value(arg_list: Any, key: str, content_bytes: bytes) -> Optional[str]:
    """Find `key: 'value'` among an argument_list's `pair` children."""
    for arg in _children(arg_list):
        if _zero_arg(arg, 'kind') != 'pair':
            continue
        children = _children(arg)
        key_node = next((c for c in children if _zero_arg(c, 'kind') in ('hash_key_symbol', 'simple_symbol')), None)
        if key_node is None:
            continue
        key_text = _get_text(key_node, content_bytes).lstrip(':')
        if key_text != key:
            continue
        value_node = next((c for c in children if _zero_arg(c, 'kind') == 'string'), None)
        if value_node is not None:
            return _string_content(value_node, content_bytes)
    return None


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                  surfaces: Dict[str, List[Dict[str, Any]]], in_routes: bool = False) -> None:
    children = _children(node)
    ident = next((c for c in children if _zero_arg(c, 'kind') == 'identifier'), None)
    if ident is None:
        return
    name = _get_text(ident, content_bytes)

    # A receiver call (`obj.method(...)`) carries a literal `.` token child
    # between the receiver and the method identifier; a bare call (implicit
    # self, e.g. top-level DSL invocations like `get '/x' do ... end`) does
    # not. Checking child kinds directly (not `children[0] is ident`) matters
    # because a receiver can itself be an `identifier` (e.g. `http.get(url)`).
    has_receiver = any(_zero_arg(c, 'kind') == '.' for c in children)

    if name == 'fetch' and children and _zero_arg(children[0], 'kind') == 'constant' and \
            _get_text(children[0], content_bytes) == 'ENV':
        args = _arg_list_child(node)
        strings = _string_arg_texts(args, content_bytes) if args else []
        if strings:
            surfaces['env'].append({
                'type': 'env_var', 'name': strings[0], 'expr': 'ENV.fetch',
                'file': file_path, 'line': _get_line(node),
            })
        return

    if name in _ROUTE_VERBS and not has_receiver and not in_routes:
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


def _process_element_reference(node: Any, file_path: str, content_bytes: bytes,
                                surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    # ENV['KEY'] — element_reference with a leading ENV constant and a string index.
    children = _children(node)
    if not children or _zero_arg(children[0], 'kind') != 'constant' or \
            _get_text(children[0], content_bytes) != 'ENV':
        return
    key = next((c for c in children if _zero_arg(c, 'kind') == 'string'), None)
    if key is None:
        return
    surfaces['env'].append({
        'type': 'env_var', 'name': _string_content(key, content_bytes), 'expr': 'ENV',
        'file': file_path, 'line': _get_line(node),
    })
