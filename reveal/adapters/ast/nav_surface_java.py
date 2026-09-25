"""Tree-sitter surface extraction for Java — env vars, FS writes, HTTP routes, CLI, imports.

BACK-403 pt 2. Mirrors nav_surface_ts.py's shape (categorised dict of surface
entries) but walks Java's grammar: annotations for HTTP routes (Spring MVC —
the dominant Java web framework; JAX-RS is a possible follow-on, not covered
here), `System.getenv` for env access, `public static void main` for the CLI
entrypoint, and import-root taxonomy for network/db/sdk egress.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .nav_surface_common import (
    disclose_parse_recovery,
    INHERIT_KEY, ROUTE_CLASSES_KEY, SPRING_ROUTE_ANNOTATIONS, _get_text, _get_line, join_route_path,
    merge_routes_by_path, type_simple_name, mapping_paths, route_prefixes,
)
from .surface_rules import RuleScan

logger = logging.getLogger(__name__)

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')


def scan_file_surface_java(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Java file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace', encoding='utf-8')
        parser = get_parser('java')
        tree = ts_parse(parser, source)
    except Exception as e:
        logger.warning("surface scan (Java) failed to parse %s: %s", file_path, e)
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return disclose_parse_recovery(tree, file_path, _scan_tree(tree, file_path, content_bytes))


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    rules = RuleScan('java', content_bytes)
    rule_kinds, visit = rules.kinds, rules.visit

    # Each node travels with its class (name, own @RequestMapping paths or
    # None, base type names).
    classes: List[Dict[str, Any]] = []
    stack: List[Tuple[Any, _Controller]] = [(tree_root(tree), (None, None, []))]
    while stack:
        node, controller = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in rule_kinds:
            visit(node, kind)

        if kind in ('class_declaration', 'interface_declaration'):
            controller = (_class_name(node, content_bytes), _class_route_prefixes(node, content_bytes),
                          _base_type_names(node, content_bytes))
            if controller[0]:
                classes.append({'name': controller[0], 'prefixes': controller[1], 'bases': controller[2]})
        elif kind == 'method_declaration':
            _process_method(node, file_path, content_bytes, surfaces, controller)

        for ch in reversed(_children(node)):
            stack.append((ch, controller))

    rules.apply(surfaces, file_path)
    if classes:
        surfaces[ROUTE_CLASSES_KEY] = classes
    return surfaces


# (class name, the class's own @RequestMapping paths or None, base type names)
_Controller = Tuple[Optional[str], Optional[List[str]], List[str]]


def _class_name(class_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(class_node):
        if _zero_arg(ch, 'kind') == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _base_type_names(class_node: Any, content_bytes: bytes) -> List[str]:
    """Superclass and interfaces -- Spring finds a class-level @RequestMapping
    on either."""
    names: List[str] = []
    for ch in _children(class_node):
        if _zero_arg(ch, 'kind') not in ('superclass', 'super_interfaces', 'extends_interfaces'):
            continue
        for sub in _children(ch):
            kinds = [sub] if _zero_arg(sub, 'kind') != 'type_list' else _children(sub)
            names.extend(type_simple_name(_get_text(t, content_bytes)) for t in kinds
                         if _zero_arg(t, 'kind') in ('type_identifier', 'generic_type', 'scoped_type_identifier'))
    return names


def _annotation_name(annotation_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(annotation_node):
        if _zero_arg(ch, 'kind') == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _annotation_elements(annotation_node: Any, content_bytes: bytes) -> Dict[str, List[str]]:
    """Each annotation element's values, an array flattened; the bare argument
    of `@GetMapping("/x")` is the implicit `value`. A string is its text, an
    enum constant its last segment (`RequestMethod.GET` -> GET), anything else
    '?' -- a constant's value is not known statically."""
    elements: Dict[str, List[str]] = {}
    for ch in _children(annotation_node):
        if _zero_arg(ch, 'kind') != 'annotation_argument_list':
            continue
        for arg in _children(ch):
            kind = _zero_arg(arg, 'kind')
            if kind in ('(', ')', ','):
                continue
            if kind == 'element_value_pair':
                kids = _children(arg)
                if len(kids) >= 3:
                    elements[_get_text(kids[0], content_bytes)] = _element_values(kids[2], content_bytes)
            else:
                elements['value'] = _element_values(arg, content_bytes)
    return elements


