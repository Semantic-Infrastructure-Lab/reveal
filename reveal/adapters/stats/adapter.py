"""Statistics adapter (stats://) for codebase metrics and hotspots."""

from pathlib import Path
from typing import Dict, Any, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from ..help_data import load_help_data
from ...utils.query import (
    parse_query_params,
    parse_query_filters,
    parse_result_control,
)
from ...utils.validation import require_path_exists

# Import modular functions
from .renderer import StatsRenderer
from .analysis import find_analyzable_files, analyze_file, get_file_display_path
from .metrics import calculate_file_stats
from .queries import get_quality_config, field_value, compare, matches_filters
from .aggregation import aggregate_stats, identify_hotspots


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


_SCHEMA_QUERY_PARAMS = {
    'hotspots': {'type': 'boolean', 'description': 'Include hotspot analysis (files needing attention)', 'examples': ['hotspots=true']},
    'code_only': {'type': 'boolean', 'description': 'Exclude data/config files from analysis', 'examples': ['code_only=true']},
    'min_lines': {'type': 'integer', 'description': 'Filter files with at least this many lines', 'examples': ['min_lines=50']},
    'max_lines': {'type': 'integer', 'description': 'Filter files with at most this many lines', 'examples': ['max_lines=500']},
    'min_complexity': {'type': 'number', 'description': 'Filter files with avg complexity >= this', 'examples': ['min_complexity=5.0']},
    'max_complexity': {'type': 'number', 'description': 'Filter files with avg complexity <= this', 'examples': ['max_complexity=15.0']},
    'min_functions': {'type': 'integer', 'description': 'Filter files with at least this many functions', 'examples': ['min_functions=10']},
    'churn': {'type': 'boolean', 'description': 'Fold commit-touch counts into hotspot scoring (default: on for git repos, silently off otherwise). Set churn=false to opt out and fall back to complexity-only scoring.', 'examples': ['churn=false']},
    'since': {'type': 'string', 'description': 'Bound the churn walk to commits on/after this ISO date (default: full history). Only affects churn scoring, not the file list itself.', 'examples': ['since=2026-01-01']},
    'no_merges': {'type': 'boolean', 'description': 'Exclude merge commits from the churn tally', 'examples': ['no_merges=1']},
}

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
                'deep_nesting': {'type': 'integer'}, 'check_issues': {'type': 'integer'},
            }},
        }},
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'stats://./src', 'description': 'Get codebase statistics for src directory', 'output_type': 'stats_summary'},
    {'uri': 'stats://./src?hotspots=true', 'description': 'Include hotspot analysis (files needing attention)', 'output_type': 'stats_summary'},
    {'uri': 'stats://./src?min_complexity=5.0', 'description': 'Show only files with avg complexity >= 5.0', 'output_type': 'stats_summary'},
    {'uri': 'stats://./src?code_only=true', 'description': 'Exclude data/config files', 'output_type': 'stats_summary'},
    {'uri': 'stats://src/core.py', 'description': 'File-level statistics', 'output_type': 'stats_file'},
    {'uri': 'stats://./src?hotspots=true', 'description': 'Ranked list of files with quality issues', 'output_type': 'stats_summary'},
]

_SCHEMA_NOTES = [
    'quality_score is 0-100: 100 = no issues; weighted by severity (error/warning/info)',
    'Complexity is heuristic-based (average functions per 100 lines) — not cyclomatic complexity',
    'hotspots=true adds a ranked list of files most in need of refactoring',
    'Both files and directories are supported; directories show aggregate + per-file breakdown',
]


