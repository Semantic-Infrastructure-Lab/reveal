"""Rails routing DSL interpreter for surface `http` (BACK-1417).

A ``routes.draw do ... end`` block is a program, not a list of route lines:
``resources :users`` declares up to 8 routes, ``namespace``/``scope`` prefix
everything inside them, and a bare ``get "x"`` means a different path in a
``resources`` block (nested, ``/users/:user_id/x``), in ``member`` (``/users/:id/x``)
and in ``collection`` (``/users/x``). Reading only ``get '/path'`` lines found 13 of
Discourse's 1,121 routes.

This walks the block the way ``ActionDispatch::Routing::Mapper`` evaluates it:

- verbs (``get``/``post``/``put``/``patch``/``delete``/``options``) and ``match``
  (``via:``), ``root``, ``mount`` (any verb);
- ``resources``/``resource`` (``only:``/``except:``/``path:``/``param:``/
  ``controller:``), with ``member``/``collection``/``new`` blocks, ``on:``, and
  nesting (``Mapper#decomposed_match``: a route directly inside ``resources`` is
  nested under ``:<singular>_id``, directly inside ``resource`` it is a member);
- ``namespace``/``scope``/``controller``/``constraints``/``defaults`` blocks,
  ``concern``/``concerns``;
- Ruby around the DSL: both branches of ``if``/``unless``/``case`` (each route
  under one carries its ``condition``), a loop over a literal array unrolled
  (``%w[users u].each do |root_path|``), a local assigned a literal
  (``base = "/c/:id"``), and a draw-level ``def patch(*); end`` that disables
  a verb, as Discourse does.

A path part that is not a literal (an interpolated variable no literal loop
binds) is kept as ``{expr}`` -- the route is reported, never dropped or guessed.
Routes of an engine (``MyEngine.routes.draw``) are relative to wherever the app
mounts it; their paths start with ``{MyEngine}``.
"""

import re
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from .nav_surface_common import _get_text, _get_line

from reveal.core import node_children as _children
from reveal.core.treesitter_compat import _zero_arg

_VERBS = ('get', 'post', 'put', 'patch', 'delete', 'options')
_CANONICAL_ACTIONS = ('index', 'create', 'new', 'show', 'update', 'destroy')
_ROUTE_BLOCK_METHODS = ('draw', 'append', 'prepend')
_LOOP_METHODS = ('each', 'each_with_index')
_CONTROL_KINDS = ('then', 'else', 'case', 'when', 'begin', 'parenthesized_statements',
                  'body_statement', 'block_body', 'do_block', 'block')
_PLACEHOLDER_MAX = 40
_MAX_DEPTH = 40

# (action, verbs, scope) per resource kind, in Mapper#resources' order.
_PLURAL_ACTIONS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ('index', ('GET',), 'collection'),
    ('create', ('POST',), 'collection'),
    ('new', ('GET',), 'new'),
    ('edit', ('GET',), 'member'),
    ('show', ('GET',), 'member'),
    ('update', ('PATCH', 'PUT'), 'member'),
    ('destroy', ('DELETE',), 'member'),
)
_SINGULAR_ACTIONS: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ('create', ('POST',), 'collection'),
    ('new', ('GET',), 'new'),
    ('edit', ('GET',), 'member'),
    ('show', ('GET',), 'member'),
    ('update', ('PATCH', 'PUT'), 'member'),
    ('destroy', ('DELETE',), 'member'),
)


def is_route_block(node: Any, content_bytes: bytes) -> bool:
    """`X.routes.draw do ... end` (also `.append`/`.prepend`)."""
    kids = _children(node)
    method = next((c for c in kids if _zero_arg(c, 'kind') == 'identifier'), None)
    if method is None or _get_text(method, content_bytes) not in _ROUTE_BLOCK_METHODS:
        return False
    receiver = kids[0] if kids else None
    if receiver is None or _zero_arg(receiver, 'kind') != 'call' \
            or not _get_text(receiver, content_bytes).endswith('.routes'):
        return False
    return _block_of(node) is not None


