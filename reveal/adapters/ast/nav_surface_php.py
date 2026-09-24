"""Tree-sitter surface extraction for PHP — env vars, HTTP routes, imports.

BACK-403 pt 2 (surface breadth). Mirrors nav_surface_java.py's categorised-dict
shape but walks PHP's grammar for the three dominant web frameworks:

- **Laravel** routes: ``Route::get('/path', ...)`` — a ``scoped_call_expression``
  whose receiver ``name`` is ``Route`` and whose method ``name`` is an HTTP verb.
- **Symfony** routes: the ``#[Route('/path', methods: ['GET'])]`` attribute — an
  ``attribute`` node (inside ``attribute_group``/``attribute_list``) named
  ``Route`` on a class or method.
- **WordPress** REST routes: ``register_rest_route('ns/v1', '/data', ...)`` — a
  bare ``function_call_expression``.

env access: ``getenv('KEY')`` and the ``$_ENV['KEY']`` superglobal (``$_SERVER``
is deliberately excluded — it is a request superglobal, not env config, and
folding it in floods the read with request-header noise).

network/db/sdk egress is rule-driven (BACK-1334 c) through this walk's
``RuleScan``: ``use`` import roots (``surface_rules_imports.py``) and the I/O
builtins (curl/PDO/mysqli, URL ``fopen``; ``surface_rules_php_builtins.py``).
The subprocess and file-write builtins (exec/file_put_contents) are still matched
here by exact name against curated tables (BACK-1090).

No CLI entrypoint category: PHP CLI scripts have no standard ``main`` node
(execution starts at top-of-file), so surfacing one honestly is N/A.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once
from .surface_rules import RuleScan

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

logger = logging.getLogger(__name__)

# Laravel Route facade verbs → HTTP method. 'match'/'resource' are excluded:
# their path isn't the first string arg (match's first arg is a verb array),
# so surfacing them here would report a wrong path.
_LARAVEL_ROUTE_VERBS: Dict[str, str] = {
    'get': 'GET',
    'post': 'POST',
    'put': 'PUT',
    'patch': 'PATCH',
    'delete': 'DELETE',
    'options': 'OPTIONS',
    'any': 'ANY',
}

# PHP builtins (BACK-1090): PHP I/O is global functions, not imports. Curated,
# exact-name tables; a call is recorded only for the names below. The network
# and database builtins are rule rows (surface_rules_php_builtins.py).
_SUBPROCESS_FUNCS: frozenset = frozenset({
    'exec', 'shell_exec', 'system', 'passthru', 'proc_open', 'popen', 'pcntl_exec',
})
_FS_WRITE_FUNCS: frozenset = frozenset({'file_put_contents', 'move_uploaded_file'})
# fopen() takes a URL or a path: a URL is network (a rule row), never a file write.
_URL_SCHEMES: tuple = ('http://', 'https://', 'ftp://')

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')


def scan_file_surface_php(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one PHP file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace', encoding='utf-8')
        parser = get_parser('php')
        tree = ts_parse(parser, source)
    except Exception as e:
        logger.warning("surface scan (PHP) failed to parse %s: %s", file_path, e)
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    rules = RuleScan('php', content_bytes)
    rule_kinds, visit = rules.kinds, rules.visit

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in rule_kinds:
            visit(node, kind)

        if kind == 'scoped_call_expression':
            _process_scoped_call(node, file_path, content_bytes, surfaces)
        elif kind == 'function_call_expression':
            _process_function_call(node, file_path, content_bytes, surfaces)
        elif kind == 'shell_command_expression':
            _add_once(surfaces['subprocess'], {
                'type': 'subprocess', 'name': '`...`',
                'file': file_path, 'line': _get_line(node),
            })
        elif kind == 'attribute':
            _process_attribute(node, file_path, content_bytes, surfaces)
        elif kind == 'subscript_expression':
            _process_subscript(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    rules.apply(surfaces, file_path)
    return surfaces


def _string_arg_texts(arguments_node: Any, content_bytes: bytes) -> List[str]:
    """Ordered string-literal texts among an `arguments` node's direct args."""
    out: List[str] = []
    for arg in _children(arguments_node):
        if _zero_arg(arg, 'kind') != 'argument':
            continue
        for sub in _children(arg):
            if _zero_arg(sub, 'kind') == 'string':
                out.append(_string_content(sub, content_bytes))
    return out


def _string_content(string_node: Any, content_bytes: bytes) -> str:
    for ch in _children(string_node):
        if _zero_arg(ch, 'kind') == 'string_content':
            return _get_text(ch, content_bytes)
    return _get_text(string_node, content_bytes).strip('"\'')


def _scoped_call_names(node: Any, content_bytes: bytes) -> tuple:
    """(receiver, method) for a scoped_call_expression `Receiver::method(...)`."""
    names = [c for c in _children(node) if _zero_arg(c, 'kind') == 'name']
    if len(names) < 2:
        return None, None
    return _get_text(names[0], content_bytes), _get_text(names[1], content_bytes)


def _arguments_child(node: Any) -> Optional[Any]:
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'arguments':
            return ch
    return None


