"""Tree-sitter surface extraction for Kotlin — env vars, HTTP routes, CLI, imports.

BACK-403 pt 2 (surface breadth). Mirrors nav_surface_java.py's categorised-dict
shape but walks Kotlin's grammar for its two dominant web frameworks:

- **Ktor** routes: ``get("/path") { call.respond(...) }`` — a ``call_expression``
  whose callee is a *bare* ``simple_identifier`` HTTP verb (not a member call)
  with a trailing route-handler ``annotated_lambda``. The bare-callee + trailing
  closure pair separates a Ktor route from an ordinary ``list.get(0)`` member
  call.
- **Spring** routes: the same ``@GetMapping``/``@PostMapping``/… annotations as
  Java (Kotlin Spring reuses Spring MVC), parsed from the ``annotation`` node.
- **CLI entrypoint**: a top-level ``fun main`` (Kotlin's entrypoint is a
  top-level function, gated to direct children of the file so a class method
  named ``main`` isn't misclassified).
- **env**: ``System.getenv("KEY")``.
- **network/db/sdk**: ``import`` dotted-root taxonomy. Kotlin runs on the JVM,
  so most of Java's package taxonomy applies, plus Kotlin-native HTTP/DB libs.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once

from reveal.core import node_children as _children

_NET_PACKAGES: frozenset = frozenset({
    'okhttp3', 'retrofit2', 'io.ktor.client', 'java.net.http', 'org.apache.http',
})

_DB_PACKAGES: frozenset = frozenset({
    'java.sql', 'javax.persistence', 'jakarta.persistence', 'org.hibernate',
    'org.jetbrains.exposed', 'com.mongodb', 'org.springframework.data',
    'redis.clients.jedis',
})

_SDK_PACKAGES: frozenset = frozenset({
    'com.stripe', 'com.twilio', 'software.amazon.awssdk', 'com.amazonaws',
    'com.google.cloud', 'com.azure', 'com.slack.api',
})

# Ktor bare-verb route builders → HTTP method.
_KTOR_ROUTE_VERBS: Dict[str, str] = {
    'get': 'GET',
    'post': 'POST',
    'put': 'PUT',
    'patch': 'PATCH',
    'delete': 'DELETE',
    'head': 'HEAD',
    'options': 'OPTIONS',
}

# Spring MVC route annotations (shared with Java Spring) → inferred HTTP method.
_SPRING_ROUTE_ANNOTATIONS: Dict[str, str] = {
    'GetMapping': 'GET',
    'PostMapping': 'POST',
    'PutMapping': 'PUT',
    'DeleteMapping': 'DELETE',
    'PatchMapping': 'PATCH',
    'RequestMapping': 'ANY',
}

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')


def scan_file_surface_kotlin(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Kotlin file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('kotlin')
        tree = parser.parse(source)
    except Exception:
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    root = tree.root_node()

    # CLI entrypoint: a top-level `fun main` (direct child of the file only, so a
    # class method named main isn't misclassified as an entrypoint).
    for child in _children(root):
        if child.kind() == 'function_declaration' and _function_name(child, content_bytes) == 'main':
            surfaces['cli'].append({
                'type': 'main', 'name': 'main', 'file': file_path, 'line': _get_line(child),
            })

    stack = [root]
    while stack:
        node = stack.pop()
        kind = node.kind()

        if kind == 'import_header':
            _process_import(node, file_path, content_bytes, surfaces)
        elif kind == 'call_expression':
            _process_call(node, file_path, content_bytes, surfaces)
        elif kind == 'function_declaration':
            _process_annotations(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


def _function_name(func_node: Any, content_bytes: bytes) -> Optional[str]:
    # A top-level `fun main` has no receiver_type; its name is the simple_identifier.
    for ch in _children(func_node):
        if ch.kind() == 'receiver_type':
            return None  # extension function — not the entrypoint
        if ch.kind() == 'simple_identifier':
            return _get_text(ch, content_bytes)
    return None


_PACKAGE_TAXONOMY: tuple = (
    (_NET_PACKAGES, 'network'),
    (_DB_PACKAGES, 'db'),
    (_SDK_PACKAGES, 'sdk'),
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
    for packages, category in _PACKAGE_TAXONOMY:
        for prefix in packages:
            if module == prefix or module.startswith(prefix + '.'):
                entry = {'type': 'import', 'name': module, 'file': file_path, 'line': line}
                _add_once(surfaces[category], entry)
                return


def _string_content(string_node: Any, content_bytes: bytes) -> str:
    for ch in _children(string_node):
        if ch.kind() == 'string_content':
            return _get_text(ch, content_bytes)
    return _get_text(string_node, content_bytes).strip('"')


def _call_suffix(node: Any) -> Optional[Any]:
    for ch in _children(node):
        if ch.kind() == 'call_suffix':
            return ch
    return None


def _has_annotated_lambda(call_suffix_node: Any) -> bool:
    return any(c.kind() == 'annotated_lambda' for c in _children(call_suffix_node))


def _value_arguments(call_suffix_node: Any) -> Optional[Any]:
    for ch in _children(call_suffix_node):
        if ch.kind() == 'value_arguments':
            return ch
    return None


def _first_string_arg(value_arguments_node: Any, content_bytes: bytes) -> Optional[str]:
    for arg in _children(value_arguments_node):
        if arg.kind() != 'value_argument':
            continue
        for sub in _children(arg):
            if sub.kind() == 'string_literal':
                return _string_content(sub, content_bytes)
    return None


def _navigation_receiver_and_method(nav_node: Any, content_bytes: bytes) -> tuple:
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


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                  surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    children = _children(node)
    if not children:
        return
    callee = children[0]
    suffix = _call_suffix(node)
    if suffix is None:
        return
    line = _get_line(node)

    # Ktor route: bare verb identifier + trailing handler closure.
    if callee.kind() == 'simple_identifier':
        verb = _get_text(callee, content_bytes)
        if verb in _KTOR_ROUTE_VERBS and _has_annotated_lambda(suffix):
            vargs = _value_arguments(suffix)
            path = _first_string_arg(vargs, content_bytes) if vargs else None
            surfaces['http'].append({
                'type': 'route', 'name': verb, 'path': path or '/',
                'methods': _KTOR_ROUTE_VERBS[verb], 'decorator': verb,
                'file': file_path, 'line': line,
            })
        return

    # env: System.getenv("KEY")
    if callee.kind() == 'navigation_expression':
        receiver, method = _navigation_receiver_and_method(callee, content_bytes)
        if receiver == 'System' and method == 'getenv':
            vargs = _value_arguments(suffix)
            key = _first_string_arg(vargs, content_bytes) if vargs else None
            if key:
                surfaces['env'].append({
                    'type': 'env_var', 'name': key, 'expr': 'System.getenv',
                    'file': file_path, 'line': line,
                })


def _process_annotations(node: Any, file_path: str, content_bytes: bytes,
                         surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    name = _plain_function_name(node, content_bytes)
    for annotation in _find_annotations(node):
        anno_name, path = _annotation_name_and_path(annotation, content_bytes)
        if anno_name in _SPRING_ROUTE_ANNOTATIONS:
            surfaces['http'].append({
                'type': 'route', 'name': name or '?', 'path': path or '?',
                'methods': _SPRING_ROUTE_ANNOTATIONS[anno_name],
                'decorator': f'@{anno_name}', 'file': file_path, 'line': _get_line(node),
            })


def _plain_function_name(func_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(func_node):
        if ch.kind() == 'simple_identifier':
            return _get_text(ch, content_bytes)
    return None


def _find_annotations(func_node: Any) -> List[Any]:
    for ch in _children(func_node):
        if ch.kind() == 'modifiers':
            return [m for m in _children(ch) if m.kind() == 'annotation']
    return []


def _annotation_name_and_path(annotation_node: Any, content_bytes: bytes) -> tuple:
    """(annotation_name, first_string_arg) for @Name or @Name("/path")."""
    for ch in _children(annotation_node):
        if ch.kind() == 'constructor_invocation':
            name = None
            path = None
            for sub in _children(ch):
                if sub.kind() == 'user_type':
                    name = _get_text(sub, content_bytes)
                elif sub.kind() == 'value_arguments':
                    path = _first_string_arg(sub, content_bytes)
            return name, path
        if ch.kind() == 'user_type':
            return _get_text(ch, content_bytes), None
    return None, None
