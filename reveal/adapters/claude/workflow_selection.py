"""Native workflow selection at the existing CLI's row-population owner."""
from copy import deepcopy
from typing import Any, Dict, Mapping

from .controls import WORKFLOW_WHERE_RULE
from .handlers.post_process import select_workflow_rows

MATCH_RULE = 'Case-insensitive literal substring of workflow tool name or operation detail; not tool-result text'


def workflow_selection_requested(params):
    return params.get('where') is not None or params.get('match') is not None


def select_workflow_result(result: Dict[str, Any], params: Mapping[str, Any]) -> Dict[str, Any]:
    if not workflow_selection_requested(params):
        return result
    rows = result['workflow']
    before = len(rows)
    terms = params.get('where')
    for expression in terms or ():
        rows = select_workflow_rows(rows, tool=expression.partition('==')[2])
    rows = select_workflow_rows(rows, term=params.get('match'))
    result.update(workflow=rows, displayed_steps=len(rows))
    if len(rows) < before:
        result['filtered_from'] = before
    if terms is not None:
        result.setdefault('scope', {}).update(where=list(terms), where_rule=WORKFLOW_WHERE_RULE)
    result.setdefault('meta', {})['workflow_selection'] = {
        'match': params.get('match'), 'where': list(terms) if terms is not None else None,
        'match_rule': MATCH_RULE, 'where_rule': WORKFLOW_WHERE_RULE,
        'before': before, 'selected': len(rows),
    }
    return result


def workflow_requirement_error(adapter, result, prior_facts=None):
    if result.get('type') != 'claude_workflow' or not workflow_selection_requested(adapter.query_params):
        return None
    receipt = result.get('meta', {}).get('workflow_selection')
    if not isinstance(receipt, dict) or receipt != getattr(adapter, '_workflow_selection', None):
        return 'Claude workflow missing measured selection decisions'
    if result.get('collapsed_steps') != receipt['before']:
        return 'Claude workflow changed its pre-selection collapsed population'
    page = result.get('meta', {}).get('pagination')
    if page is not None and (not isinstance(page, dict) or page.get('total') != receipt['selected']):
        return 'Claude workflow pagination changed the selected population'
    if prior_facts is None and page is None and len(result.get('workflow', [])) != receipt['selected']:
        return 'Claude workflow changed its selected rows without pagination'
    return None


def remember_workflow_selection(adapter: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    adapter._workflow_selection = deepcopy(result.get('meta', {}).get('workflow_selection'))
    return result
