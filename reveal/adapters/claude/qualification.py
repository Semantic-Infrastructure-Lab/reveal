"""Direct transcript operation identity and measured source qualification."""
from typing import Any, Dict

from ...utils.observations import count_observations, validate_observation_counts
from ...utils.results import AnalysisCompleteness, result_execution_facts
from .analysis.records import valid_record_proof as _valid_record_proof

from .resources import SESSION_VIEWS, selected_type


def validate_resource(resource, parse_identifier, prefixes):
    """Reject ignored suffixes before answer dispatch; namespace names own their paths."""
    from ...errors import RequestValidationError
    noun, _, suffix = resource.partition('/')
    roots = ('history', 'info', 'settings', 'config', 'sessions')
    if noun in roots and suffix:
        raise RequestValidationError(f'claude://{noun} does not support a resource suffix: {suffix}')
    if resource in ('', '.', 'session/') or noun in (*prefixes, 'sessions', 'search'):
        return
    name, view = parse_identifier(resource)
    if name and '/' not in name and (view in SESSION_VIEWS or view in ('chain', 'user', 'assistant') or view.startswith('message/')):
        return
    raise RequestValidationError(f'Unsupported Claude session resource: {resource}')


def uri_result_type(resource):
    path, _, query = resource.partition('?')
    return predicted_result_type(path, query=query)


def predicted_result_type(resource, *, query=None, params=None):
    from ...errors import RequestValidationError
    from .params import bind_request
    from .resources import operation_type
    try:
        effective, runtime = bind_request(query, params, resource)
    except (RequestValidationError, UnicodeDecodeError):
        # Prediction must not raise outside the router's answered-call boundary.
        # Canonical construction validates the original input and reports the error.
        return operation_type(resource, {})
    return operation_type(effective, runtime)


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
    if result.get('type') in ('claude_plan', 'claude_agent', 'claude_plans', 'claude_agents', 'claude_memory', 'claude_hooks'):
        from .workspace_scan import workspace_execution_facts
        return workspace_execution_facts(result)
    if result.get('type') == 'claude_info':
        from .info import info_execution_facts
        return info_execution_facts(result)
    if result.get('type') in ('claude_settings', 'claude_config'):
        from .installation import installation_execution_facts
        return installation_execution_facts(result)
    if result.get('type') == 'claude_history':
        from .history import history_execution_facts
        return history_execution_facts(result)
    if result.get('type') == 'claude_chain':
        from .chain import chain_execution_facts
        return chain_execution_facts(result)
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
    from .controls import control_requirement_error
    from .pagination import page_requirement_error
    from .workflow_selection import workflow_requirement_error
    control_error = (control_requirement_error(adapter, result)
                     or workflow_requirement_error(adapter, result, prior_facts)
                     or page_requirement_error(adapter, result, prior_facts))
    if control_error:
        return control_error
    if expected_type in ('claude_plan', 'claude_agent'):
        from .markdown_lookup import lookup_requirement_error
        error = lookup_requirement_error(adapter, result, expected_type, prior_facts)
        fields: Dict[str, Any] = {'matches': list} if result.get('ambiguous') else {'content': str} if 'content' in result else {}
        return error or _presentation_error(adapter, result, fields, prior_facts)
    if expected_type in ('claude_plans', 'claude_agents', 'claude_memory', 'claude_hooks'):
        return _workspace_answer_error(adapter, result, expected_type, prior_facts)
    if expected_type == 'claude_info':
        from .info import info_requirement_error
        return info_requirement_error(adapter, result, prior_facts)
    if expected_type in ('claude_settings', 'claude_config'):
        return _installation_answer_error(adapter, result, expected_type, prior_facts)
    if expected_type == 'claude_history':
        return _resource_answer_error(adapter, result, expected_type, prior_facts)
    if result.get('error') or result.get('applicable') is False:
        return None
    if expected_type in _RESOURCE_FIELDS:
        return _resource_answer_error(adapter, result, expected_type, prior_facts)
    return _transcript_answer_error(adapter, result, expected_type, prior_facts)


def _transcript_answer_error(adapter, result, expected_type, prior_facts):
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


def _installation_answer_error(adapter, result, expected_type, prior_facts):
    from .installation import installation_requirement_error, installation_fields, installation_scalar_error
    error = installation_requirement_error(adapter, result, expected_type, prior_facts)
    if error:
        return error
    fields = installation_fields(adapter, expected_type)
    error = installation_scalar_error(adapter, result, fields, prior_facts)
    containers = {key: kind for key, kind in fields.items() if isinstance(result.get(key), (list, str, dict))}
    return error or _presentation_error(adapter, result, containers, prior_facts)


def _workspace_answer_error(adapter, result, expected_type, prior_facts):
    from .workspace_scan import LIST_FIELDS, workspace_requirement_error
    if expected_type == 'claude_hooks' and adapter.resource.partition('/')[2].strip():
        from .hook_events import hook_event_requirement_error, hook_event_fields
        error = hook_event_requirement_error(adapter, result, prior_facts)
        return error or _presentation_error(adapter, result, hook_event_fields(result), prior_facts)
    error = workspace_requirement_error(adapter, result, expected_type, prior_facts)
    return error or _presentation_error(adapter, result, {LIST_FIELDS[expected_type]: list}, prior_facts)


_RESOURCE_FIELDS = {'claude_session_list': 'recent_sessions',
                   'claude_cross_session_search': 'matches', 'claude_file_sessions': 'sessions',
                   'claude_chain': 'chain', 'claude_history': 'entries'}


def _resource_answer_error(adapter, result, expected_type, prior_facts):
    from .catalog import catalog_requirement_error
    from .content import content_requirement_error
    from .chain import chain_requirement_error
    from .history import history_requirement_error
    qualify = {'claude_session_list': catalog_requirement_error,
               'claude_chain': chain_requirement_error,
               'claude_history': history_requirement_error}.get(expected_type, content_requirement_error)
    error = qualify(adapter, result, prior_facts)
    return error or _presentation_error(adapter, result, {_RESOURCE_FIELDS[expected_type]: list}, prior_facts)


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
