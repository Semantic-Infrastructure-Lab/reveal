"""Direct transcript operation identity and measured source qualification."""
from typing import Any, Dict

from ...utils.observations import count_observations, validate_observation_counts
from ...utils.query_binding import prepare_declared_params
from ...utils.query_parser import peek_query_items
from ...utils.results import AnalysisCompleteness, result_execution_facts
from .params import PARAM_SPECS
from .analysis.records import valid_record_proof as _valid_record_proof

SESSION_VIEWS = frozenset(('', 'messages', 'prompts', 'thinking', 'tools', 'files', 'workflow',
                           'agents', 'context', 'timeline', 'errors', 'summary', 'tokens',
                           'digest', 'exchanges', 'message'))
QUERY_VIEWS = (('summary', 'claude_analytics'), ('digest', 'claude_digest'),
               ('timeline', 'claude_timeline'), ('errors', 'claude_errors'),
               ('tokens', 'claude_token_breakdown'), ('tools', 'claude_tool_calls'),
               ('search', 'claude_search_results'), ('tail', 'claude_messages'), ('last', 'claude_messages'))
RESOURCE_VIEWS = (('thinking', 'claude_thinking'), ('tools', 'claude_tool_summary'),
                  ('files', 'claude_files'), ('workflow', 'claude_workflow'),
                  ('agents', 'claude_session_agents'), ('context', 'claude_context'),
                  ('prompts', 'claude_user_prompts'), ('exchanges', 'claude_exchanges'),
                  ('errors', 'claude_errors'), ('summary', 'claude_analytics'),
                  ('digest', 'claude_digest'), ('timeline', 'claude_timeline'),
                  ('tokens', 'claude_token_breakdown'), ('messages', 'claude_messages'))


def catalog_type(resource):
    path, _, query = resource.partition('?')
    if path in ('', '.', 'sessions') or path.startswith('sessions/'):
        params = prepare_declared_params(PARAM_SPECS, query, 'uri')
        return ('claude_cross_session_search' if dict(peek_query_items(params)).get('search')
                else 'claude_session_list')
    if path == 'search' or path.startswith('search/'):
        return 'claude_cross_session_search'
    if path == 'files' or path.startswith('files/'):
        return 'claude_file_sessions'
    return None


def direct_session(resource, parse_identifier, prefixes):
    path = resource.partition('?')[0]
    if not path or path in ('.', 'sessions', 'sessions/') or path.startswith(('sessions/', 'search/')) or path == 'search':
        return False
    if any(path == prefix or path.startswith(prefix + '/') for prefix in prefixes):
        return False
    name, subpath = parse_identifier(path)
    return bool(name) and '/' not in name and (subpath in SESSION_VIEWS or subpath.startswith('message/'))


def _active(params):
    return {key for key, value in peek_query_items(params) if value is not None and value is not False}


def selected_type(resource, params):
    active = _active(params)
    if len(active.intersection(('tools', 'errors', 'contains'))) > 1:
        return 'claude_filtered_results'
    for key, kind in QUERY_VIEWS:
        if key in active:
            return kind
    for segment, kind in RESOURCE_VIEWS:
        if '/' + segment in resource:
            if 'raw' in active and segment in ('prompts', 'messages'):
                return 'claude_user_messages' if segment == 'prompts' else 'claude_assistant_messages'
            return kind
    if '/message/' in resource:
        return 'claude_message'
    if resource.endswith('/message'):
        return 'claude_message_range'
    return 'claude_session_overview'


def uri_result_type(resource):
    kind = catalog_type(resource)
    if kind:
        return kind
    path, _, query = resource.partition('?')
    params = prepare_declared_params(PARAM_SPECS, query, 'uri')
    return selected_type(path, params)


def _count(value):
    return type(value) is int and value >= 0


