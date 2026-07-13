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

network/db/sdk egress: ``use`` import-root taxonomy (PHP namespaces use ``\``
separators). PHP builtins (PDO/mysqli/curl) are language constructs, not ``use``
imports, so — as with the other curated-taxonomy scanners — they are not tracked.

No CLI entrypoint category: PHP CLI scripts have no standard ``main`` node
(execution starts at top-of-file), so surfacing one honestly is N/A.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once

from reveal.core import node_children as _children

# PHP namespaces use '\' separators, so taxonomy prefixes are matched against
# the raw dotted-with-backslash `use` target text.
_NET_PACKAGES: frozenset = frozenset({
    'GuzzleHttp', 'Symfony\\Component\\HttpClient', 'Symfony\\Contracts\\HttpClient',
    'Http\\Client', 'GuzzleHttp\\Client',
})

_DB_PACKAGES: frozenset = frozenset({
    'Doctrine\\ORM', 'Doctrine\\DBAL', 'Illuminate\\Database', 'Predis',
})

_SDK_PACKAGES: frozenset = frozenset({
    'Stripe', 'Twilio', 'Aws', 'Google\\Cloud', 'SendGrid', 'Mailgun',
})

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

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')


def scan_file_surface_php(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one PHP file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('php')
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

        if kind == 'namespace_use_declaration':
            _process_use(node, file_path, content_bytes, surfaces)
        elif kind == 'scoped_call_expression':
            _process_scoped_call(node, file_path, content_bytes, surfaces)
        elif kind == 'function_call_expression':
            _process_function_call(node, file_path, content_bytes, surfaces)
        elif kind == 'attribute':
            _process_attribute(node, file_path, content_bytes, surfaces)
        elif kind == 'subscript_expression':
            _process_subscript(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


_PACKAGE_TAXONOMY: tuple = (
    (_NET_PACKAGES, 'network'),
    (_DB_PACKAGES, 'db'),
    (_SDK_PACKAGES, 'sdk'),
)


def _process_use(node: Any, file_path: str, content_bytes: bytes,
                 surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for clause in _children(node):
        if clause.kind() != 'namespace_use_clause':
            continue
        for ch in _children(clause):
            if ch.kind() in ('qualified_name', 'name'):
                module = _get_text(ch, content_bytes)
                _categorize_module(module, file_path, _get_line(node), surfaces)


def _categorize_module(module: str, file_path: str, line: int,
                       surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for packages, category in _PACKAGE_TAXONOMY:
        for prefix in packages:
            if module == prefix or module.startswith(prefix + '\\'):
                entry = {'type': 'import', 'name': module, 'file': file_path, 'line': line}
                _add_once(surfaces[category], entry)
                return


def _string_arg_texts(arguments_node: Any, content_bytes: bytes) -> List[str]:
    """Ordered string-literal texts among an `arguments` node's direct args."""
    out: List[str] = []
    for arg in _children(arguments_node):
        if arg.kind() != 'argument':
            continue
        for sub in _children(arg):
            if sub.kind() == 'string':
                out.append(_string_content(sub, content_bytes))
    return out


def _string_content(string_node: Any, content_bytes: bytes) -> str:
    for ch in _children(string_node):
        if ch.kind() == 'string_content':
            return _get_text(ch, content_bytes)
    return _get_text(string_node, content_bytes).strip('"\'')


def _scoped_call_names(node: Any, content_bytes: bytes) -> tuple:
    """(receiver, method) for a scoped_call_expression `Receiver::method(...)`."""
    names = [c for c in _children(node) if c.kind() == 'name']
    if len(names) < 2:
        return None, None
    return _get_text(names[0], content_bytes), _get_text(names[1], content_bytes)


def _arguments_child(node: Any) -> Optional[Any]:
    for ch in _children(node):
        if ch.kind() == 'arguments':
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


def _process_function_call(node: Any, file_path: str, content_bytes: bytes,
                           surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    name_node = None
    for ch in _children(node):
        if ch.kind() == 'name':
            name_node = ch
            break
    if name_node is None:
        return
    fname = _get_text(name_node, content_bytes)
    args = _arguments_child(node)
    strings = _string_arg_texts(args, content_bytes) if args else []

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
        if ch.kind() == 'name':
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
        if arg.kind() != 'argument':
            continue
        arg_children = _children(arg)
        # named arg `methods: [...]` carries a leading `name` child
        named = next((c for c in arg_children if c.kind() == 'name'), None)
        if named is not None and _get_text(named, content_bytes) == 'methods':
            verbs = _array_string_texts(arg, content_bytes)
            if verbs:
                methods = '|'.join(v.upper() for v in verbs)
        elif path is None:
            for sub in arg_children:
                if sub.kind() == 'string':
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
        if n.kind() == 'string':
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
    var = next((c for c in children if c.kind() == 'variable_name'), None)
    if var is None or _get_text(var, content_bytes) != '$_ENV':
        return
    key = next((c for c in children if c.kind() == 'string'), None)
    if key is None:
        return
    surfaces['env'].append({
        'type': 'env_var', 'name': _string_content(key, content_bytes), 'expr': '$_ENV',
        'file': file_path, 'line': _get_line(node),
    })
