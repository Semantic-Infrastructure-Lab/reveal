"""metrics:// -- per-file lines, complexity, quality and churn, file hotspots, and provenance.

stats became metrics (BACK-2069, surface program D2) and absorbed classify:// (``?view=provenance``)
and the file hotspot ranking (``?hotspots=true``, which the hotspots noun's file section reads).
``stats://`` stays registered as a retired spelling of the same adapter: it answers the same and
prints the replaced-by note from the RETIREMENTS table until the cut (D5).
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, cast
from reveal.reveal_types import CONTRACT_VERSION

from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from ...utils.query import (
    parse_query_params,
    parse_query_filters,
    parse_result_control,
    unknown_sort_field_warning,
)
from ...utils.query_parser import (
    CliBinding, ParamSpec, QueryParams, ResourceSpec, nonnegative_display_limit, param_schema,
    peek_query_items, split_exclude_param, whole_number,
)
from ...utils.query_binding import bind_declared_params, boolean_value
from ...utils.gitignore import respect_gitignore_param
from ...utils.path_utils import failure_of, in_test_scope, to_relative_display
from ...utils.results import AnalysisCompleteness, ResultBuilder, note_truncation, note_warning, result_execution_facts
from ...utils.validation import require_path_exists
from ...utils.parallel import pool_worker_count, submit_each

# Import modular functions
from .renderer import StatsRenderer
from .analysis import find_analyzable_files, analyze_file, get_file_display_path, is_failure
from .issue_count import note_issue_count_basis, renamed_field
from .metrics import calculate_file_stats
from .queries import SORT_FIELDS, get_quality_config, field_value, compare, matches_filters
from .aggregation import aggregate_stats, identify_hotspots
from .provenance import PROVENANCE_RESULT_TYPE, provenance_report
from ...reveal_types import PathFailure


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


# metrics' views: the default per-file metrics, and the full-population provenance report
# that classify:// answered (no file analysis, no rule pass).
VIEWS = ('provenance',)

def _count(name: str):
    """A whole-number parameter: 5 and 5.0 are accepted, 5.5, text and booleans are not."""
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


def _text(name: str):
    """A value-carrying parameter: bare presence (``?since``) is not a value."""
    def convert(value: Any) -> str:
        if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
            raise ValueError(f'{name} requires a value')
        return str(value)
    return convert


def _display_count(name: str):
    def convert(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError(f'{name} must be a non-negative integer, not a boolean')
        return nonnegative_display_limit(value, name)
    return convert


TEST_CHOICES = ('include', 'exclude')

# The declaration `reveal metrics` and metrics:// are both generated from (BACK-2146). Operator filters
# (`lines>50`, `complexity=5..15`) are not parameters: they stay a URI-only expression language and
# are read from the query keys no parameter claims (MetricsAdapter._expression_filters).
_VIEW = ParamSpec('view', 'string', 'provenance: the provenance tag (first_party/test/vendor/minified) of every analyzable file, with summary.total, by_provenance, excluded and excluded_by_extension; no file is analyzed and no rule runs (was classify://)',
                  None, _text('view'), ('view=provenance',), choices=VIEWS, role='analysis',
                  cli=CliBinding(('--view',), metavar='VIEW'))
_HOTSPOTS = ParamSpec('hotspots', 'boolean', 'Include hotspot analysis (files needing attention)', False,
                      boolean_value, ('hotspots=true',), role='analysis',
                      cli=CliBinding(('--hotspots',), action='store_true'))
_TOP = ParamSpec('top', 'integer', 'Max number of hotspot files to return when hotspots=true (default: 10, 0 = all)',
                 10, _display_count('top'), ('top=25',), minimum=0, zero_policy='all', role='analysis',
                 cli=CliBinding(('--top',), metavar='N'))
_CODE_ONLY = ParamSpec('code_only', 'boolean', 'Exclude data/config files from analysis', False,
                       boolean_value, ('code_only=true',), role='analysis',
                       cli=CliBinding(('--code-only',), action='store_true'))
_MIN_LINES = ParamSpec('min_lines', 'integer', 'Filter files with at least this many lines', None,
                       _count('min_lines'), ('min_lines=50',), role='analysis',
                       cli=CliBinding(('--min-lines',), metavar='N'))
_MAX_LINES = ParamSpec('max_lines', 'integer', 'Filter files with at most this many lines', None,
                       _count('max_lines'), ('max_lines=500',), role='analysis',
                       cli=CliBinding(('--max-lines',), metavar='N'))
_MIN_COMPLEXITY = ParamSpec('min_complexity', 'number', 'Filter files with avg complexity >= this', None,
                            _number('min_complexity'), ('min_complexity=5.0',), role='analysis',
                            cli=CliBinding(('--min-complexity',), metavar='N'))
_MAX_COMPLEXITY = ParamSpec('max_complexity', 'number', 'Filter files with avg complexity <= this', None,
                            _number('max_complexity'), ('max_complexity=15.0',), role='analysis',
                            cli=CliBinding(('--max-complexity',), metavar='N'))
_MIN_FUNCTIONS = ParamSpec('min_functions', 'integer', 'Filter files with at least this many functions', None,
                           _count('min_functions'), ('min_functions=10',), role='analysis',
                           cli=CliBinding(('--min-functions',), metavar='N'))
_CHURN = ParamSpec('churn', 'boolean', 'Fold commit-touch counts into hotspot scoring (default: on for git repos, silently off otherwise). Set churn=false to opt out and fall back to complexity-only scoring.',
                   True, boolean_value, ('churn=false',), role='analysis',
                   cli=CliBinding(('--no-churn',), action='store_false'))
_SINCE = ParamSpec('since', 'string', 'Bound the churn walk to commits on/after this ISO date (default: full history). Only affects churn scoring, not the file list itself.',
                   None, _text('since'), ('since=2026-01-01',), role='analysis',
                   cli=CliBinding(('--since',), metavar='DATE'))
_NO_MERGES = ParamSpec('no_merges', 'boolean', 'Exclude merge commits from the churn tally', False,
                       boolean_value, ('no_merges=1',), role='analysis',
                       cli=CliBinding(('--no-merges',), action='store_true'))
_TESTS = ParamSpec('tests', 'string',
                   'Test files in the hotspot ranking (path_utils.is_test_path: a tests/ or test/ directory, test_*.py, *_test.go, *Tests.java, '
                   '*.spec.ts, ..., judged from the scanned path\'s own name down): include them (default here) or exclude them from '
                   'hotspots=true. Totals, the files list and every other view still count them; overview passes exclude unless asked',
                   'include', _text('tests'), ('tests=exclude',), choices=TEST_CHOICES, role='analysis',
                   cli=CliBinding(('--tests',), metavar='{include,exclude}'))
_SUMMARY_ONLY = ParamSpec('summary_only', 'boolean', 'Omit the per-file "files" array from the result — just the aggregate summary (+ hotspots, if also requested). Use on unscoped whole-repo calls, where the per-file array can reach tens of MB and dwarfs the summary block that is usually the actual signal wanted.',
                          False, boolean_value, ('summary_only=true',), role='analysis',
                          cli=CliBinding(('--summary-only',), action='store_true'))
_SORT = ParamSpec('sort', 'string', 'Sort the files by a field, ascending; a leading - sorts descending', None,
                  _text('sort'), ('sort=-lines',), role='analysis', cli=CliBinding(('--sort',), metavar='FIELD'))
_LIMIT = ParamSpec('limit', 'integer', 'Keep at most this many files (0 = no cap)', None,
                   _display_count('limit'), ('limit=10',), minimum=0, zero_policy='no cap', role='analysis',
                   cli=CliBinding(('--limit',), metavar='N'))
_OFFSET = ParamSpec('offset', 'integer', 'Skip this many files before the first one kept', None,
                    _display_count('offset'), ('offset=5',), minimum=0, role='analysis',
                    cli=CliBinding(('--offset',), metavar='N'))

PARAM_SPECS = (_VIEW, _HOTSPOTS, _TOP, _CODE_ONLY, _MIN_LINES, _MAX_LINES, _MIN_COMPLEXITY, _MAX_COMPLEXITY,
               _MIN_FUNCTIONS, _CHURN, _SINCE, _NO_MERGES, _TESTS, _SUMMARY_ONLY, _SORT, _LIMIT, _OFFSET)

# Query keys a parameter does not claim but the adapter reads: the walk's scope (overview composes them).
_SCOPE_KEYS = frozenset({'exclude', 'respect_gitignore'})

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
            }},
            'hotspots': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'file': {'type': 'string'}, 'quality_score': {'type': 'number'},
                'hotspot_score': {'type': 'number'}, 'issues': {'type': 'array', 'items': {'type': 'string'}},
            }}},
            'test_scope': {'type': 'object', 'description': 'Present when ?tests= was given with hotspots=true: the rule, the mode and how many files the ranking left out',
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
    {'uri': 'metrics://./src?hotspots=true', 'description': 'Include hotspot analysis (files needing attention)', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?min_complexity=5.0', 'description': 'Show only files with avg complexity >= 5.0', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?code_only=true', 'description': 'Exclude data/config files', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?summary_only=true', 'description': 'Aggregate summary only, no per-file array — for large repos where the full file list is impractical to consume directly', 'output_type': 'stats_summary'},
    {'uri': 'metrics://src/core.py', 'description': 'File-level statistics', 'output_type': 'stats_file'},
    {'uri': 'metrics://./src?hotspots=true', 'description': 'Ranked list of files with quality issues', 'output_type': 'stats_summary'},
    {'uri': 'metrics://./src?view=provenance', 'description': 'Provenance tag of every analyzable file, with exclusions by extension (was classify://)', 'output_type': 'classify_report'},
]

_SCHEMA_NOTES = [
    'quality_score is 0-100: 100 = no issues; weighted by severity (error/warning/info)',
    'Complexity is cyclomatic, from the tree-sitter AST: 1 plus one per decision node (if/elif, loops, except/catch arms, case arms, and/or, ternaries); languages without a tree-sitter complexity fall back to a text heuristic',
    'hotspots=true adds a ranked list of files most in need of refactoring',
    'tests=exclude leaves test files (is_test_path) out of the hotspots=true ranking only and reports test_scope.files_excluded; the default (include) ranks them, as overview://\'s own default (exclude) does not',
    'quality.local_check_issues counts the findings of file-local check rules only, so a file has one count whatever else is in the tree; meta.issue_count names the rule and the rule set. Cross-file rules (import cycles, duplicate literals, ...) run under reveal check.',
    'Both files and directories are supported; directories show aggregate + per-file breakdown',
    'view=provenance answers what classify:// did: every analyzable file tagged first_party/test/vendor/minified, without analysis or rules; stats:// and classify:// are retired spellings that answer the same',
    'On large repos, an unscoped call returns one entry per file (can reach tens of MB) — use summary_only=true when only the aggregate summary/hotspots are needed',
]


@register_adapter('metrics')
@register_renderer(StatsRenderer)
class MetricsAdapter(ResourceAdapter):
    """Codebase metrics, file hotspots and provenance (was stats:// and classify://)."""
    HELP_CLUSTER = 'Code Analysis'
    QUICK_RANK: Optional[int] = 2

    BUDGET_LIST_FIELD = 'files'
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESULT_TYPE = 'stats_summary'
    FINDINGS_POLICIES = ('none',)  # metrics reports a count; it has no findings gate
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = PARAM_SPECS
    CLI_QUERY_FLAGS = {
        'respect_gitignore': 'respect_gitignore=false',  # --no-gitignore (BACK-1202)
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
            'query_params': param_schema(PARAM_SPECS),
            'operators': {},
            'elements': {},
            'cli_flags': ['--hotspots', '--format=json'],
            'supports_batch': False,
            'supports_advanced': True,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

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
        return result_execution_facts(
            result, completeness=AnalysisCompleteness.INCOMPLETE if lost else AnalysisCompleteness.COMPLETE)

    def __init__(self, resource: str, query: Optional[str] = None, *, params: Optional[Dict[str, Any]] = None):
        """Initialize the metrics adapter.

        Args:
            resource: File or directory path to analyze
            query: Query parameters (e.g., "hotspots=true&min_lines=50" or "lines>50&complexity<10")
            params: Parameters already bound against PARAM_SPECS (the declared command and URI route);
                    given, ``query`` is not read.
        """
        self.path = require_path_exists(Path(resource)).resolve()  # the message names the path as spelled
        self._churn_disclosure: Optional[str] = None  # BACK-1166: set by _compute_churn_counts
        self._traversal_failures: List[PathFailure] = []

        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                PARAM_SPECS, params, transport='typed')
            filter_query, self.result_control = parse_result_control(self._control_query())
            filter_query = self._expression_filters()
        else:
            # Parse query string with type coercion (for legacy params)
            self.query_params = parse_query_params(query or '', coerce=True)
            # Parse result control (sort, limit, offset) - extract from query string
            filter_query, self.result_control = parse_result_control(query or '')

        # Parse query filters (new unified syntax: lines>50, complexity=5..15, etc.)
        # Only parse if the query contains new-style operators (>, <, !=, ~=, ..)
        # Legacy parameters (min_lines, max_lines, etc.) are handled via query_params
        self.query_filters = []
        if filter_query and any(op in filter_query for op in ['>', '<', '!=', '~=', '..']):
            # No fallback to "no filters": that would answer an unfiltered query as if it
            # were the filtered one (BACK-1059). A ValueError here fails the query.
            self.query_filters = parse_query_filters(filter_query)

        # Load quality scoring config (with defaults)
        self._quality_config = get_quality_config(self.path)

        # BACK-507: warn on unrecognized params (e.g. ?complexity=true, which
        # isn't a stats param — the real ones are min_complexity/max_complexity).
        # Mixed adapter: skip filter expressions (complexity>10) and the
        # cross-cutting result-control params this adapter honors.
        self._warn_unknown_query_params(
            self.query_params,
            skip_filter_keys=True,
            extra_known_keys={'sort', 'limit', 'offset', 'exclude', 'respect_gitignore'},
        )
        self.view = self.query_params.get('view')
        if self.view is not None and self.view not in VIEWS:
            raise ValueError(f"view={self.view!r} is not a metrics view; the one view is "
                             f"{', '.join(VIEWS)} (omit view for per-file metrics)")
        self._analysis_failures: list = []
        self._excluded_by_extension: Dict[str, int] = {}

    def _control_query(self) -> str:
        """The bound sort/limit/offset as the query text ``parse_result_control`` reads, so a bound
        parameter and a legacy query string give one ResultControl."""
        bound = dict(peek_query_items(self.query_params))
        return '&'.join(f'{name}={bound[name]}' for name in ('sort', 'limit', 'offset') if name in bound)

    def _expression_filters(self) -> str:
        """The operator-filter expressions of a bound request: the query keys no parameter claims.

        ``lines>50`` parses as a bare key and ``complexity>=5`` as key ``complexity>`` with value
        ``5``; joining them back gives the text the filter parser reads. The scope keys (exclude,
        respect_gitignore) are not expressions.
        """
        claimed = {spec.name for spec in PARAM_SPECS} | _SCOPE_KEYS
        return '&'.join(key if value is True else f'{key}={value}'
                        for key, value in peek_query_items(self.query_params) if key not in claimed)

    def _merge_query_params(self, hotspots, code_only, min_lines, max_lines,
                           min_complexity, max_complexity, min_functions,
                           summary_only) -> tuple:
        """Merge query params with flag params (query params take precedence)."""
        return (
            self.query_params.get('hotspots', hotspots),
            self.query_params.get('code_only', code_only),
            self.query_params.get('min_lines', min_lines),
            self.query_params.get('max_lines', max_lines),
            self.query_params.get('min_complexity', min_complexity),
            self.query_params.get('max_complexity', max_complexity),
            self.query_params.get('min_functions', min_functions),
            self.query_params.get('summary_only', summary_only)
        )

    def _collect_filtered_stats(self, code_only, min_lines, max_lines,
                                min_complexity, max_complexity, min_functions) -> list:
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
        return [
            s for s in all_stats
            if s and not is_failure(s) and matches_filters(
                s, min_lines, max_lines, min_complexity, max_complexity, min_functions,
                self.query_filters, field_value, compare
            )
        ]

    def _record_analysis_results(self, all_stats: list) -> None:
        """Capture raw rule facts before filters, paging, and presentation cuts."""
        self._analysis_failures = [s for s in all_stats
                                   if is_failure(s) or s and (s.get('parse_degraded')
                                                              or s.get('check_rules_failed'))]

    def _disclose_issue_count(self, result: dict) -> None:
        """Say what the issue count counts, and flag a renamed spelling the query used.

        The scan-cap and discovery-loss notes of the cross-file rules are not part of the
        count's evidence any more (BACK-1884): those rules do not run here.
        """
        note_issue_count_basis(result)
        for message in self._quality_config.get('deprecations', []):
            note_warning(result, {'type': 'deprecated_config_key', 'message': message})
        used = [name for name in [qf.field for qf in self.query_filters] + [self.result_control.sort_field]
                if renamed_field(name)]
        for name in dict.fromkeys(used):
            note_warning(result, {
                'type': 'deprecated_field',
                'message': f"{name} was renamed {renamed_field(name)}; the old name still answers",
            })

    def _apply_sorting(self, file_stats: list) -> list:
        """Apply sorting to file stats if sort field is specified."""
        if not self.result_control.sort_field:
            return list(file_stats)

        # Type narrowing: sort_field is guaranteed non-None after the check above
        sort_field = self.result_control.sort_field
        assert sort_field is not None

        try:
            sorted_stats = list(file_stats)
            sorted_stats.sort(
                key=lambda x: field_value(x, sort_field) or 0,
                reverse=self.result_control.sort_descending
            )
            return sorted_stats
        except (TypeError, KeyError):
            return list(file_stats)  # Skip sorting if field doesn't exist

    def _apply_pagination(self, file_stats: list) -> list:
        """Apply offset and limit pagination to file stats."""
        result = file_stats
        if self.result_control.offset and self.result_control.offset > 0:
            result = result[self.result_control.offset:]
        if self.result_control.limit and self.result_control.limit > 0:
            result = result[:self.result_control.limit]
        return result

    def _top_hotspots(self, result: dict, ranked: list) -> list:
        """Cut the ranked hotspots to ``?top=N`` and record the cut (BACK-1179, BACK-1543).

        ``?top=0`` means no cap, as it does for hotspots:// (BACK-1505): ``[:0]`` was an
        empty list, which reads as a clean codebase.
        """
        top = self.int_param('top', 10)
        shown = ranked[:top] if top > 0 else ranked
        note_truncation(result, 'hotspots', len(shown), len(ranked), 'limit', hint='raise ?top=N')
        return shown

    def _record_traversal_failure(self, error: OSError) -> None:
        """Directory loss has an unknown missing file population."""
        self._traversal_failures.append(failure_of(error))

    def _disclose_failures(self, result: dict) -> None:
        """Disclose directory and file analysis loss without treating totals as complete."""
        from ..ast.analysis import traversal_failed_warning
        note_warning(result, cast(Optional[Dict[str, Any]],
                                  traversal_failed_warning(self._traversal_failures, self.path)))
        self._disclose_issue_count(result)
        degraded = [s for s in self._analysis_failures if s.get('parse_degraded')]
        if degraded:
            note_warning(result, {
                'type': 'parse_degraded', 'count': len(degraded),
                'message': f"{len(degraded)} file(s) did not parse cleanly; statistics may be incomplete",
            })
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

    def _add_truncation_metadata(self, result: dict, displayed: int, total: int) -> None:
        """Record a ?limit/?offset cut of the files list (note_truncation, BACK-1059)."""
        if displayed < total:
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
            no_merges = self.query_params.get('no_merges') is True

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

    def _add_hotspots(self, result: dict, file_stats: list) -> None:
        """Rank the same analyzed population for file and directory requests."""
        file_stats = self._rank_population(result, file_stats)
        churn_counts = None
        if self.query_params.get('churn', True) is not False:
            churn_counts = self._compute_churn_counts(file_stats)
            if self._churn_disclosure:
                result.setdefault('warnings', []).append({
                    'type': 'churn_unavailable',
                    'message': self._churn_disclosure,
                })
        result['hotspots'] = self._top_hotspots(
            result, identify_hotspots(file_stats, churn_counts=churn_counts))

    def _rank_population(self, result: dict, file_stats: list) -> list:
        """The files the hotspot ranking sees: all of them, or without the test files (``?tests=exclude``).

        The rule is ``is_test_path`` judged from the scanned path's own name down (``in_test_scope``, the one
        patches:// and testability:// use). Only the ranking is narrowed: the totals and the files list keep
        counting tests. A request that names ``tests`` records what it did as ``test_scope``.
        """
        if self.query_params.get('tests') is None:
            return file_stats
        mode = _TESTS.read(self.query_params)
        kept = file_stats if mode == 'include' else [
            f for f in file_stats if not in_test_scope(self.path / f['file'], self.path)]
        result['test_scope'] = {'rule': 'is_test_path', 'tests': mode, 'files_excluded': len(file_stats) - len(kept)}
        return kept

    def get_structure(self,
                     hotspots: bool = False,
                     code_only: bool = False,
                     min_lines: Optional[int] = None,
                     max_lines: Optional[int] = None,
                     min_complexity: Optional[float] = None,
                     max_complexity: Optional[float] = None,
                     min_functions: Optional[int] = None,
                     summary_only: bool = False,
                     **kwargs) -> Dict[str, Any]:
        """Get statistics for file or directory.

        Args:
            hotspots: If True, include hotspot analysis (flag - legacy)
            code_only: If True, exclude data/config files from analysis
            min_lines: Filter files with at least this many lines
            max_lines: Filter files with at most this many lines
            min_complexity: Filter files with avg complexity >= this
            max_complexity: Filter files with avg complexity <= this
            min_functions: Filter files with at least this many functions
            summary_only: If True, omit the per-file 'files' array from the
                result — just the aggregate summary (+ hotspots, if also
                requested). BACK-1008: an unscoped whole-repo stats:// call
                returns one entry per file, which dwarfs the summary block
                that's usually the actual signal wanted (15.6MB/747K lines on
                an 18K-file repo) and is impractical to consume directly in
                an LLM context. The full per-file walk still runs (needed for
                the aggregate and for hotspots) — this only trims the output.

        Returns:
            Dict containing statistics and optionally hotspots
        """
        if self.view == 'provenance':
            # classify's full population: the walk and the path/banner/locale heuristics only.
            return provenance_report(self.path, respect_gitignore=respect_gitignore_param(self.query_params))
        self._traversal_failures = []
        self._record_analysis_results([])
        # Merge query params with flag params
        hotspots, code_only, min_lines, max_lines, min_complexity, max_complexity, min_functions, summary_only = \
            self._merge_query_params(hotspots, code_only, min_lines, max_lines,
                                    min_complexity, max_complexity, min_functions,
                                    summary_only)

        # Handle single file analysis
        if self.path.is_file():
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
            result = aggregate_stats([file_stats] if file_stats else [], self.path)
            self._record_analysis_results([file_stats])
            self._disclose_failures(result)
            result.update(
                contract_version=CONTRACT_VERSION,
                type='stats_file',
                source=str(self.path),
                source_type='file',
            )
            if hotspots:
                self._add_hotspots(result, [file_stats] if file_stats else [])
            if summary_only:
                result.pop('files', None)
            return result

        # Collect filtered directory statistics
        dir_file_stats = self._collect_filtered_stats(
            code_only, min_lines, max_lines, min_complexity, max_complexity, min_functions
        )
        total_filtered = len(dir_file_stats)

        # Apply sorting and pagination
        controlled_stats = self._apply_sorting(dir_file_stats)
        controlled_stats = self._apply_pagination(controlled_stats)

        # Aggregate and build result
        result = aggregate_stats(controlled_stats, self.path)
        self._add_truncation_metadata(result, len(controlled_stats), total_filtered)
        note_warning(result, unknown_sort_field_warning(
            self.result_control.sort_field, dir_file_stats, field_value, SORT_FIELDS))
        self._disclose_failures(result)
        self._disclose_exclusions(result)

        if hotspots:
            # The filtered population, not the limit/offset page: paging the files list must not
            # change which files are the hotspots (BACK-2146).
            self._add_hotspots(result, dir_file_stats)

        if summary_only:
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
