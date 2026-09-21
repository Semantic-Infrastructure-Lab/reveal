"""Tree-sitter surface extraction for Java — env vars, FS writes, HTTP routes, CLI, imports.

BACK-403 pt 2. Mirrors nav_surface_ts.py's shape (categorised dict of surface
entries) but walks Java's grammar: annotations for HTTP routes (Spring MVC —
the dominant Java web framework; JAX-RS is a possible follow-on, not covered
here), `System.getenv` for env access, `public static void main` for the CLI
entrypoint, and import-root taxonomy for network/db/sdk egress.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import _get_text, _get_line, _add_once, categorize_by_prefix
from .surface_rules import RuleScan

logger = logging.getLogger(__name__)

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

_NET_PACKAGES: frozenset = frozenset({
    'java.net.http', 'okhttp3', 'org.apache.http', 'org.apache.hc', 'retrofit2',
    # JDK classic networking (BACK-1090): exact classes, not `java.net` -- URI,
    # URLEncoder, InetAddress etc. are not egress.
    'java.net.URL', 'java.net.HttpURLConnection', 'java.net.URLConnection',
    'java.net.Socket', 'java.net.ServerSocket', 'java.net.DatagramSocket',
})

_DB_PACKAGES: frozenset = frozenset({
    'java.sql', 'javax.persistence', 'jakarta.persistence', 'org.hibernate',
    'redis.clients.jedis', 'com.mongodb', 'org.springframework.data',
})

_SDK_PACKAGES: frozenset = frozenset({
    'com.stripe', 'com.twilio', 'com.slack.api', 'software.amazon.awssdk',
    'com.amazonaws', 'com.google.cloud', 'com.microsoft.azure', 'com.azure',
})

# Spring MVC route annotations → inferred HTTP method (RequestMapping needs
# its own 'method' element to know the verb; left as ANY here — a precise
# read would resolve RequestMethod.GET etc., not attempted this pass).
_SPRING_ROUTE_ANNOTATIONS: Dict[str, str] = {
    'GetMapping': 'GET',
    'PostMapping': 'POST',
    'PutMapping': 'PUT',
    'DeleteMapping': 'DELETE',
    'PatchMapping': 'PATCH',
    'RequestMapping': 'ANY',
}


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
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    rules = RuleScan('java', content_bytes)
    rule_kinds, visit = rules.kinds, rules.visit

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in rule_kinds:
            visit(node, kind)

        if kind == 'import_declaration':
            _process_import(node, file_path, content_bytes, surfaces)
        elif kind == 'method_declaration':
            _process_method(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    rules.apply(surfaces, file_path)
    return surfaces


def _import_dotted_name(node: Any, content_bytes: bytes) -> str:
    """Flatten a scoped_identifier (or bare identifier) import target to 'a.b.c',
    dropping a trailing '*' wildcard segment."""
    text = _get_text(node, content_bytes)
    return text.rstrip('*').rstrip('.')


def _process_import(node: Any, file_path: str, content_bytes: bytes,
                     surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    target = None
    for ch in _children(node):
        if _zero_arg(ch, 'kind') in ('scoped_identifier', 'identifier'):
            target = ch
    if target is None:
        return
    module = _import_dotted_name(target, content_bytes)
    line = _get_line(node)
    categorize_by_prefix(module, file_path, line, surfaces, _PACKAGE_TAXONOMY, '.')


_PACKAGE_TAXONOMY: tuple = (
    (_NET_PACKAGES, 'network'),
    (_DB_PACKAGES, 'db'),
    (_SDK_PACKAGES, 'sdk'),
)


def _annotation_name(annotation_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(annotation_node):
        if _zero_arg(ch, 'kind') == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _annotation_path_arg(annotation_node: Any, content_bytes: bytes) -> Optional[str]:
    """First bare string_literal arg, or the 'value'/'path' element_value_pair."""
    for ch in _children(annotation_node):
        if _zero_arg(ch, 'kind') != 'annotation_argument_list':
            continue
        for arg in _children(ch):
            if _zero_arg(arg, 'kind') == 'string_literal':
                return _string_literal_text(arg, content_bytes)
            if _zero_arg(arg, 'kind') == 'element_value_pair':
                pair_children = _children(arg)
                if len(pair_children) < 3:
                    continue
                key_name = _get_text(pair_children[0], content_bytes)
                if key_name in ('value', 'path') and \
                        _zero_arg(pair_children[2], 'kind') == 'string_literal':
                    return _string_literal_text(pair_children[2], content_bytes)
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
                     surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    line = _get_line(node)
    name = _method_name(node, content_bytes)

    # CLI entrypoint: public static void main(String[] args)
    if name == 'main' and _is_static_modifier_present(node):
        surfaces['cli'].append({
            'type': 'main', 'name': 'main', 'file': file_path, 'line': line,
        })

    for annotation in _find_method_annotations(node):
        anno_name = _annotation_name(annotation, content_bytes)
        if anno_name in _SPRING_ROUTE_ANNOTATIONS:
            path_arg = _annotation_path_arg(annotation, content_bytes)
            surfaces['http'].append({
                'type': 'route',
                'name': name or '?',
                'path': path_arg or '?',
                'methods': _SPRING_ROUTE_ANNOTATIONS[anno_name],
                'decorator': f'@{anno_name}',
                'file': file_path,
                'line': line,
            })
