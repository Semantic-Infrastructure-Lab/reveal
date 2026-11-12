"""Direct Codex transcript identity, required-source evidence and observations."""
from typing import Any, Callable, Dict, Tuple

from ...errors import RequestValidationError
from ...utils.jsonl_records import valid_record_proof
from ...utils.observations import count_observations, validate_observation_counts
from ...utils.query_parser import peek_query_items
from ...utils.results import (AnalysisCompleteness, FailureCause, failure_execution_facts,
                              result_execution_facts)
from .params import bind_query
from .history import execution_facts as history_facts, answer_requirement_error as history_error
from .configuration import execution_facts as config_facts, answer_requirement_error as config_error
from .content import execution_facts as content_facts, answer_requirement_error as content_error
from .rollout import ROLLOUT_RULE, rollout_lost as _rollout_lost
from .catalog import (CATALOG_PATHS, execution_facts as catalog_facts,
                      answer_requirement_error as catalog_error)

RESOURCE_OWNERS: Dict[str, Tuple[Callable[..., Any], Callable[..., Any]]] = {
    'codex_history': (history_facts, history_error),
    'codex_config': (config_facts, config_error),
    'codex_content_search': (content_facts, content_error),
    'codex_session_list': (catalog_facts, catalog_error),
}

VIEW_TYPES = {'': 'codex_session_overview', 'messages': 'codex_messages', 'tools': 'codex_tools',
              'errors': 'codex_errors', 'shell': 'codex_shell', 'workflow': 'codex_workflow',
              'timeline': 'codex_timeline', 'digest': 'codex_digest', 'exchanges': 'codex_exchanges'}
CONTAINERS: Dict[str, Dict[str, Any]] = {'codex_session_overview': {}, 'codex_messages': {'messages': list},
              'codex_tools': {'tools': list}, 'codex_errors': {'errors': list},
              'codex_shell': {'shell_calls': list}, 'codex_tokens': {'token_turns': list},
              'codex_workflow': {'events': list}, 'codex_timeline': {'events': list},
              'codex_digest': {'prompts': list, 'assistant_narrative': list},
              'codex_exchanges': {'exchanges': list}, 'codex_message': {'record': dict}}
COUNTS = {'codex_session_overview': ('user_turns', 'agent_turns', 'tool_calls', 'shell_calls', 'reasoning_blocks'),
          'codex_messages': ('total_turns',), 'codex_tools': ('total',), 'codex_errors': ('total',),
          'codex_shell': ('total',), 'codex_tokens': ('total_turns',), 'codex_workflow': ('total',),
          'codex_timeline': ('total',), 'codex_digest': ('prompt_count', 'narrative_turn_count', 'user_turns', 'agent_turns'),
          'codex_exchanges': ('exchange_count',), 'codex_message': ('record_index',)}
RESULT_VARIANTS = {kind: ('codex_error', 'codex_not_installed') for kind in (*CONTAINERS, 'codex_goal')}


def selected_type(resource, params):
    if resource in ('config', 'history'):
        return 'codex_' + resource
    values = dict(peek_query_items(params))
    if resource in CATALOG_PATHS:
        return 'codex_content_search' if values.get('search') else 'codex_session_list'
    for name, kind in (('last', 'codex_messages'), ('tokens', 'codex_tokens'), ('goal', 'codex_goal')):
        if name in values and values[name] is not None and values[name] is not False:
            return kind
    sub = resource.partition('/')[2]
    return 'codex_message' if sub.startswith('message/') else VIEW_TYPES.get(sub, 'codex_session_overview')


def uri_result_type(resource):
    path, _, query = resource.partition('?')
    try:
        params = bind_query(query, None)
    except (RequestValidationError, ValueError, UnicodeDecodeError):
        params = {}
    return selected_type(path, params)


def index_request_error(resource):
    sub = resource.partition('/')[2]
    if not sub.startswith('message/'):
        return None
    raw = sub[len('message/'):]
    try:
        int(raw)
    except ValueError:
        return f'Invalid message index: {raw!r}'
    return None


def _invalid_envelope(result):
    return any(entry.get('code') == 'invalid_adapter_answer' for entry in result.get('meta', {}).get('errors', [])
               if isinstance(entry, dict))


def _source_state(lookup, rollout):
    if lookup.get('selected_id') is None or not rollout:
        return AnalysisCompleteness.FAILED
    if lookup.get('failed_operations') or _rollout_lost(rollout):
        usable = rollout.get('analyzed_records') or (rollout.get('opened') and not _rollout_lost(rollout))
        return AnalysisCompleteness.INCOMPLETE if usable else AnalysisCompleteness.FAILED
    return AnalysisCompleteness.COMPLETE


def _goal_state(lookup, goal):
    if not goal.get('failed_operations') and not lookup.get('failed_operations'):
        return AnalysisCompleteness.COMPLETE
    usable = goal.get('query_complete') or goal.get('decision') == 'source_absent'
    return AnalysisCompleteness.INCOMPLETE if usable else AnalysisCompleteness.FAILED


