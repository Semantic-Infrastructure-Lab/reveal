"""Declared Git controls, applied through the existing resource and predicate owners."""
from dataclasses import dataclass
from typing import Any

from ...utils.query_binding import boolean_value
from ...utils.query_parser import CliBinding, ParamSpec, ParamValueError, nonempty_scalar, nonnegative_display_limit


def expressions(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
        raise ValueError('where requires nonempty expressions')
    return list(values)


def predicates(value):
    from ...utils.query_parser import parse_query_filters
    terms = expressions(value)
    try:
        for term in terms:
            parse_query_filters(term, percent_decode_values=True, record=False)
    except UnicodeDecodeError:
        raise
    except ValueError as exc:
        raise ParamValueError(str(exc)) from exc
    return terms


def detail(value: Any) -> str:
    if isinstance(value, bool):
        return 'full' if value else 'normal'
    name = nonempty_scalar(value)
    return 'normal' if name == 'summary' else name


@dataclass(frozen=True)
class MergePolicy:
    include: bool
    legacy: bool


def merge_policy(value):
    positive = str(value).lower()
    included = positive == 'on' if positive in ('on', 'off') else boolean_value(value)
    return MergePolicy(included, not isinstance(value, bool) and positive not in ('on', 'off'))


def string(name, description, *, aliases=(), choices=()):
    return ParamSpec(name, 'string', description, None, nonempty_scalar, aliases=aliases, choices=choices,
                     cli=CliBinding(('--' + name,)))


VIEW = string('view', 'history, blame, diff or ownership; omitted preserves resource-dependent inspection',
              aliases=('type',), choices=('history', 'log', 'blame', 'diff', 'ownership'))
WHERE = ParamSpec('where', 'array', 'Existing commit predicates; repeat to AND (Git DSL percent-decodes values)',
                  [], predicates, role='filter-expression', cli=CliBinding(('--where',), action='append'))
DETAIL = ParamSpec('detail', 'string', 'normal, full blame, or raw historical file content', None, detail,
                   choices=('normal', 'full', 'raw'), cli=CliBinding(('--detail',)))
MERGES = ParamSpec('merges', 'boolean', 'Include or exclude merge commits; omitted preserves each view default',
                   None, merge_policy, cli=CliBinding(('--merges',)))
NO_MERGES = ParamSpec('no_merges', 'boolean', 'Legacy exclusion of merge commits in history', None, boolean_value)
RAW = ParamSpec('raw', 'boolean', 'Legacy raw historical file content', None, boolean_value)
SORT = string('sort', 'Commit field; prefix - for descending')
LIMIT = ParamSpec('limit', 'integer', 'Existing view cap: rows, or commit-input budget on timelines; zero is empty', None,
                  lambda v: nonnegative_display_limit(v, name='limit'), minimum=0,
                  zero_policy='empty page', cli=CliBinding(('--limit',)))
OFFSET = ParamSpec('offset', 'integer', 'Rows skipped after sorting', 0,
                   lambda v: nonnegative_display_limit(v, name='offset'), minimum=0,
                   cli=CliBinding(('--offset',)))
CONTEXT = ParamSpec('context', 'integer', 'Context lines for a diff', None,
                    lambda v: nonnegative_display_limit(v, name='context'), minimum=0,
                    cli=CliBinding(('--context',)))
PARAM_SPECS = (VIEW, WHERE, DETAIL, MERGES, NO_MERGES, RAW, SORT, LIMIT, OFFSET, CONTEXT,
               *(string(name, description) for name, description in (
                   ('ref', 'Starting branch, tag or commit'), ('element', 'Semantic element name'),
                   ('bucket', 'Timeline period: week or month'), ('ignore', 'Blame commit hash prefixes to suppress'))),
               *(ParamSpec(name, 'array', description, [], expressions,
                           cli=CliBinding(('--' + name,), action='append'))
                 for name, description in (('since', 'Inclusive starting date'), ('until', 'Inclusive ending date'))))


def runtime_query(params):
    """Translate bound controls to the existing view readers without URI serialization."""
    from ...utils.query_parser import QueryParams, peek_query_items, parse_query_params
    values = dict(peek_query_items(params))
    query = QueryParams({key: value for key, value in values.items()
                         if value is not None and value != []
                         and key not in ('where', 'view', 'detail', 'raw', 'merges', 'no_merges')})
    view = VIEW.read(params)
    if view is not None:
        query['type'] = 'history' if view == 'log' else view
    _runtime_detail(params, query)
    _runtime_merges(params, query)
    items: list[tuple[str, Any]] = []
    for key, value in list(peek_query_items(query)):
        if key in ('since', 'until'):
            items.extend((key, date) for date in value)
            query[key] = value[-1]
        else:
            items.append((key, value))
    for expression in WHERE.read(params):
        for part in expression.split('&'):
            for key, value in peek_query_items(parse_query_params(part)):
                query[key] = value
                items.append((key, value))
    return query, items


def _runtime_detail(params, query):
    from ...errors import RequestValidationError
    level = DETAIL.read(params)
    raw = RAW.read(params)
    if level is not None and raw is not None:
        raise RequestValidationError('detail and legacy raw cannot be supplied together')
    if level == 'raw':
        query['raw'] = '1'
    elif level is not None:
        query['detail'] = 'summary' if level == 'normal' else level
    if raw is not None:
        query['raw'] = '1' if raw else '0'


def _runtime_merges(params, query):
    from ...errors import RequestValidationError
    merges = MERGES.read(params)
    no_merges = NO_MERGES.read(params)
    if merges is not None and not merges.legacy and no_merges is not None:
        raise RequestValidationError('merges and legacy no_merges cannot be supplied together')
    if merges is not None:
        key = 'merges' if merges.legacy or query.get('type') == 'ownership' else 'no_merges'
        included = merges.include if key == 'merges' else not merges.include
        query[key] = '1' if included else '0'
    if no_merges is not None:
        query['no_merges'] = '1' if no_merges else '0'