def _element_values(node: Any, content_bytes: bytes) -> List[str]:
    kind = _zero_arg(node, 'kind')
    if kind == 'element_value_array_initializer':
        return [value for ch in _children(node) if _zero_arg(ch, 'kind') not in ('{', '}', ',')
                for value in _element_values(ch, content_bytes)]
    if kind == 'string_literal':
        return [_string_literal_text(node, content_bytes)]
    if kind == 'field_access':
        return [_get_text(node, content_bytes).rsplit('.', 1)[-1]]
    return ['?']


def _class_route_prefixes(class_node: Any, content_bytes: bytes) -> Optional[List[str]]:
    """A controller's class-level @RequestMapping paths, or None (BACK-1418:
    they were never joined to the methods' paths)."""
    for annotation in _find_method_annotations(class_node):
        if _annotation_name(annotation, content_bytes) == 'RequestMapping':
            return [p or '' for p in mapping_paths(_annotation_elements(annotation, content_bytes))]
    return None


def _string_literal_text(node: Any, content_bytes: bytes) -> str:
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'string_fragment':
            return _get_text(ch, content_bytes)
    return _get_text(node, content_bytes).strip('"')


def _find_method_annotations(method_node: Any) -> List[Any]:
    for ch in _children(method_node):
        if _zero_arg(ch, 'kind') == 'modifiers':
            return [
                m for m in _children(ch)
                if _zero_arg(m, 'kind') in ('annotation', 'marker_annotation')
            ]
    return []


def _method_name(method_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(method_node):
        if _zero_arg(ch, 'kind') == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _is_static_modifier_present(method_node: Any) -> bool:
    for ch in _children(method_node):
        if _zero_arg(ch, 'kind') != 'modifiers':
            continue
        return any(_zero_arg(m, 'kind') == 'static' for m in _children(ch))
    return False


def _process_method(node: Any, file_path: str, content_bytes: bytes,
                    surfaces: Dict[str, List[Dict[str, Any]]],
                    controller: _Controller = (None, None, [])) -> None:
    line = _get_line(node)
    name = _method_name(node, content_bytes)

    # CLI entrypoint: public static void main(String[] args)
    if name == 'main' and _is_static_modifier_present(node):
        surfaces['cli'].append({
            'type': 'main', 'name': 'main', 'file': file_path, 'line': line,
        })

    routes: List[Tuple[List[str], Optional[str]]] = []
    decorators = []
    for annotation in _find_method_annotations(node):
        anno_name = _annotation_name(annotation, content_bytes)
        if anno_name not in SPRING_ROUTE_ANNOTATIONS:
            continue
        decorators.append(f'@{anno_name}')
        elements = _annotation_elements(annotation, content_bytes)
        verbs = [SPRING_ROUTE_ANNOTATIONS[anno_name]]
        if anno_name == 'RequestMapping':
            verbs = [v.upper() for v in elements.get('method', []) if v != '?'] or ['ANY']
        routes.extend((verbs, path) for path in mapping_paths(elements))
    class_name, prefixes, bases = controller
    for methods, path in merge_routes_by_path(routes):
        for prefix in route_prefixes(prefixes):
            entry = {
                'type': 'route',
                'name': name or '?',
                'path': join_route_path(prefix, path) or '?',
                'methods': methods,
                'decorator': ' '.join(decorators),
                'file': file_path,
                'line': line,
            }
            if prefixes is None and bases and class_name:
                entry[INHERIT_KEY] = {'class': class_name, 'action': name, 'tokens': False, 'template': path}
            surfaces['http'].append(entry)