def execution_facts(result):
    if _invalid_envelope(result):
        return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
    owner = RESOURCE_OWNERS.get(result.get('type'))
    if owner is not None:
        return owner[0](result)
    if result.get('scope', {}).get('request_rejected'):
        return failure_execution_facts(FailureCause.INVALID_REQUEST)
    meta = result.get('meta', {})
    lookup, rollout = meta.get('session_lookup', {}), meta.get('rollout_analysis', {})
    absence = lookup.get('decision') in ('missing', 'ambiguous', 'source_absent') and not lookup.get('failed_operations')
    if absence:
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE,
                                      failure_cause=FailureCause.INVALID_REQUEST)
    state = _goal_state(lookup, meta.get('goal_lookup', {})) if result.get('type') == 'codex_goal' else _source_state(lookup, rollout)
    cause = FailureCause.INVALID_REQUEST if state is AnalysisCompleteness.COMPLETE else FailureCause.ANALYSIS
    return result_execution_facts(result, completeness=state, failure_cause=cause)


def _lookup_error(adapter, result):
    lookup = adapter._session_lookup
    if lookup is None or result.get('meta', {}).get('session_lookup') != lookup.receipt():
        return 'Codex answer missing consistent session lookup decisions'
    if lookup.selected is None:
        if result.get('type') not in ('codex_error', 'codex_not_installed') or result.get('error') != adapter._lookup_error_message:
            return 'Codex answer changed its lookup failure or absence diagnostic'
    elif result.get('type') in ('codex_error', 'codex_not_installed'):
        return 'Codex answer changed its selected view into a lookup error'
    elif result.get('session_id') != lookup.selected['id']:
        return 'Codex answer changed its selected session identity'
    return None


def _rollout_error(adapter, result):
    proof = result.get('meta', {}).get('rollout_analysis')
    if (not valid_record_proof(proof) or proof != adapter._rollout_analysis
            or proof.get('count_rule') != ROLLOUT_RULE):
        return 'Codex answer missing consistent rollout record decisions'
    return None


def _indexed_absence(adapter, result):
    raw = adapter.resource.partition('/message/')[2]
    try:
        index = int(raw)
    except ValueError:
        return 'Codex indexed answer has no validated request index'
    count = result['meta']['rollout_analysis']['analyzed_records']
    resolved = index if index >= 0 else count + index
    expected = f'No record at index {index} (session has {count} records)'
    if 0 <= resolved < count or result.get('error') != expected:
        return 'Codex indexed answer changed its absence decision'
    return None


def _view_counts(result, expected_type):
    counts = {key: result.get(key) for key in COUNTS[expected_type]}
    if any(type(value) is not int or value < 0 for value in counts.values()):
        return counts, 'Codex answer missing required nonnegative view counts'
    if expected_type == 'codex_tokens':
        value = result.get('grand_total')
        if 'grand_total' not in result or (value is not None and (type(value) is not int or value < 0)):
            return counts, 'Codex token answer missing its known or unknown grand total'
        counts['grand_total'] = value
    return counts, None


def _indexed_observation_error(adapter, result):
    total = result['meta']['rollout_analysis']['analyzed_records']
    raw = int(adapter.resource.partition('/message/')[2])
    if result['record_index'] != (raw if raw >= 0 else total + raw) or result['record_index'] >= total:
        return 'Codex indexed answer changed its observed record index'
    return None


def _view_error(adapter, result, expected_type, prior_facts):
    fields = CONTAINERS[expected_type]
    if not all(isinstance(result.get(key), kind) for key, kind in fields.items()):
        return 'Codex answer missing required view observations'
    counts, error = _view_counts(result, expected_type)
    if error:
        return error
    if expected_type == 'codex_message':
        error = _indexed_observation_error(adapter, result)
        if error:
            return error
    current = count_observations(result, ((key,) for key in fields))
    if prior_facts is None:
        adapter._session_observations, adapter._session_counts = current, counts
    if counts != adapter._session_counts:
        return 'Codex presentation changed its source population counts'
    return validate_observation_counts(result, adapter._session_observations, current, label='Codex')


def _goal_error(adapter, result):
    expected = adapter._goal_answer
    if result.get('meta', {}).get('goal_lookup') != expected['meta']['goal_lookup']:
        return 'Codex goal answer changed its source acquisition decisions'
    for key in ('goal', 'thread_id', 'error'):
        if (key in result) != (key in expected) or result.get(key) != expected.get(key):
            return 'Codex goal answer changed its acquired goal or absence diagnostic'
    return None


def _rejected_index_error(adapter, result, expected_type):
    reason = adapter._request_index_error
    if (result.get('type') != expected_type or reason != index_request_error(adapter.resource) or result.get('error') != reason
            or result.get('scope', {}).get('request_rejected') != reason):
        return 'Codex answer changed its authored index rejection'
    return None


def answer_requirement_error(adapter, result, expected_type, prior_facts=None):
    owner = RESOURCE_OWNERS.get(expected_type)
    if owner is not None:
        return owner[1](adapter, result, prior_facts)
    goal = expected_type == 'codex_goal' and result.get('type') == 'codex_goal'
    source = adapter.CODEX_HOME / 'goals_1.sqlite' if goal else adapter.CODEX_DB
    if result.get('source') != str(source) or result.get('source_type') != 'database':
        return 'Codex answer changed its required database source identity'
    if adapter._request_index_error is not None:
        return _rejected_index_error(adapter, result, expected_type)
    error = _lookup_error(adapter, result)
    if error or adapter._session_lookup.selected is None:
        return error
    if goal:
        return _goal_error(adapter, result)
    error = _rollout_error(adapter, result)
    if error:
        return error
    if result.get('error'):
        return _indexed_absence(adapter, result) if expected_type == 'codex_message' else 'Codex view introduced an unowned error'
    return _view_error(adapter, result, expected_type, prior_facts)