def scan_route_block(node: Any, content_bytes: bytes, file_path: str) -> List[Dict[str, Any]]:
    """Every route a `routes.draw` block declares."""
    receiver = _get_text(_children(node)[0], content_bytes)
    owner = receiver[:-len('.routes')]
    is_app = owner.endswith('::Application') or owner in ('Rails.application', 'Rails::Application')
    interp = _Interpreter(content_bytes, file_path)
    body = _block_body(_block_of(node))
    interp.disabled_verbs = _disabled_verbs(body, content_bytes)
    root = _Scope(path='' if is_app else '{' + owner.lstrip(':') + '}')
    interp.run(body, root, {})
    return interp.routes


@dataclass(frozen=True)
class _Resource:
    name: str
    singular: bool
    path: str
    param: str
    controller: str
    actions: Tuple[str, ...]

    def member_path(self) -> str:
        return self.path if self.singular else f'{self.path}/:{self.param}'

    def nested_path(self) -> str:
        if self.singular:
            return self.path
        return f'{self.path}/:{_singularize(self.name)}_{self.param}'


@dataclass(frozen=True)
class _Scope:
    path: str = ''
    module: str = ''
    level: Optional[str] = None  # resources | resource | member | collection | new | nested
    resource: Optional[_Resource] = None
    concerns: Dict[str, Any] = field(default_factory=dict, compare=False)


