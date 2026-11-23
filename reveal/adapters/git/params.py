"""Declared Git controls, applied through the existing resource and predicate owners."""
from typing import Any

from ...utils.query_binding import boolean_value, legacy_switch, switch_value, verbose_legacy
from ...utils.query_parser import CliBinding, LegacySpelling, ParamSpec, ParamValueError, nonempty_scalar, nonnegative_display_limit, legacy_check, legacy_slices
from ...utils.time_window import time_window_param


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
    return nonempty_scalar(value)  # summary is a value entry translated to normal (its declaration)


def raw_detail(value: Any) -> Any:
    """Legacy ``raw`` as the detail level it stands for: true is ``detail=raw``; false is not given (the structure)."""
    try:
        return 'raw' if boolean_value(value) else None
    except ValueError:
        raise ParamValueError(f'raw must be a valid boolean, got {value!r}: use detail=raw (--detail raw)') from None


def commit_prefixes(value: Any) -> list[str]:
    """Blame's suppressed commits: hash prefixes, comma-separated, from one value or every repeat of it."""
    values = value if isinstance(value, (list, tuple)) else [value]
    if any(not isinstance(item, str) or '\x00' in item for item in values):
        raise ParamValueError(f'ignore-commits must be commit hash prefixes, got {value!r}')
    prefixes = [part.strip() for item in values for part in item.split(',') if part.strip()]
    if not prefixes:
        raise ParamValueError('ignore-commits needs a commit hash prefix: --ignore-commits SHA[,SHA...]')
    return list(dict.fromkeys(prefixes))


def _ignore_off(raw: Any) -> bool:
    """Whether a legacy ``ignore`` value is ``off`` (any case): it turned auto-ignore off."""
    return isinstance(raw, str) and raw.strip().lower() == 'off'


# The commit fields where filters and bare URI keys read (COMMAND_MODEL "Bare URI keys": a closed field set), each
# described once: the schema's filter_fields and the where declaration read this table.
COMMIT_FILTER_FIELDS = {
    'author': ('string', 'Commit author name (case-insensitive; ~= is a regex)'),
    'email': ('string', 'Commit author email (case-insensitive; ~= is a regex)'),
    'date': ('string', 'Commit date: =, !=, >, <, >=, <= and a range =a..b with an ISO date or timestamp. A year, '
                       'month or day bound (2026, 2026-01, 2026-01-31) is the whole period; a zone (Z, +02:00) is '
                       'converted to the local time commit dates are written in'),
    'hash': ('string', 'Commit short hash (7 characters, compared whole; ~=^PREFIX matches a prefix)'),
    'message': ('string', 'Commit message (~= is a regex)'),
    'timestamp': ('integer', 'Commit time in epoch seconds (>, <, >=, <=, =, !=)'),
    'content': ('string', 'Changed-line pickaxe: commits whose diff added or removed a line containing the literal '
                          'text (content~=TEXT; flat history or repository recent commits only)'),
}


def string(name, description, *, legacy=(), choices=(), role=None, answers=()):
    return ParamSpec(name, 'string', description, None, nonempty_scalar, legacy=legacy, choices=choices, role=role,
                     cli=CliBinding(('--' + name,)), answers=answers)


# The answers each control is read by (COMMAND_MODEL "Applicability", BACK-2656). The repository overview, a ref's
# history, a path's history and a timeline walk commits: they read the commit filter and the merge policy; ownership
# reads the row controls and merges but aggregates unfiltered; scan-limit budgets the aggregates' commit input; blame
# reads detail, ignore-commits and auto-ignore, a diff context, and the element narrows a file's history, blame, diff and timeline. A file's
# content reads raw (detail=raw selects it). The repository's timeline is the timeline type too: its element check is
# validate_resource_controls' (a repository has no element).
_COMMITS = ('git_repository', 'git_ref', 'git_file_history', 'git_directory_history', 'git_timeline')
_ROWS = (*_COMMITS, 'git_ownership')
_AGGREGATES = ('git_ownership', 'git_timeline')
_BLAME, _DIFF = 'git_file_blame', 'git_file_diff'


def aggregate_selection(values) -> bool:
    """Whether a request's controls select an aggregate answer: ownership, or history bucketed into a timeline."""
    view = values.get('view')
    return view == 'ownership' or (view in ('history', 'log') and bool(values.get('bucket')))


