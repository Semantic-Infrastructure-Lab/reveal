"""Tree-sitter surface extraction for C# — env vars, FS writes, HTTP routes, CLI, imports.

BACK-403 pt 2. Mirrors nav_surface_java.py's shape: attributes for ASP.NET Core
HTTP routes, `Environment.GetEnvironmentVariable` for env access,
`static void/int Main` for the CLI entrypoint, and using-root taxonomy for
network/db/sdk egress.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .nav_surface_common import _get_text, _get_line, _add_once

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse

_NET_PACKAGES: frozenset = frozenset({'System.Net.Http', 'RestSharp'})

_DB_PACKAGES: frozenset = frozenset({
    'System.Data', 'Microsoft.EntityFrameworkCore', 'Npgsql', 'MongoDB.Driver',
    'StackExchange.Redis', 'Dapper',
})

_SDK_PACKAGES: frozenset = frozenset({
    'Stripe', 'Twilio', 'Azure', 'Amazon', 'AWSSDK', 'Google.Cloud',
})

# ASP.NET Core route attributes → inferred HTTP method. [Route] alone carries
# no verb (it's often paired with an Http* attribute on the same method, or
# used for controller-level prefixes) — recorded as ANY.
_ASPNET_ROUTE_ATTRIBUTES: Dict[str, str] = {
    'HttpGet': 'GET',
    'HttpPost': 'POST',
    'HttpPut': 'PUT',
    'HttpDelete': 'DELETE',
    'HttpPatch': 'PATCH',
    'Route': 'ANY',
}

_FS_WRITE_CONSTRUCTORS: frozenset = frozenset({'StreamWriter', 'FileStream'})
_FS_WRITE_STATIC_METHODS: frozenset = frozenset({'WriteAllText', 'WriteAllBytes', 'AppendAllText'})

_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs')


def scan_file_surface_csharp(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one C# file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace')
        parser = get_parser('c_sharp')
        tree = ts_parse(parser, source)
    except Exception:
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return _scan_tree(tree, file_path, content_bytes)


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = node.kind()

        if kind == 'using_directive':
            _process_using(node, file_path, content_bytes, surfaces)
        elif kind == 'method_declaration':
            _process_method(node, file_path, content_bytes, surfaces)
        elif kind == 'invocation_expression':
            _process_call(node, file_path, content_bytes, surfaces)
        elif kind == 'object_creation_expression':
            _process_object_creation(node, file_path, content_bytes, surfaces)

        for ch in reversed(_children(node)):
            stack.append(ch)

    return surfaces


def _process_using(node: Any, file_path: str, content_bytes: bytes,
                    surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    target = None
    for ch in _children(node):
        if ch.kind() in ('qualified_name', 'identifier'):
            target = ch
    if target is None:
        return
    module = _get_text(target, content_bytes)
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


def _attribute_name(attribute_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(attribute_node):
        if ch.kind() == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _attribute_path_arg(attribute_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(attribute_node):
        if ch.kind() != 'attribute_argument_list':
            continue
        for arg in _children(ch):
            if arg.kind() == 'attribute_argument':
                for sub in _children(arg):
                    if sub.kind() == 'string_literal':
                        return _string_literal_text(sub, content_bytes)
    return None


def _string_literal_text(node: Any, content_bytes: bytes) -> str:
    for ch in _children(node):
        if ch.kind() == 'string_literal_content':
            return _get_text(ch, content_bytes)
    return _get_text(node, content_bytes).strip('"')


def _find_method_attributes(method_node: Any) -> List[Any]:
    attrs = []
    for ch in _children(method_node):
        if ch.kind() == 'attribute_list':
            attrs.extend(a for a in _children(ch) if a.kind() == 'attribute')
    return attrs


def _method_name(method_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(method_node):
        if ch.kind() == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _is_static_modifier_present(method_node: Any) -> bool:
    for ch in _children(method_node):
        if ch.kind() == 'modifier' and any(m.kind() == 'static' for m in _children(ch)):
            return True
    return False


def _process_method(node: Any, file_path: str, content_bytes: bytes,
                     surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    line = _get_line(node)
    name = _method_name(node, content_bytes)

    # CLI entrypoint: static void/int Main(string[] args)
    if name == 'Main' and _is_static_modifier_present(node):
        surfaces['cli'].append({
            'type': 'main', 'name': 'Main', 'file': file_path, 'line': line,
        })

    route_attrs = [
        (a, _attribute_name(a, content_bytes)) for a in _find_method_attributes(node)
    ]
    route_attrs = [(a, n) for a, n in route_attrs if n in _ASPNET_ROUTE_ATTRIBUTES]
    if route_attrs:
        verb, path_arg, decorator = _merge_route_attrs(route_attrs, content_bytes)
        surfaces['http'].append({
            'type': 'route',
            'name': name or '?',
            'path': path_arg or '?',
            'methods': verb,
            'decorator': decorator,
            'file': file_path,
            'line': line,
        })


def _merge_route_attrs(
    route_attrs: List[Any], content_bytes: bytes,
) -> Tuple[str, Optional[str], str]:
    # A method commonly carries an Http* verb attribute AND a separate [Route]
    # attribute for its path (`[HttpPost] [Route("/users")]`) — merge those
    # into one entry instead of reporting the same endpoint twice. Prefer the
    # verb attribute's own path if it has one; otherwise fall back to any
    # co-occurring [Route]'s path.
    verb = 'ANY'
    decorators = []
    path_arg = None
    for attribute, attr_name in route_attrs:
        decorators.append(f'[{attr_name}]')
        this_path = _attribute_path_arg(attribute, content_bytes)
        if attr_name != 'Route':
            verb = _ASPNET_ROUTE_ATTRIBUTES[attr_name]
        if this_path and path_arg is None:
            path_arg = this_path
    return verb, path_arg, ' '.join(decorators)


def _invocation_obj_method(node: Any, content_bytes: bytes) -> Tuple[Optional[str], Optional[str]]:
    """For invocation_expression, return (obj, method) from a member_access_expression callee."""
    children = _children(node)
    if not children:
        return None, None
    callee = children[0]
    if callee.kind() != 'member_access_expression':
        return None, None
    parts = _children(callee)
    if len(parts) < 3:
        return None, None
    obj = _get_text(parts[0], content_bytes)
    method = _get_text(parts[-1], content_bytes)
    return obj, method


def _process_call(node: Any, file_path: str, content_bytes: bytes,
                   surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    obj, method = _invocation_obj_method(node, content_bytes)
    if obj is None or method is None:
        return
    line = _get_line(node)

    if obj == 'Environment' and method == 'GetEnvironmentVariable':
        key = _first_string_arg(node, content_bytes)
        if key:
            surfaces['env'].append({
                'type': 'env_var', 'name': key, 'expr': 'Environment.GetEnvironmentVariable',
                'file': file_path, 'line': line,
            })
    elif obj == 'File' and method in _FS_WRITE_STATIC_METHODS:
        surfaces['fs'].append({
            'type': 'fs_write', 'name': f'File.{method}', 'file': file_path, 'line': line,
        })


def _process_object_creation(node: Any, file_path: str, content_bytes: bytes,
                              surfaces: Dict[str, List[Dict[str, Any]]]) -> None:
    for ch in _children(node):
        if ch.kind() == 'identifier':
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
            if arg.kind() == 'argument':
                for sub in _children(arg):
                    if sub.kind() == 'string_literal':
                        return _string_literal_text(sub, content_bytes)
            elif arg.kind() == 'string_literal':
                return _string_literal_text(arg, content_bytes)
    return None