class _Interpreter:
    def __init__(self, content_bytes: bytes, file_path: str) -> None:
        self.content_bytes = content_bytes
        self.file_path = file_path
        self.routes: List[Dict[str, Any]] = []
        self.disabled_verbs: frozenset = frozenset()
        self.condition: Optional[str] = None  # the if/unless a route sits under
        self.depth = 0
        self._calls: Dict[str, Callable[..., None]] = {
            'match': self._match, 'root': self._root, 'mount': self._mount,
            'resources': self._resources, 'resource': self._resources,
            'namespace': self._namespace, 'scope': self._scope,
            'controller': self._transparent, 'constraints': self._transparent,
            'defaults': self._transparent, 'with_options': self._transparent,
            'member': self._level_block, 'collection': self._level_block,
            'new': self._level_block, 'nested': self._level_block,
            'concern': self._concern, 'concerns': self._concerns,
        }

    # -- statements -------------------------------------------------------

    def run(self, node: Optional[Any], scope: _Scope, env: Dict[str, Optional[str]]) -> None:
        if node is None or self.depth > _MAX_DEPTH:
            return
        self.depth += 1
        try:
            for stmt in _children(node):
                self._statement(stmt, scope, env)
        finally:
            self.depth -= 1

    def _statement(self, stmt: Any, scope: _Scope, env: Dict[str, Optional[str]]) -> None:
        kind = _zero_arg(stmt, 'kind')
        if kind == 'call':
            self._call(stmt, scope, env)
        elif kind in ('if', 'unless', 'elsif', 'if_modifier', 'unless_modifier'):
            self._conditional(stmt, kind, scope, env)
        elif kind == 'assignment':
            # `base = "/c/:id"` then `get "#{base}/x"`: a local bound to a
            # literal is substituted; bound to anything else, it is unknown.
            kids = _children(stmt)
            if kids and _zero_arg(kids[0], 'kind') == 'identifier':
                env[_get_text(kids[0], self.content_bytes)] = \
                    _literal(kids[-1], self.content_bytes, env)
        elif kind in _CONTROL_KINDS:
            self.run(stmt, scope, env)

    def _conditional(self, stmt: Any, kind: str, scope: _Scope,
                     env: Dict[str, Optional[str]]) -> None:
        """Both branches are reported -- the environment is not known
        statically -- and each route under one carries the condition it needs
        (`if Rails.env.test?`), so a test-only route does not read as live."""
        kids = [c for c in _children(stmt) if _zero_arg(c, 'is_named')]
        if len(kids) < 2:
            return
        if kind.endswith('_modifier'):
            cond_node, branches = kids[-1], [(kids[0], True)]
        else:
            cond_node = kids[0]
            branches = [(k, _zero_arg(k, 'kind') == 'then') for k in kids[1:]
                        if _zero_arg(k, 'kind') in ('then', 'else', 'elsif')]
        text = ' '.join(_get_text(cond_node, self.content_bytes).split())
        if len(text) > _PLACEHOLDER_MAX:
            text = text[:_PLACEHOLDER_MAX] + '…'
        negated = kind.startswith('unless')
        cond = f'unless {text}' if negated else f'if {text}'
        other = f'if {text}' if negated else f'unless {text}'
        outer = self.condition
        try:
            for branch, taken in branches:
                here = cond if taken else other
                self.condition = f'{outer} and {here}' if outer else here
                self._statement(branch, scope, env)
        finally:
            self.condition = outer

    def _call(self, node: Any, scope: _Scope, env: Dict[str, Optional[str]]) -> None:
        has_receiver = any(_zero_arg(c, 'kind') == '.' for c in _children(node))
        method = _call_name(node, self.content_bytes)
        if has_receiver:
            if method in _LOOP_METHODS or _block_of(node) is not None:
                self._loop(node, method, scope, env)
            return
        args = _arg_list(node)
        if method in _VERBS:
            self._verb(node, method, args, scope, env)
        elif method in self._calls:
            self._calls[method](node, method, args, scope, env)
        elif _block_of(node) is not None:
            self.run(_block_body(_block_of(node)), scope, env)

    def _loop(self, node: Any, method: str, scope: _Scope, env: Dict[str, Optional[str]]) -> None:
        """`%w[a b].each do |x| ... end` runs once per element with x bound;
        any other block runs once with its parameters unbound."""
        block = _block_of(node)
        if block is None:
            return
        params = _block_params(block, self.content_bytes)
        receiver = _children(node)[0]
        values = _literal_list(receiver, self.content_bytes) if method in _LOOP_METHODS else None
        if values is None:
            self.run(_block_body(block), scope, {**env, **{p: None for p in params}})
            return
        for index, value in enumerate(values):
            bound = dict(env)
            if params:
                bound[params[0]] = value
            if len(params) > 1 and method == 'each_with_index':
                bound[params[1]] = str(index)
            self.run(_block_body(block), scope, bound)

    # -- routes -----------------------------------------------------------

    def _verb(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
              env: Dict[str, Optional[str]]) -> None:
        if method in self.disabled_verbs:
            return
        self._map(node, args, scope, env, (method.upper(),))

    def _match(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
               env: Dict[str, Optional[str]]) -> None:
        via = _option(args, 'via', self.content_bytes)
        verbs = _literal_list(via, self.content_bytes) if via is not None else None
        if verbs is None and via is not None:
            single = _literal(via, self.content_bytes, env)
            verbs = [single] if single else None
        if not verbs or 'all' in verbs:
            methods: Tuple[str, ...] = ('ANY',)
        else:
            methods = tuple(v.upper() for v in verbs if v not in self.disabled_verbs)
            if not methods:
                return
        self._map(node, args, scope, env, methods)

    def _root(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
              env: Dict[str, Optional[str]]) -> None:
        to = _option(args, 'to', self.content_bytes)
        positional = _positional(args)
        target_node = to if to is not None else (positional[0] if positional else None)
        target = _literal(target_node, self.content_bytes, env) if target_node is not None else None
        self._add(node, {'name': 'root', 'decorator': 'root', 'path': _join(scope.path, '/'),
                         'methods': ('GET',), 'target': target})

    def _mount(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
               env: Dict[str, Optional[str]]) -> None:
        at = _option(args, 'at', self.content_bytes)
        app = None
        if at is None:
            pair = _string_valued_pair(args, self.content_bytes)
            if pair is not None:
                app, at = pair
        else:
            positional = _positional(args)
            app = positional[0] if positional else None
        if at is None:
            return
        path = self._text(at, env)
        app_text = _get_text(app, self.content_bytes) if app is not None else None
        self._add(node, {'name': 'mount', 'decorator': 'mount', 'path': _join(scope.path, path),
                         'methods': ('ANY',), 'target': app_text})

    def _map(self, node: Any, args: Optional[Any], scope: _Scope,
             env: Dict[str, Optional[str]], methods: Tuple[str, ...]) -> None:
        """Mapper#match: `get "p" => "c#a"`, `get "p", to: "c#a"`, `get :action`."""
        method = _call_name(node, self.content_bytes)
        path_node, target = self._path_and_target(args, env)
        if path_node is None:
            return
        if target and '#' in target:
            target = scope.module + target  # `to:` is relative to the namespace's module
        on = _option(args, 'on', self.content_bytes)
        on_level = _literal(on, self.content_bytes, env) if on is not None else None
        is_symbol = _zero_arg(path_node, 'kind') == 'simple_symbol'
        segment = self._text(path_node, env)
        route_scope = self._decomposed_scope(scope, on_level)
        if is_symbol and route_scope.level in ('collection', 'member', 'new') \
                and segment in _CANONICAL_ACTIONS:
            path = route_scope.path or '/'
        else:
            path = _join(route_scope.path, segment)
        self._add(node, {'name': segment if is_symbol else method, 'decorator': method,
                         'path': path, 'methods': methods, 'target': target})

    def _decomposed_scope(self, scope: _Scope, on: Optional[str]) -> _Scope:
        """Mapper#decomposed_match: `on:` enters that scope; directly inside
        `resources` a route is nested, directly inside `resource` a member."""
        if on in ('member', 'collection', 'new') and scope.resource is not None:
            return self._enter(scope, on)
        if scope.level == 'resources':
            return self._enter(scope, 'nested')
        if scope.level == 'resource':
            return self._enter(scope, 'member')
        return scope

    def _path_and_target(self, args: Optional[Any],
                         env: Dict[str, Optional[str]]) -> Tuple[Optional[Any], Optional[str]]:
        pair = _string_valued_pair(args, self.content_bytes)
        if pair is not None:
            path_node, to_node = pair
        else:
            positional = _positional(args)
            path_node = positional[0] if positional else None
            to_node = _option(args, 'to', self.content_bytes)
        target = _literal(to_node, self.content_bytes, env) if to_node is not None else None
        return path_node, target

    # -- resources --------------------------------------------------------

    def _resources(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
                   env: Dict[str, Optional[str]]) -> None:
        names = [n for n in (_literal(p, self.content_bytes, env) for p in _positional(args)) if n]
        if not names:
            return
        if scope.level in ('resources', 'resource'):
            scope = self._enter(scope, 'nested')
        singular = method == 'resource'
        for name in names:
            resource = self._resource(name, singular, args, env)
            inner = replace(scope, level=method, resource=resource)
            block = _block_of(node)
            if block is not None:
                self.run(_block_body(block), inner, env)
            for concern in _literal_list(_option(args, 'concerns', self.content_bytes),
                                         self.content_bytes) or []:
                self._replay_concern(concern, inner, env)
            actions = _SINGULAR_ACTIONS if singular else _PLURAL_ACTIONS
            for action, verbs, level in actions:
                if action not in resource.actions:
                    continue
                verbs = tuple(v for v in verbs if v.lower() not in self.disabled_verbs)
                if not verbs:
                    continue
                at = self._enter(inner, level)
                path = at.path if action != 'edit' else _join(at.path, 'edit')
                target = f'{scope.module}{resource.controller}#{action}'
                self._add(node, {'name': action, 'decorator': method, 'path': path or '/',
                                 'methods': verbs, 'target': target})

    def _resource(self, name: str, singular: bool, args: Optional[Any],
                  env: Dict[str, Optional[str]]) -> _Resource:
        def opt(key: str) -> Optional[str]:
            value = _option(args, key, self.content_bytes)
            return _literal(value, self.content_bytes, env) if value is not None else None

        defaults = [a for a, _, _ in (_SINGULAR_ACTIONS if singular else _PLURAL_ACTIONS)]
        only = _option(args, 'only', self.content_bytes)
        except_ = _option(args, 'except', self.content_bytes)
        if only is not None:
            actions = tuple(self._names(only, env))
        elif except_ is not None:
            skipped = set(self._names(except_, env))
            actions = tuple(a for a in defaults if a not in skipped)
        else:
            actions = tuple(defaults)
        path = opt('path')
        controller = opt('controller') or (_pluralize(name) if singular else name)
        return _Resource(name=name, singular=singular, path=name if path is None else path,
                         param=opt('param') or 'id', controller=controller, actions=actions)

    def _names(self, node: Any, env: Dict[str, Optional[str]]) -> List[str]:
        listed = _literal_list(node, self.content_bytes)
        if listed is not None:
            return listed
        single = _literal(node, self.content_bytes, env)
        return [single] if single else []

    def _enter(self, scope: _Scope, level: str) -> _Scope:
        """Mapper's member/collection/new/nested scopes of the current resource."""
        resource = scope.resource
        if resource is None:
            return replace(scope, level=level)
        if level == 'member':
            segment = resource.member_path()
        elif level == 'new':
            segment = f'{resource.path}/new'
        elif level == 'nested':
            segment = resource.nested_path()
        else:
            segment = resource.path
        return replace(scope, level=level, path=_join(scope.path, segment))

    def _level_block(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
                     env: Dict[str, Optional[str]]) -> None:
        block = _block_of(node)
        if block is not None and scope.resource is not None:
            self.run(_block_body(block), self._enter(scope, method), env)

    # -- scopes -----------------------------------------------------------

    def _namespace(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
                   env: Dict[str, Optional[str]]) -> None:
        positional = _positional(args)
        name = _literal(positional[0], self.content_bytes, env) if positional else None
        if name is None:
            return
        path_opt = _option(args, 'path', self.content_bytes)
        segment = name if path_opt is None else (_literal(path_opt, self.content_bytes, env) or '')
        module_opt = _option(args, 'module', self.content_bytes)
        module = _literal(module_opt, self.content_bytes, env) if module_opt is not None else name
        inner = replace(scope, path=_join(scope.path, segment),
                        module=scope.module + (f'{module}/' if module else ''))
        self.run(_block_body(_block_of(node)), inner, env)

    def _scope(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
               env: Dict[str, Optional[str]]) -> None:
        """Mapper#scope: a positional path, or `path:` (nil changes nothing)."""
        positional = [p for p in _positional(args)
                      if _zero_arg(p, 'kind') in ('string', 'simple_symbol')]
        path_opt = _option(args, 'path', self.content_bytes)
        segment = ''
        if positional:
            segment = '/'.join(self._text(p, env) for p in positional)
        elif path_opt is not None and _zero_arg(path_opt, 'kind') != 'nil':
            segment = self._text(path_opt, env)
        module_opt = _option(args, 'module', self.content_bytes)
        module = _literal(module_opt, self.content_bytes, env) if module_opt is not None else None
        inner = replace(scope, path=_join(scope.path, segment) if segment else scope.path,
                        module=scope.module + (f'{module}/' if module else ''))
        self.run(_block_body(_block_of(node)), inner, env)

    def _transparent(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
                     env: Dict[str, Optional[str]]) -> None:
        self.run(_block_body(_block_of(node)), scope, env)

    def _concern(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
                 env: Dict[str, Optional[str]]) -> None:
        positional = _positional(args)
        name = _literal(positional[0], self.content_bytes, env) if positional else None
        block = _block_of(node)
        if name and block is not None:
            scope.concerns[name] = _block_body(block)

    def _concerns(self, node: Any, method: str, args: Optional[Any], scope: _Scope,
                  env: Dict[str, Optional[str]]) -> None:
        for p in _positional(args):
            for name in self._names(p, env):
                self._replay_concern(name, scope, env)

    def _replay_concern(self, name: str, scope: _Scope, env: Dict[str, Optional[str]]) -> None:
        body = scope.concerns.get(name)
        if body is not None:
            self.run(body, scope, env)

    # -- output -----------------------------------------------------------

    def _text(self, node: Any, env: Dict[str, Optional[str]]) -> str:
        value = _literal(node, self.content_bytes, env)
        return value if value is not None else _placeholder(node, self.content_bytes)

    def _add(self, node: Any, route: Dict[str, Any]) -> None:
        """Record a route: name, decorator, path, methods (a tuple), target."""
        entry = {'type': 'route', **route, 'methods': '|'.join(route['methods']),
                 'file': self.file_path, 'line': _get_line(node)}
        if self.condition:
            entry['condition'] = self.condition
        self.routes.append(entry)


