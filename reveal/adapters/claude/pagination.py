"""Answer-row sorting and pagination, separate from source/input budgets."""
from copy import deepcopy
from typing import Any, Dict

from ...errors import RequestValidationError
from ...utils.query_control import apply_result_control, declared_result_control
from ...utils.query_parser import peek_query_items
from ...utils.results import note_truncation
from .resources import operation_type


PAGE_SPECS = {
    'claude_session_list': ('recent_sessions', ('session', 'project', 'modified', 'size_kb')),
    'claude_cross_session_search': ('matches', ('session', 'project', 'modified')),
    'claude_file_sessions': ('sessions', ('session', 'project', 'modified', 'total_ops')),
    'claude_history': ('entries', ('timestamp', 'project', 'session_id', 'prompt')),
    'claude_plans': ('plans', ('name', 'modified', 'size_kb', 'title')),
    'claude_agents': ('agents', ('name', 'modified', 'size_kb', 'description', 'model')),
    'claude_memory': ('memories', ('name', 'project', 'modified', 'size_bytes', 'type')),
    'claude_hooks': ('hooks', ('event', 'kind', 'modified', 'size_bytes', 'script_count', 'name')),
    'claude_config': ('projects', ()),
    'claude_messages': ('messages', ('message_index', 'turn', 'timestamp', 'char_count')),
    'claude_user_messages': ('messages', ('message_index', 'timestamp')),
    'claude_assistant_messages': ('messages', ('message_index', 'timestamp')),
    'claude_user_prompts': ('messages', ('message_index', 'timestamp')),
    'claude_message_range': ('messages', ('message_index', 'timestamp')),
    'claude_thinking': ('blocks', ('message_index', 'timestamp')),
    'claude_tool_calls': ('calls', ('message_index', 'timestamp')),
    'claude_files': ('operations', ('timestamp',)),
    'claude_workflow': ('workflow', ('timestamp', 'tool', 'detail')),
    'claude_session_agents': ('agents', ()),
    'claude_context': ('changes', ('timestamp',)),
    'claude_timeline': ('timeline', ('timestamp',)),
    'claude_errors': ('errors', ('timestamp',)),
    'claude_exchanges': ('exchanges', ('message_index', 'timestamp')),
    'claude_search_results': ('matches', ('message_index', 'timestamp')),
    'claude_filtered_results': ('results', ('message_index', 'timestamp')),
    'claude_token_breakdown': ('messages', ('message_index', 'timestamp')),
    'claude_chain': ('chain', ()),
}
PAGE_RULE = 'Answer rows after analysis/name/content filters, before pagination and output budgets; sort then offset then limit; zero limit is uncapped; source/input budgets are unchanged'
SORT_RULE = 'Shared result-control ordering: nulls last in either direction; mixed numbers/text compare numerically where possible, otherwise values compare as text'


def page_requested(params):
    return any(value is not None for key, value in peek_query_items(params) if key in ('limit', 'offset', 'sort'))


def validate_page_scope(params, resource):
    if not page_requested(params):
        return
    kind = operation_type(resource, params)
    if kind not in PAGE_SPECS or (kind == 'claude_config' and params.get('key')):
        raise RequestValidationError('limit/offset/sort require a supported list answer')
    sort = params.get('sort')
    field = sort[1:] if sort and sort.startswith('-') else sort
    if sort and field not in PAGE_SPECS[kind][1]:
        raise RequestValidationError(f'Unsupported sort field for {kind}: {sort}')
    if params.get('tail') is not None or params.get('last') is not None:
        raise RequestValidationError('limit/offset/sort cannot combine with legacy tail/last')


def page_result(result: Dict[str, Any], params) -> Dict[str, Any]:
    if not page_requested(params):
        return result
    field = _page_field(result)
    rows = result.get(field)
    if not isinstance(rows, list):
        return _unavailable_page(result, params, field)
    control = declared_result_control(params)
    if control.limit == 0:
        control.limit = None
    result[field] = apply_result_control(rows, control)
    receipt = _request_receipt(params, field)
    receipt.update(applied=True, total=len(rows), shown=len(result[field]))
    result.setdefault('meta', {})['pagination'] = receipt
    update_display_counts(result)
    return result


