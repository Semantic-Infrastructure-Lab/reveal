"""Tree-sitter surface extraction for Java — env vars, FS writes, HTTP routes, CLI, imports.

BACK-403 pt 2. Mirrors nav_surface_ts.py's shape (categorised dict of surface
entries) but walks Java's grammar: annotations for HTTP routes (Spring MVC —
the dominant Java web framework; JAX-RS is a possible follow-on, not covered
here), `System.getenv` for env access, `public static void main` for the CLI
entrypoint, and import-root taxonomy for network/db/sdk egress.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.core import node_children as _children

_NET_PACKAGES: frozenset = frozenset({
    'java.net.http', 'okhttp3', 'org.apache.http', 'org.apache.hc', 'retrofit2',
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

_FS_WRITE_CONSTRUCTORS: frozenset = frozenset({'FileWriter', 'FileOutputStream', 'PrintWriter'})
_FS_WRITE_METHODS: frozenset = frozenset({'write', 'newBufferedWriter'})

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')


def scan_file_surface_java(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one Java file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('java')
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
        elif kind == 'method_declaration':
            _process_method(node, file_path, content_bytes, surfaces)
        elif kind == 'method_invocation':
            _process_call(node, file_path, content_bytes, surfaces)
        elif kind == 'object_creation_expression':
            _process_object_creation(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

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
        if ch.kind() in ('scoped_identifier', 'identifier'):
            target = ch
    if target is None:
        return
    module = _import_dotted_name(target, content_bytes)
    line = _get_line(node)
    _categorize_module(module, file_path, line, surfaces)


_PACKAGE_TAXONOMY: tuple = (
    (_NET_PACKAGES, 'network'),
    (_DB_PACKAGES, 'db'),
    (_SDK_PACKAGES, 'sdk'),
)


def _categorize_module(module: str, file_path: str, line: int,
                        surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for packages, category in _PACKAGE_TAXONOMY:
        for prefix in packages:
            if module == prefix or module.startswith(prefix + '.'):
                entry = {'type': 'import', 'name': module, 'file': file_path, 'line': line}
                _add_once(surfaces[category], entry)
                return


def _annotation_name(annotation_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(annotation_node):
        if ch.kind() == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _annotation_path_arg(annotation_node: Any, content_bytes: bytes) -> Optional[str]:
    """First bare string_literal arg, or the 'value'/'path' element_value_pair."""
    for ch in _children(annotation_node):
        if ch.kind() != 'annotation_argument_list':
            continue
        for arg in _children(ch):
            if arg.kind() == 'string_literal':
                return _string_literal_text(arg, content_bytes)
            if arg.kind() == 'element_value_pair':
                pair_children = _children(arg)
                if len(pair_children) < 3:
                    continue
                key_name = _get_text(pair_children[0], content_bytes)
                if key_name in ('value', 'path') and pair_children[2].kind() == 'string_literal':
                    return _string_literal_text(pair_children[2], content_bytes)
    return None


def _string_literal_text(node: Any, content_bytes: bytes) -> str:
    for ch in _children(node):
        if ch.kind() == 'string_fragment':
            return _get_text(ch, content_bytes)
    return _get_text(node, content_bytes).strip('"')


def _find_method_annotations(method_node: Any) -> List[Any]:
    for ch in _children(method_node):
        if ch.kind() == 'modifiers':
            return [m for m in _children(ch) if m.kind() in ('annotation', 'marker_annotation')]
    return []


def _method_name(method_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(method_node):
        if ch.kind() == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _is_static_modifier_present(method_node: Any) -> bool:
    for ch in _children(method_node):
        if ch.kind() != 'modifiers':
            continue
        return any(m.kind() == 'static' for m in _children(ch))
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


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                   surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    children = _children(node)
    # method_invocation: identifier '.' identifier argument_list  (obj.method(...))
    idents = [c for c in children if c.kind() == 'identifier']
    if len(idents) < 2:
        return
    obj, method = _get_text(idents[0], content_bytes), _get_text(idents[1], content_bytes)
    line = _get_line(node)

    if obj == 'System' and method == 'getenv':
        key = _first_string_arg(node, content_bytes)
        if key:
            surfaces['env'].append({
                'type': 'env_var', 'name': key, 'expr': 'System.getenv',
                'file': file_path, 'line': line,
            })
    elif method in _FS_WRITE_METHODS and obj == 'Files':
        surfaces['fs'].append({
            'type': 'fs_write', 'name': f'Files.{method}', 'file': file_path, 'line': line,
        })


def _process_object_creation(node: Any, file_path: str, content_bytes: bytes,
                              surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for ch in _children(node):
        if ch.kind() == 'type_identifier':
            type_name = _get_text(ch, content_bytes)
            if type_name in _FS_WRITE_CONSTRUCTORS:
                surfaces['fs'].append({
                    'type': 'fs_write', 'name': f'new {type_name}()',
                    'file': file_path, 'line': _get_line(node),
                })
            return


def _first_string_arg(call_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(call_node):
        if ch.kind() != 'argument_list':
            continue
        for arg in _children(ch):
            if arg.kind() == 'string_literal':
                return _string_literal_text(arg, content_bytes)
    return None


def _add_once(lst: List[Dict[str, Any]], entry: Dict[str, Any]) -> None:
    key = (entry.get('name', ''), entry.get('file', ''), entry.get('line', 0))
    for existing in lst:
        if (existing.get('name', ''), existing.get('file', ''), existing.get('line', 0)) == key:
            return
    lst.append(entry)
