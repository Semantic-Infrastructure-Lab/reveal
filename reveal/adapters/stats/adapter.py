"""metrics:// -- per-file lines, complexity, quality and churn, file hotspots, and provenance.

stats became metrics (BACK-2069, surface program D2) and absorbed classify:// (``?view=provenance``)
and the file hotspot ranking (``?hotspots=true``, which the hotspots noun's file section reads).
``stats://`` stays registered as a retired spelling of the same adapter: it answers the same and
prints the replaced-by note from the RETIREMENTS table until the cut (D5).
"""

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional, cast
from reveal.reveal_types import CONTRACT_VERSION

from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from ...utils.query import (
    parse_query_filters,
    parse_result_control,
    unknown_sort_field_warning,
)
from ...utils.query_control import sort_failed_warning, sort_nulls_last
from ...utils.query_eval import find_unknown_filter_fields
from ...utils.query_parser import (
    CliBinding, ParamSpec, ParamValueError, QueryParams, ResourceSpec, filter_expression, mark_query_keys, param_schema,
    peek_query_items, split_exclude_param, where_param, whole_number,
)
from ...utils.query_binding import bind_declared_params, boolean_value
from ...utils.gitignore import respect_gitignore_param
from ...utils.path_utils import TestLayout, failure_of, provenance_for_display_path, to_relative_display
from ...utils.results import AnalysisCompleteness, ResultBuilder, note_truncation, note_warning, result_execution_facts
from ...utils.validation import require_path_exists
from ...utils.parallel import pool_worker_count, submit_each

# Import modular functions
from .renderer import StatsRenderer
from .analysis import find_analyzable_files, analyze_file, get_file_display_path, is_failure
from .issue_count import note_issue_count_basis, renamed_field
from .metrics import calculate_file_stats
from .queries import SORT_FIELDS, get_quality_config, field_value, compare, matches_filters
from .aggregation import aggregate_stats, has_findings, identify_hotspots
from .provenance import PROVENANCE_RESULT_TYPE, provenance_report
from ...reveal_types import PathFailure
from ...errors import RequestValidationError


def _pool_results(executor, args: list) -> list:
    """Run ``_analyze_file_worker`` over *args* in *executor*; one result per arg, in
    input order. A future that failed (a dead worker breaks the pool and fails every
    pending one, so the culprit cannot be told from the files lost with it) becomes the
    same failure record a raising analyzer yields, so it reaches ``_analysis_failures``
    and the run's warning instead of failing the whole scan (BACK-1718)."""
    futures = submit_each(executor, _analyze_file_worker, args)
    results = []
    for a, future in zip(args, futures):
        try:
            results.append(future.result())
        except Exception as e:  # boundary-ok: broad-except -- future.result() re-raises whatever the worker raised (arbitrary analyzer and rule code) or BrokenProcessPool; the failure record below goes to _analysis_failures and the run's analysis_failed warning
            results.append({'analysis_failed': f"{type(e).__name__}: {e}", 'path': a[0]})
    return results


def _analyze_file_worker(args: tuple):
    """Top-level worker for ProcessPoolExecutor — args must be picklable.

    Defined at module level (not as a closure) so pickling works.
    Tree-sitter nodes are safe here because each worker process has its own
    C runtime; there is no cross-thread node transfer.
    """
    file_path_str, quality_config, base_path_str = args
    from pathlib import Path as _Path
    from reveal.adapters.stats.analysis import analyze_file as _analyze_file
    from reveal.adapters.stats.analysis import get_file_display_path as _get_display
    from reveal.adapters.stats.metrics import calculate_file_stats as _calc_stats
    _fp = _Path(file_path_str)
    _bp = _Path(base_path_str)
    return _analyze_file(
        _fp,
        lambda fp, s, c: _calc_stats(fp, s, c, quality_config, lambda p: _get_display(p, _bp))
    )


# metrics' views: the default per-file metrics; the ranked hotspot files (their rows, capped by limit, with
# the findings verdict); and the full-population provenance report that classify:// answered (no file
# analysis, no rule pass).
VIEWS = ('provenance', 'hotspots')
DETAIL_LEVELS = ('normal', 'summary')
# The hotspot view's row cap when no limit is given (the legacy hotspots=true ranking's top default).
HOTSPOT_VIEW_LIMIT = 10
# Shared controls of the one vocabulary that metrics does not take (D18): rejected, never folded into where.
UNSUPPORTED_SHARED = ('match', 'kind', 'depth', 'until')
# Operators that make a bare URI key a filter expression (``lines>5``, ``lines=1..5``); a bare ``key=value``
# is a filter only beside one of them, as before where was declared (BACK-2278).
_FILTER_OPERATORS = ('>', '<', '!=', '~=', '!~', '..')