# type and the log view are older words for view (D20; COMMAND_MODEL "Spellings"): their rows note the replacement.
# A type= aggregate request's limit bounded the commit input, which is scan-limit now (ruling Q1 A): the binder moves it.
VIEW = string('view', 'history, blame, diff or ownership; omitted preserves resource-dependent inspection',
              legacy=(LegacySpelling('type', rebinds=(('limit', 'scan-limit'),), rebinds_when=aggregate_selection),
                      LegacySpelling('view', value='log', codec=lambda _: 'history')),
              choices=('history', 'blame', 'diff', 'ownership'), role='operation')  # log: a value entry of history
WHERE = ParamSpec('where', 'array', 'Existing commit predicates; repeat to AND (Git DSL percent-decodes values)',
                  [], predicates, role='filter-expression', repeatable=True, cli=CliBinding(('--where',)),
                  fields=tuple(COMMIT_FILTER_FIELDS), answers=_COMMITS)
# Legacy raw is detail=raw (raw=false: the structure, the omitted level); summary is the older word for normal.
DETAIL = ParamSpec('detail', 'string', 'normal, full blame, or raw historical file content', None, detail,
                   choices=('normal', 'full', 'raw'), cli=CliBinding(('--detail',)),
                   legacy=(verbose_legacy('full', 'detail=full (--detail full)'), LegacySpelling('raw', codec=raw_detail),
                           LegacySpelling('detail', value='summary', codec=lambda _: 'normal')),
                   answers=(_BLAME, 'git_file'))
# One on/off switch on every view (COMMAND_MODEL "Switches"): a legacy boolean spelling (merges=0/1) is its value, and
# legacy no_merges is merges=off (the Metrics declaration, BACK-2621).
MERGES = ParamSpec('merges', 'boolean', 'Include or exclude merge commits; omitted preserves each view default',
                   None, switch_value, cli=CliBinding(('--merges',)),
                   legacy=(LegacySpelling('no_merges', codec=legacy_switch('no_merges', 'off', 'on'),
                                          flag='--no-merges', flag_value=True),), answers=_ROWS)
SORT = string('sort', 'Commit field; prefix - for descending', answers=_ROWS)
LIMIT = ParamSpec('limit', 'integer', 'Returned rows; 0 = no cap (a legacy type= aggregate request binds its limit as scan-limit)', None,
                  lambda v: nonnegative_display_limit(v, name='limit'), minimum=0,
                  zero_policy='no cap', cli_flags=(('all', '1000000'),), cli=CliBinding(('--limit',)), answers=_ROWS)
# Omitted, the timeline reads at most 20,000 commits and ownership every commit; 0 is no budget (it read every commit
# while declared 'count no commits', BACK-2616 B16).
SCAN_LIMIT = ParamSpec('scan-limit', 'integer', 'Commit-input budget for ownership or timeline (omitted: timeline '
                       '20,000, ownership unbounded; 0 = no budget); required loss exits 3',
                       None, lambda v: nonnegative_display_limit(v, name='scan-limit'), minimum=0,
                       aliases=('scan_limit',), zero_policy='no cap',
                       cli=CliBinding(('--scan-limit',), dest='scan_limit'), answers=_AGGREGATES)
OFFSET = ParamSpec('offset', 'integer', 'Rows skipped after sorting', 0,
                   lambda v: nonnegative_display_limit(v, name='offset'), minimum=0,
                   cli=CliBinding(('--offset',)), answers=_ROWS)
CONTEXT = ParamSpec('context', 'integer', 'Context lines for a diff', None,
                    lambda v: nonnegative_display_limit(v, name='context'), minimum=0,
                    cli=CliBinding(('--context',)), answers=(_DIFF,))
# Blame's suppression is two controls (Scott 2026-11-22, BACK-2733): the commits to suppress (they filter, so they repeat
# and commas join) and the auto-ignore switch (.git-blame-ignore-revs and the noise heuristic; COMMAND_MODEL "Switches").
# The older word ignore carried both in one scalar: ignore=off is auto-ignore=off and ignore=SHAS the commits, so its
# value decides its target (LegacySpelling.sets_when); its answers are the same, its row notes the replacement.
IGNORE_COMMITS = ParamSpec('ignore-commits', 'array', 'Blame commit hash prefixes to suppress (comma-separated; repeat '
                           'to add more)', None, commit_prefixes, aliases=('ignore_commits',), repeatable=True,
                           cli=CliBinding(('--ignore-commits',), dest='ignore_commits'), answers=(_BLAME,),
                           legacy=(LegacySpelling('ignore', flag='--ignore', sets=(('auto-ignore', 'off'),),
                                                  sets_when=_ignore_off,
                                                  codec=lambda raw: None if _ignore_off(raw) else raw),))
