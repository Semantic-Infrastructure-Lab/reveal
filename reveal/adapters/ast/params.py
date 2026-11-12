"""Declared AST controls; expressions continue through the existing AST filter parser."""
from typing import Any

from ...utils.query_binding import boolean_value
from ...utils.query_parser import CliBinding, ParamSpec, QueryParams, peek_query_items
from ...utils.query_control import ResultControl
from .queries import ALL_OP, parse_query, validate_filter_values, _condition


def _expressions(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError('where requires one or more nonempty expressions')
    return list(values)


WHERE = ParamSpec('where', 'array', 'Filter expressions, ANDed; repeat --where for multiple bounds',
                  [], _expressions, role='filter-expression', cli=CliBinding(('--where',), action='append'))
KIND = ParamSpec('kind', 'string', 'Element kind (function, method, class, struct, import, interface, ...)',
                 None, str, aliases=('type',), cli=CliBinding(('--kind', '--type')))
VIEW = ParamSpec('view', 'string', 'Answer view: calls, dict-heatmap or dict-schemas (Python evidence)',
                 None, lambda value: None if value is True else str(value), aliases=('show',),
                 cli=CliBinding(('--view', '--show')))
BUILTINS = ParamSpec('builtins', 'boolean', 'Include builtin calls in the calls view', False,
                     boolean_value, cli=CliBinding(('--builtins',), action='store_true'))
REVEAL_TYPE = ParamSpec('reveal-type', 'string', 'Type evidence for a variable (Python only)',
                        None, lambda value: None if value is True else str(value), aliases=('reveal_type',), uri_codec='raw',
                        cli=CliBinding(('--reveal-type',), dest='reveal_type'))
SORT = ParamSpec('sort', 'string', 'Sort field; prefix - for descending', None, str,
                 cli=CliBinding(('--sort',)))
LIMIT = ParamSpec('limit', 'integer', 'Answer rows (0 returns an empty page)', None, int,
                  minimum=0, zero_policy='empty page', cli=CliBinding(('--limit',)))
OFFSET = ParamSpec('offset', 'integer', 'Answer rows skipped after sorting', 0, int,
                   minimum=0, cli=CliBinding(('--offset',)))
PARAM_SPECS = (WHERE, KIND, VIEW, BUILTINS, REVEAL_TYPE, SORT, LIMIT, OFFSET)


def _and_kind(query: dict, condition: dict) -> None:
    prior = query.get('type')
    conditions = [] if prior is None else (prior['value'] if prior['op'] == ALL_OP else [prior])
    added = condition['value'] if condition['op'] == ALL_OP else [condition]
    combined = conditions + added
    query['type'] = combined[0] if len(combined) == 1 else {'op': ALL_OP, 'value': combined}


def ast_query(params: QueryParams):
    query = parse_query('&'.join(WHERE.read(params)))
    if 'kind' in query:
        _and_kind(query, query.pop('kind'))
    kind = KIND.read(params)
    if kind is not None:
        _and_kind(query, _condition('=', kind))
    validate_filter_values(query)
    return query


def result_control(params: QueryParams) -> ResultControl:
    # Validated bindings are inspected here; ResultControl records reads only when applied.
    values = dict(peek_query_items(params))
    sort = values.get('sort')
    control = ResultControl(sort_field=sort.lstrip('-') if sort else None,
                            sort_descending=bool(sort and sort.startswith('-')),
                            limit=values.get('limit'), offset=values.get('offset', 0))
    control.__dict__['_reads'] = params._reads
    return control