_ENGINE_PREFIX = re.compile(r'^/?\{([A-Za-z_][\w:]*)\}')


def resolve_engine_mounts(http_entries: List[Dict[str, Any]]) -> None:
    """Re-path each engine route (`/{MyEngine}/x`) under the path the app
    mounts that engine at (`mount MyEngine, at: "/p"`), usually drawn in
    another file. An engine mounted at more than one path, or never, keeps
    its `{MyEngine}` prefix. `AdminEngine.routes.draw` written inside
    `module Plugin` matches a mount of `Plugin::AdminEngine` when no other
    mounted engine has that last name."""
    mounts: Dict[str, set] = {}
    for entry in http_entries:
        if entry.get('decorator') == 'mount' and entry.get('target'):
            mounts.setdefault(entry['target'].lstrip(':'), set()).add(entry['path'])
    by_last: Dict[str, List[str]] = {}
    for target in mounts:
        by_last.setdefault(target.rsplit('::', 1)[-1], []).append(target)
    for entry in http_entries:
        match = _ENGINE_PREFIX.match(entry.get('path') or '')
        if not match:
            continue
        engine = match.group(1)
        if engine not in mounts and '::' not in engine and len(by_last.get(engine, [])) == 1:
            engine = by_last[engine][0]
        paths = mounts.get(engine)
        if paths and len(paths) == 1:
            entry['path'] = _join(next(iter(paths)), entry['path'][match.end():])