AUTO_IGNORE = ParamSpec('auto-ignore', 'boolean', 'Auto-ignore noise commits in blame (.git-blame-ignore-revs and the '
                        'noise heuristic): on (the default) or off', None, switch_value, aliases=('auto_ignore',),
                        cli=CliBinding(('--auto-ignore',), dest='auto_ignore'), answers=(_BLAME,))
PARAM_SPECS = (VIEW, WHERE, DETAIL, MERGES, SORT, LIMIT, SCAN_LIMIT, OFFSET, CONTEXT,
               string('ref', 'Starting branch, tag or commit'),
               string('element', 'Semantic element name', answers=('git_file_history', _BLAME, _DIFF, 'git_timeline')),
               string('bucket', 'Timeline period: week or month', choices=('week', 'month'), answers=('git_timeline',)),
               IGNORE_COMMITS, AUTO_IGNORE,
               # since/until are settings (one bound each, COMMAND_MODEL "Conflicting values") in the one time-window
               # grammar (COMMAND_MODEL "Time window", BACK-2728), compared at the bound's precision as date>=/date<=
               *(time_window_param(name, description, answers=_COMMITS)
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
                         and key not in ('where', 'view', 'detail', 'merges', 'scan-limit', 'ignore-commits',
                                         'auto-ignore')})
    view = VIEW.read(params)
    if view is not None:
        query['type'] = 'history' if view == 'log' else view
    _runtime_detail(params, query)
    _runtime_merges(params, query)
    _runtime_ignore(params, query)
    items: list[tuple[str, Any]] = list(peek_query_items(query))
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
                                     '(reveal git PATH/FILE --view history --element NAME)')


def _validate_content_scope(values, subpath):
    from ...errors import RequestValidationError
    view = values.get('view')
    content = any(part.partition('=')[0].strip() in ('content', 'content~')
                  for term in values.get('where', []) for part in term.split('&'))
    if content and (values.get('bucket') or view == 'ownership'
                    or (subpath and view not in ('history', 'log'))):
        raise RequestValidationError('changed-line content predicates require flat history or repository recent commits')


def _aggregate_controls(params, values):
    """An aggregate answer's row controls apply to its rows, and scan-limit is its commit input (a legacy type=
    request's limit arrives here as scan-limit, bound so by VIEW's declaration)."""
    from ...utils.query_control import declared_result_control
    if not aggregate_selection(values):
        return values, None
    control = declared_result_control(params)
    scan = SCAN_LIMIT.read(params)
    for key in ('limit', 'sort', 'offset'):
        values.pop(key, None)
    if scan is not None:
        values['limit'] = scan
    return values, control


# The one hint of an aggregate's commit-input cut (ownership and timeline), whatever spelled the budget (ruling Q1 A).
AGGREGATE_INPUT_HINT = 'raise scan-limit; aggregate counts cover only the retained commit input'


def apply_aggregate_rows(result: dict, control) -> dict:
    from ...utils.query import apply_result_control, unknown_sort_field_warning
    from ...utils.results import note_truncation, note_warning, truncations_of, relabel_truncations
    if control is None:
        return result
    for entry in truncations_of(result):
        if entry.get('field') == 'commits':
            entry['cause'] = 'scan-limit'
    relabel_truncations(result, 'commits', AGGREGATE_INPUT_HINT)
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
    if level == 'raw':
        query['raw'] = '1'
    elif level is not None:
        query['detail'] = 'summary' if level == 'normal' else level


def _runtime_ignore(params, query):
    """Blame's suppressed commits (a list of prefixes) and its auto-ignore switch, as the blame reader takes them."""
    commits = IGNORE_COMMITS.read(params)
    if commits:
        query['ignore-commits'] = list(commits)
    if AUTO_IGNORE.read(params) is False:
        query['auto-ignore'] = 'off'


def _runtime_merges(params, query):
    merges = MERGES.read(params)
    if merges is not None:
        key = 'merges' if query.get('type') == 'ownership' else 'no_merges'
        included = merges if key == 'merges' else not merges
        query[key] = '1' if included else '0'
