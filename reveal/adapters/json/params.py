"""JSON controls distinguish dataset predicates from legacy first-word inspection modes."""
from typing import Any

from ...errors import RequestValidationError
from ...utils.query_binding import boolean_value
from ...utils.query_parser import CliBinding, ParamSpec, ParamValueError, QueryParams, parse_query_params, peek_query_items
from ...utils.query_control import declared_result_control as result_control, parse_result_control
from ...utils.query import parse_query_filters

VIEWS = ('value', 'schema', 'flatten', 'type', 'keys', 'length')
LEGACY_SELECTORS = ('schema', 'flatten', 'gron', 'type', 'keys', 'length')


def expressions(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError('where requires nonempty expressions')
    return list(values)


def view_name(value: Any) -> str:
    name = str(value)
    return 'flatten' if name == 'gron' else name


def nonnegative(name, value):
    try:
        _, control = parse_result_control(f'{name}={value}')
    except ValueError as exc:
        raise ParamValueError(str(exc)) from exc
    return object.__getattribute__(control, name)


VIEW = ParamSpec('view', 'string', 'Answer view: value, schema, flatten, type, keys or length',
                 'value', view_name, choices=VIEWS, legacy_selectors=LEGACY_SELECTORS,
                 cli=CliBinding(('--view',)))
WHERE = ParamSpec('where', 'array', 'Array-element predicates, ANDed; repeat for multiple constraints',
                  [], expressions, role='filter-expression', cli=CliBinding(('--where',), action='append'))
DETAIL = ParamSpec('detail', 'string', 'Flatten text detail: full (default) or raw lines',
                   'full', str, choices=('full', 'raw'), cli=CliBinding(('--detail',)))
SORT = ParamSpec('sort', 'string', 'Array field; prefix - for descending', None, str,
                 cli=CliBinding(('--sort',)))
LIMIT = ParamSpec('limit', 'integer', 'Array rows; zero is an empty page', None, lambda v: nonnegative('limit', v), minimum=0,
                  zero_policy='empty page', cli=CliBinding(('--limit',)))
OFFSET = ParamSpec('offset', 'integer', 'Array rows skipped after sorting', 0, lambda v: nonnegative('offset', v), minimum=0,
                   cli=CliBinding(('--offset',)))
PARAM_SPECS = (VIEW, WHERE, DETAIL, SORT, LIMIT, OFFSET)


def result_type(params: Any) -> str:
    view = view_name(dict(peek_query_items(params)).get('view', 'value'))
    return 'json_' + view if view in VIEWS else 'json_value'


def uri_result_type(resource: str) -> str:
    query = resource.partition('?')[2]
    first = query.partition('&')[0].lower()
    if first in LEGACY_SELECTORS:
        return 'json_' + view_name(first)
    return result_type(parse_query_params(query))


def validate_request(params: QueryParams, args=None) -> None:
    values = dict(peek_query_items(params))
    view = VIEW.validate(values.get('view'))
    if not params._selectors and view != 'value':
        if values.get('where') or any(key in values for key in ('sort', 'limit', 'offset')):
            raise RequestValidationError('where/sort/limit/offset require the value view')
    if values.get('detail') and view != 'flatten':
        raise RequestValidationError('detail requires the flatten view')
    if view == 'value':
        try:
            parse_query_filters('&'.join(WHERE.read(params)), record=False)
        except ValueError as exc:
            raise RequestValidationError(str(exc)) from exc


def legacy_raw(params: QueryParams) -> bool:
    if params._selectors.get('view') not in ('flatten', 'gron'):
        return False
    terms = dict(peek_query_items(params)).get('where', [])
    raw = any(term.strip().lower() == 'data-only' for term in terms)
    if raw:
        params.mark('data-only')
    return bool(raw)