@register_adapter('stats')
@register_renderer(StatsRenderer)
class StatsAdapter(ResourceAdapter):
    """Adapter for analyzing codebase statistics and identifying hotspots."""

    BUDGET_LIST_FIELD = 'files'

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for stats:// adapter.

        Help data loaded from reveal/adapters/help_data/stats.yaml
        to reduce function complexity.
        """
        return load_help_data('stats') or {}

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for stats:// adapter."""
        return {
            'adapter': 'stats',
            'description': 'Codebase metrics, quality analysis, and hotspot detection',
            'uri_syntax': 'stats://<path>?<filter1>&<filter2>&...',
            'query_params': _SCHEMA_QUERY_PARAMS,
            'operators': {},
            'elements': {},
            'cli_flags': ['--hotspots', '--format=json'],
            'supports_batch': False,
            'supports_advanced': True,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    def __init__(self, path: str, query_string: Optional[str] = None):
        """Initialize stats adapter.

        Args:
            path: File or directory path to analyze
            query_string: Query parameters (e.g., "hotspots=true&min_lines=50" or "lines>50&complexity<10")
        """
        self.path = require_path_exists(Path(path).resolve())

        # Parse query string with type coercion (for legacy params)
        self.query_params = parse_query_params(query_string or '', coerce=True)

        # Parse result control (sort, limit, offset) - extract from query string
        filter_query, self.result_control = parse_result_control(query_string or '')

        # Parse query filters (new unified syntax: lines>50, complexity=5..15, etc.)
        # Only parse if the query contains new-style operators (>, <, !=, ~=, ..)
        # Legacy parameters (min_lines, max_lines, etc.) are handled via query_params
        self.query_filters = []
        if filter_query and any(op in filter_query for op in ['>', '<', '!=', '~=', '..']):
            try:
                self.query_filters = parse_query_filters(filter_query)
            except Exception:
                # If parsing fails, fall back to empty filters (legacy params will be used)
                self.query_filters = []

        # Load quality scoring config (with defaults)
        self._quality_config = get_quality_config(self.path)

    def _merge_query_params(self, hotspots, code_only, min_lines, max_lines,
                           min_complexity, max_complexity, min_functions) -> tuple:
        """Merge query params with flag params (query params take precedence)."""
        return (
            self.query_params.get('hotspots', hotspots),
            self.query_params.get('code_only', code_only),
            self.query_params.get('min_lines', min_lines),
            self.query_params.get('max_lines', max_lines),
            self.query_params.get('min_complexity', min_complexity),
            self.query_params.get('max_complexity', max_complexity),
            self.query_params.get('min_functions', min_functions)
        )

    def _collect_filtered_stats(self, code_only, min_lines, max_lines,
                                min_complexity, max_complexity, min_functions) -> list:
        """Collect file stats that match the specified filters."""
        from concurrent.futures import ProcessPoolExecutor

        files = list(find_analyzable_files(self.path, code_only=code_only))
        if not files:
            return []

        quality_config = self._quality_config
        base_path_str = str(self.path)
        args = [(str(f), quality_config, base_path_str) for f in files]

        # Use up to 8 workers; fall back to serial for tiny file sets to avoid
        # process-spawn overhead.
        workers = min(8, max(1, len(files) // 10))
        if workers > 1:
            with ProcessPoolExecutor(max_workers=workers) as executor:
                all_stats = list(executor.map(_analyze_file_worker, args))
        else:
            all_stats = [_analyze_file_worker(a) for a in args]

        return [
            s for s in all_stats
            if s and matches_filters(
                s, min_lines, max_lines, min_complexity, max_complexity, min_functions,
                self.query_filters, field_value, compare
            )
        ]

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

    def _add_truncation_metadata(self, result: dict, displayed: int, total: int) -> None:
        """Add truncation metadata to result if results were limited."""
        if displayed < total:
            if 'warnings' not in result:
                result['warnings'] = []
            result['warnings'].append({
                'type': 'truncated',
                'message': f'Results truncated: showing {displayed} of {total} total matches'
            })
            result['displayed_results'] = displayed
            result['total_matches'] = total

    def _compute_churn_counts(self, file_stats: list) -> Optional[Dict[str, int]]:
        """Compute per-file commit-touch counts for hotspot scoring (BACK-483).

        Fails open (returns None) whenever git isn't available or usable —
        churn is an optional scoring signal, not a hard requirement, so any
        error here degrades to today's complexity-only hotspot behavior
        rather than breaking `stats://`/`reveal hotspots`.
        """
        try:
            import pygit2
        except ImportError:
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

            from ..git import files as git_files  # deferred: avoid stats<->git import cycle at module load
            counts_by_repo_rel = git_files.get_churn_counts(
                repo, 'HEAD', set(display_to_repo_rel.values()),
                since=since, no_merges=no_merges,
            )

            return {
                display: counts_by_repo_rel.get(repo_rel, 0)
                for display, repo_rel in display_to_repo_rel.items()
                if repo_rel in counts_by_repo_rel
            }
        except Exception:
            return None

    def get_structure(self,
                     hotspots: bool = False,
                     code_only: bool = False,
                     min_lines: Optional[int] = None,
                     max_lines: Optional[int] = None,
                     min_complexity: Optional[float] = None,
                     max_complexity: Optional[float] = None,
                     min_functions: Optional[int] = None,
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

        Returns:
            Dict containing statistics and optionally hotspots
        """
        # Merge query params with flag params
        hotspots, code_only, min_lines, max_lines, min_complexity, max_complexity, min_functions = \
            self._merge_query_params(hotspots, code_only, min_lines, max_lines,
                                    min_complexity, max_complexity, min_functions)

        # Handle single file analysis
        if self.path.is_file():
            file_stats = analyze_file(
                self.path,
                lambda fp, structure, content: calculate_file_stats(
                    fp, structure, content, self._quality_config,
                    lambda p: get_file_display_path(p, self.path)
                )
            )
            return aggregate_stats([file_stats] if file_stats else [], self.path)

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

        # Add hotspots if requested
        if hotspots:
            churn_counts = None
            if self.query_params.get('churn', True) is not False:
                churn_counts = self._compute_churn_counts(controlled_stats)
            result['hotspots'] = identify_hotspots(controlled_stats, churn_counts=churn_counts)

        return {
            'contract_version': '1.0',
            'type': 'stats_structure',
            'source': str(self.path),
            'source_type': 'directory' if self.path.is_dir() else 'file',
            **result,
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get statistics for a specific file.

        Args:
            element_name: Relative path to file from base path

        Returns:
            Dict with file statistics or None if not found
        """
        target_path = self.path / element_name
        if not target_path.exists() or not target_path.is_file():
            return None

        return analyze_file(
            target_path,
            lambda fp, structure, content: calculate_file_stats(
                fp, structure, content, self._quality_config,
                lambda p: get_file_display_path(p, self.path)
            )
        )

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