_CONTAINERS: Dict[str, Dict[str, Any]] = {
    'claude_session_overview': {'files_touched': list, 'tools_used': dict, 'file_operations': dict, 'token_summary': dict},
    'claude_analytics': {'files_touched': list, 'tools_used': dict, 'file_operations': dict, 'token_summary': dict,
                         'tool_success_rate': dict},
    'claude_messages': {'messages': list},
    'claude_user_messages': {'messages': list},
    'claude_assistant_messages': {'messages': list},
    'claude_user_prompts': {'messages': list},
    'claude_thinking': {'blocks': list},
    'claude_tool_calls': {'calls': list},
    'claude_tool_summary': {'tools': dict, 'details': dict},
    'claude_files': {'operations': list, 'by_operation': dict},
    'claude_workflow': {'workflow': list},
    'claude_session_agents': {'agents': list},
    'claude_context': {'changes': list},
    'claude_token_breakdown': {'messages': list, 'totals': dict},
    'claude_timeline': {'timeline': list},
    'claude_errors': {'errors': list},
    'claude_digest': {'prompts': list, 'assistant_narrative': list},
    'claude_exchanges': {'exchanges': list},
    'claude_search_results': {'matches': list},
    'claude_filtered_results': {'results': list},
    'claude_message': {'message': dict, 'text': str},
    'claude_message_range': {'messages': list},
}
_COUNTS = {
    'claude_session_overview': 'message_count', 'claude_analytics': 'message_count',
    'claude_messages': 'total_turns', 'claude_user_messages': 'message_count',
    'claude_assistant_messages': 'message_count', 'claude_user_prompts': 'message_count',
    'claude_thinking': 'thinking_block_count', 'claude_tool_calls': 'call_count',
    'claude_tool_summary': 'total_calls', 'claude_files': 'total_operations',
    'claude_workflow': 'total_steps', 'claude_session_agents': 'total_agents',
    'claude_context': 'total_changes', 'claude_timeline': 'event_count',
    'claude_errors': 'error_count', 'claude_digest': 'message_count',
    'claude_exchanges': 'exchange_count', 'claude_search_results': 'match_count',
    'claude_filtered_results': 'result_count',
    'claude_message_range': 'total_messages',
}


def execution_facts(result):
    if result.get('type') in ('claude_cross_session_search', 'claude_file_sessions'):
        from .content import content_execution_facts
        return content_execution_facts(result)
    if result.get('type') == 'claude_session_list':
        from .catalog import catalog_execution_facts
        return catalog_execution_facts(result)
    state = AnalysisCompleteness.COMPLETE
    meta = result.get('meta', {})
    proof = meta.get('transcript_analysis', {})
    lost = proof.get('failed_records') or meta.get('transcript_selection', {}).get('failed_operations')
    if lost:
        state = AnalysisCompleteness.INCOMPLETE if proof.get('analyzed_records') else AnalysisCompleteness.FAILED
    return result_execution_facts(result, completeness=state)


def answer_requirement_error(adapter, result, expected_type, prior_facts=None):
    if result.get('error') or result.get('applicable') is False:
        return None
    if expected_type in _CATALOG_FIELDS:
        return _catalog_answer_error(adapter, result, expected_type, prior_facts)
    error = _source_decision_error(adapter, result)
    if error:
        return error
    proof = result['meta']['transcript_analysis']
    fields = _CONTAINERS.get(expected_type)
    if not fields or not all(isinstance(result.get(key), kind) for key, kind in fields.items()):
        return 'Claude answer missing required view observations'
    count = _COUNTS.get(expected_type)
    if count and not _count(result.get(count)):
        return 'Claude answer missing required nonnegative view count'
    if expected_type in ('claude_session_overview', 'claude_analytics', 'claude_digest'):
        if result['message_count'] != proof['analyzed_records']:
            return 'Claude record count disagrees with its source proof'
    error = _indexed_observation_error(result, proof, expected_type)
    return error or _presentation_error(adapter, result, fields, prior_facts)


def _indexed_observation_error(result, proof, expected_type):
    if expected_type == 'claude_message':
        index = result.get('message_index')
        if not _count(index) or index >= proof['analyzed_records']:
            return 'Claude indexed answer missing an observed source index'
    return None


_CATALOG_FIELDS = {'claude_session_list': 'recent_sessions',
                   'claude_cross_session_search': 'matches', 'claude_file_sessions': 'sessions'}


def _catalog_answer_error(adapter, result, expected_type, prior_facts):
    from .catalog import catalog_requirement_error
    from .content import content_requirement_error
    qualify = catalog_requirement_error if expected_type == 'claude_session_list' else content_requirement_error
    error = qualify(adapter, result, prior_facts)
    return error or _presentation_error(adapter, result, {_CATALOG_FIELDS[expected_type]: list}, prior_facts)


def _source_decision_error(adapter, result):
    proof = result.get('meta', {}).get('transcript_analysis')
    if not _valid_record_proof(proof) or proof != getattr(adapter, '_transcript_analysis', None):
        return 'Claude answer missing consistent transcript record decisions'
    lookup = getattr(adapter, '_conversation_lookup', None)
    selection = result.get('meta', {}).get('transcript_selection')
    if lookup is None or selection != lookup.receipt() or not all(_count(selection.get(key)) for key in ('failed_operations', 'recovered_operations')):
        return 'Claude answer missing transcript selection decisions'
    return None


def _presentation_error(adapter, result, fields, prior_facts):
    current = count_observations(result, ((key,) for key in fields))
    if prior_facts is None:
        adapter._session_observations = current
    return validate_observation_counts(result, adapter._session_observations, current, label='Claude')
