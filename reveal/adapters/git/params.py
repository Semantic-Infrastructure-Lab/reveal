"""Declared Git controls, applied through the existing resource and predicate owners."""
from typing import Any

from ...utils.query_binding import boolean_value, switch_value, verbose_legacy
from ...utils.query_parser import CliBinding, LegacySpelling, ParamSpec, ParamValueError, nonempty_scalar, nonnegative_display_limit, legacy_check, legacy_slices


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


def string(name, description, *, legacy=(), choices=(), role=None, answers=()):
    return ParamSpec(name, 'string', description, None, nonempty_scalar, legacy=legacy, choices=choices, role=role,
                     cli=CliBinding(('--' + name,)), answers=answers)


# The answers each control is read by (COMMAND_MODEL "Applicability", BACK-2656). The repository overview, a ref's
# history, a path's history and a timeline walk commits: they read the commit filter and the merge policy; ownership
# reads the row controls and merges but aggregates unfiltered; scan-limit budgets the aggregates' commit input; blame
# reads detail and ignore, a diff context, and the element narrows a file's history, blame, diff and timeline. A file's
# content reads raw (detail=raw selects it). The repository's timeline is the timeline type too: its element check is
# validate_resource_controls' (a repository has no element).
_COMMITS = ('git_repository', 'git_ref', 'git_file_history', 'git_directory_history', 'git_timeline')
_ROWS = (*_COMMITS, 'git_ownership')
_AGGREGATES = ('git_ownership', 'git_timeline')
_BLAME, _DIFF = 'git_file_blame', 'git_file_diff'

VIEW = string('view', 'history, blame, diff or ownership; omitted preserves resource-dependent inspection',
              legacy=(LegacySpelling('type'),), choices=('history', 'log', 'blame', 'diff', 'ownership'), role='operation')
WHERE = ParamSpec('where', 'array', 'Existing commit predicates; repeat to AND (Git DSL percent-decodes values)',
                  [], predicates, role='filter-expression', repeatable=True, cli=CliBinding(('--where',)),
                  fields=('author', 'email', 'date', 'hash', 'message', 'timestamp', 'content'), answers=_COMMITS)
DETAIL = ParamSpec('detail', 'string', 'normal, full blame, or raw historical file content', None, detail,
                   choices=('normal', 'full', 'raw'), cli=CliBinding(('--detail',)),
                   legacy=(verbose_legacy('full', 'detail=full (--detail full)'),), answers=(_BLAME, 'git_file'))
# One on/off switch on every view (COMMAND_MODEL "Switches"): a legacy boolean spelling (merges=0/1) is its value.
MERGES = ParamSpec('merges', 'boolean', 'Include or exclude merge commits; omitted preserves each view default',
                   None, switch_value, cli=CliBinding(('--merges',)), answers=_ROWS)
NO_MERGES = ParamSpec('no_merges', 'boolean', 'Legacy exclusion of merge commits in history', None, boolean_value,
                      answers=_COMMITS)
RAW = ParamSpec('raw', 'boolean', 'Legacy raw historical file content', None, boolean_value,
                answers=('git_file', 'git_file_structure'))
SORT = string('sort', 'Commit field; prefix - for descending', answers=_ROWS)
LIMIT = ParamSpec('limit', 'integer', 'Returned rows; 0 = no cap (legacy type= aggregate requests retain input-window limits)', None,
                  lambda v: nonnegative_display_limit(v, name='limit'), minimum=0,
                  zero_policy='no cap', cli_flags=(('all', '1000000'),), cli=CliBinding(('--limit',)), answers=_ROWS)
SCAN_LIMIT = ParamSpec('scan-limit', 'integer', 'Commit-input budget for ownership or timeline; required loss exits 3',
                       None, lambda v: nonnegative_display_limit(v, name='scan-limit'), minimum=0,
                       aliases=('scan_limit',), zero_policy='count no commits',
                       cli=CliBinding(('--scan-limit',), dest='scan_limit'), answers=_AGGREGATES)
OFFSET = ParamSpec('offset', 'integer', 'Rows skipped after sorting', 0,
                   lambda v: nonnegative_display_limit(v, name='offset'), minimum=0,
                   cli=CliBinding(('--offset',)), answers=_ROWS)
CONTEXT = ParamSpec('context', 'integer', 'Context lines for a diff', None,
                    lambda v: nonnegative_display_limit(v, name='context'), minimum=0,
                    cli=CliBinding(('--context',)), answers=(_DIFF,))
PARAM_SPECS = (VIEW, WHERE, DETAIL, MERGES, NO_MERGES, RAW, SORT, LIMIT, SCAN_LIMIT, OFFSET, CONTEXT,
               string('ref', 'Starting branch, tag or commit'),
               string('element', 'Semantic element name', answers=('git_file_history', _BLAME, _DIFF, 'git_timeline')),
               string('bucket', 'Timeline period: week or month', choices=('week', 'month'), answers=('git_timeline',)),
               string('ignore', 'Blame commit hash prefixes to suppress', answers=(_BLAME,)),
               # since/until are settings (one bound each, COMMAND_MODEL "Conflicting values"), carried as a list
               *(ParamSpec(name, 'array', description, [], expressions, cli=CliBinding(('--' + name,)), answers=_COMMITS)
                 for name, description in (('since', 'Inclusive starting date'), ('until', 'Inclusive ending date'))))
# --head/--tail/--range slice this noun's rows today: flag-only legacy modifiers until the cut, read by the answers named
# (BACK-2673; their notes are the flag:<noun>.<flag> RETIREMENTS rows).
_SLICED = ('git_repository', 'git_ref', 'git_file_history', 'git_directory_history')
PARAM_SPECS = (*PARAM_SPECS, *legacy_slices(head=_SLICED, tail=_SLICED, range=_SLICED),
               legacy_check())  # --check never changed a Git answer (BACK-2708)


QUERY_CONTROL_NAMES = frozenset(name for spec in PARAM_SPECS for name in spec.spellings)


def runtime_query(params):
    """Translate bound controls to the existing view readers without URI serialization."""
    from ...utils.query_parser import QueryParams, peek_query_items, parse_query_params
    values, aggregate_control = _aggregate_controls(params, dict(peek_query_items(params)))
    query = QueryParams({key: value for key, value in values.items()
                         if value is not None and value != []
                         and key not in ('where', 'view', 'detail', 'raw', 'merges', 'no_merges', 'scan-limit')})
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
    # Which answers read scan-limit, element and the rest is their declaration's (BACK-2656); a repository's timeline
    # shares the timeline type with a path's, so only this resource check can tell that it has no element to narrow to.
    if values.get('element') is not None and not subpath:
        raise RequestValidationError("element names an element of a file: give the file's path "
                                     '(git://PATH/FILE?view=history&element=NAME)')
    if values.get('detail') is not None and values.get('raw') is not None:
        raise RequestValidationError('detail and legacy raw cannot be supplied together')
    if values.get('merges') is not None and values.get('no_merges') is not None:
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
        key = 'merges' if query.get('type') == 'ownership' else 'no_merges'
        included = merges if key == 'merges' else not merges
        query[key] = '1' if included else '0'
    if no_merges is not None:
        query['no_merges'] = '1' if no_merges else '0'
