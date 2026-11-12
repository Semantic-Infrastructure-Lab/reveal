"""Canonical controls translate to the existing, resource-specific readers."""
from ...errors import RequestValidationError


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
