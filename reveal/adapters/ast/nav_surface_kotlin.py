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

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .nav_surface_common import (
    disclose_parse_recovery,
    INHERIT_KEY, ROUTE_CLASSES_KEY, SPRING_ROUTE_ANNOTATIONS, _get_text, _get_line, join_route_path,
    merge_routes_by_path, type_simple_name,
)
from .surface_rules import RuleScan

logger = logging.getLogger(__name__)

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

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

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')


def scan_file_surface_kotlin(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Kotlin file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace', encoding='utf-8')
        parser = get_parser('kotlin')
        tree = ts_parse(parser, source)
    except Exception as e:
        logger.warning("surface scan (Kotlin) failed to parse %s: %s", file_path, e)
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return disclose_parse_recovery(tree, file_path, _scan_tree(tree, file_path, content_bytes))


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    rules = RuleScan('kotlin', content_bytes)
    rule_kinds, visit = rules.kinds, rules.visit
    root = tree_root(tree)

    # CLI entrypoint: a top-level `fun main` (direct child of the file only, so a
    # class method named main isn't misclassified as an entrypoint).
    for child in _children(root):
        if _zero_arg(child, 'kind') == 'function_declaration' and \
                _function_name(child, content_bytes) == 'main':
            surfaces['cli'].append({
                'type': 'main', 'name': 'main', 'file': file_path, 'line': _get_line(child),
            })

    # Each node travels with its class (name, own Spring @RequestMapping paths
    # or None, supertype names).
    classes: List[Dict[str, Any]] = []
    stack: List[Tuple[Any, _Controller]] = [(root, (None, None, []))]
    while stack:
        node, controller = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in rule_kinds:
            visit(node, kind)

        if kind in ('class_declaration', 'object_declaration'):
            controller = (_class_name(node, content_bytes), _class_route_prefixes(node, content_bytes),
                          _supertype_names(node, content_bytes))
            if controller[0]:
                classes.append({'name': controller[0], 'prefixes': controller[1], 'bases': controller[2]})
        elif kind == 'call_expression':
            _process_call(node, file_path, content_bytes, surfaces)
        elif kind == 'function_declaration':
            _process_annotations(node, file_path, content_bytes, surfaces, controller)

        for ch in reversed(_children(node)):
            stack.append((ch, controller))

    rules.apply(surfaces, file_path)
    if classes:
        surfaces[ROUTE_CLASSES_KEY] = classes
    return surfaces


# (class name, the class's own @RequestMapping paths or None, supertype names)
_Controller = Tuple[Optional[str], Optional[List[str]], List[str]]


def _class_name(class_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(class_node):
        if _zero_arg(ch, 'kind') == 'type_identifier':
            return _get_text(ch, content_bytes)
    return None


def _supertype_names(class_node: Any, content_bytes: bytes) -> List[str]:
    names = []
    for ch in _children(class_node):
        if _zero_arg(ch, 'kind') == 'delegation_specifier':
            for sub in _children(ch):
                if _zero_arg(sub, 'kind') == 'constructor_invocation':
                    sub = next((t for t in _children(sub) if _zero_arg(t, 'kind') == 'user_type'), sub)
                if _zero_arg(sub, 'kind') == 'user_type':
                    names.append(type_simple_name(_get_text(sub, content_bytes)))
    return names


def _function_name(func_node: Any, content_bytes: bytes) -> Optional[str]:
    # A top-level `fun main` has no receiver_type; its name is the simple_identifier.
    for ch in _children(func_node):
        if _zero_arg(ch, 'kind') == 'receiver_type':
            return None  # extension function — not the entrypoint
        if _zero_arg(ch, 'kind') == 'simple_identifier':
            return _get_text(ch, content_bytes)
    return None



def _string_content(string_node: Any, content_bytes: bytes) -> str:
    for ch in _children(string_node):
        if _zero_arg(ch, 'kind') == 'string_content':
            return _get_text(ch, content_bytes)
    return _get_text(string_node, content_bytes).strip('"')


def _call_suffix(node: Any) -> Optional[Any]:
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'call_suffix':
            return ch
    return None


def _has_annotated_lambda(call_suffix_node: Any) -> bool:
    return any(_zero_arg(c, 'kind') == 'annotated_lambda' for c in _children(call_suffix_node))


def _value_arguments(call_suffix_node: Any) -> Optional[Any]:
    for ch in _children(call_suffix_node):
        if _zero_arg(ch, 'kind') == 'value_arguments':
            return ch
    return None


def _first_string_arg(value_arguments_node: Any, content_bytes: bytes) -> Optional[str]:
    for arg in _children(value_arguments_node):
        if _zero_arg(arg, 'kind') != 'value_argument':
            continue
        for sub in _children(arg):
            if _zero_arg(sub, 'kind') == 'string_literal':
                return _string_content(sub, content_bytes)
    return None


def _navigation_receiver_and_method(nav_node: Any, content_bytes: bytes) -> tuple:
    children = _children(nav_node)
    if len(children) < 2:
        return None, None
    receiver = children[0]
    suffix = children[-1]
    if _zero_arg(suffix, 'kind') != 'navigation_suffix':
        return None, None
    method = None
    for ch in _children(suffix):
        if _zero_arg(ch, 'kind') == 'simple_identifier':
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
    if _zero_arg(callee, 'kind') == 'simple_identifier':
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


def _process_annotations(node: Any, file_path: str, content_bytes: bytes,
                         surfaces: Dict[str, List[Dict[str, Any]]],
                         controller: _Controller = (None, None, [])) -> None:
    name = _plain_function_name(node, content_bytes)
    routes: List[Tuple[List[str], Optional[str]]] = []
    decorators = []
    for annotation in _find_annotations(node):
        anno_name, elements = _annotation_name_and_elements(annotation, content_bytes)
        if anno_name not in SPRING_ROUTE_ANNOTATIONS:
            continue
        decorators.append(f'@{anno_name}')
        verbs = [SPRING_ROUTE_ANNOTATIONS[anno_name]]
        if anno_name == 'RequestMapping':
            verbs = [v.upper() for v in elements.get('method', []) if v != '?'] or ['ANY']
        routes.extend((verbs, path) for path in _mapping_paths(elements))
    class_name, prefixes, bases = controller
    for methods, path in merge_routes_by_path(routes):
        for prefix in (prefixes or [None]):
            entry = {
                'type': 'route', 'name': name or '?',
                'path': join_route_path(prefix, path) or '?',
                'methods': methods, 'decorator': ' '.join(decorators),
                'file': file_path, 'line': _get_line(node),
            }
            if prefixes is None and bases and class_name:
                entry[INHERIT_KEY] = {'class': class_name, 'action': name, 'tokens': False, 'template': path}
            surfaces['http'].append(entry)


def _mapping_paths(elements: Dict[str, List[str]]) -> List[Optional[str]]:
    return elements.get('value') or elements.get('path') or [None]


def _class_route_prefixes(class_node: Any, content_bytes: bytes) -> Optional[List[str]]:
    """A Spring controller's class-level @RequestMapping paths, or None
    (BACK-1418: they were never joined to the functions' paths)."""
    for annotation in _find_annotations(class_node):
        anno_name, elements = _annotation_name_and_elements(annotation, content_bytes)
        if anno_name == 'RequestMapping':
            return [p or '' for p in _mapping_paths(elements)]
    return None


def _plain_function_name(func_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(func_node):
        if _zero_arg(ch, 'kind') == 'simple_identifier':
            return _get_text(ch, content_bytes)
    return None


def _find_annotations(func_node: Any) -> List[Any]:
    for ch in _children(func_node):
        if _zero_arg(ch, 'kind') == 'modifiers':
            return [m for m in _children(ch) if _zero_arg(m, 'kind') == 'annotation']
    return []


def _annotation_name_and_elements(annotation_node: Any,
                                  content_bytes: bytes) -> Tuple[Optional[str], Dict[str, List[str]]]:
    """(annotation name, element values) for @Name or @Name(...). A bare
    argument is the implicit `value`; an array is flattened; a string is its
    text, an enum constant its last segment (RequestMethod.GET -> GET),
    anything else '?'."""
    for ch in _children(annotation_node):
        kind = _zero_arg(ch, 'kind')
        if kind == 'user_type':
            return _get_text(ch, content_bytes), {}
        if kind != 'constructor_invocation':
            continue
        name = None
        elements: Dict[str, List[str]] = {}
        for sub in _children(ch):
            sub_kind = _zero_arg(sub, 'kind')
            if sub_kind == 'user_type':
                name = _get_text(sub, content_bytes)
            elif sub_kind == 'value_arguments':
                for arg in _children(sub):
                    if _zero_arg(arg, 'kind') != 'value_argument':
                        continue
                    kids = _children(arg)
                    key = 'value'
                    if any(_zero_arg(k, 'kind') == '=' for k in kids):
                        key = _get_text(kids[0], content_bytes)
                    elements[key] = _element_values(kids[-1], content_bytes)
        return name, elements
    return None, {}


def _element_values(node: Any, content_bytes: bytes) -> List[str]:
    kind = _zero_arg(node, 'kind')
    if kind == 'collection_literal':
        return [value for ch in _children(node) if _zero_arg(ch, 'kind') not in ('[', ']', ',')
                for value in _element_values(ch, content_bytes)]
    if kind == 'string_literal':
        return [_string_content(node, content_bytes)]
    if kind == 'navigation_expression':
        return [_get_text(node, content_bytes).rsplit('.', 1)[-1]]
    return ['?']
