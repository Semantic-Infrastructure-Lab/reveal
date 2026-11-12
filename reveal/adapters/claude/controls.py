"""Canonical controls translate to the existing, resource-specific readers."""
from typing import Any, Dict
import json
from ...errors import RequestValidationError
from .resources import _parse_session_identifier, selected_type, NON_SESSION_NAMESPACES


def apply_view(params, resource):
    view = params.pop('view', None)
    if view is None:
        return resource
    noun = resource.partition('/')[0]
    if resource in ('', '.') or noun in NON_SESSION_NAMESPACES:
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


_FULL_TYPES = frozenset(('claude_messages', 'claude_message', 'claude_message_range',
                         'claude_exchanges', 'claude_workflow', 'claude_tool_calls',
                         'claude_assistant_messages'))
_RAW_TYPES = frozenset(('claude_messages', 'claude_user_prompts', 'claude_user_messages',
                        'claude_assistant_messages'))


def apply_detail(params, resource):
    level = params.get('detail')
    if level is None:
        return
    if level == 'normal':
        if any(key in params for key in ('summary', 'full', 'raw')):
            raise RequestValidationError('detail=normal conflicts with a legacy detail control')
        return
    if resource in ('', '.') or resource.partition('/')[0] in NON_SESSION_NAMESPACES:
        raise RequestValidationError(f'detail={level} is not supported on this resource')
    kind = selected_type(resource, params)
    if level == 'summary' and kind in ('claude_session_overview', 'claude_analytics'):
        if 'raw' in params or 'full' in params:
            raise RequestValidationError('detail=summary conflicts with raw/full')
        params['summary'] = True
    elif level == 'full' and kind in _FULL_TYPES:
        params['full'] = True
    elif level == 'raw' and kind in _RAW_TYPES:
        params.update(raw=True, full=True)
    else:
        raise RequestValidationError(f'detail={level} is not supported by this session view')


def detail_requirement_error(adapter, result):
    if adapter.query_params.get('detail') in ('full', 'raw') and result.get('full') is not True:
        return 'Claude answer missing requested full/raw detail intent'
    return None


def validate_where_scope(params, resource):
    if params.get('where') is None:
        return
    if resource.rstrip('/') not in ('', '.', 'sessions') or params.get('search'):
        raise RequestValidationError('where session predicates are supported only on catalog listings, without content search')


SESSION_WHERE_RULE = 'AND of case-insensitive literal substrings of the session name; not README titles or message content'


def filter_session_names(result: Dict[str, Any], params) -> Dict[str, Any]:
    terms = params.get('where')
    if terms is None:
        return result
    needles = [term.partition('~=')[2].lower() for term in terms]
    rows = [row for row in result['recent_sessions']
            if all(needle in str(row['session']).lower() for needle in needles)]
    result.update(recent_sessions=rows, session_count=len(rows))
    result.setdefault('scope', {}).update(
        where=list(terms), where_rule=SESSION_WHERE_RULE)
    return result


def where_requirement_error(adapter, result):
    terms = adapter.query_params.get('where')
    scope = result.get('scope', {})
    if terms is not None and (scope.get('where') != terms or scope.get('where_rule') != SESSION_WHERE_RULE):
        return 'Claude presentation cannot change requested session-name predicate scope'
    return None


def control_requirement_error(adapter, result):
    return (detail_requirement_error(adapter, result) or where_requirement_error(adapter, result)
            or composite_requirement_error(adapter, result) or date_requirement_error(adapter, result))


COMPOSITE_QUERY_RULE = 'Canonical JSON receipt of applied bound filters; independent of transport syntax'


def composite_query_receipt(params):
    """Describe the filters actually applied, including literal API overlays."""
    values = {name: params[name] for name in ('tools', 'errors', 'contains') if name in params}
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def composite_requirement_error(adapter, result):
    if result.get('type') != 'claude_filtered_results':
        return None
    expected = composite_query_receipt(adapter.query_params)
    if result.get('query') != expected or result.get('meta', {}).get('query_rule') != COMPOSITE_QUERY_RULE:
        return 'Claude answer missing the applied composite-filter receipt'
    return None


def validate_display_scope(args, kind):
    if getattr(args, 'with_stats', False) and kind != 'claude_session_list':
        raise RequestValidationError('--with-stats requires a session listing')


def date_requirement_error(adapter, result):
    if result.get('type') != 'claude_session_list':
        return None
    if not (adapter.query_params.get('since') or adapter.query_params.get('until')):
        return None
    observed = getattr(adapter, '_catalog_date_scope', None)
    if not isinstance(observed, dict) or result.get('scope', {}).get('date_window') != observed:
        return 'Claude presentation cannot change the measured catalog date window'
    return None


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


# These modifiers have a reader only on the listed answer populations.
MODIFIER_SCOPES = {
    'key': ('claude_settings', 'claude_config'),
    'project': ('claude_history',),
    'patches': ('claude_files',),
    'word': ('claude_cross_session_search',),
    'snippet': ('claude_cross_session_search',),
    'filter': ('claude_session_list',),
    'since': ('claude_session_list', 'claude_cross_session_search', 'claude_file_sessions', 'claude_history'),
    'until': ('claude_session_list', 'claude_cross_session_search'),
}


def validate_modifier_scope(params, resource):
    from .resources import operation_type
    kind = operation_type(resource, params)
    for name, supported in MODIFIER_SCOPES.items():
        if name in params and kind not in supported:
            raise RequestValidationError(f'{name} is supported only by: ' + ', '.join(supported))


SESSION_SELECTORS = frozenset(('summary', 'digest', 'timeline', 'errors', 'tokens', 'tools', 'tail', 'last'))
SEARCH_POPULATIONS = frozenset(('claude_cross_session_search', 'claude_search_results', 'claude_history',
                                'claude_plans', 'claude_agents', 'claude_memory'))


def validate_selectors(params, resource):
    from .resources import operation_type
    selected = set(params).intersection(SESSION_SELECTORS | {'search'})
    namespace = resource.partition('/')[0]
    if resource.rstrip('/') in ('', '.') or namespace in NON_SESSION_NAMESPACES:
        misplaced = selected.intersection(SESSION_SELECTORS)
        if misplaced:
            raise RequestValidationError('Session selectors require a session resource: ' + ', '.join(sorted(misplaced)))
    if 'search' in selected and operation_type(resource, params) not in SEARCH_POPULATIONS:
        raise RequestValidationError('search selector is unsupported on this resource')
    if {'tail', 'last'} <= selected:
        last_count = params['last'] or 1
        if params['tail'] != last_count:
            raise RequestValidationError('Conflicting tail/last selectors select different counts')
        selected.remove('last')
    if len(selected) > 1 and not selected <= {'tools', 'errors'}:
        raise RequestValidationError('Conflicting Claude selectors: ' + ', '.join(sorted(selected)))