def _process_scoped_call(node: Any, file_path: str, content_bytes: bytes,
                         surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    receiver, method = _scoped_call_names(node, content_bytes)
    if receiver != 'Route' or method not in _LARAVEL_ROUTE_VERBS:
        return
    args = _arguments_child(node)
    strings = _string_arg_texts(args, content_bytes) if args else []
    surfaces['http'].append({
        'type': 'route',
        'name': method,
        'path': strings[0] if strings else '?',
        'methods': _LARAVEL_ROUTE_VERBS[method],
        'decorator': f'Route::{method}',
        'file': file_path,
        'line': _get_line(node),
    })


def _record_builtin_call(fname: str, strings: List[str], node: Any, file_path: str,
                         surfaces: Dict[str, List[Dict[str, Any]]]) -> bool:
    """Classify a call to a PHP subprocess / file-write builtin (BACK-1090). True when
    recorded. Network and database builtins are rule rows."""
    line = _get_line(node)
    if fname in _SUBPROCESS_FUNCS:
        category, kind = 'subprocess', 'subprocess'
    elif fname in _FS_WRITE_FUNCS:
        category, kind = 'fs', 'fs_write'
    elif fname == 'fopen':
        # Only write/append/create modes are a write; a URL is network egress (a rule row).
        if len(strings) >= 2 and any(m in strings[1] for m in 'wacx') \
                and not strings[0].startswith(('php://', *_URL_SCHEMES)):
            category, kind = 'fs', 'fs_write'
        else:
            return False
    else:
        return False
    _add_once(surfaces[category], {'type': kind, 'name': fname, 'file': file_path, 'line': line})
    return True


def _process_function_call(node: Any, file_path: str, content_bytes: bytes,
                           surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    name_node = None
    for ch in _children(node):
        if _zero_arg(ch, 'kind') in ('name', 'qualified_name'):
            name_node = ch
            break
    if name_node is None:
        return
    fname = _get_text(name_node, content_bytes).lstrip('\\')  # `\curl_init()` == `curl_init()`
    args = _arguments_child(node)
    strings = _string_arg_texts(args, content_bytes) if args else []
    if _record_builtin_call(fname, strings, node, file_path, surfaces):
        return

    if fname == 'getenv' and strings:
        surfaces['env'].append({
            'type': 'env_var', 'name': strings[0], 'expr': 'getenv',
            'file': file_path, 'line': _get_line(node),
        })
    elif fname == 'register_rest_route' and strings:
        # register_rest_route('namespace/v1', '/route', ...) — full path is ns + route
        path = '/'.join(s.strip('/') for s in strings[:2]) if len(strings) >= 2 else strings[0]
        surfaces['http'].append({
            'type': 'route', 'name': 'register_rest_route', 'path': '/' + path.lstrip('/'),
            'methods': 'ANY', 'decorator': 'register_rest_route',
            'file': file_path, 'line': _get_line(node),
        })


def _process_attribute(node: Any, file_path: str, content_bytes: bytes,
                       surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    # Symfony #[Route('/path', methods: ['GET'])]
    name_node = None
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'name':
            name_node = ch
            break
    if name_node is None or _get_text(name_node, content_bytes) != 'Route':
        return
    args = _arguments_child(node)
    if args is None:
        return
    path = None
    methods = 'ANY'
    for arg in _children(args):
        if _zero_arg(arg, 'kind') != 'argument':
            continue
        arg_children = _children(arg)
        # named arg `methods: [...]` carries a leading `name` child
        named = next((c for c in arg_children if _zero_arg(c, 'kind') == 'name'), None)
        if named is not None and _get_text(named, content_bytes) == 'methods':
            verbs = _array_string_texts(arg, content_bytes)
            if verbs:
                methods = '|'.join(v.upper() for v in verbs)
        elif path is None:
            for sub in arg_children:
                if _zero_arg(sub, 'kind') == 'string':
                    path = _string_content(sub, content_bytes)
    surfaces['http'].append({
        'type': 'route', 'name': 'Route', 'path': path or '?',
        'methods': methods, 'decorator': '#[Route]',
        'file': file_path, 'line': _get_line(node),
    })


def _array_string_texts(node: Any, content_bytes: bytes) -> List[str]:
    """All string_content texts nested under an array_creation_expression in node,
    in source order."""
    out: List[str] = []

    def _rec(n: Any) -> None:
        if _zero_arg(n, 'kind') == 'string':
            out.append(_string_content(n, content_bytes))
            return
        for c in _children(n):
            _rec(c)

    for child in _children(node):
        _rec(child)
    return out


def _process_subscript(node: Any, file_path: str, content_bytes: bytes,
                       surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    # $_ENV['KEY'] — subscript_expression with a $_ENV variable_name and a string key
    children = _children(node)
    var = next((c for c in children if _zero_arg(c, 'kind') == 'variable_name'), None)
    if var is None or _get_text(var, content_bytes) != '$_ENV':
        return
    key = next((c for c in children if _zero_arg(c, 'kind') == 'string'), None)
    if key is None:
        return
    surfaces['env'].append({
        'type': 'env_var', 'name': _string_content(key, content_bytes), 'expr': '$_ENV',
        'file': file_path, 'line': _get_line(node),
    })
