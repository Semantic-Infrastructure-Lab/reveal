"""Tree-sitter surface extraction for Swift — env vars, HTTP routes, CLI, imports.

BACK-403 pt 2 (surface breadth). Mirrors nav_surface_java.py's categorised-dict
shape but walks Swift's grammar:

- **Vapor** routes: ``app.get("users", ":id") { req in ... }`` — a
  ``call_expression`` whose callee is a ``navigation_expression`` ending in an
  HTTP-verb method and whose ``call_suffix`` carries a trailing
  ``lambda_literal`` (the route handler). The trailing closure is the
  discriminator that separates a route registration from an ordinary ``.get``
  member call, and multiple string path segments are joined with ``/``.
- **CLI entrypoint**: the ``@main`` attribute on a type declaration.
- **env**: Vapor's ``Environment.get("KEY")`` and
  ``ProcessInfo.processInfo.environment["KEY"]``.
- **network/db/sdk**: ``import`` module-name taxonomy. ``Foundation`` (which
  contains ``URLSession``) is deliberately *not* classed as network — it is
  imported almost everywhere and would flood the read; only dedicated HTTP/DB/
  SDK modules are tracked, the same curated approach as the other scanners.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.core import node_children as _children

_NET_MODULES: frozenset = frozenset({
    'Alamofire', 'Moya', 'AsyncHTTPClient', 'NIOHTTP1', 'NIOHTTP2',
})

_DB_MODULES: frozenset = frozenset({
    'GRDB', 'SQLite', 'RealmSwift', 'MongoKitten', 'Fluent', 'FluentKit',
    'PostgresKit', 'MySQLKit', 'PostgresNIO',
})

_SDK_MODULES: frozenset = frozenset({
    'Stripe', 'StripeKit', 'Soto', 'AWSSDKSwift', 'FirebaseCore',
    'FirebaseFirestore', 'FirebaseAuth', 'Sentry',
})

_VAPOR_ROUTE_VERBS: Dict[str, str] = {
    'get': 'GET',
    'post': 'POST',
    'put': 'PUT',
    'patch': 'PATCH',
    'delete': 'DELETE',
}

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')


def scan_file_surface_swift(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Swift file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('swift')
        tree = parser.parse(source)
    except Exception:
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _get_text(node, content_bytes: bytes) -> str:
    return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')


def _get_line(node) -> int:
    return node.start_position().row + 1


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}

    stack = [tree.root_node()]
    while stack:
        node = stack.pop()
        kind = node.kind()

        if kind == 'import_declaration':
            _process_import(node, file_path, content_bytes, surfaces)
        elif kind == 'call_expression':
            _process_call(node, file_path, content_bytes, surfaces)
        elif kind == 'attribute':
            _process_attribute(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


_MODULE_TAXONOMY: tuple = (
    (_NET_MODULES, 'network'),
    (_DB_MODULES, 'db'),
    (_SDK_MODULES, 'sdk'),
)


def _process_import(node: Any, file_path: str, content_bytes: bytes,
                    surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for ch in _children(node):
        if ch.kind() == 'identifier':
            module = _get_text(ch, content_bytes)
            _categorize_module(module, file_path, _get_line(node), surfaces)
            return


def _categorize_module(module: str, file_path: str, line: int,
                       surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    # Swift imports may be submodule-qualified (e.g. `import Firebase.Firestore`);
    # match on the first (top-level module) segment.
    top = module.split('.')[0]
    for modules, category in _MODULE_TAXONOMY:
        if top in modules:
            entry = {'type': 'import', 'name': module, 'file': file_path, 'line': line}
            _add_once(surfaces[category], entry)
            return


def _string_literal_text(node: Any, content_bytes: bytes) -> str:
    for ch in _children(node):
        if ch.kind() == 'line_str_text':
            return _get_text(ch, content_bytes)
    return _get_text(node, content_bytes).strip('"')


def _navigation_receiver_and_method(nav_node: Any, content_bytes: bytes) -> tuple:
    """(receiver_text, method_name) for a navigation_expression `X.method`."""
    children = _children(nav_node)
    if len(children) < 2:
        return None, None
    receiver = children[0]
    suffix = children[-1]
    if suffix.kind() != 'navigation_suffix':
        return None, None
    method = None
    for ch in _children(suffix):
        if ch.kind() == 'simple_identifier':
            method = _get_text(ch, content_bytes)
    return _get_text(receiver, content_bytes), method


def _call_suffix(node: Any) -> Optional[Any]:
    for ch in _children(node):
        if ch.kind() == 'call_suffix':
            return ch
    return None


def _has_trailing_lambda(call_suffix_node: Any) -> bool:
    return any(c.kind() == 'lambda_literal' for c in _children(call_suffix_node))


def _value_arguments(call_suffix_node: Any) -> Optional[Any]:
    for ch in _children(call_suffix_node):
        if ch.kind() == 'value_arguments':
            return ch
    return None


def _arg_string_texts(value_arguments_node: Any, content_bytes: bytes) -> List[str]:
    out: List[str] = []
    for arg in _children(value_arguments_node):
        if arg.kind() != 'value_argument':
            continue
        for sub in _children(arg):
            if sub.kind() == 'line_string_literal':
                out.append(_string_literal_text(sub, content_bytes))
    return out


def _is_subscript(value_arguments_node: Any) -> bool:
    # A subscript `x["k"]` parses to a value_arguments whose bracket token is '['.
    for ch in _children(value_arguments_node):
        if ch.kind() == '[':
            return True
        if ch.kind() == '(':
            return False
    return False


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                  surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    children = _children(node)
    if not children or children[0].kind() != 'navigation_expression':
        return
    receiver, method = _navigation_receiver_and_method(children[0], content_bytes)
    if method is None:
        return
    suffix = _call_suffix(node)
    if suffix is None:
        return
    line = _get_line(node)

    # Vapor route: verb method + trailing handler closure.
    if method in _VAPOR_ROUTE_VERBS and _has_trailing_lambda(suffix):
        vargs = _value_arguments(suffix)
        segments = _arg_string_texts(vargs, content_bytes) if vargs else []
        path = '/' + '/'.join(s.strip('/') for s in segments) if segments else '/'
        surfaces['http'].append({
            'type': 'route', 'name': method, 'path': path,
            'methods': _VAPOR_ROUTE_VERBS[method], 'decorator': f'{receiver}.{method}',
            'file': file_path, 'line': line,
        })
        return

    # env: Environment.get("KEY")
    if receiver == 'Environment' and method == 'get':
        vargs = _value_arguments(suffix)
        keys = _arg_string_texts(vargs, content_bytes) if vargs else []
        if keys:
            surfaces['env'].append({
                'type': 'env_var', 'name': keys[0], 'expr': 'Environment.get',
                'file': file_path, 'line': line,
            })
        return

    # env: ProcessInfo.processInfo.environment["KEY"]  (subscript on .environment)
    if method == 'environment':
        vargs = _value_arguments(suffix)
        if vargs is not None and _is_subscript(vargs):
            keys = _arg_string_texts(vargs, content_bytes)
            if keys:
                surfaces['env'].append({
                    'type': 'env_var', 'name': keys[0], 'expr': 'ProcessInfo.environment',
                    'file': file_path, 'line': line,
                })


def _process_attribute(node: Any, file_path: str, content_bytes: bytes,
                       surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    # @main entrypoint attribute — user_type child named 'main'.
    for ch in _children(node):
        if ch.kind() == 'user_type' and _get_text(ch, content_bytes) == 'main':
            surfaces['cli'].append({
                'type': 'main', 'name': '@main', 'file': file_path, 'line': _get_line(node),
            })
            return


def _add_once(lst: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    key = (entry.get('name', ''), entry.get('file', ''), entry.get('line', 0))
    for existing in lst:
        if (existing.get('name', ''), existing.get('file', ''), existing.get('line', 0)) == key:
            return
    lst.append(entry)