def _request_receipt(params, field):
    return {'field': field, 'limit': params.get('limit'), 'offset': params.get('offset', 0),
            'sort': params.get('sort'), 'count_rule': PAGE_RULE, 'sort_rule': SORT_RULE}


def _unavailable_page(result: Dict[str, Any], params, field) -> Dict[str, Any]:
    if not result.get('error'):
        raise RequestValidationError('limit/offset/sort require a list in the selected answer')
    receipt = _request_receipt(params, field)
    receipt.update(applied=False, total=None, shown=None, reason='Required answer source failed before list acquisition')
    result.setdefault('meta', {})['pagination'] = receipt
    return result


def update_display_counts(result):
    receipt = result.get('meta', {}).get('pagination', {})
    field = receipt.get('field')
    if not receipt.get('applied') or not isinstance(result.get(field), list):
        return
    shown = len(result[field])
    result['displayed_count'] = shown
    if result['type'] in ('claude_plans', 'claude_agents', 'claude_message_range'):
        result['displayed'] = shown
    if result['type'] == 'claude_workflow':
        result['displayed_steps'] = shown
    note_truncation(result, field, shown, receipt['total'], 'pagination-and-output')


def page_requirement_error(adapter, result, prior_facts):
    if not page_requested(adapter.query_params):
        return None
    receipt = result.get('meta', {}).get('pagination')
    if not _valid_receipt(receipt, adapter.query_params, result, prior_facts):
        return 'Claude answer missing requested pagination decisions'
    if prior_facts is None:
        adapter._page_receipt = deepcopy(receipt)
    if receipt != adapter._page_receipt:
        return 'Claude presentation cannot change measured pagination decisions'
    return None


def _valid_receipt(receipt, params, result, prior_facts):
    if not isinstance(receipt, dict) or receipt.get('count_rule') != PAGE_RULE:
        return False
    expected = _request_receipt(params, _page_field(result))
    if any(receipt.get(key) != value for key, value in expected.items()):
        return False
    if receipt.get('applied') is False:
        return bool(result.get('error')) and receipt.get('total') is None and receipt.get('shown') is None
    if receipt.get('applied') is not True:
        return False
    return _valid_page_counts(receipt, result, prior_facts)


def _valid_page_counts(receipt, result, prior_facts):
    total, shown = receipt.get('total'), receipt.get('shown')
    if not all(type(value) is int and value >= 0 for value in (total, shown)):
        return False
    available = max(total - receipt['offset'], 0)
    expected_count = min(receipt['limit'], available) if receipt['limit'] else available
    rows = result.get(receipt.get('field'))
    return (shown == expected_count and isinstance(rows, list)
            and (prior_facts is not None or len(rows) == shown))


def _page_field(result):
    if result.get('type') == 'claude_hooks' and result.get('kind') == 'directory':
        return 'scripts'
    return PAGE_SPECS[result['type']][0]


def page_schema():
    return {kind: {'field': field, 'sort_fields': list(fields), 'descending_prefix': '-',
                   'zero_limit': 'uncapped', 'count_rule': PAGE_RULE,
                   **({'directory_field': 'scripts'} if kind == 'claude_hooks' else {})}
            for kind, (field, fields) in PAGE_SPECS.items()}


def validate_page_display_args(params, args):
    if not page_requested(params):
        return
    if any(getattr(args, name, None) is not None for name in ('head', 'tail', 'range', 'name', 'type')):
        raise RequestValidationError('Canonical pagination cannot combine with legacy --head/--tail/--range/--name/--type; use declared controls')
    if getattr(args, 'all', False) and params.get('limit') not in (None, 0):
        raise RequestValidationError('--all conflicts with a bounded limit; use limit=0 for uncapped output')
