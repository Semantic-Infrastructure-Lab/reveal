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


@register_adapter('stats')
@register_renderer(StatsRenderer)
class StatsAdapter(ResourceAdapter):
    """Adapter for analyzing codebase statistics and identifying hotspots."""

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for stats:// adapter.

        Help data loaded from reveal/adapters/help_data/stats.yaml
        to reduce function complexity.
        """
        return load_help_data('stats') or {}

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for stats:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'stats',
            'description': 'Codebase metrics, quality analysis, and hotspot detection',
            'uri_syntax': 'stats://<path>?<filter1>&<filter2>&...',
            'query_params': {
                'hotspots': {
                    'type': 'boolean',
                    'description': 'Include hotspot analysis (files needing attention)',
                    'examples': ['hotspots=true']
                },
                'code_only': {
                    'type': 'boolean',
                    'description': 'Exclude data/config files from analysis',
                    'examples': ['code_only=true']
                },
                'min_lines': {
                    'type': 'integer',
                    'description': 'Filter files with at least this many lines',
                    'examples': ['min_lines=50']
                },
                'max_lines': {
                    'type': 'integer',
                    'description': 'Filter files with at most this many lines',
                    'examples': ['max_lines=500']
                },
                'min_complexity': {
                    'type': 'number',
                    'description': 'Filter files with avg complexity >= this',
                    'examples': ['min_complexity=5.0']
                },
                'max_complexity': {
                    'type': 'number',
                    'description': 'Filter files with avg complexity <= this',
                    'examples': ['max_complexity=15.0']
                },
                'min_functions': {
                    'type': 'integer',
                    'description': 'Filter files with at least this many functions',
                    'examples': ['min_functions=10']
                }
            },
            'operators': {},  # No operators, uses query params
            'elements': {},  # No element-based queries
            'cli_flags': ['--only-failures'],
            'supports_batch': False,
            'supports_advanced': True,
            'output_types': [
                {
                    'type': 'stats_summary',
                    'description': 'Directory-level codebase statistics',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'stats_summary'},
                            'path': {'type': 'string'},
                            'summary': {
                                'type': 'object',
                                'properties': {
                                    'total_files': {'type': 'integer'},
                                    'total_lines': {'type': 'integer'},
                                    'total_code_lines': {'type': 'integer'},
                                    'total_functions': {'type': 'integer'},
                                    'total_classes': {'type': 'integer'},
                                    'avg_complexity': {'type': 'number'},
                                    'avg_quality_score': {'type': 'number'}
                                }
                            },
                            'hotspots': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'file': {'type': 'string'},
                                        'quality_score': {'type': 'number'},
                                        'hotspot_score': {'type': 'number'},
                                        'issues': {'type': 'array', 'items': {'type': 'string'}}
                                    }
                                }
                            }
                        }
                    },
                    'example': {
                        'type': 'stats_summary',
                        'path': './src',
                        'summary': {
                            'total_files': 42,
                            'total_lines': 8543,
                            'total_code_lines': 6234,
                            'total_functions': 187,
                            'total_classes': 34,
                            'avg_complexity': 4.2,
                            'avg_quality_score': 78.5
                        },
                        'hotspots': [
                            {
                                'file': 'src/core.py',
                                'quality_score': 45.2,
                                'hotspot_score': 85.3,
                                'issues': ['High complexity', 'Long functions', 'Deep nesting']
                            }
                        ]
                    }
                },
                {
                    'type': 'stats_file',
                    'description': 'File-level statistics',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'stats_file'},
                            'file': {'type': 'string'},
                            'lines': {
                                'type': 'object',
                                'properties': {
                                    'total': {'type': 'integer'},
                                    'code': {'type': 'integer'},
                                    'comments': {'type': 'integer'},
                                    'empty': {'type': 'integer'}
                                }
                            },
                            'elements': {
                                'type': 'object',
                                'properties': {
                                    'functions': {'type': 'integer'},
                                    'classes': {'type': 'integer'},
                                    'imports': {'type': 'integer'}
                                }
                            },
                            'complexity': {
                                'type': 'object',
                                'properties': {
                                    'average': {'type': 'number'},
                                    'max': {'type': 'integer'}
                                }
                            },
                            'quality': {
                                'type': 'object',
                                'properties': {
                                    'score': {'type': 'number'},
                                    'long_functions': {'type': 'integer'},
                                    'deep_nesting': {'type': 'integer'}
                                }
                            }
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'stats://./src',
                    'description': 'Get codebase statistics for src directory',
                    'output_type': 'stats_summary'
                },
                {
                    'uri': 'stats://./src?hotspots=true',
                    'description': 'Include hotspot analysis (files needing attention)',
                    'output_type': 'stats_summary'
                },
                {
                    'uri': 'stats://./src?min_complexity=5.0',
                    'description': 'Show only files with avg complexity >= 5.0',
                    'output_type': 'stats_summary'
                },
                {
                    'uri': 'stats://./src?code_only=true',
                    'description': 'Exclude data/config files',
                    'output_type': 'stats_summary'
                },
                {
                    'uri': 'stats://src/core.py',
                    'description': 'File-level statistics',
                    'output_type': 'stats_file'
                },
                {
                    'uri': 'stats://./src --only-failures',
                    'description': 'Show only files with quality issues',
                    'cli_flag': '--only-failures',
                    'output_type': 'stats_summary'
                }
            ]
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
        file_stats = []
        for file_path in find_analyzable_files(self.path, code_only=code_only):
            stats = analyze_file(
                file_path,
                lambda fp, structure, content: calculate_file_stats(
                    fp, structure, content, self._quality_config,
                    lambda p: get_file_display_path(p, self.path)
                )
            )
            if stats and matches_filters(
                stats, min_lines, max_lines, min_complexity, max_complexity, min_functions,
                self.query_filters, field_value, compare
            ):
                file_stats.append(stats)
        return file_stats

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
            result['hotspots'] = identify_hotspots(controlled_stats)

        return result

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