# -- tree helpers -----------------------------------------------------------

def _call_name(node: Any, content_bytes: bytes) -> str:
    method = next((c for c in _children(node) if _zero_arg(c, 'kind') == 'identifier'), None)
    return _get_text(method, content_bytes) if method is not None else ''


def _block_of(node: Any) -> Optional[Any]:
    return next((c for c in _children(node) if _zero_arg(c, 'kind') in ('do_block', 'block')), None)


def _block_body(block: Optional[Any]) -> Optional[Any]:
    if block is None:
        return None
    return next((c for c in _children(block)
                 if _zero_arg(c, 'kind') in ('body_statement', 'block_body')), None)


def _block_params(block: Any, content_bytes: bytes) -> List[str]:
    params = next((c for c in _children(block) if _zero_arg(c, 'kind') == 'block_parameters'), None)
    if params is None:
        return []
    return [_get_text(c, content_bytes) for c in _children(params)
            if _zero_arg(c, 'kind') == 'identifier']


def _arg_list(node: Any) -> Optional[Any]:
    return next((c for c in _children(node) if _zero_arg(c, 'kind') == 'argument_list'), None)


def _positional(args: Optional[Any]) -> List[Any]:
    if args is None:
        return []
    return [c for c in _children(args)
            if _zero_arg(c, 'kind') not in ('pair', '(', ')', ',', 'block_argument')]


