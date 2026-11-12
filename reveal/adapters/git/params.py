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
    from ...utils.query_parser import parse_query_filters, query_key
    terms = expressions(value)
    try:
        for term in terms:
            for part in term.split('&'):
                if query_key(part) in QUERY_CONTROL_NAMES:
                    raise ParamValueError('where cannot set query controls; use the named control outside where')
                field, separator, text = part.partition('=')
                if field.strip() in ('content', 'content~'):
                    if not separator or not text.strip():
                        raise ParamValueError('content predicate requires nonempty literal text')
                else:
                    parse_query_filters(part, percent_decode_values=True, record=False)
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
VERBOSE = ParamSpec('verbose', 'boolean', 'Legacy full blame detail', False, boolean_value)
NO_MERGES = ParamSpec('no_merges', 'boolean', 'Legacy exclusion of merge commits in history', None, boolean_value)
RAW = ParamSpec('raw', 'boolean', 'Legacy raw historical file content', None, boolean_value)
SORT = string('sort', 'Commit field; prefix - for descending')
LIMIT = ParamSpec('limit', 'integer', 'Returned rows; zero is empty (legacy type= aggregate requests retain input-window limits)', None,
                  lambda v: nonnegative_display_limit(v, name='limit'), minimum=0,
                  zero_policy='empty page', cli_flags=(('all', '1000000'),), cli=CliBinding(('--limit',)))
SCAN_LIMIT = ParamSpec('scan-limit', 'integer', 'Commit-input budget for ownership or timeline; required loss exits 3',
                       None, lambda v: nonnegative_display_limit(v, name='scan-limit'), minimum=0,
                       aliases=('scan_limit',), zero_policy='count no commits',
                       cli=CliBinding(('--scan-limit',), dest='scan_limit'))
OFFSET = ParamSpec('offset', 'integer', 'Rows skipped after sorting', 0,
                   lambda v: nonnegative_display_limit(v, name='offset'), minimum=0,
                   cli=CliBinding(('--offset',)))
CONTEXT = ParamSpec('context', 'integer', 'Context lines for a diff', None,
                    lambda v: nonnegative_display_limit(v, name='context'), minimum=0,
                    cli=CliBinding(('--context',)))
PARAM_SPECS = (VIEW, WHERE, DETAIL, VERBOSE, MERGES, NO_MERGES, RAW, SORT, LIMIT, SCAN_LIMIT, OFFSET, CONTEXT,
               *(string(name, description) for name, description in (
                   ('ref', 'Starting branch, tag or commit'), ('element', 'Semantic element name'),
                   ('bucket', 'Timeline period: week or month'), ('ignore', 'Blame commit hash prefixes to suppress'))),
               *(ParamSpec(name, 'array', description, [], expressions,
                           cli=CliBinding(('--' + name,), action='append'))
                 for name, description in (('since', 'Inclusive starting date'), ('until', 'Inclusive ending date'))))


QUERY_CONTROL_NAMES = frozenset(name for spec in PARAM_SPECS for name in (spec.name, *spec.aliases))


def runtime_query(params):
    """Translate bound controls to the existing view readers without URI serialization."""
    from ...utils.query_parser import QueryParams, peek_query_items, parse_query_params
    values, aggregate_control = _aggregate_controls(params, dict(peek_query_items(params)))
    query = QueryParams({key: value for key, value in values.items()
                         if value is not None and value != []
                         and key not in ('where', 'view', 'detail', 'verbose', 'raw', 'merges', 'no_merges', 'scan-limit')})
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
    return query, items, aggregate_control




def validate_resource_controls(params, subpath):
    from ...errors import RequestValidationError
    from ...utils.query_parser import peek_query_items
    values = dict(peek_query_items(params))
    view = values.get('view')
    _validate_content_scope(values, subpath)
    if values.get('detail') == 'raw' and (not subpath or view is not None):
        raise RequestValidationError('detail=raw requires a file-content request (omit view)')
    aggregate = view == 'ownership' or (view in ('history', 'log') and values.get('bucket'))
    if values.get('scan-limit') is not None and not aggregate:
        raise RequestValidationError('scan-limit requires ownership or a bucketed history view')
    if values.get('detail') is not None and values.get('raw') is not None:
        raise RequestValidationError('detail and legacy raw cannot be supplied together')
    merges = values.get('merges')
    if merges is not None and not merges.legacy and values.get('no_merges') is not None:
        raise RequestValidationError('merges and legacy no_merges cannot be supplied together')


def _validate_content_scope(values, subpath):
    from ...errors import RequestValidationError
    view = values.get('view')
    content = any(part.partition('=')[0].strip() in ('content', 'content~')
                  for term in values.get('where', []) for part in term.split('&'))
    if content and (values.get('bucket') or view == 'ownership'
                    or (subpath and view not in ('history', 'log'))):
        raise RequestValidationError('changed-line content predicates require flat history or repository recent commits')


def _aggregate_controls(params, values):
    from ...utils.query_control import declared_result_control
    view = values.get('view')
    aggregate = view == 'ownership' or (view in ('history', 'log') and values.get('bucket'))
    if not aggregate:
        return values, None
    legacy = ('type' in params._supplied_aliases
              and not params._overrides.intersection({'view', 'sort', 'limit', 'offset', 'scan-limit'})
              and values.get('scan-limit') is None)
    if legacy:
        if view == 'ownership' and values.get('limit') == 0:
            LIMIT.read(params)  # the old zero explicitly removes the input window
            values.pop('limit')
        return values, None
    control = declared_result_control(params)
    scan = SCAN_LIMIT.read(params)
    for key in ('limit', 'sort', 'offset'):
        values.pop(key, None)
    if scan is not None:
        values['limit'] = scan
    return values, control


def apply_aggregate_rows(result: dict, control) -> dict:
    from ...utils.query import apply_result_control, unknown_sort_field_warning
    from ...utils.results import note_truncation, note_warning, truncations_of, relabel_truncations
    if control is None:
        return result
    for entry in truncations_of(result):
        if entry.get('field') == 'commits':
            entry['cause'] = 'scan-limit'
    relabel_truncations(result, 'commits', 'raise scan-limit; aggregate counts cover only the retained commit input')
    if not control.any_set():
        return result
    field = 'authors' if result['type'] == 'git_ownership' else 'buckets'
    whole = result[field]
    if control.sort_field:
        note_warning(result, unknown_sort_field_warning(control.sort_field, whole))
    rows = apply_result_control(whole, control)
    result[field] = rows
    note_truncation(result, field, len(rows), len(whole), 'limit',
                    hint='raise limit or page with offset; aggregate counts retain the input population')
    return result

def _runtime_detail(params, query):
    level = DETAIL.read(params)
    if VERBOSE.read(params) and level is None:
        level = 'full'
    raw = RAW.read(params)
    if level == 'raw':
        query['raw'] = '1'
    elif level is not None:
        query['detail'] = 'summary' if level == 'normal' else level
    if raw is not None:
        query['raw'] = '1' if raw else '0'


def _runtime_merges(params, query):
    merges = MERGES.read(params)
    no_merges = NO_MERGES.read(params)
    if merges is not None:
        key = 'merges' if merges.legacy or query.get('type') == 'ownership' else 'no_merges'
        included = merges.include if key == 'merges' else not merges.include
        query[key] = '1' if included else '0'
    if no_merges is not None:
        query['no_merges'] = '1' if no_merges else '0'
