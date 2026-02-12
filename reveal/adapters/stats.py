"""Statistics adapter (stats://) for codebase metrics and hotspots."""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List, cast

from .base import ResourceAdapter, register_adapter, register_renderer
from .help_data import load_help_data
from ..registry import get_analyzer
from ..utils.query import (
    parse_query_params,
    parse_query_filters,
    parse_result_control,
    compare_values,
)

# Quality scoring defaults - configurable via .reveal/stats-quality.yaml
QUALITY_DEFAULTS = {
    'thresholds': {
        'complexity_target': 10,       # Functions above this get penalized
        'function_length_target': 50,  # Lines; functions above this penalized
        'deep_nesting_depth': 4,       # Nesting beyond this penalized
    },
    'penalties': {
        'complexity': {
            'multiplier': 3,           # Points lost per unit above target
            'max': 30,                 # Maximum penalty
        },
        'length': {
            'divisor': 2,              # Points lost = (excess / divisor)
            'max': 20,
        },
        'ratios': {
            'multiplier': 50,          # For long_func_ratio, deep_nesting_ratio
            'max': 25,
        },
    }
}


class StatsRenderer:
    """Renderer for statistics adapter results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render codebase statistics.

        Args:
            result: Structure dict from StatsAdapter.get_structure()
            format: Output format ('text', 'json')
        """
        if format == 'json':
            from ..main import safe_json_dumps
            print(safe_json_dumps(result))
            return

        # Text format - single file stats
        if 'file' in result and 'summary' not in result:
            file_name = result.get('file', 'file')
            lines = result.get('lines', {})
            elements = result.get('elements', {})
            complexity = result.get('complexity', {})
            quality = result.get('quality', {})

            print(f"File Statistics: {file_name}\n")
            print(f"Lines:      {lines.get('total', 0)} ({lines.get('code', 0)} code, {lines.get('comments', 0)} comments)")
            print(f"Functions:  {elements.get('functions', 0)}")
            print(f"Classes:    {elements.get('classes', 0)}")
            print(f"Complexity: {complexity.get('average', 0):.2f} (avg), {complexity.get('max', 0)} (max)")
            print(f"Quality:    {quality.get('score', 0):.1f}/100")

            # Show issues if present
            issues = result.get('issues', {})
            long_funcs = issues.get('long_functions', [])
            deep_nesting = issues.get('deep_nesting', [])
            if long_funcs or deep_nesting:
                print("\nIssues:")
                if long_funcs:
                    print(f"  Long functions: {len(long_funcs)}")
                if deep_nesting:
                    print(f"  Deep nesting: {len(deep_nesting)}")
            return

        # Text format - directory stats
        if 'summary' in result:
            path = result.get('path', '.')
            s = result['summary']
            print(f"Codebase Statistics: {path}\n")
            print(f"Files:      {s['total_files']}")
            print(f"Lines:      {s['total_lines']:,} ({s['total_code_lines']:,} code)")
            print(f"Functions:  {s['total_functions']}")
            print(f"Classes:    {s['total_classes']}")
            print(f"Complexity: {s['avg_complexity']:.2f} (avg)")
            print(f"Quality:    {s['avg_quality_score']:.1f}/100")

            # Show hotspots if present
            if 'hotspots' in result and result['hotspots']:
                print(f"\nTop Hotspots ({len(result['hotspots'])}):")
                for i, h in enumerate(result['hotspots'], 1):
                    print(f"\n{i}. {h['file']}")
                    print(f"   Quality: {h['quality_score']:.1f}/100 | Score: {h['hotspot_score']:.1f}")
                    print(f"   Issues: {', '.join(h['issues'])}")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render file-specific statistics.

        Args:
            result: Element dict from StatsAdapter.get_element()
            format: Output format ('text', 'json')
        """
        if format == 'json':
            from ..main import safe_json_dumps
            print(safe_json_dumps(result))
            return

        # Text format - file stats
        print(f"File: {result.get('file', 'unknown')}")
        print(f"\nLines:")
        print(f"  Total:    {result['lines']['total']}")
        print(f"  Code:     {result['lines']['code']}")
        print(f"  Comments: {result['lines']['comments']}")
        print(f"  Empty:    {result['lines']['empty']}")
        print(f"\nElements:")
        print(f"  Functions: {result['elements']['functions']}")
        print(f"  Classes:   {result['elements']['classes']}")
        print(f"  Imports:   {result['elements']['imports']}")
        print(f"\nComplexity:")
        print(f"  Average:   {result['complexity']['average']:.2f}")
        print(f"  Max:       {result['complexity']['max']}")
        print(f"\nQuality:")
        print(f"  Score:     {result['quality']['score']:.1f}/100")
        print(f"  Long funcs: {result['quality']['long_functions']}")
        print(f"  Deep nest:  {result['quality']['deep_nesting']}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error analyzing statistics: {error}", file=sys.stderr)


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
        self.path = Path(path).resolve()
        if not self.path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

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
        self._quality_config = self._get_quality_config()

    def _get_quality_config(self) -> Dict[str, Any]:
        """Load quality scoring configuration.

        Config search order:
        1. ./.reveal/stats-quality.yaml (project)
        2. ~/.config/reveal/stats-quality.yaml (user)
        3. Hardcoded QUALITY_DEFAULTS (fallback)

        Returns:
            Quality config dict with thresholds and penalties
        """
        import copy
        config = copy.deepcopy(QUALITY_DEFAULTS)

        config_paths = [
            self.path / '.reveal' / 'stats-quality.yaml' if self.path.is_dir() else self.path.parent / '.reveal' / 'stats-quality.yaml',
            Path.home() / '.config' / 'reveal' / 'stats-quality.yaml',
        ]

        try:
            import yaml
            for path in config_paths:
                if path.exists():
                    with open(path) as f:
                        loaded_raw = yaml.safe_load(f)
                        if loaded_raw and isinstance(loaded_raw, dict):
                            loaded: Dict[str, Any] = loaded_raw
                            # Deep merge loaded config into defaults
                            for key in ['thresholds', 'penalties']:
                                if key in loaded and isinstance(loaded[key], dict) and isinstance(config[key], dict):
                                    loaded_section = cast(Dict[str, Any], loaded[key])
                                    config_section = cast(Dict[str, Any], config[key])
                                    if key == 'penalties':
                                        for subkey in loaded_section:
                                            if subkey in config_section:
                                                config_section[subkey].update(loaded_section[subkey])
                                    else:
                                        config_section.update(loaded_section)
                            break
        except ImportError:
            pass  # yaml not available, use defaults
        except Exception:
            pass  # Any config error, use defaults

        return config

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
        for file_path in self._find_analyzable_files(self.path, code_only=code_only):
            stats = self._analyze_file(file_path)
            if stats and self._matches_filters(
                stats, min_lines, max_lines, min_complexity, max_complexity, min_functions
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
                key=lambda x: self._field_value(x, sort_field) or 0,
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
            file_stats = self._analyze_file(self.path)
            return self._aggregate_stats([file_stats] if file_stats else [])

        # Collect filtered directory statistics
        dir_file_stats = self._collect_filtered_stats(
            code_only, min_lines, max_lines, min_complexity, max_complexity, min_functions
        )
        total_filtered = len(dir_file_stats)

        # Apply sorting and pagination
        controlled_stats = self._apply_sorting(dir_file_stats)
        controlled_stats = self._apply_pagination(controlled_stats)

        # Aggregate and build result
        result = self._aggregate_stats(controlled_stats)
        self._add_truncation_metadata(result, len(controlled_stats), total_filtered)

        # Add hotspots if requested
        if hotspots:
            result['hotspots'] = self._identify_hotspots(controlled_stats)

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

        return self._analyze_file(target_path)

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

    def _find_analyzable_files(self, directory: Path, code_only: bool = False) -> List[Path]:
        """Find all files that can be analyzed.

        Args:
            directory: Directory to search
            code_only: If True, exclude data/config files

        Returns:
            List of analyzable file paths
        """
        # Data/config extensions to exclude when code_only=True
        DATA_EXTENSIONS = {'.xml', '.csv', '.sql'}
        CONFIG_EXTENSIONS = {'.yaml', '.yml', '.toml'}

        analyzable = []
        for root, dirs, files in os.walk(directory):
            # Skip common ignore directories
            dirs[:] = [d for d in dirs if d not in {
                '.git', '__pycache__', 'node_modules', '.venv', 'venv',
                'dist', 'build', '.pytest_cache', '.mypy_cache'
            }]

            for file in files:
                file_path = Path(root) / file

                # Check if reveal can analyze this file type
                if not get_analyzer(str(file_path)):
                    continue

                # Apply code_only filter
                if code_only:
                    suffix = file_path.suffix.lower()

                    # Exclude data files
                    if suffix in DATA_EXTENSIONS:
                        continue

                    # Exclude config files
                    if suffix in CONFIG_EXTENSIONS:
                        continue

                    # Exclude large JSON files (>10KB, likely data not code)
                    if suffix == '.json':
                        try:
                            if file_path.stat().st_size > 10240:  # 10KB
                                continue
                        except (OSError, PermissionError):
                            # If we can't stat it, include it
                            pass

                analyzable.append(file_path)

        return analyzable

    def _analyze_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Analyze a single file.

        Args:
            file_path: Path to file

        Returns:
            Dict with file statistics or None if analysis fails
        """
        try:
            # Get analyzer for this file
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return None

            # Analyze structure
            analyzer = analyzer_class(str(file_path))
            structure_dict = analyzer.get_structure()

            # Calculate statistics (analyzer has content)
            stats = self._calculate_file_stats(file_path, structure_dict, analyzer.content)
            return stats

        except Exception as e:
            # Silently skip files that can't be analyzed
            return None

    def _calculate_file_stats(self,
                             file_path: Path,
                             structure: Dict[str, Any],
                             content: str) -> Dict[str, Any]:
        """Calculate statistics for a file.

        Args:
            file_path: Path to file
            structure: Parsed structure from analyzer
            content: File content

        Returns:
            Dict with file statistics
        """
        lines = content.splitlines()
        total_lines = len(lines)

        # Count empty and comment lines (simple heuristic)
        empty_lines = sum(1 for line in lines if not line.strip())
        comment_lines = sum(1 for line in lines if line.strip().startswith(('#', '//', '/*', '*')))
        code_lines = total_lines - empty_lines - comment_lines

        # Extract element counts
        functions = structure.get('functions', [])
        classes = structure.get('classes', [])
        imports = structure.get('imports', [])

        # Calculate complexity metrics
        complexities = []
        long_functions = []
        deep_nesting = []

        for func in functions:
            # Get complexity if available
            complexity = self._estimate_complexity(func, content)
            if complexity:
                complexities.append(complexity)

            # Check for long functions (>100 lines)
            func_lines = func.get('line_count', 0)
            if func_lines > 100:
                long_functions.append({
                    'name': func.get('name', '<unknown>'),
                    'lines': func_lines,
                    'start_line': func.get('line', 0)
                })

            # Check for deep nesting (>4 levels)
            depth = func.get('depth', 0)
            if depth > 4:
                deep_nesting.append({
                    'name': func.get('name', '<unknown>'),
                    'depth': depth,
                    'start_line': func.get('line', 0)
                })

        avg_complexity = sum(complexities) / len(complexities) if complexities else 0
        avg_func_length = sum(f.get('line_count', 0) for f in functions) / len(functions) if functions else 0

        # Calculate quality score (0-100, higher is better)
        quality_score = self._calculate_quality_score(
            avg_complexity, avg_func_length, len(long_functions), len(deep_nesting), len(functions)
        )

        # For single file analysis, self.path is the file itself
        # Use the file name instead of trying to get relative path
        if self.path.is_file() and file_path == self.path:
            file_display = file_path.name
        elif file_path.is_relative_to(self.path):
            file_display = str(file_path.relative_to(self.path))
        else:
            file_display = str(file_path)

        return {
            'file': file_display,
            'lines': {
                'total': total_lines,
                'code': code_lines,
                'empty': empty_lines,
                'comments': comment_lines,
            },
            'elements': {
                'functions': len(functions),
                'classes': len(classes),
                'imports': len(imports),
            },
            'complexity': {
                'average': round(avg_complexity, 2),
                'max': max(complexities) if complexities else 0,
                'min': min(complexities) if complexities else 0,
            },
            'quality': {
                'score': round(quality_score, 1),
                'long_functions': len(long_functions),
                'deep_nesting': len(deep_nesting),
                'avg_function_length': round(avg_func_length, 1),
            },
            'issues': {
                'long_functions': long_functions,
                'deep_nesting': deep_nesting,
            }
        }

    def _estimate_complexity(self, func: Dict[str, Any], content: str) -> Optional[int]:
        """Estimate cyclomatic complexity for a function.

        Args:
            func: Function metadata
            content: File content

        Returns:
            Complexity score or None
        """
        start_line = func.get('line', 0)
        end_line = func.get('end_line', start_line)

        if start_line == 0 or end_line == 0:
            return None

        lines = content.splitlines()
        if start_line > len(lines) or end_line > len(lines):
            return None

        func_content = '\n'.join(lines[start_line - 1:end_line])

        # Calculate complexity (same algorithm as C901 rule)
        complexity = 1
        decision_keywords = [
            'if ', 'elif ', 'else:', 'else ', 'for ', 'while ',
            'and ', 'or ', 'try:', 'except ', 'except:', 'case ', 'when ',
        ]

        for keyword in decision_keywords:
            complexity += func_content.count(keyword)

        return complexity

    def _calculate_quality_score(self,
                                 avg_complexity: float,
                                 avg_func_length: float,
                                 long_func_count: int,
                                 deep_nesting_count: int,
                                 total_functions: int) -> float:
        """Calculate quality score (0-100, higher is better).

        Uses configurable thresholds from .reveal/stats-quality.yaml or defaults.

        Args:
            avg_complexity: Average cyclomatic complexity
            avg_func_length: Average function length in lines
            long_func_count: Number of functions >100 lines
            deep_nesting_count: Number of functions with depth >4
            total_functions: Total number of functions

        Returns:
            Quality score 0-100
        """
        # Get config values (with defaults)
        thresholds = self._quality_config.get('thresholds', {})
        penalties = self._quality_config.get('penalties', {})

        complexity_target = thresholds.get('complexity_target', 10)
        length_target = thresholds.get('function_length_target', 50)

        complexity_pen = penalties.get('complexity', {})
        length_pen = penalties.get('length', {})
        ratio_pen = penalties.get('ratios', {})

        score = 100.0

        # Penalize high complexity
        if avg_complexity > complexity_target:
            multiplier = complexity_pen.get('multiplier', 3)
            max_penalty = complexity_pen.get('max', 30)
            score -= min(max_penalty, (avg_complexity - complexity_target) * multiplier)

        # Penalize long functions
        if avg_func_length > length_target:
            divisor = length_pen.get('divisor', 2)
            max_penalty = length_pen.get('max', 20)
            score -= min(max_penalty, (avg_func_length - length_target) / divisor)

        # Penalize files with many long functions
        if total_functions > 0:
            long_func_ratio = long_func_count / total_functions
            multiplier = ratio_pen.get('multiplier', 50)
            max_penalty = ratio_pen.get('max', 25)
            score -= min(max_penalty, long_func_ratio * multiplier)

        # Penalize deep nesting
        if total_functions > 0:
            deep_nesting_ratio = deep_nesting_count / total_functions
            multiplier = ratio_pen.get('multiplier', 50)
            max_penalty = ratio_pen.get('max', 25)
            score -= min(max_penalty, deep_nesting_ratio * multiplier)

        return max(0, score)

    def _field_value(self, stats: Dict[str, Any], field: str) -> Any:
        """Extract field value from stats dict.

        Supports nested fields like 'lines.total', 'complexity.average', etc.

        Args:
            stats: File statistics dict
            field: Field name (may include dots for nesting)

        Returns:
            Field value or None if not found
        """
        # Map common field names to nested paths
        field_map = {
            'lines': 'lines.total',
            'code_lines': 'lines.code',
            'comment_lines': 'lines.comments',
            'complexity': 'complexity.average',
            'max_complexity': 'complexity.max',
            'functions': 'elements.functions',
            'classes': 'elements.classes',
            'quality': 'quality.score',
        }

        # Use mapped field if available
        field_path = field_map.get(field, field)

        # Navigate nested structure
        value = stats
        for part in field_path.split('.'):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None

        return value

    def _compare(self, value: Any, op: str, target: Any) -> bool:
        """Compare a value against a target using an operator.

        Uses unified compare_values() from query.py to eliminate duplication.

        Args:
            value: The value to compare
            op: Comparison operator (>, <, >=, <=, ==, =, !=, ~=, ..)
            target: The target value

        Returns:
            True if comparison passes
        """
        return compare_values(
            value,
            op,
            target,
            options={
                'allow_list_any': False,  # Stats doesn't have list fields
                'case_sensitive': False,
                'coerce_numeric': True,
                'none_matches_not_equal': False  # Stats: None doesn't match anything
            }
        )

    def _matches_filters(self,
                        stats: Dict[str, Any],
                        min_lines: Optional[int],
                        max_lines: Optional[int],
                        min_complexity: Optional[float],
                        max_complexity: Optional[float],
                        min_functions: Optional[int]) -> bool:
        """Check if file stats match filter criteria.

        Supports both legacy parameters (min_lines, max_lines, etc.) and
        new unified query filters (lines>50, complexity=5..15, etc.).

        Args:
            stats: File statistics
            min_lines: Minimum line count (legacy)
            max_lines: Maximum line count (legacy)
            min_complexity: Minimum avg complexity (legacy)
            max_complexity: Maximum avg complexity (legacy)
            min_functions: Minimum function count (legacy)

        Returns:
            True if matches all filters
        """
        # Check legacy parameters (backward compatibility)
        if min_lines is not None and stats['lines']['total'] < min_lines:
            return False
        if max_lines is not None and stats['lines']['total'] > max_lines:
            return False
        if min_complexity is not None and stats['complexity']['average'] < min_complexity:
            return False
        if max_complexity is not None and stats['complexity']['average'] > max_complexity:
            return False
        if min_functions is not None and stats['elements']['functions'] < min_functions:
            return False

        # Check new query filters (unified syntax)
        for qf in self.query_filters:
            value = self._field_value(stats, qf.field)
            if not self._compare(value, qf.op, qf.value):
                return False

        return True

    def _aggregate_stats(self, file_stats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate statistics from multiple files.

        Args:
            file_stats: List of file statistics

        Returns:
            Dict with aggregated statistics
        """
        if not file_stats:
            return {
                'contract_version': '1.0',
                'type': 'stats_summary',
                'source': str(self.path),
                'source_type': 'directory' if self.path.is_dir() else 'file',
                'summary': {
                    'total_files': 0,
                    'total_lines': 0,
                    'total_code_lines': 0,
                    'total_functions': 0,
                    'total_classes': 0,
                    'avg_complexity': 0,
                    'avg_quality_score': 0,
                },
                'files': []
            }

        total_lines = sum(s['lines']['total'] for s in file_stats)
        total_code = sum(s['lines']['code'] for s in file_stats)
        total_functions = sum(s['elements']['functions'] for s in file_stats)
        total_classes = sum(s['elements']['classes'] for s in file_stats)

        # Weighted average complexity (by number of functions)
        complexity_sum = sum(s['complexity']['average'] * s['elements']['functions'] for s in file_stats)
        avg_complexity = complexity_sum / total_functions if total_functions > 0 else 0

        avg_quality = sum(s['quality']['score'] for s in file_stats) / len(file_stats)

        return {
            'contract_version': '1.0',
            'type': 'stats_summary',
            'source': str(self.path),
            'source_type': 'directory' if self.path.is_dir() else 'file',
            'summary': {
                'total_files': len(file_stats),
                'total_lines': total_lines,
                'total_code_lines': total_code,
                'total_functions': total_functions,
                'total_classes': total_classes,
                'avg_complexity': round(avg_complexity, 2),
                'avg_quality_score': round(avg_quality, 1),
            },
            'files': file_stats
        }

    def _identify_hotspots(self, file_stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify top 10 hotspot files.

        Hotspots are files with quality issues: long functions, high complexity,
        deep nesting, or low quality scores.

        Args:
            file_stats: List of file statistics

        Returns:
            List of top 10 hotspot files sorted by severity
        """
        # Score each file by number and severity of issues
        scored_files = []
        for stats in file_stats:
            hotspot_score = 0
            issues = []

            # Low quality score
            quality = stats['quality']['score']
            if quality < 70:
                hotspot_score += (70 - quality) / 10
                issues.append(f"Quality: {quality:.1f}/100")

            # High complexity
            complexity = stats['complexity']['average']
            if complexity > 10:
                hotspot_score += complexity - 10
                issues.append(f"Avg complexity: {complexity:.1f}")

            # Long functions
            long_funcs = stats['quality']['long_functions']
            if long_funcs > 0:
                hotspot_score += long_funcs * 5
                issues.append(f"{long_funcs} function(s) >100 lines")

            # Deep nesting
            deep_nest = stats['quality']['deep_nesting']
            if deep_nest > 0:
                hotspot_score += deep_nest * 3
                issues.append(f"{deep_nest} function(s) depth >4")

            if hotspot_score > 0:
                scored_files.append({
                    'file': stats['file'],
                    'hotspot_score': round(hotspot_score, 1),
                    'quality_score': quality,
                    'issues': issues,
                    'details': {
                        'lines': stats['lines']['total'],
                        'functions': stats['elements']['functions'],
                        'complexity': stats['complexity']['average'],
                    }
                })

        # Sort by hotspot score (descending) and return top 10
        scored_files.sort(key=lambda x: x['hotspot_score'], reverse=True)
        return scored_files[:10]