def _pair_key(pair: Any, content_bytes: bytes) -> Tuple[Optional[str], bool]:
    """(key, is_symbol) of `key: v` / `:key => v` / `"key" => v`."""
    key = _children(pair)[0]
    kind = _zero_arg(key, 'kind')
    if kind == 'hash_key_symbol':
        return _get_text(key, content_bytes), True
    if kind == 'simple_symbol':
        return _get_text(key, content_bytes).lstrip(':'), True
    return None, False


def _option(args: Optional[Any], key: str, content_bytes: bytes) -> Optional[Any]:
    """The value node of keyword option `key` among the call's arguments."""
    if args is None:
        return None
    for pair in _children(args):
        if _zero_arg(pair, 'kind') != 'pair':
            continue
        name, is_symbol = _pair_key(pair, content_bytes)
        if is_symbol and name == key:
            return _children(pair)[-1]
    return None


def _string_valued_pair(args: Optional[Any], content_bytes: bytes) -> Optional[Tuple[Any, Any]]:
    """`"path" => "c#a"` (Mapper#match takes the first non-symbol key), also
    inside a hash argument (`get({ "p" => "c#a" }.merge(opts))`); for mount,
    `App => "/path"` gives (App, "/path")."""
    if args is None:
        return None
    candidates = list(_children(args))
    for arg in list(candidates):
        kind = _zero_arg(arg, 'kind')
        if kind == 'hash':
            candidates.extend(_children(arg))
        elif kind == 'call' and _children(arg) and _zero_arg(_children(arg)[0], 'kind') == 'hash':
            candidates.extend(_children(_children(arg)[0]))
    for pair in candidates:
        if _zero_arg(pair, 'kind') != 'pair':
            continue
        _, is_symbol = _pair_key(pair, content_bytes)
        if not is_symbol:
            kids = _children(pair)
            return kids[0], kids[-1]
    return None


def _literal(node: Optional[Any], content_bytes: bytes,
             env: Optional[Dict[str, Optional[str]]] = None) -> Optional[str]:
    """A string/symbol literal's value; interpolations resolve through `env`
    (literal loop variables). None when any part is not a literal."""
    if node is None:
        return None
    kind = _zero_arg(node, 'kind')
    if kind == 'simple_symbol':
        return _get_text(node, content_bytes).lstrip(':')
    if kind in ('hash_key_symbol', 'bare_symbol', 'bare_string', 'identifier'):
        if kind == 'identifier':
            return (env or {}).get(_get_text(node, content_bytes))
        return _get_text(node, content_bytes)
    if kind == 'string':
        parts = []
        for ch in _children(node):
            ch_kind = _zero_arg(ch, 'kind')
            if ch_kind in ('string_content', 'escape_sequence'):
                parts.append(_get_text(ch, content_bytes))
            elif ch_kind == 'interpolation':
                inner = [c for c in _children(ch) if _zero_arg(c, 'kind') not in ('#{', '}')]
                value = _literal(inner[0], content_bytes, env) if len(inner) == 1 else None
                if value is None:
                    return None
                parts.append(value)
        return ''.join(parts)
    return None