def _count(name: str):
    """A whole-number parameter: 5 and 5.0 are accepted, 5.5, text and booleans are not. A spec's own
    minimum rejects a negative row cap or offset as 'must be >= 0' (BACK-2621, the Imports wording)."""
    def convert(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError(f'{name} requires a whole number, not a boolean')
        return whole_number(float(value) if isinstance(value, str) else value)
    return convert


def _number(name: str):
    """A numeric threshold (an average complexity may be fractional); booleans and text are rejected."""
    def convert(value: Any) -> float:
        if isinstance(value, bool):
            raise ValueError(f'{name} requires a number, not a boolean')
        return float(value)
    return convert


def _text(name: str) -> Callable[[Any], str]:
    """A value-carrying parameter: bare presence (``?since``) is not a value."""
    def convert(value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
            raise ValueError(f'{name} requires a value')
        return str(value)
    return convert


def _iso_date(name: str) -> Callable[[Any], str]:
    """A churn-window start: an ISO date (or timestamp) in the form the churn walk parses (BACK-2621).
    A value it cannot parse was a churn_unavailable warning and exit 0; it is an invalid request."""
    def convert(value: Any) -> str:
        text = _text(name)(value)
        try:
            datetime.fromisoformat(text)
        except ValueError:
            raise ParamValueError(f'{name} must be an ISO date (YYYY-MM-DD), got {text!r}') from None
        return text
    return convert


def _switch(value: Any) -> bool:
    """An on/off switch (churn, merges): Git's merges codec, on|off or a boolean (BACK-2621)."""
    from ..git.params import merge_policy  # deferred: the git package imports its adapter
    return bool(merge_policy(value).include)


def _detail(value: Any) -> str:
    if value not in DETAIL_LEVELS:
        raise ParamValueError(f'detail must be normal or summary, got {value!r}: metrics has no fuller level '
                              '(summary omits the per-file rows)')
    return str(value)


def _unsupported(name: str) -> Callable[[Any], Any]:
    def convert(value: Any) -> Any:
        raise ParamValueError(
            f'metrics does not support {name}: filter the files with where (where=lines>50, --where '
            f"'avg_complexity>=5'); supported controls: {', '.join(spec.name for spec in DECLARED_SPECS)}")
    return convert


TEST_CHOICES = ('include', 'exclude')

# The declaration `reveal metrics` and metrics:// are both generated from (BACK-2146, BACK-2621). Operator
# filters (`lines>50`, `complexity=5..15`) are where's terms: the binder folds a bare URI key into it.
_VIEW = ParamSpec('view', 'string', 'hotspots: the ranked hotspot files are the rows (quality, complexity and churn '
                  'score, each with its provenance tag), capped by limit (default 10, 0 = all), with the --fail-on '
                  'findings verdict; provenance: the provenance tag (first_party/test/vendor/minified) of every '
                  'analyzable file, with summary.total, by_provenance, excluded and excluded_by_extension; no file is '
                  'analyzed and no rule runs (was classify://). Omitted: per-file metrics',
                  None, _text('view'), ('view=hotspots', 'view=provenance'), choices=VIEWS, role='analysis',
                  cli=CliBinding(('--view',), metavar='VIEW'))
_WHERE = where_param('Keep the files whose field matches: FIELD OP VALUE (lines>50, avg_complexity>=5, '
                     'complexity=5..15, functions!=0, a dotted path such as lines.total); repeat to AND. A bare URI '
                     'key with an operator (?lines>50) is the same filter', ('where=lines>50', 'where=avg_complexity>=5'))
_HOTSPOTS = ParamSpec('hotspots', 'boolean', 'Legacy: per-file rows plus the hotspot ranking, top capping it; '
                      'replaced by view=hotspots', False, boolean_value, ('hotspots=true',), role='analysis',
                      retired=True, cli=CliBinding(('--hotspots',), action='store_true'))
_TOP = ParamSpec('top', 'integer', 'Legacy hotspot cap: limit in view=hotspots; with legacy hotspots=true it caps the '
                 'ranking (default 10, 0 = all)', 10, _count('top'), ('top=25',), minimum=0, zero_policy='all',
                 role='analysis', retired=True, cli=CliBinding(('--top',), metavar='N'))
# The map's spelling (BACK-2621); code_only is an alias that answers the same, as scan_limit is for Imports.
_CODE_ONLY = ParamSpec('code-only', 'boolean', 'Exclude data/config files (xml, csv, sql, yaml, toml, large json) '
                       'from the walk; totals describe the code files', False, boolean_value, ('code-only=true',),
                       role='analysis', aliases=('code_only',),
                       cli=CliBinding(('--code-only',), dest='code_only', action='store_true'))
_MIN_LINES = ParamSpec('min_lines', 'integer', 'Legacy: where lines>=N', None,
                       _count('min_lines'), ('min_lines=50',), role='analysis', retired=True,
                       cli=CliBinding(('--min-lines',), metavar='N'))
_MAX_LINES = ParamSpec('max_lines', 'integer', 'Legacy: where lines<=N', None,
                       _count('max_lines'), ('max_lines=500',), role='analysis', retired=True,
                       cli=CliBinding(('--max-lines',), metavar='N'))
_MIN_COMPLEXITY = ParamSpec('min_complexity', 'number', 'Legacy: where avg_complexity>=N (the file average)', None,
                            _number('min_complexity'), ('min_complexity=5.0',), role='analysis', retired=True,
                            cli=CliBinding(('--min-complexity',), metavar='N'))
_MAX_COMPLEXITY = ParamSpec('max_complexity', 'number', 'Legacy: where avg_complexity<=N (the file average)', None,
                            _number('max_complexity'), ('max_complexity=15.0',), role='analysis', retired=True,
                            cli=CliBinding(('--max-complexity',), metavar='N'))
_MIN_FUNCTIONS = ParamSpec('min_functions', 'integer', 'Legacy: where functions>=N', None,
                           _count('min_functions'), ('min_functions=10',), role='analysis', retired=True,
                           cli=CliBinding(('--min-functions',), metavar='N'))
# Legacy threshold -> the where term it is: field and operator; the value keeps the legacy validation.
_LEGACY_THRESHOLDS = ((_MIN_LINES, 'lines>='), (_MAX_LINES, 'lines<='), (_MIN_FUNCTIONS, 'functions>='),
                      (_MIN_COMPLEXITY, 'avg_complexity>='), (_MAX_COMPLEXITY, 'avg_complexity<='))
_CHURN = ParamSpec('churn', 'boolean', 'Fold commit-touch counts into the hotspot score: on (default in a git '
                   'repository; silently off elsewhere) or off for complexity-only scoring',
                   True, _switch, ('churn=off',), role='analysis', cli=CliBinding(('--churn',), metavar='on|off'))
_NO_CHURN = ParamSpec('no_churn', 'boolean', 'Legacy --no-churn: churn off', None, boolean_value, role='analysis',
                      retired=True, cli=CliBinding(('--no-churn',), action='store_true'))
_SINCE = ParamSpec('since', 'string', 'Bound the churn walk to commits on/after this ISO date (default: full history). Only affects churn scoring, not the file list itself.',
                   None, _iso_date('since'), ('since=2026-01-01',), role='analysis',
                   cli=CliBinding(('--since',), metavar='DATE'))
_MERGES = ParamSpec('merges', 'boolean', 'Count merge commits in the churn tally: on (default) or off', None,
                    _switch, ('merges=off',), role='analysis', cli=CliBinding(('--merges',), metavar='on|off'))
_NO_MERGES = ParamSpec('no_merges', 'boolean', 'Legacy: merges=off', None,
                       boolean_value, ('no_merges=1',), role='analysis', retired=True,
                       cli=CliBinding(('--no-merges',), action='store_true'))
_TESTS = ParamSpec('tests', 'string',
                   'Test/support files in the hotspot ranking, selected by conventional names plus project test_layout.additional_paths: '
                   'include them (default) or exclude them from the ranking. Only the ranking changes; totals and files still count them',
                   'include', _text('tests'), ('tests=exclude',), choices=TEST_CHOICES, role='analysis',
                   cli=CliBinding(('--tests',), metavar='{include,exclude}'))
_DETAIL = ParamSpec('detail', 'string', 'normal: the per-file rows; summary: the aggregate summary only (the per-file '
                    'walk still runs; use it on unscoped whole-repo calls, where the rows can reach tens of MB)',
                    'normal', _detail, ('detail=summary',), choices=DETAIL_LEVELS, role='presentation',
                    cli=CliBinding(('--detail',), metavar='LEVEL'))
_SUMMARY_ONLY = ParamSpec('summary_only', 'boolean', 'Legacy: detail=summary', False, boolean_value,
                          ('summary_only=true',), role='analysis', retired=True,
                          cli=CliBinding(('--summary-only',), action='store_true'))
_SORT = ParamSpec('sort', 'string', 'Sort the files by a field, ascending; a leading - sorts descending', None,
                  _text('sort'), ('sort=-lines',), role='analysis', cli=CliBinding(('--sort',), metavar='FIELD'))
_LIMIT = ParamSpec('limit', 'integer', 'Keep at most this many rows: files, or the ranked files of view=hotspots '
                   '(default 10 there); 0 = no cap', None, _count('limit'), ('limit=10',), minimum=0,
                   zero_policy='no cap', role='analysis', cli=CliBinding(('--limit',), metavar='N'))
_OFFSET = ParamSpec('offset', 'integer', 'Skip this many rows before the first one kept', None,
                    _count('offset'), ('offset=5',), minimum=0, role='analysis',
                    cli=CliBinding(('--offset',), metavar='N'))
# The walk's scope, from the URI or the global --exclude/--no-gitignore (overview composes them); declared so
# where does not take them for filters. No subcommand flag: the global flags carry them.
_EXCLUDE = ParamSpec('exclude', 'string', 'Exclusion patterns, comma-separated (.gitignore syntax); --exclude fills it',
                     None, _text('exclude'), role='scope')
_RESPECT_GITIGNORE = ParamSpec('respect_gitignore', 'string', 'false includes files git ignores; --no-gitignore '
                               'fills it', None, lambda value: value, role='scope')

# Every control the schema documents; the unsupported shared controls are declared only to reject them.
DECLARED_SPECS = (_VIEW, _WHERE, _HOTSPOTS, _TOP, _CODE_ONLY, _MIN_LINES, _MAX_LINES, _MIN_COMPLEXITY, _MAX_COMPLEXITY,
                  _MIN_FUNCTIONS, _CHURN, _NO_CHURN, _SINCE, _MERGES, _NO_MERGES, _TESTS, _DETAIL, _SUMMARY_ONLY,
                  _SORT, _LIMIT, _OFFSET, _EXCLUDE, _RESPECT_GITIGNORE)
_UNSUPPORTED_SPECS = tuple(ParamSpec(name, 'string', argparse.SUPPRESS, None, _unsupported(name), role='unsupported',
                                     cli=CliBinding((f'--{name}',), metavar='VALUE'))
                           for name in UNSUPPORTED_SHARED)
PARAM_SPECS = DECLARED_SPECS + _UNSUPPORTED_SPECS

def _supplied(params: Any) -> Dict[str, Any]:
    return dict(peek_query_items(params))  # validating is not reading


def _hotspots_conflict(supplied: Dict[str, Any]) -> Optional[str]:
    view, hotspots = supplied.get('view'), supplied.get('hotspots')
    if view == 'provenance' and hotspots is True:
        return ('hotspots conflicts with view=provenance: one request has one view; '
                'the hotspot ranking is view=hotspots (--view hotspots)')
    if view == 'hotspots' and hotspots is False:
        return 'hotspots=false conflicts with view=hotspots: drop the legacy hotspots'
    return None


def _top_conflict(supplied: Dict[str, Any]) -> Optional[str]:
    if supplied.get('view') == 'hotspots' and 'top' in supplied and 'limit' in supplied \
            and supplied['top'] != supplied['limit']:
        return (f"top={supplied['top']} conflicts with limit={supplied['limit']}: in view=hotspots legacy top "
                'is limit; give limit=N (--limit N) once')
    return None


def _churn_conflict(supplied: Dict[str, Any]) -> Optional[str]:
    if supplied.get('no_churn') is True and supplied.get('churn') is True:
        return '--no-churn conflicts with churn=on: give churn once (--churn off)'
    return None


def _merges_conflict(supplied: Dict[str, Any]) -> Optional[str]:
    if 'no_merges' in supplied and 'merges' in supplied and supplied['merges'] == supplied['no_merges']:
        return (f"no_merges={str(supplied['no_merges']).lower()} conflicts with "
                f"merges={'on' if supplied['merges'] else 'off'}: give merges=on|off (--merges on|off) once")
    return None


def _detail_conflict(supplied: Dict[str, Any]) -> Optional[str]:
    if 'summary_only' in supplied and 'detail' in supplied and \
            (supplied['detail'] == 'summary') != supplied['summary_only']:
        return (f"summary_only={str(supplied['summary_only']).lower()} conflicts with detail={supplied['detail']}: "
                'give detail=normal|summary (--detail) once')
    return None


# The combinations binding cannot see (D18: conflicting old/new controls exit 2; an equal pair is accepted once).
_CONFLICTS = (_hotspots_conflict, _top_conflict, _churn_conflict, _merges_conflict, _detail_conflict)


def _validate_request(params: Any) -> None:
    supplied = _supplied(params)
    for conflict in _CONFLICTS:
        message = conflict(supplied)
        if message:
            raise RequestValidationError(message)


def _explicit_where(params: Any, terms: List[str]) -> List[str]:
    """The terms given as where (``where=``, ``--where`` or a keyword), as opposed to the bare URI keys
    the binder folded in: on a URI source they are the ``where=`` parts; on a typed one every term."""
    source = getattr(params, '_source_query', None)
    if source is None:
        return list(terms)
    from urllib.parse import unquote
    explicit = []
    for part in source.split('&'):
        key, separator, value = part.strip().partition('=')
        if key == _WHERE.name and separator:
            explicit.append(unquote(value))
    return explicit


def _filter_terms(params: Any, *, legacy_thresholds: bool = True) -> tuple:
    """The filter expressions of a bound request, and the bare keys that are no filter.

    where's explicit terms always filter; a bare URI key does when any bare key carries an operator
    (``lines=1`` beside ``functions>=0``), else it is an unrecognized param (BACK-2278). Each legacy
    threshold is its where term (min_lines=N is lines>=N; the complexity pair is the file average,
    avg_complexity, never the highest-function max_complexity field).
    """
    terms = list(_WHERE.read(params))
    explicit = _explicit_where(params, terms)
    bare = list(terms)
    for term in explicit:
        if term in bare:
            bare.remove(term)
    ignored = []
    if bare and not explicit and not any(op in term for term in bare for op in _FILTER_OPERATORS):
        ignored = [(key, value if separator else True)
                   for key, separator, value in (term.partition('=') for term in bare)]
        terms = explicit
    if not legacy_thresholds:  # view=provenance reads no file filter: they stay unread, and say so
        return terms, ignored
    legacy = [f'{field}{spec.read(params)}' for spec, field in _LEGACY_THRESHOLDS if spec.read(params) is not None]
    return terms + legacy, ignored


# The warning types _disclose_failures emits that say the answer lacks files it should have counted.
REQUIRED_WARNINGS = frozenset({'analysis_failed', 'analysis_incomplete', 'parse_degraded', 'check_rules_failed'})

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'stats_summary',
        'description': 'Directory-level codebase statistics',
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'stats_summary'},
            'path': {'type': 'string'},
            'summary': {'type': 'object', 'properties': {
                'total_files': {'type': 'integer'}, 'total_lines': {'type': 'integer'},
                'total_code_lines': {'type': 'integer'}, 'total_functions': {'type': 'integer'},
                'total_classes': {'type': 'integer'}, 'avg_complexity': {'type': 'number'},
                'avg_quality_score': {'type': 'number'},
                'has_findings': {'type': 'boolean', 'description': 'Present with hotspots=true: an analysed file has quality below 70 or a function with complexity above 20, over every analysed file before filters and cuts; --fail-on findings exits 1 on it'},
            }},
            'hotspots': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'file': {'type': 'string'}, 'quality_score': {'type': 'number'},
                'hotspot_score': {'type': 'number'}, 'issues': {'type': 'array', 'items': {'type': 'string'}},
                'provenance': {'type': ['string', 'null'], 'enum': ['test', 'vendor', 'minified', None],
                               'description': 'Path-only tag of the file under the scan root; null is first party (view=provenance spells it first_party)'},
            }}},
            'test_scope': {'type': 'object', 'description': 'Present when ?tests= was given with hotspots=true: the selected project policy, the mode and how many analyzed files the ranking left out',
                           'properties': {'rule': {'type': 'string', 'const': 'is_test_path'},
                                          'tests': {'type': 'string', 'enum': list(TEST_CHOICES)},
                                          'files_excluded': {'type': 'integer'}}},
        }},
        'example': {
            'type': 'stats_summary', 'path': './src',
            'summary': {'total_files': 42, 'total_lines': 8543, 'total_code_lines': 6234,
                        'total_functions': 187, 'total_classes': 34, 'avg_complexity': 4.2, 'avg_quality_score': 78.5},
            'hotspots': [{'file': 'src/core.py', 'quality_score': 45.2, 'hotspot_score': 85.3,
                          'issues': ['High complexity', 'Long functions', 'Deep nesting']}],
        },
    },
    {
        'type': 'stats_file',
        'description': 'File-level statistics',
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'stats_file'},
            'file': {'type': 'string'},
            'lines': {'type': 'object', 'properties': {
                'total': {'type': 'integer'}, 'code': {'type': 'integer'},
                'comments': {'type': 'integer'}, 'empty': {'type': 'integer'},
            }},
            'elements': {'type': 'object', 'properties': {
                'functions': {'type': 'integer'}, 'classes': {'type': 'integer'},
                'imports': {'type': 'integer'},
            }},
            'complexity': {'type': 'object', 'properties': {
                'average': {'type': 'number'}, 'max': {'type': 'integer'},
            }},
            'quality': {'type': 'object', 'properties': {
                'score': {'type': 'number'}, 'long_functions': {'type': 'integer'},
                'deep_nesting': {'type': 'integer'}, 'local_check_issues': {'type': 'integer'},
            }},
        }},
    },
    {
        'type': 'classify_report',
        'description': 'view=provenance: one row per analyzable file with its provenance tag, plus a summary by tag and the files no analyzer reads',
        'schema': {'type': 'object', 'properties': {
            'files': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'file': {'type': 'string'}, 'provenance': {'type': 'string'},
            }}},
            'summary': {'type': 'object', 'properties': {
                'total': {'type': 'integer'}, 'by_provenance': {'type': 'object'},
                'excluded': {'type': 'integer'}, 'excluded_by_extension': {'type': 'object'},
            }},
        }},
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'metrics://./src', 'description': 'Get codebase statistics for src directory', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?view=hotspots', 'description': 'The ranked hotspot files (files needing attention), 10 by default', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?where=avg_complexity>=5', 'description': 'Show only files with avg complexity >= 5', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?code-only=true', 'description': 'Exclude data/config files', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?detail=summary', 'description': 'Aggregate summary only, no per-file array — for large repos where the full file list is impractical to consume directly', 'output_type': 'stats_summary'},
    {'uri': 'metrics://src/core.py', 'description': 'File-level statistics', 'output_type': 'stats_file'},
    {'uri': 'metrics://./src?view=hotspots&limit=0', 'description': 'Every ranked hotspot file (limit=0 is uncapped)', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?view=provenance', 'description': 'Provenance tag of every analyzable file, with exclusions by extension (was classify://)', 'output_type': 'classify_report'},
]

_SCHEMA_NOTES = [
    'quality_score is 0-100: 100 = no issues; weighted by severity (error/warning/info)',
    'Complexity is cyclomatic, from the tree-sitter AST: 1 plus one per decision node (if/elif, loops, except/catch arms, case arms, and/or, ternaries); languages without a tree-sitter complexity fall back to a text heuristic',
    'view=hotspots answers the ranked list of files most in need of refactoring as its rows (limit caps them, default 10; offset pages them); each entry carries provenance, the path-only test/vendor/minified tag of its file under the scan root (null = first party). Legacy hotspots=true adds the same ranking beside the per-file rows, top capping it',
    'view=hotspots adds summary.has_findings: an analysed file with quality below 70 or a function with complexity above 20 (fixed thresholds), over every analysed file before where, tests= and the limit/offset cuts; --fail-on findings exits 1 on it (default none). The other views have no findings and exit 2 under --fail-on findings',
    'tests=exclude leaves conventional and project-declared test/support files out of the hotspot ranking only; test_scope records the selected policy and files_excluded. The default includes them. Ordinary overview does not request this ranking',
    'where filters the files (FIELD OP VALUE, repeatable, ANDed); avg_complexity is the file average (complexity is its alias) and max_complexity the most complex function. Legacy min_lines/max_lines/min_functions and min_complexity/max_complexity are those where terms (the complexity pair on avg_complexity)',
    'quality.local_check_issues counts the findings of file-local check rules only, so a file has one count whatever else is in the tree; meta.issue_count names the rule and the rule set. Cross-file rules (import cycles, duplicate literals, ...) run under reveal check.',
    'Both files and directories are supported; directories show aggregate + per-file breakdown',
    'view=provenance answers what classify:// did: every analyzable file tagged first_party/test/vendor/minified, without analysis or rules; stats:// and classify:// are retired spellings that answer the same',
    'On large repos, an unscoped call returns one entry per file (can reach tens of MB) — use detail=summary when only the aggregate summary is needed',
]


def _requests(value: Any) -> bool:
    """Whether a boolean query value turns its view on: bare presence or true. A malformed value is
    left to the parameter's own validation."""
    if value is None:
        return False
    if value == '':
        return True
    try:
        return boolean_value(value)
    except ValueError:
        return True


@register_adapter('metrics')
@register_renderer(StatsRenderer)
class MetricsAdapter(ResourceAdapter):
    """Codebase metrics, file hotspots and provenance (was stats:// and classify://)."""
    HELP_CLUSTER = 'Code Analysis'
    QUICK_RANK: Optional[int] = 2

    BUDGET_LIST_FIELD = 'files'
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESULT_TYPE = 'stats_summary'
    # --fail-on findings gates the hotspots=true view only (imports' findings views are the precedent): its
    # summary.has_findings is the serious-hotspot predicate over the analysed population (BACK-2149).
    FINDINGS_POLICIES = ('none', 'findings')
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = PARAM_SPECS
    # api.query binds typed keywords through PARAM_SPECS like the URI query (BACK-2621): a declared keyword
    # answers as its URI spelling does and beats the URI value; an undeclared one raises TypeError.
    BOUND_QUERY_CALL = True
    CLI_QUERY_FLAGS = {
        'respect_gitignore': 'respect_gitignore=false',  # --no-gitignore (BACK-1202)
        'hotspots': 'hotspots=true',  # global --hotspots on the URI form (BACK-2621)
        'code_only': 'code-only=true',  # global --code-only on the URI form (BACK-2621)
        'all': 'top=1000000',  # lifts the hotspots=true top=10 default (BACK-1379)
        # BACK-1379: get_structure already reads since from query_params and threads
        # it into get_churn_counts() to bound hotspots=true's churn scoring, but
        # nothing declared the flag, so --since was silently dropped on the CLI path
        # (confirmed live: 2 -> 1 hotspots with a manually-appended &since=, no
        # effect via --since alone). No 'until' entry -- get_churn_counts() has no
        # until parameter to bind to (BACK-1379 follow-up filed separately).
        'since': 'since={value}',
    }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for metrics:// adapter.

        Help data loaded from reveal/adapters/help_data/metrics.yaml
        to reduce function complexity.
        """
        return load_help_data('metrics') or {}

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for metrics:// adapter."""
        return {
            'adapter': 'metrics',
            'description': 'Codebase metrics, quality analysis, file hotspots and provenance',
            'uri_syntax': 'metrics://<path>?<filter1>&<filter2>&...',
            'resource': MetricsAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': MetricsAdapter.DEFAULT_FAIL_ON,
                                 'fail_on': list(MetricsAdapter.FINDINGS_POLICIES)},
            'query_params': param_schema(DECLARED_SPECS),
            'operators': {},
            'elements': {},
            'cli_flags': ['--view', '--where', '--format=json'],
            'supports_batch': False,
            'supports_advanced': True,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    @staticmethod
    def validate_request(params, args):
        """--fail-on findings gates the hotspot ranking only (view=hotspots, or legacy hotspots=true): any
        other view has no findings verdict, so the gate could never fire and a CI run that forgot the
        ranking passed (BACK-2528)."""
        if vars(args).get('fail_on') != 'findings':
            return
        keys = dict(peek_query_items(params))  # validating is not reading
        if keys.get('view') == 'hotspots' or (keys.get('view') != 'provenance' and _requests(keys.get('hotspots'))):
            return
        raise RequestValidationError(
            '--fail-on findings has no verdict to gate in this view: metrics gates the hotspot ranking '
            '(exit 1 when an analysed file has quality below 70 or a function complexity above 20), '
            'not the default or provenance view; add --view hotspots, or drop --fail-on')

    @staticmethod
    def result_type_for(params) -> str:
        """The answer type the selected view produces, from key presence before conversion."""
        return PROVENANCE_RESULT_TYPE if dict(peek_query_items(params)).get('view') == 'provenance' else 'stats_summary'

    @staticmethod
    def result_type_at(params, path: str) -> str:
        """A file answers ``stats_file`` and a directory ``stats_summary``; the provenance view is
        a ``classify_report`` for either."""
        expected = MetricsAdapter.result_type_for(params)
        return 'stats_file' if expected == 'stats_summary' and Path(path).is_file() else expected

    @staticmethod
    def execution_facts(result):
        """Files the scan was meant to count and did not make the answer incomplete; a result with
        nothing countable at all, or an error, is failed. Informational notes (excluded extensions,
        a deprecated config key, an unavailable churn signal) are not failures."""
        meta = result.get('meta') or {}
        if result.get('error') or meta.get('errors'):
            return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
        lost = any(warning.get('type') in REQUIRED_WARNINGS for warning in meta.get('warnings', []))
        summary = result.get('summary')
        return result_execution_facts(
            result, completeness=AnalysisCompleteness.INCOMPLETE if lost else AnalysisCompleteness.COMPLETE,
            findings=isinstance(summary, dict) and summary.get('has_findings') is True)

    def __init__(self, resource: str, query: Optional[str] = None, *, params: Optional[Dict[str, Any]] = None):
        """Initialize the metrics adapter.

        Args:
            resource: File or directory path to analyze
            query: Query parameters (e.g., "hotspots=true&min_lines=50" or "lines>50&complexity<10")
            params: Parameters already bound against PARAM_SPECS (the declared command and URI route);
                    given, ``query`` is not read.
        """
        # (Every transport binds the same declarations; conflicting old/new spellings reject here.)
        self.path = Path(os.path.abspath(require_path_exists(Path(resource))))  # the message names the path as spelled
        self._churn_disclosure: Optional[str] = None  # BACK-1166: set by _compute_churn_counts
        self._traversal_failures: List[PathFailure] = []

        # Every transport binds through PARAM_SPECS (BACK-2621): the raw-query constructor that library
        # callers use validates and normalizes as the URI does; keys no parameter claims stay operator filters.
        if params is None:
            params = bind_declared_params(PARAM_SPECS, query or '', transport='uri')
        elif not isinstance(params, QueryParams):
            params = bind_declared_params(PARAM_SPECS, params, transport='typed')
        elif not params._normalized and dict(peek_query_items(params)):
            # A parsed but unbound query (a library caller's parse_query_params): bind its text so bare
            # operator keys become where's terms as on the URI.
            params = bind_declared_params(PARAM_SPECS, '&'.join(filter_expression(key, value) for key, value
                                                                 in peek_query_items(params)), transport='uri')
        _validate_request(params)
        self.query_params = params
        filter_query, self.result_control = parse_result_control(self._control_query())
        self.view = _VIEW.read(self.query_params)  # the binder already checked it against VIEWS

        # where's terms, the legacy thresholds translated into it. No fallback to "no filters": that
        # would answer an unfiltered query as if it were the filtered one (BACK-1059); a ValueError
        # here fails the query.
        terms, ignored = _filter_terms(params, legacy_thresholds=self.view != 'provenance')
        self.query_filters = parse_query_filters('&'.join(terms)) if terms else []

        # Load quality scoring config (with defaults)
        self._quality_config = get_quality_config(self.path)

        # BACK-507: a bare key that is no filter (no operator in any bare key: ?complexity=true, ?lines=1)
        # is an unrecognized param, warned and ignored; beside an operator it is a filter (BACK-2278).
        if ignored:
            self._warn_unknown_query_params(dict(ignored))
            mark_query_keys(params, *(key for key, _value in ignored))  # named once, not again as unused
        self._analysis_failures: list = []
        self._population_findings = False
        self._analyzed_count = 0
        self._excluded_by_extension: Dict[str, int] = {}
        self._unknown_filter_fields: List[str] = []
        self._sort_failure: Optional[Dict[str, Any]] = None

    def _control_query(self) -> str:
        """The bound sort/limit/offset as the query text ``parse_result_control`` reads, so a bound
        parameter and a legacy query string give one ResultControl (the per-file rows' controls)."""
        bound = dict(peek_query_items(self.query_params))
        return '&'.join(f'{name}={bound[name]}' for name in ('sort', 'limit', 'offset') if name in bound)

    def _analysis_controls(self) -> tuple:
        """The bound controls of the per-file views, read where they apply (not on view=provenance):
        whether the ranking runs, the code-only walk, and whether the per-file rows are omitted."""
        params = self.query_params
        hotspots = _HOTSPOTS.read(params) or self.view == 'hotspots'  # legacy beside the view: read, accepted once
        legacy_summary = _SUMMARY_ONLY.read(params)  # read beside detail: an equal pair is accepted once
        summary = _DETAIL.read(params) == 'summary' or legacy_summary
        return hotspots, _CODE_ONLY.read(params), summary

    def _collect_filtered_stats(self, code_only) -> list:
        """Collect file stats that match the specified filters."""
        from concurrent.futures import ProcessPoolExecutor
        from ...logging_setup import worker_bootstrap

        # BACK-1042: ?exclude=pat1,pat2 / ?respect_gitignore=false, composed
        # in by overview's --exclude/--no-gitignore flags (also usable
        # directly on stats:// itself).
        exclude_param = self.query_params.get('exclude')
        exclude_patterns = split_exclude_param(exclude_param) or None
        respect_gitignore = respect_gitignore_param(self.query_params)

        self._analysis_failures = []
        self._excluded_by_extension = {}
        files = list(find_analyzable_files(
            self.path, code_only=code_only,
            respect_gitignore=respect_gitignore, exclude_patterns=exclude_patterns,
            excluded_by_extension=self._excluded_by_extension,
            on_error=self._record_traversal_failure,
        ))
        if not files:
            return []

        quality_config = self._quality_config
        base_path_str = str(self.path)
        args = [(str(f), quality_config, base_path_str) for f in files]

        # Use up to 8 workers; fall back to serial for tiny file sets to avoid
        # process-spawn overhead. BACK-1004: REVEAL_MAX_WORKERS overrides this
        # (matches adapters/imports.py's _parallel_worker_count) — this was the
        # only uncapped worker pool reachable from `overview`, causing
        # concurrent full-repo scans on one machine to blow past timeouts even
        # though each is fast in isolation.
        workers = pool_worker_count(min(8, max(1, len(files) // 10)))
        if workers > 1:
            # No rule index is preloaded: the issue count runs the file-local rules only
            # (issue_count.py), and the project-wide indexes (I002, D005, T006, M102, I007)
            # belong to rules it leaves out (BACK-1884; they were built here by BACK-531).
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=worker_bootstrap,
            ) as executor:
                all_stats = _pool_results(executor, args)
        else:
            all_stats = [_analyze_file_worker(a) for a in args]

        self._record_analysis_results(all_stats)
        return self._filter_analyzed([s for s in all_stats if s and not is_failure(s)])

    def _filter_analyzed(self, analyzed: list) -> list:
        """The analyzed files the filters keep, for a directory and a single file alike (a
        single file was returned whatever the filters said, BACK-2308)."""
        matched = [
            s for s in analyzed
            if matches_filters(s, self.query_filters, field_value, compare)
        ]
        self._unknown_filter_fields = []
        if analyzed and not matched:
            # A filter field no analyzed file has is why nothing matched: a typo, not a
            # genuine zero (BACK-2299, json:// BACK-1165).
            self._unknown_filter_fields = find_unknown_filter_fields(analyzed, self.query_filters, field_value)
        return matched

    def _record_analysis_results(self, all_stats: list) -> None:
        """Capture raw rule facts before filters, paging, and presentation cuts.

        The findings verdict is taken here too, over every analysed file: no file filter
        (min_complexity is an average), ?tests= ranking scope, page or top cut moves it (BACK-2149).
        """
        self._analysis_failures = [s for s in all_stats
                                   if is_failure(s) or s and (s.get('parse_degraded')
                                                              or s.get('check_rules_failed'))]
        analysed = [s for s in all_stats if s and not is_failure(s)]
        self._analyzed_count = len(analysed)
        self._population_findings = has_findings((s['quality']['score'] for s in analysed),
                                                 (s['complexity']['max'] for s in analysed))

    def _disclose_issue_count(self, result: dict) -> None:
        """Say what the issue count counts, and flag a renamed spelling the query used.

        The scan-cap and discovery-loss notes of the cross-file rules are not part of the
        count's evidence any more (BACK-1884): those rules do not run here.
        """
        note_issue_count_basis(result)
        for message in self._quality_config.get('deprecations', []):
            note_warning(result, {'type': 'deprecated_config_key', 'message': message})
        # The per-file rows' sort only where those rows are drawn: view=hotspots leaves it unread, and says so.
        sort = [] if self.view == 'hotspots' else [self.result_control.sort_field]
        used = [name for name in [qf.field for qf in self.query_filters] + sort if renamed_field(name)]
        for name in dict.fromkeys(used):
            note_warning(result, {
                'type': 'deprecated_field',
                'message': f"{name} was renamed {renamed_field(name)}; the old name still answers",
            })

    def _unknown_filter_field_warning(self) -> Optional[Dict[str, Any]]:
        """The ``unknown_filter_field`` warning for filter fields no analyzed file has, or None."""
        if not self._unknown_filter_fields:
            return None
        fields = ', '.join(f"'{f}'" for f in self._unknown_filter_fields)
        return {
            'type': 'unknown_filter_field',
            'message': (f"Filter field(s) {fields} never appear on any scanned file — this may be a "
                        f"typo rather than a genuine zero-match. Fields: {', '.join(SORT_FIELDS)}, "
                        f"or a dotted path such as lines.total"),
        }

    def _apply_sorting(self, file_stats: list) -> list:
        """Apply sorting to file stats if sort field is specified."""
        self._sort_failure = None
        if not self.result_control.sort_field:
            return list(file_stats)

        # Type narrowing: sort_field is guaranteed non-None after the check above
        sort_field = self.result_control.sort_field
        assert sort_field is not None

        try:
            # A missing value goes last in either direction, as on json:// (BACK-2298); it
            # sorted as 0.
            return sort_nulls_last(file_stats, lambda x: field_value(x, sort_field),
                                   self.result_control.sort_descending)
        except TypeError as error:
            # Values that do not compare (``sort=elements`` reads a dict per file): walk order,
            # and the result says it is not sorted (BACK-2308; it said nothing). field_value
            # reads with ``in`` and raises no KeyError.
            self._sort_failure = sort_failed_warning(sort_field, error)
            return list(file_stats)

    def _apply_pagination(self, file_stats: list) -> list:
        """Apply offset and limit pagination to file stats."""
        result = file_stats
        if self.result_control.offset and self.result_control.offset > 0:
            result = result[self.result_control.offset:]
        if self.result_control.limit and self.result_control.limit > 0:
            result = result[:self.result_control.limit]
        return result

    def _top_hotspots(self, result: dict, ranked: list) -> list:
        """Cut the ranked hotspots and record the cut (BACK-1179, BACK-1543).

        view=hotspots: the ranking is the rows, paged by offset and capped by limit (legacy top is
        limit there; default 10, 0 = no cap). Legacy hotspots=true: ``?top=N`` caps it beside the
        per-file rows; ``?top=0`` means no cap, as for hotspots:// (BACK-1505): ``[:0]`` was an empty
        list, which reads as a clean codebase.
        """
        if self.view == 'hotspots':
            limit = _LIMIT.read(self.query_params)
            if 'top' in _supplied(self.query_params):  # legacy top is limit here (equal to it when both given)
                top = _TOP.read(self.query_params)
                limit = top if limit is None else limit
            limit = HOTSPOT_VIEW_LIMIT if limit is None else limit
            offset = _OFFSET.read(self.query_params) or 0
            page = ranked[offset:]
            shown = page[:limit] if limit > 0 else page
            note_truncation(result, 'hotspots', len(shown), len(ranked), 'limit', hint='raise ?limit=N')
            return shown
        top = self.int_param('top', 10)
        shown = ranked[:top] if top > 0 else ranked
        note_truncation(result, 'hotspots', len(shown), len(ranked), 'limit', hint='raise ?top=N')
        return shown

    def _record_traversal_failure(self, error: OSError) -> None:
        """Directory loss has an unknown missing file population."""
        self._traversal_failures.append(failure_of(error))

    def _parse_degraded_warning(self) -> Optional[Dict[str, Any]]:
        """The files the parser read only with error recovery, named with the line where known: stderr
        alone carried which files and why before (COMMAND_MODEL 'Transports', BACK-2650)."""
        degraded = sorted((s for s in self._analysis_failures if s.get('parse_degraded')), key=lambda s: s['file'])
        if not degraded:
            return None
        shown = [to_relative_display(s['file'], self.path) for s in degraded[:5]]
        places = [f"{name} (line {s['parse_error_line']})" if s.get('parse_error_line') else name
                  for name, s in zip(shown, degraded)]
        more = f" and {len(degraded) - len(shown)} more" if len(degraded) > len(shown) else ''
        return {'type': 'parse_degraded', 'count': len(degraded), 'files': shown,
                'message': (f"{len(degraded)} file(s) did not parse cleanly; statistics may be incomplete: "
                            f"{', '.join(places)}{more}")}

    def _disclose_failures(self, result: dict) -> None:
        """Disclose directory and file analysis loss without treating totals as complete."""
        from ..ast.analysis import traversal_failed_warning
        note_warning(result, cast(Optional[Dict[str, Any]],
                                  traversal_failed_warning(self._traversal_failures, self.path)))
        self._disclose_issue_count(result)
        note_warning(result, self._parse_degraded_warning())
        rules_failed = sorted(s['file'] for s in self._analysis_failures if s.get('check_rules_failed'))
        if rules_failed:
            shown = rules_failed[:5]
            more = f" and {len(rules_failed) - len(shown)} more" if len(rules_failed) > len(shown) else ''
            note_warning(result, {
                'type': 'check_rules_failed', 'count': len(rules_failed), 'files': shown,
                'message': (f"{len(rules_failed)} file(s) had check rules that could not run; their "
                            f"check-issue counts are lower bounds and quality scores may be optimistic: "
                            f"{', '.join(shown)}{more}"),
            })
        failed = sorted(f['path'] for f in self._analysis_failures if is_failure(f))
        if not failed:
            return
        shown = [to_relative_display(f, self.path) for f in failed[:5]]
        more = f" and {len(failed) - len(shown)} more" if len(failed) > len(shown) else ''
        meta = result.setdefault('meta', {})
        meta.setdefault('warnings', []).append({
            'type': 'analysis_failed',
            'count': len(failed),
            'files': shown,
            'message': (f"{len(failed)} file(s) failed analysis and are not counted: "
                        f"{', '.join(shown)}{more}"),
        })

    def _disclose_exclusions(self, result: dict) -> None:
        """Keep the unsupported population in numeric summaries and composed warnings."""
        excluded = dict(sorted(self._excluded_by_extension.items()))
        count = sum(excluded.values())
        result['summary'].update(excluded=count, excluded_by_extension=excluded)
        if count:
            note_warning(result, {
                'type': 'unsupported_extensions', 'count': count,
                'excluded_by_extension': excluded,
                'message': (f"{count} file(s) excluded because no analyzer is registered: "
                            + ', '.join(f'{ext} ({n})' for ext, n in excluded.items())
                            + '; totals describe only the analyzed population'),
            })

    def _add_truncation_metadata(self, result: dict, displayed: int, total: int, *, rows_omitted: bool = False) -> None:
        """Record a ?limit/?offset cut of the files list (note_truncation, BACK-1059)."""
        if not rows_omitted and displayed < total:
            note_truncation(result, 'files', displayed, total, 'limit')
            result['displayed_results'] = displayed
            result['total_matches'] = total

    def _compute_churn_counts(self, file_stats: list) -> Optional[Dict[str, int]]:
        """Compute per-file commit-touch counts for hotspot scoring (BACK-483).

        Fails open (returns None) whenever git isn't available or usable —
        churn is an optional scoring signal, not a hard requirement, so any
        error here degrades to today's complexity-only hotspot behavior
        rather than breaking `stats://`/`reveal hotspots`.

        BACK-1166: "not a git repo" is a legitimate, silent None (nothing to
        disclose). An actual failure (pygit2 missing, walk error) instead
        records a reason in self._churn_disclosure for get_structure() to
        surface — previously indistinguishable from "no churn requested".
        """
        self._churn_disclosure: Optional[str] = None
        try:
            import pygit2
        except ImportError:
            self._churn_disclosure = (
                "churn scoring unavailable: pygit2 not installed "
                "(hotspot ranking used complexity/size only)"
            )
            return None

        try:
            repo_path = pygit2.discover_repository(str(self.path))
            if not repo_path:
                return None
            repo = pygit2.Repository(repo_path)
            workdir = Path(repo.workdir) if repo.workdir else None
            if workdir is None:
                return None

            since = self.query_params.get('since')
            # merges=off, or legacy no_merges: the churn cache key keeps its no_merges meaning.
            no_merges = _NO_MERGES.read(self.query_params) is True or _MERGES.read(self.query_params) is False

            # Map each file's display path (relative to self.path, what
            # identify_hotspots/hotspot output key on) to its repo-relative
            # path (what pygit2 diff deltas report), and scope the walk to
            # exactly those paths.
            display_to_repo_rel: Dict[str, str] = {}
            for stats in file_stats:
                display = stats['file']
                abs_path = (self.path / display) if self.path.is_dir() else self.path
                try:
                    repo_rel = abs_path.resolve().relative_to(workdir.resolve()).as_posix()
                except ValueError:
                    continue
                display_to_repo_rel[display] = repo_rel

            if not display_to_repo_rel:
                return None

            from ..git import churn as git_churn  # deferred: avoid stats<->git import cycle at module load
            counts_by_repo_rel = git_churn.get_churn_counts(
                repo, 'HEAD', set(display_to_repo_rel.values()),
                since=since, no_merges=no_merges,
            )

            return {
                display: counts_by_repo_rel.get(repo_rel, 0)
                for display, repo_rel in display_to_repo_rel.items()
                if repo_rel in counts_by_repo_rel
            }
        except Exception as e:  # boundary-ok: broad-except -- churn is an optional scoring signal built from pygit2 repository discovery plus a history walk (GitError, KeyError, OSError, and whatever a damaged repository adds); the reason is stored in _churn_disclosure and surfaces as a meta warning
            self._churn_disclosure = (
                f"churn scoring failed: {e} "
                "(hotspot ranking used complexity/size only)"
            )
            return None

    def _add_hotspots(self, result: dict, file_stats: list, layout: Optional[TestLayout]) -> None:
        """Rank the same analyzed population for file and directory requests."""
        file_stats = self._rank_population(result, file_stats, layout)
        churn_counts = None
        if _CHURN.read(self.query_params) and not _NO_CHURN.read(self.query_params):
            churn_counts = self._compute_churn_counts(file_stats)
            if self._churn_disclosure:
                # In the envelope, so the text answer prints it too (it sat in a top-level list, BACK-2621).
                note_warning(result, {'type': 'churn_unavailable', 'message': self._churn_disclosure})
        result['hotspots'] = self._top_hotspots(
            result, identify_hotspots(file_stats, churn_counts=churn_counts))
        # The path-only tag the hotspots noun put on its file entries (test/vendor/minified, None for first
        # party), from the display path under the scan root, never the target's spelling (BACK-2149, BACK-2487).
        base = self.path if self.path.is_dir() else self.path.parent
        for entry in result['hotspots']:
            entry['provenance'] = provenance_for_display_path(entry['file'], base)
        result['summary']['has_findings'] = self._population_findings

    def _rank_population(self, result: dict, file_stats: list, layout: Optional[TestLayout]) -> list:
        """Narrow only the ranking, using the policy selected before analysis.

        Files, totals and diagnostics retain their analyzed population. Counts here
        describe the filtered ranking population before its top cut, not discovery.
        """
        if layout is None:
            return file_stats
        mode = _TESTS.read(self.query_params)
        base = self.path if self.path.is_dir() else self.path.parent
        kept = file_stats if mode == 'include' else [
            f for f in file_stats if not layout.is_test(base / f['file'])]
        result['test_scope'] = {**layout.as_dict(base), 'tests': mode,
                                'files_excluded': len(file_stats) - len(kept)}
        return kept

    def _ranking_layout(self) -> Optional[TestLayout]:
        """The test layout the ranking narrows by, when tests= was given (validated before analysis)."""
        if self.query_params.get('tests') is None:
            return None
        _TESTS.read(self.query_params)  # reject direct/raw invalid modes before policy or analysis
        from ...config import RevealConfig
        layout = TestLayout.for_path(self.path, fallback_root=self.path)
        return RevealConfig.get(layout.anchor).apply_test_layout(layout)

    def _file_structure(self, hotspots: bool, rows_omitted: bool, layout: Optional[TestLayout]) -> Dict[str, Any]:
        """The answer for a single-file target: its stats, filtered like a directory's rows."""
        file_stats = analyze_file(
            self.path,
            lambda fp, structure, content: calculate_file_stats(
                fp, structure, content, self._quality_config,
                lambda p: get_file_display_path(p, self.path)
            )
        )
        if is_failure(file_stats):
            return dict(ResultBuilder.create_error(
                result_type='stats_file', source=self.path,
                error=f"analysis failed: {file_stats['analysis_failed']}"))  # type: ignore[index]
        kept = self._filter_analyzed([file_stats] if file_stats else [])
        result = aggregate_stats(kept, self.path)
        self._record_analysis_results([file_stats])
        note_warning(result, unknown_sort_field_warning(
            self.result_control.sort_field, kept, field_value, SORT_FIELDS))
        note_warning(result, self._unknown_filter_field_warning())
        self._disclose_failures(result)
        result.update(
            contract_version=CONTRACT_VERSION,
            type='stats_file',
            source=str(self.path),
            source_type='file',
        )
        if hotspots:
            self._add_hotspots(result, kept, layout)
        if rows_omitted:
            result.pop('files', None)
        return result

    def get_structure(self) -> Dict[str, Any]:
        """Get statistics for file or directory: the view the constructor-bound parameters select.

        Every control is a declared parameter bound at construction (BACK-2621); get_structure
        takes no keywords. summary_only omits the per-file 'files' array from the result -- just
        the aggregate summary (+ hotspots, if also requested). BACK-1008: an unscoped whole-repo
        call returns one entry per file, which dwarfs the summary block that's usually the actual
        signal wanted (15.6MB/747K lines on an 18K-file repo). The full per-file walk still runs
        (needed for the aggregate and for hotspots) -- summary_only only trims the output.

        Returns:
            Dict containing statistics and optionally hotspots
        """
        if self.view == 'provenance':
            # classify's full population: the walk and the path/banner/locale heuristics only.
            return provenance_report(self.path, respect_gitignore=respect_gitignore_param(self.query_params))
        self._traversal_failures = []
        self._record_analysis_results([])
        hotspots, code_only, summary_only = self._analysis_controls()
        # view=hotspots: the ranked files are the rows; no per-file rows, so sort/limit/offset page the ranking.
        rows_omitted = summary_only or self.view == 'hotspots'

        layout = self._ranking_layout() if hotspots else None
        if self.path.is_file():
            return self._file_structure(hotspots, rows_omitted, layout)

        # Collect filtered directory statistics
        dir_file_stats = self._collect_filtered_stats(code_only)
        total_filtered = len(dir_file_stats)

        # Apply sorting and pagination to the per-file rows (view=hotspots pages its ranking instead)
        controlled_stats: list = []
        if self.view != 'hotspots':
            controlled_stats = self._apply_pagination(self._apply_sorting(dir_file_stats))

        # Aggregate and build result
        result = aggregate_stats(dir_file_stats, self.path)
        result['files'] = controlled_stats
        result['population'] = {
            'summary': 'filtered_analyzed_files', 'analyzed_files': self._analyzed_count,
            'filtered_files': total_filtered,
            'displayed_files': 0 if rows_omitted else len(controlled_stats),
        }
        self._add_truncation_metadata(result, len(controlled_stats), total_filtered, rows_omitted=rows_omitted)
        if self.view != 'hotspots':
            note_warning(result, unknown_sort_field_warning(
                self.result_control.sort_field, dir_file_stats, field_value, SORT_FIELDS))
            note_warning(result, self._sort_failure)
        note_warning(result, self._unknown_filter_field_warning())
        self._disclose_failures(result)
        self._disclose_exclusions(result)

        if hotspots:
            # The filtered population, not the limit/offset page: paging the files list must not
            # change which files are the hotspots (BACK-2146).
            self._add_hotspots(result, dir_file_stats, layout)

        if rows_omitted:
            result.pop('files', None)

        result.update(
            contract_version=CONTRACT_VERSION,
            type='stats_summary',
            source=str(self.path),
            source_type='directory' if self.path.is_dir() else 'file',
        )
        return result

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific file.

        Args:
            element_name: Relative path to file from base path

        Returns:
            Dict with file statistics or None if not found
        """
        self._traversal_failures = []
        self._record_analysis_results([])
        target_path = self.path / element_name
        if not target_path.exists() or not target_path.is_file():
            return None

        file_stats = analyze_file(
            target_path,
            lambda fp, structure, content: calculate_file_stats(
                fp, structure, content, self._quality_config,
                lambda p: get_file_display_path(p, self.path)
            )
        )
        if is_failure(file_stats):
            return {'error': f"{element_name}: analysis failed: {file_stats['analysis_failed']}"}  # type: ignore[index]
        self._record_analysis_results([file_stats])
        if file_stats:
            self._disclose_failures(file_stats)
        return file_stats

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about analyzed path.

        Returns:
            Dict with path metadata
        """
        return {
            'type': 'statistics',
            'path': str(self.path),
            'is_directory': self.path.is_dir(),
            'exists': self.path.exists(),
        }


@register_adapter('stats')
@register_renderer(StatsRenderer)
class StatsAdapter(MetricsAdapter):
    """stats://, the retired spelling of metrics:// (BACK-2069): the same adapter and answer.

    The note naming metrics:// comes from the ``scheme:stats`` row of the RETIREMENTS table
    (cli/invocation.py), printed where the URI is parsed; nothing here prints it.
    """
    QUICK_RANK = None
    # The opt-in is class-local (factory.uses_bound_query_call): the retired spelling binds typed
    # keywords as metrics:// does, since get_structure takes none (BACK-2621).
    BOUND_QUERY_CALL = True

    @staticmethod
    def get_help() -> Dict[str, Any]:
        help_data = dict(MetricsAdapter.get_help())
        help_data.update(
            name='stats',
            description=help_data.get('description', ''),
            syntax='stats://<path>[?<filters>]',
        )
        return help_data

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        schema = dict(MetricsAdapter.get_schema())
        # The schema of the stats:// spelling, so its examples spell it too (as trace:// keeps its own).
        examples = [{**ex, 'uri': 'stats://' + ex['uri'][len('metrics://'):]} for ex in schema['example_queries']]
        schema.update(adapter='stats', uri_syntax='stats://<path>?<filter1>&<filter2>&...', example_queries=examples,
                      notes=['Retired spelling of metrics:// (the same answer); stats:// prints a '
                             'replaced-by note until the cut release.', *schema['notes']])
        return schema
