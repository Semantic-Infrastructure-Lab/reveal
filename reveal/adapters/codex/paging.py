"""Answer-row pages of Codex list answers (ruling Q6, COMMAND_MODEL Caps): --limit/--offset over the rows the selected
answer holds, after analysis and before output budgets. Source reads and counting rules are unchanged."""
from typing import Any, Dict

from ...errors import RequestValidationError
from ...utils.query_control import apply_result_control, declared_result_control
from ...utils.query_parser import peek_query_items
from ...utils.results import note_truncation
from .params import PAGE_FIELDS

PAGE_RULE = ('Answer rows after the answer\'s own filters and snippet caps, before output budgets; offset then limit; '
             'zero limit is uncapped; source reads, totals and counting rules are unchanged')


def page_requested(params) -> bool:
    return any(value is not None for key, value in peek_query_items(params) if key in ('limit', 'offset'))


def page_result(result: Dict[str, Any], params) -> Dict[str, Any]:
    """*result* with its list paged when --limit or --offset is given. An answer whose required source failed before
    its rows were read keeps its failure; any other answer without its list is an invalid request (the declarations
    refuse the controls on answers that hold none, so this guards the join)."""
    if not page_requested(params):
        return result
    field = PAGE_FIELDS.get(result.get('type', ''))
    rows = result.get(field) if field else None
    receipt: Dict[str, Any] = {'field': field, 'limit': params.get('limit'), 'offset': params.get('offset', 0),
                               'count_rule': PAGE_RULE}
    if field is None or not isinstance(rows, list):
        if not result.get('error'):
            raise RequestValidationError('limit/offset require a list in the selected answer')
        receipt.update(applied=False, total=None, shown=None,
                       reason='Required answer source failed before list acquisition')
        result.setdefault('meta', {})['pagination'] = receipt
        return result
    paged = apply_result_control(rows, declared_result_control(params))
    result[field] = paged
    receipt.update(applied=True, total=len(rows), shown=len(paged))
    result.setdefault('meta', {})['pagination'] = receipt
    note_truncation(result, field, len(paged), len(rows), 'pagination')
    return result