def _literal_list(node: Optional[Any], content_bytes: bytes) -> Optional[List[str]]:
    """`%w[a b]`, `%i[a b]`, `[:a, "b"]` -> ['a', 'b']; None if not all literal."""
    if node is None:
        return None
    kind = _zero_arg(node, 'kind')
    if kind not in ('string_array', 'symbol_array', 'array'):
        return None
    out = []
    for ch in _children(node):
        ch_kind = _zero_arg(ch, 'kind')
        if ch_kind in ('%w(', '%i(', '[', ']', ',') or not _zero_arg(ch, 'is_named'):
            continue
        value = _literal(ch, content_bytes)
        if value is None:
            return None
        out.append(value)
    return out


def _disabled_verbs(body: Optional[Any], content_bytes: bytes) -> frozenset:
    """A draw-level `def patch(*); end` overrides Mapper#patch, so neither
    `patch "x"` nor a resource's PATCH update is ever added."""
    disabled = set()
    for stmt in _children(body) if body is not None else []:
        if _zero_arg(stmt, 'kind') != 'method':
            continue
        kids = [c for c in _children(stmt) if _zero_arg(c, 'is_named')]
        name = next((c for c in kids if _zero_arg(c, 'kind') == 'identifier'), None)
        has_body = any(_zero_arg(c, 'kind') in ('body_statement', 'block_body') for c in kids)
        if name is not None and not has_body and _get_text(name, content_bytes) in _VERBS:
            disabled.add(_get_text(name, content_bytes))
    return frozenset(disabled)


def _placeholder(node: Any, content_bytes: bytes) -> str:
    text = ' '.join(_get_text(node, content_bytes).split())
    for ch in _children(node) if _zero_arg(node, 'kind') == 'string' else []:
        if _zero_arg(ch, 'kind') == 'interpolation':
            return _interpolated_placeholder(node, content_bytes)
    return '{' + text + '}' if len(text) <= _PLACEHOLDER_MAX else '{…}'


def _interpolated_placeholder(node: Any, content_bytes: bytes) -> str:
    """"#{root}/x" -> "{root}/x": literal runs kept, each unknown part braced."""
    parts = []
    for ch in _children(node):
        kind = _zero_arg(ch, 'kind')
        if kind in ('string_content', 'escape_sequence'):
            parts.append(_get_text(ch, content_bytes))
        elif kind == 'interpolation':
            inner = ' '.join(_get_text(ch, content_bytes)[2:-1].split())
            parts.append('{' + (inner if len(inner) <= _PLACEHOLDER_MAX else '…') + '}')
    return ''.join(parts)


def _join(prefix: str, segment: str) -> str:
    """Mapper.normalize_path("#{prefix}/#{segment}"): one leading slash,
    repeated slashes squeezed, no trailing slash, and a slash before an
    optional group moved inside it (`/t/(:id)` is `/t(/:id)`)."""
    path = re.sub(r'/+', '/', f'/{prefix}/{segment}').rstrip('/') or '/'
    path = re.sub(r'/(\(+)/?', r'\1/', path)
    if re.fullmatch(r'(\(+[^)]+\))(\(+/:[^)]+\))*', path):
        path = re.sub(r'^(\(+)/', r'/\1', path)
    return path


def _singularize(word: str) -> str:
    """The inflector's common cases -- enough for `:<singular>_id` params."""
    if word.endswith('ies') and len(word) > 3:
        return word[:-3] + 'y'
    if re.search(r'(ss|x|z|ch|sh|us)es$', word):
        return word[:-2]
    if word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word


def _pluralize(word: str) -> str:
    if re.search(r'[^aeiou]y$', word):
        return word[:-1] + 'ies'
    if re.search(r'(s|x|z|ch|sh)$', word):
        return word + 'es'
    return word + 's'
