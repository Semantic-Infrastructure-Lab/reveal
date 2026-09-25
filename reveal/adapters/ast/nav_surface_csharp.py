"""Tree-sitter surface extraction for C# — env vars, FS writes, HTTP routes, CLI, imports.

BACK-403 pt 2. Mirrors nav_surface_java.py's shape: attributes for ASP.NET Core
HTTP routes, `Environment.GetEnvironmentVariable` for env access,
`static void/int Main` for the CLI entrypoint, and using-root taxonomy for
network/db/sdk egress.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .nav_surface_common import (
    disclose_parse_recovery,
    INHERIT_KEY, ROUTE_CLASSES_KEY, _get_text, _get_line, join_route_path, merge_routes_by_path,
    replace_route_tokens, route_prefixes, type_simple_name,
)
from .surface_rules import RuleScan

logger = logging.getLogger(__name__)

from reveal.core import node_children as _children
from reveal.core import tree_root, ts_parse
from reveal.core.treesitter_compat import _zero_arg

# ASP.NET Core verb attributes -> HTTP method. Each may carry its own route
# template; several on one action are several routes (or one route answering
# several verbs when their templates agree).
_ASPNET_VERB_ATTRIBUTES: Dict[str, str] = {
    'HttpGet': 'GET',
    'HttpPost': 'POST',
    'HttpPut': 'PUT',
    'HttpDelete': 'DELETE',
    'HttpPatch': 'PATCH',
    'HttpHead': 'HEAD',
    'HttpOptions': 'OPTIONS',
}
# [Route] carries a template and no verb (on a class it is the controller's
# prefix); [AcceptVerbs("GET", "HEAD", Route = "...")] carries verbs.
_ASPNET_ROUTE_ATTRIBUTES = frozenset(_ASPNET_VERB_ATTRIBUTES) | {'Route', 'AcceptVerbs'}

# (class name, the class's own [Route] prefixes or None, base type names)
_Controller = Tuple[Optional[str], Optional[List[str]], List[str]]


_EMPTY_KEYS = ('cli', 'http', 'env', 'network', 'db', 'sdk', 'fs', 'subprocess')


def scan_file_surface_csharp(file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse one C# file and return categorised surface entries."""
    try:
        from tree_sitter_language_pack import get_parser
        source = Path(file_path).read_text(errors='replace', encoding='utf-8')
        parser = get_parser('c_sharp')
        tree = ts_parse(parser, source)
    except Exception as e:
        logger.warning("surface scan (C#) failed to parse %s: %s", file_path, e)
        return {k: [] for k in _EMPTY_KEYS}

    content_bytes = source.encode('utf-8')
    return disclose_parse_recovery(tree, file_path, _scan_tree(tree, file_path, content_bytes))


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    rules = RuleScan('csharp', content_bytes)
    rule_kinds, visit = rules.kinds, rules.visit

    # Each node travels with its enclosing controller (_Controller: class
    # name, the class's own [Route] prefixes or None, its base type names).
    classes: List[Dict[str, Any]] = []
    stack: List[Tuple[Any, _Controller]] = [(tree_root(tree), (None, None, []))]
    while stack:
        node, controller = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in rule_kinds:
            visit(node, kind)

        if kind == 'class_declaration':
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


def _attribute_name(attribute_node: Any, content_bytes: bytes) -> Optional[str]:
    """`HttpGet` for [HttpGet], [HttpGetAttribute] and [Microsoft.AspNetCore.Mvc.HttpGet]."""
    for ch in _children(attribute_node):
        if _zero_arg(ch, 'kind') in ('identifier', 'qualified_name'):
            name = _get_text(ch, content_bytes).rsplit('.', 1)[-1]
            return name[:-len('Attribute')] if name.endswith('Attribute') and name != 'Attribute' else name
    return None


def _attribute_args(attribute_node: Any, content_bytes: bytes) -> Tuple[List[str], Dict[str, str]]:
    """(positional, named) arguments. A string is its text; anything else (a
    constant, an expression) is '?' -- its value is not known statically."""
    positional: List[str] = []
    named: Dict[str, str] = {}
    for ch in _children(attribute_node):
        if _zero_arg(ch, 'kind') != 'attribute_argument_list':
            continue
        for arg in _children(ch):
            if _zero_arg(arg, 'kind') != 'attribute_argument':
                continue
            kids = _children(arg)
            is_named = any(_zero_arg(k, 'kind') == '=' for k in kids)
            value = _argument_value(kids[-1], content_bytes) if kids else '?'
            if is_named:
                named[_get_text(kids[0], content_bytes)] = value
            else:
                positional.append(value)
    return positional, named


def _argument_value(node: Any, content_bytes: bytes) -> str:
    kind = _zero_arg(node, 'kind')
    if kind == 'string_literal':
        return _string_literal_text(node, content_bytes)
    if kind == 'verbatim_string_literal':
        return _get_text(node, content_bytes)[2:-1]
    return '?'


def _class_name(class_node: Any, content_bytes: bytes) -> Optional[str]:
    for ch in _children(class_node):
        if _zero_arg(ch, 'kind') == 'identifier':
            return _get_text(ch, content_bytes)
    return None


def _base_type_names(class_node: Any, content_bytes: bytes) -> List[str]:
    for ch in _children(class_node):
        if _zero_arg(ch, 'kind') == 'base_list':
            return [type_simple_name(_get_text(b, content_bytes)) for b in _children(ch)
                    if _zero_arg(b, 'kind') in ('identifier', 'generic_name', 'qualified_name')]
    return []


