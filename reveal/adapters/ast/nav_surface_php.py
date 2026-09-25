"""Tree-sitter surface extraction for PHP — env vars, HTTP routes, imports.

BACK-403 pt 2 (surface breadth). Mirrors nav_surface_java.py's categorised-dict
shape but walks PHP's grammar for the three dominant web frameworks:

- **Laravel** routes: ``Route::get('/path', ...)`` — a ``scoped_call_expression``
  whose receiver ``name`` is ``Route`` and whose method ``name`` is an HTTP verb.
- **Symfony** routes: the ``#[Route('/path', methods: ['GET'])]`` attribute — an
  ``attribute`` node (inside ``attribute_group``/``attribute_list``) named
  ``Route`` on a method. On the class it is the prefix of every method route.
- **WordPress** REST routes: ``register_rest_route('ns/v1', '/data', ...)`` — a
  bare ``function_call_expression``. Namespace and route are evaluated
  (``_eval_string``) through ``.``, ``sprintf`` and the enclosing class's
  ``$this->prop`` / ``self::CONST`` literals; an unresolvable part stays in the
  path as ``{$expr}``. Methods come from the endpoint arrays' ``'methods'``
  (``WP_REST_Server::READABLE`` etc.), GET when an endpoint names none.

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
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from .nav_surface_common import disclose_parse_recovery, _get_text, _get_line, _add_once, join_route_path
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

# WP_REST_Server's method constants (wp-includes/rest-api/class-wp-rest-server.php).
_WP_REST_METHOD_CONSTANTS: Dict[str, str] = {
    'READABLE': 'GET',
    'CREATABLE': 'POST',
    'EDITABLE': 'POST, PUT, PATCH',
    'DELETABLE': 'DELETE',
    'ALLMETHODS': 'GET, POST, PUT, PATCH, DELETE',
}

_CLASS_KINDS = ('class_declaration', 'anonymous_class')
# A placeholder longer than this is shown as `{…}`, not as its source text.
_PLACEHOLDER_MAX = 40
_EVAL_MAX_DEPTH = 8


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
    return disclose_parse_recovery(tree, file_path, _scan_tree(tree, file_path, content_bytes))


def _scan_tree(tree: Any, file_path: str, content_bytes: bytes) -> Dict[str, List[Dict[str, Any]]]:
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in _EMPTY_KEYS}
    rules = RuleScan('php', content_bytes)
    rule_kinds, visit = rules.kinds, rules.visit

    # Pre-order walk: a class is seen before anything inside it, so the
    # innermost enclosing class of a call is the last one containing it.
    classes: List['_ClassScope'] = []

    def scope_of(node: Any) -> Optional['_ClassScope']:
        start = _zero_arg(node, 'start_byte')
        for cls in reversed(classes):
            if cls.start <= start < cls.end:
                return cls
        return None

    stack = [tree_root(tree)]
    while stack:
        node = stack.pop()
        kind = _zero_arg(node, 'kind')
        if kind in rule_kinds:
            visit(node, kind)

        if kind in _CLASS_KINDS:
            classes.append(_ClassScope(node, content_bytes))
        elif kind == 'scoped_call_expression':
            _process_scoped_call(node, file_path, content_bytes, surfaces, scope_of)
        elif kind == 'function_call_expression':
            _process_function_call(node, file_path, content_bytes, surfaces, scope_of)
        elif kind == 'shell_command_expression':
            _add_once(surfaces['subprocess'], {
                'type': 'subprocess', 'name': '`...`',
                'file': file_path, 'line': _get_line(node),
            })
        elif kind == 'attribute':
            _process_attribute(node, file_path, content_bytes, surfaces, scope_of)
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
                         surfaces: Dict[str, List[Dict[str, Any]]], scope_of: Any) -> None:
    receiver, method = _scoped_call_names(node, content_bytes)
    if receiver != 'Route' or method not in _LARAVEL_ROUTE_VERBS:
        return
    values = _argument_values(_arguments_child(node))
    path = _eval_string(values[0], content_bytes, scope_of(node))[0] if values else '?'
    surfaces['http'].append({
        'type': 'route',
        'name': method,
        'path': path,
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
                           surfaces: Dict[str, List[Dict[str, Any]]], scope_of: Any) -> None:
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
    elif fname == 'register_rest_route':
        route = _wp_rest_route(_argument_values(args), content_bytes, scope_of(node))
        if route is not None:
            surfaces['http'].append({**route, 'file': file_path, 'line': _get_line(node)})


def _wp_rest_route(values: List[Any], content_bytes: bytes,
                   scope: Optional['_ClassScope']) -> Optional[Dict[str, Any]]:
    """register_rest_route($namespace, $route, $args): the route is served at
    '/' . trim($namespace, '/') . '/' . trim($route, '/').

    Core and plugins build both from `$this->namespace` / `$this->rest_base`
    and `sprintf`, not literals (84 of WordPress core's 86 calls). Resolved
    parts are joined; an unresolvable part stays in the path as `{$expr}` --
    the route is reported, never dropped (BACK-1417).
    """
    if not values:
        return None
    namespace = _eval_string(values[0], content_bytes, scope)[0].strip('/')
    route = _eval_string(values[1], content_bytes, scope)[0].strip('/') if len(values) > 1 else ''
    path = '/' + '/'.join(p for p in (namespace, route) if p)
    endpoints = values[2] if len(values) > 2 else None
    return {
        'type': 'route', 'name': 'register_rest_route', 'path': path,
        'methods': _wp_route_methods(endpoints, content_bytes, scope),
        'decorator': 'register_rest_route',
    }


def _wp_route_methods(endpoints: Optional[Any], content_bytes: bytes,
                      scope: Optional['_ClassScope']) -> str:
    """The verbs a register_rest_route $args array declares. $args is one
    endpoint (it has 'methods' or 'callback') or a list of endpoint arrays; an
    endpoint without 'methods' answers GET (register_rest_route's default)."""
    if endpoints is None or _zero_arg(endpoints, 'kind') != 'array_creation_expression':
        return 'ANY'
    entries = _array_entries(endpoints, content_bytes)
    if any(key in ('methods', 'callback') for key, _ in entries):
        arrays = [endpoints]
    else:
        arrays = [value for key, value in entries
                  if key is None and _zero_arg(value, 'kind') == 'array_creation_expression']
    verbs: List[str] = []
    for endpoint in arrays:
        declared = next((value for key, value in _array_entries(endpoint, content_bytes)
                         if key == 'methods'), None)
        found = ['GET'] if declared is None else _wp_method_values(declared, content_bytes, scope)
        verbs.extend(v for v in found if v not in verbs)
    named = [v for v in verbs if v != 'ANY']
    return '|'.join(named) if named else 'ANY'


def _wp_method_values(node: Any, content_bytes: bytes, scope: Optional['_ClassScope']) -> List[str]:
    """'GET', 'POST, PUT', WP_REST_Server::EDITABLE, or an array of those."""
    kind = _zero_arg(node, 'kind')
    if kind == 'array_creation_expression':
        out: List[str] = []
        for _, value in _array_entries(node, content_bytes):
            out.extend(v for v in _wp_method_values(value, content_bytes, scope) if v not in out)
        return out
    if kind == 'class_constant_access_expression':
        names = [_get_text(c, content_bytes) for c in _children(node)
                 if _zero_arg(c, 'kind') in ('name', 'relative_scope', 'qualified_name')]
        if len(names) == 2 and names[0].lstrip('\\') in ('WP_REST_Server', 'self', 'static') \
                and names[1] in _WP_REST_METHOD_CONSTANTS:
            return _split_verbs(_WP_REST_METHOD_CONSTANTS[names[1]])
    text, resolved = _eval_string(node, content_bytes, scope)
    return _split_verbs(text) if resolved else ['ANY']


def _split_verbs(text: str) -> List[str]:
    return [v.upper() for v in re.split(r'[\s,|]+', text) if v]


def _argument_values(arguments_node: Optional[Any]) -> List[Any]:
    """The expression of each argument, in order (a named `ns: 'x'` argument's
    expression is its last child)."""
    if arguments_node is None:
        return []
    out = []
    for arg in _children(arguments_node):
        if _zero_arg(arg, 'kind') == 'argument':
            kids = _children(arg)
            if kids:
                out.append(kids[-1])
    return out


def _array_entries(array_node: Any, content_bytes: bytes) -> List[tuple]:
    """(key, value) per element of an array_creation_expression; key is the
    string key's text, None for a positional element or a non-literal key."""
    entries = []
    for element in _children(array_node):
        if _zero_arg(element, 'kind') != 'array_element_initializer':
            continue
        kids = [c for c in _children(element) if _zero_arg(c, 'kind') != '=>']
        if not kids:
            continue
        if len(kids) >= 2:
            key_node = kids[0]
            key = _string_content(key_node, content_bytes) \
                if _zero_arg(key_node, 'kind') in ('string', 'encapsed_string') else None
            entries.append((key, kids[-1]))
        else:
            entries.append((None, kids[0]))
    return entries


class _ClassScope:
    """The literal values a class gives its constants and `$this->` properties.

    WordPress REST controllers set `$this->namespace = 'wp/v2';` and
    `$this->rest_base = 'posts';` in the constructor, then build every route
    from them. A property resolves only when every value the class gives it
    (declaration default, `$this->x = ...` anywhere in its body) is the same
    literal; anything else -- a ternary, an inherited value, `.=` -- stays
    unresolved rather than guessed.
    """

    def __init__(self, class_node: Any, content_bytes: bytes) -> None:
        self.start = _zero_arg(class_node, 'start_byte')
        self.end = _zero_arg(class_node, 'end_byte')
        self.content_bytes = content_bytes
        name = next((c for c in _children(class_node) if _zero_arg(c, 'kind') == 'name'), None)
        self.name = _get_text(name, content_bytes) if name is not None else None
        self.consts: Dict[str, Any] = {}
        self.props: Dict[str, List[Optional[Any]]] = {}
        self._resolving: set = set()
        # Symfony: the class's own #[Route] is the prefix of its method routes.
        self.route_prefix: Optional[str] = None
        self.route_attributes: set = set()
        for attr_list in _children(class_node):
            if _zero_arg(attr_list, 'kind') != 'attribute_list':
                continue
            for group in _children(attr_list):
                for attr in _children(group):
                    route = _route_attribute(attr, content_bytes) \
                        if _zero_arg(attr, 'kind') == 'attribute' else None
                    if route is not None:
                        self.route_attributes.add(_zero_arg(attr, 'start_byte'))
                        if self.route_prefix is None:
                            self.route_prefix = route[0] or ''
        body = next((c for c in _children(class_node)
                     if _zero_arg(c, 'kind') == 'declaration_list'), None)
        if body is not None:
            self._collect(body)

    def _collect(self, body: Any) -> None:
        for member in _children(body):
            kind = _zero_arg(member, 'kind')
            if kind == 'const_declaration':
                for element in _children(member):
                    if _zero_arg(element, 'kind') == 'const_element':
                        kids = _children(element)
                        if len(kids) >= 3 and _zero_arg(kids[0], 'kind') == 'name':
                            self.consts[_get_text(kids[0], self.content_bytes)] = kids[-1]
            elif kind == 'property_declaration':
                for element in _children(member):
                    if _zero_arg(element, 'kind') != 'property_element':
                        continue
                    kids = _children(element)
                    prop = self._var_name(kids[0]) if kids else None
                    if prop and len(kids) >= 3:
                        self.props.setdefault(prop, []).append(kids[-1])
        stack = list(_children(body))
        while stack:
            node = stack.pop()
            kind = _zero_arg(node, 'kind')
            if kind in _CLASS_KINDS:
                continue  # a nested class's $this is not ours
            if kind in ('assignment_expression', 'augmented_assignment_expression'):
                kids = _children(node)
                prop = self._this_member(kids[0]) if kids else None
                if prop:
                    value = kids[-1] if kind == 'assignment_expression' else None
                    self.props.setdefault(prop, []).append(value)
            stack.extend(_children(node))

    def _var_name(self, node: Any) -> Optional[str]:
        if _zero_arg(node, 'kind') != 'variable_name':
            return None
        return _get_text(node, self.content_bytes).lstrip('$')

    def _this_member(self, node: Any) -> Optional[str]:
        """`x` for `$this->x`, else None."""
        if _zero_arg(node, 'kind') != 'member_access_expression':
            return None
        kids = _children(node)
        if len(kids) < 3 or _get_text(kids[0], self.content_bytes) != '$this' \
                or _zero_arg(kids[-1], 'kind') != 'name':
            return None
        return _get_text(kids[-1], self.content_bytes)

    def _single_literal(self, key: str, values: List[Optional[Any]], depth: int) -> Optional[str]:
        if not values or None in values or key in self._resolving:
            return None
        self._resolving.add(key)
        try:
            texts = set()
            for value in values:
                text, resolved = _eval_string(value, self.content_bytes, self, depth + 1)
                if not resolved:
                    return None
                texts.add(text)
            return texts.pop() if len(texts) == 1 else None
        finally:
            self._resolving.discard(key)

    def prop(self, name: str, depth: int) -> Optional[str]:
        return self._single_literal('$' + name, self.props.get(name, []), depth)

    def const(self, name: str, depth: int) -> Optional[str]:
        node = self.consts.get(name)
        return self._single_literal(name, [node] if node is not None else [], depth)


def _placeholder(node: Any, content_bytes: bytes) -> str:
    text = ' '.join(_get_text(node, content_bytes).split())
    return '{' + text + '}' if len(text) <= _PLACEHOLDER_MAX else '{…}'


def _eval_string(node: Any, content_bytes: bytes, scope: Optional[_ClassScope],
                 depth: int = 0) -> tuple:
    """(text, resolved) for a PHP string expression: literals, `.`
    concatenation, sprintf with %s/%d, and the enclosing class's
    `$this->prop` / `self::CONST`. An unresolvable part becomes `{source}`
    and makes the whole unresolved."""
    handler = _EVALUATORS.get(_zero_arg(node, 'kind'))
    if handler is not None and depth <= _EVAL_MAX_DEPTH:
        result: Optional[tuple] = handler(node, content_bytes, scope, depth)
        if result is not None:
            return result
    return _placeholder(node, content_bytes), False


def _eval_single_quoted(node: Any, content_bytes: bytes, scope: Any, depth: int) -> tuple:
    text = _get_text(node, content_bytes)
    if text[:1] in ('b', 'B'):
        text = text[1:]
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("\\'", "'").replace('\\\\', '\\'), True
    return _string_content(node, content_bytes), True


def _eval_double_quoted(node: Any, content_bytes: bytes, scope: Any, depth: int) -> tuple:
    """`"/items/{$id}"`: literal runs as written, each interpolation evaluated."""
    parts, resolved = [], True
    for ch in _children(node):
        ch_kind = _zero_arg(ch, 'kind')
        if ch_kind in ('"', '{', '}'):
            continue
        if ch_kind in ('string_content', 'escape_sequence'):
            parts.append(_get_text(ch, content_bytes))
            continue
        text, ok = _eval_string(ch, content_bytes, scope, depth + 1)
        parts.append(text)
        resolved = resolved and ok
    return ''.join(parts), resolved


def _eval_parenthesized(node: Any, content_bytes: bytes, scope: Any, depth: int) -> Optional[tuple]:
    inner = [c for c in _children(node) if _zero_arg(c, 'kind') not in ('(', ')')]
    return _eval_string(inner[0], content_bytes, scope, depth + 1) if len(inner) == 1 else None


def _eval_concat(node: Any, content_bytes: bytes, scope: Any, depth: int) -> Optional[tuple]:
    kids = _children(node)
    if len(kids) != 3 or _get_text(kids[1], content_bytes) != '.':
        return None
    left, left_ok = _eval_string(kids[0], content_bytes, scope, depth + 1)
    right, right_ok = _eval_string(kids[2], content_bytes, scope, depth + 1)
    return left + right, left_ok and right_ok


def _eval_this_property(node: Any, content_bytes: bytes, scope: Any, depth: int) -> Optional[tuple]:
    prop = scope._this_member(node) if scope is not None else None
    value = scope.prop(prop, depth) if prop else None
    return (value, True) if value is not None else None


def _eval_class_constant(node: Any, content_bytes: bytes, scope: Any,
                         depth: int) -> Optional[tuple]:
    kids = _children(node)
    if scope is None or len(kids) != 3 \
            or _get_text(kids[0], content_bytes) not in ('self', 'static', scope.name):
        return None
    value = scope.const(_get_text(kids[-1], content_bytes), depth)
    return (value, True) if value is not None else None


def _eval_sprintf(node: Any, content_bytes: bytes, scope: Optional[_ClassScope],
                  depth: int) -> Optional[tuple]:
    """sprintf('/%s/%s', a, b) with a literal format using only %s/%d/%%."""
    kids = _children(node)
    if not kids or _get_text(kids[0], content_bytes).lstrip('\\') != 'sprintf':
        return None
    values = _argument_values(_arguments_child(node))
    if not values:
        return None
    fmt, fmt_ok = _eval_string(values[0], content_bytes, scope, depth + 1)
    if not fmt_ok or any(t not in ('%%', '%s', '%d') for t in re.findall(r'%.?', fmt)):
        return None
    args = iter(values[1:])
    resolved = True
    out: List[str] = []
    pos = 0
    for m in re.finditer(r'%.?', fmt):
        out.append(fmt[pos:m.start()])
        pos = m.end()
        if m.group() == '%%':
            out.append('%')
            continue
        arg = next(args, None)
        if arg is None:
            return None
        text, ok = _eval_string(arg, content_bytes, scope, depth + 1)
        out.append(text)
        resolved = resolved and ok
    out.append(fmt[pos:])
    return ''.join(out), resolved


_EVALUATORS: Dict[str, Any] = {
    'string': _eval_single_quoted,
    'encapsed_string': _eval_double_quoted,
    'parenthesized_expression': _eval_parenthesized,
    'binary_expression': _eval_concat,
    'member_access_expression': _eval_this_property,
    'class_constant_access_expression': _eval_class_constant,
    'function_call_expression': _eval_sprintf,
}


def _process_attribute(node: Any, file_path: str, content_bytes: bytes,
                       surfaces: Dict[str, List[Dict[str, Any]]], scope_of: Any) -> None:
    # Symfony #[Route('/path', methods: ['GET'])] on a method; on the class it
    # is the prefix of every method route in it, not a route (BACK-1417).
    route = _route_attribute(node, content_bytes)
    if route is None:
        return
    scope = scope_of(node)
    if scope is not None and _zero_arg(node, 'start_byte') in scope.route_attributes:
        return
    path, methods = route
    if scope is not None:
        path = join_route_path(scope.route_prefix, path)
    surfaces['http'].append({
        'type': 'route', 'name': 'Route', 'path': path or '?',
        'methods': methods, 'decorator': '#[Route]',
        'file': file_path, 'line': _get_line(node),
    })


def _route_attribute(node: Any, content_bytes: bytes) -> Optional[tuple]:
    """(path, methods) of a `#[Route(...)]` attribute node, None for any other
    attribute. path is None when the attribute names none."""
    name_node = None
    for ch in _children(node):
        if _zero_arg(ch, 'kind') == 'name':
            name_node = ch
            break
    if name_node is None or _get_text(name_node, content_bytes) != 'Route':
        return None
    args = _arguments_child(node)
    path = None
    methods = 'ANY'
    for arg in _children(args) if args is not None else []:
        if _zero_arg(arg, 'kind') != 'argument':
            continue
        arg_children = _children(arg)
        # named arg `methods: [...]` carries a leading `name` child
        named = next((c for c in arg_children if _zero_arg(c, 'kind') == 'name'), None)
        arg_name = _get_text(named, content_bytes) if named is not None else None
        if arg_name == 'methods':
            verbs = _array_string_texts(arg, content_bytes)
            if verbs:
                methods = '|'.join(v.upper() for v in verbs)
        elif path is None and arg_name in (None, 'path'):
            # Only the first positional argument or `path:` is the path --
            # `name: 'app_home'` / `requirements: [...]` are not.
            for sub in arg_children:
                if _zero_arg(sub, 'kind') == 'string':
                    path = _string_content(sub, content_bytes)
    return path, methods


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
