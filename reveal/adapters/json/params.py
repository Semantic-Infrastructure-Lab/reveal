"""JSON controls distinguish dataset predicates from legacy first-word inspection modes."""
from typing import Any, Dict, Optional, Tuple

from ...errors import RequestValidationError
from ...utils.query_binding import boolean_value, given_controls, unread_by_data_warning
from ...utils.query_parser import (CliBinding, LegacySpelling, ParamSpec, ParamValueError, QueryParams,
                                   parse_query_params, peek_query_items, legacy_check, legacy_slices)
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
                 'value', view_name, choices=VIEWS,
                 legacy=tuple(LegacySpelling(selector, first=True) for selector in LEGACY_SELECTORS), role='operation',
                 cli=CliBinding(('--view',)))
# The array controls are read by the value answer and detail by the flatten text (COMMAND_MODEL "Applicability",
# BACK-2656); whether the value at the path is a list only the data can tell (array_controls_unread_by_data).
_VALUE, _FLATTEN = ('json_value',), ('json_flatten',)
WHERE = ParamSpec('where', 'array', 'Array-element predicates, ANDed; repeat for multiple constraints',
                  [], expressions, role='filter-expression', repeatable=True, cli=CliBinding(('--where',)),
                  open_fields='any key of the array elements', answers=_VALUE)
DETAIL = ParamSpec('detail', 'string', 'Flatten text detail: full (default) or raw lines',
                   'full', str, choices=('full', 'raw'), cli=CliBinding(('--detail',)), answers=_FLATTEN)
SORT = ParamSpec('sort', 'string', 'Array field; prefix - for descending', None, str,
                 cli=CliBinding(('--sort',)), answers=_VALUE)
LIMIT = ParamSpec('limit', 'integer', 'Array rows; 0 = no cap', None, lambda v: nonnegative('limit', v), minimum=0,
                  zero_policy='no cap', cli=CliBinding(('--limit',)), answers=_VALUE)
OFFSET = ParamSpec('offset', 'integer', 'Array rows skipped after sorting', 0, lambda v: nonnegative('offset', v), minimum=0,
                   cli=CliBinding(('--offset',)), answers=_VALUE)
ARRAY_CONTROLS = (WHERE, SORT, LIMIT, OFFSET)
PARAM_SPECS: Tuple[ParamSpec, ...] = (VIEW, WHERE, DETAIL, SORT, LIMIT, OFFSET)
# --head/--tail/--range slice this noun's rows today: flag-only legacy modifiers until the cut, read by the answers named
# (BACK-2673; their notes are the flag:<noun>.<flag> RETIREMENTS rows).
LEGACY_SLICES = legacy_slices(head=('json_value',), tail=('json_value',), range=('json_value',))
PARAM_SPECS = (*PARAM_SPECS, *LEGACY_SLICES, legacy_check())  # --check never changed a JSON answer (BACK-2708)


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
    if VIEW.validate(values.get('view')) == 'value':
        try:
            parse_query_filters('&'.join(WHERE.read(params)), record=False)
        except ValueError as exc:
            raise RequestValidationError(str(exc)) from exc


def legacy_raw(params: QueryParams) -> bool:
    if params._selectors.get('view') not in ('flatten', 'gron'):
        return False
    terms = dict(peek_query_items(params)).get('where', [])
    raw = [term for term in terms if term.strip().lower() == 'data-only']
    if not raw:
        return False
    params.mark('data-only')
    params._folded = tuple(key for key in params._folded if key != 'data-only')  # the flatten answer's word, not where's
    if len(raw) == len(terms):  # any other term is where's, which flatten does not read
        params._given.discard('where')
    return True


def array_controls_unread_by_data(params: Dict[str, Any], value: Any, path: str) -> Optional[dict]:
    """The value answer's array controls given for a value that is not a list: only the data shows they are unread, so
    the answer carries the one shared warning, exit 0 (COMMAND_MODEL "Applicability", Scott 2026-11-18 Q2)."""
    given = [spec.name for spec in (*ARRAY_CONTROLS, *LEGACY_SLICES) if spec.name in given_controls(params)]
    return unread_by_data_warning(params, given, f'the value at {path} is {_json_kind(value)}, not a list')


def _json_kind(value: Any) -> str:
    if isinstance(value, dict):
        return 'an object'
    if isinstance(value, str):
        return 'a string'
    if isinstance(value, bool):
        return 'a boolean'
    return 'a number' if isinstance(value, (int, float)) else 'null'