def _class_route_prefixes(class_node: Any, content_bytes: bytes) -> Optional[List[str]]:
    """The templates of a controller's own [Route] attributes, or None."""
    prefixes = []
    for attribute in _find_method_attributes(class_node):
        if _attribute_name(attribute, content_bytes) == 'Route':
            positional, named = _attribute_args(attribute, content_bytes)
            template = positional[0] if positional else named.get('Template')
            if template is not None:
                prefixes.append(template)
    return prefixes or None


def _string_literal_text(node: Any, content_bytes: bytes) -> str:
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'string_literal_content':
            return _get_text(ch, content_bytes)
    return _get_text(node, content_bytes).strip('"')


def _find_method_attributes(method_node: Any) -> List[Any]:
    attrs: List[Any] = []
    for ch in _children(method_node):
        if _zero_arg(ch, 'kind') == 'attribute_list':
            attrs.extend(a for a in _children(ch) if _zero_arg(a, 'kind') == 'attribute')
    return attrs


def _method_name(method_node: Any, content_bytes: bytes) -> Optional[str]:
    # BACK-797: a `method_declaration`'s direct children can carry TWO bare
    # 'identifier' nodes, not one, whenever the return type is itself a bare
    # (non-generic, non-predefined) type name: `public Task Main(...)` and
    # `public ActionResult Foo(...)` both emit `identifier('Task'/'ActionResult')`
    # for the return type immediately followed by `identifier('Main'/'Foo')`
    # for the real method name — confirmed via direct tree-sitter parse
    # (`Task<T>`/`ActionResult<T>` don't have this problem: a generic return
    # type is a single `generic_name` node whose own `identifier` child is
    # nested, not a direct child, so it's invisible here either way).
    # Taking the FIRST identifier (as this used to) silently grabs the return
    # type instead of the name — confirmed live on samples/csharp (Jellyfin):
    # every ASP.NET action returning bare `ActionResult`/`ContentResult`
    # reported its HTTP route under the return-type name, and `async Task
    # Main(string[] args)` (the standard modern .NET entrypoint shape) was
    # invisible to `cli` detection entirely. The method's own name is always
    # the LAST bare identifier before the parameter list — an
    # `explicit_interface_specifier` (`void IFoo.Bar()`) wraps its own
    # identifier as a non-direct child, so it never interferes.
    name = None
    for ch in _children(method_node):
        if _zero_arg(ch, 'kind') == 'identifier':
            name = _get_text(ch, content_bytes)
    return name


def _is_static_modifier_present(method_node: Any) -> bool:
    for ch in _children(method_node):
        if _zero_arg(ch, 'kind') == 'modifier' and any(
            _zero_arg(m, 'kind') == 'static' for m in _children(ch)
        ):
            return True
    return False


def _process_method(node: Any, file_path: str, content_bytes: bytes,
                    surfaces: Dict[str, List[Dict[str, Any]]],
                    controller: '_Controller' = (None, None, [])) -> None:
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
    if not route_attrs:
        return
    decorator = ' '.join(f'[{attr_name}]' for _, attr_name in route_attrs)
    class_name, prefixes, bases = controller
    for methods, path in merge_routes_by_path(_action_routes(route_attrs, content_bytes)):
        for prefix in route_prefixes(prefixes):
            entry = {
                'type': 'route',
                'name': name or '?',
                'path': replace_route_tokens(_under_prefix(prefix, path), class_name, name) or '?',
                'methods': methods,
                'decorator': decorator,
                'file': file_path,
                'line': line,
            }
            # No [Route] of its own: the prefix may come from a base class in
            # another file, resolved once every file is scanned.
            if prefixes is None and bases and class_name and not (path or '').startswith(('/', '~/')):
                entry[INHERIT_KEY] = {
                    'class': class_name, 'action': name, 'tokens': True,
                    'template': replace_route_tokens(path, class_name, name),
                }
            surfaces['http'].append(entry)


def _action_routes(route_attrs: List[Any], content_bytes: bytes) -> List[Tuple[List[str], Optional[str]]]:
    """(verbs, template) for each route one action declares (BACK-1418).

    A verb attribute with a template is a route of its own; a [Route] (or an
    [AcceptVerbs] Route=) template answers the action's template-less verbs,
    or ANY; template-less verbs with no [Route] answer the controller prefix
    itself (template None). Before, the attributes were folded into one entry
    with the last verb seen, so a stacked [HttpHead] vanished.
    """
    templated: List[Tuple[List[str], Optional[str]]] = []
    bare_verbs: List[str] = []
    route_templates: List[Optional[str]] = []
    for attribute, attr_name in route_attrs:
        positional, named = _attribute_args(attribute, content_bytes)
        if attr_name == 'Route':
            route_templates.append(positional[0] if positional else named.get('Template'))
        elif attr_name == 'AcceptVerbs':
            verbs = [v.upper() for v in positional if v != '?'] or ['ANY']
            if 'Route' in named:
                templated.append((verbs, named['Route']))
            else:
                bare_verbs.extend(verbs)
        else:
            verb = _ASPNET_VERB_ATTRIBUTES[attr_name]
            template = positional[0] if positional else named.get('Template')
            if template is None:
                bare_verbs.append(verb)
            else:
                templated.append(([verb], template))
    routes = list(templated)
    for template in route_templates:
        routes.append((bare_verbs or ['ANY'], template))
    if not route_templates and bare_verbs:
        routes.append((bare_verbs, None))
    return routes


def _under_prefix(prefix: Optional[str], template: Optional[str]) -> Optional[str]:
    """ASP.NET: a template starting with '/' or '~/' ignores the controller's
    prefix; anything else is appended to it."""
    if template is not None and template.startswith(('/', '~/')):
        return template.lstrip('~')
    return join_route_path(prefix, template)
