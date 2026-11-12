"""Canonical controls translate to the existing, resource-specific readers."""
from ...errors import RequestValidationError
from .resources import _parse_session_identifier


def apply_view(params, resource):
    view = params.pop('view', None)
    if view is None:
        return resource
    noun = resource.partition('/')[0]
    namespaces = ('files', 'history', 'info', 'settings', 'plans', 'config', 'memory',
                  'agents', 'hooks', 'sessions', 'search')
    if resource in ('', '.') or noun in namespaces:
        raise RequestValidationError('view is supported only on session resources')
    name, previous = _parse_session_identifier(resource)
    if not name or '/' in name:
        raise RequestValidationError('view requires a session identifier')
    target = '' if view in ('overview', 'search') else view
    if previous and previous != target:
        raise RequestValidationError(f'view={view} conflicts with resource view {previous}')
    _validate_view_selectors(params, view)
    base = 'session/' + name if resource.startswith('session/') else name
    if view == 'search' and 'match' not in params:
        params.setdefault('search', '')
    return base + '/' + target if target else base


def _validate_view_selectors(params, view):
    compatible = {'summary': ('overview',), 'digest': ('digest',), 'timeline': ('timeline',),
                  'errors': ('errors',), 'tokens': ('tokens',), 'tools': ('tools',),
                  'search': ('search',), 'tail': ('messages',), 'last': ('messages',)}
    for selector, views in compatible.items():
        if selector in params and view not in views:
            raise RequestValidationError(f'view={view} conflicts with {selector}')


def apply_match(params, resource):
    value = params.get('match')
    params.pop('match', None)
    if value is None:
        return
    target = _match_target(params, resource)
    for name in ('search', 'contains'):
        if name in params and (name != target or params[name] != value):
            raise RequestValidationError(f'match conflicts with {name} on this resource')
    params[target] = value


def _match_target(params, resource):
    noun, _, suffix = resource.partition('/')
    if noun in ('history', 'memory', 'search', 'sessions') or resource in ('', '.'):
        return 'search'
    if noun in ('plans', 'agents') and not suffix:
        return 'search'
    return _session_match_target(params, resource, noun, suffix)


def _session_match_target(params, resource, noun, suffix):
    selectors = ('summary', 'digest', 'timeline', 'tokens', 'tail', 'last')
    if any(params.get(key) is not None for key in selectors):
        raise RequestValidationError('match is not supported with this session view selector')
    if 'raw' in params:
        raise RequestValidationError('match is not supported on raw session records')
    if 'tools' in params or 'errors' in params:
        return 'contains'
    if resource.endswith('/messages'):
        return 'contains'
    if resource.endswith('/errors'):
        params['errors'] = True
        return 'contains'
    if (noun == 'session' and suffix and '/' not in suffix) or '/' not in resource:
        if noun not in ('info', 'settings', 'config', 'hooks', 'plans', 'agents'):
            return 'search'
    raise RequestValidationError('match is not supported on this Claude resource')
