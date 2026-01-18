"""Statistics adapter (stats://) for codebase metrics and hotspots."""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

from .base import ResourceAdapter, register_adapter, register_renderer
from .help_data import load_help_data
from ..registry import get_analyzer


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

    def __init__(self, path: str, query_string: str = None):
        """Initialize stats adapter.

        Args:
            path: File or directory path to analyze
            query_string: Query parameters (e.g., "hotspots=true&min_lines=50")
        """
        self.path = Path(path).resolve()
        if not self.path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

        # Parse query string
        self.query_params = self._parse_query(query_string) if query_string else {}

    def _parse_query(self, query_string: str) -> Dict[str, Any]:
        """Parse query string into parameters.

        Args:
            query_string: URL query string (e.g., "hotspots=true&min_lines=50")

        Returns:
            Dict of parsed parameters
        """
        params = {}
        if not query_string:
            return params

        for param in query_string.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Parse boolean values
                if value.lower() in ('true', '1', 'yes'):
                    params[key] = True
                elif value.lower() in ('false', '0', 'no'):
                    params[key] = False
                # Parse numeric values
                elif value.isdigit():
                    params[key] = int(value)
                elif value.replace('.', '', 1).isdigit():
                    params[key] = float(value)
                else:
                    params[key] = value

        return params

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
        # Merge query params with flag params (query params take precedence)
        hotspots = self.query_params.get('hotspots', hotspots)
        code_only = self.query_params.get('code_only', code_only)
        min_lines = self.query_params.get('min_lines', min_lines)
        max_lines = self.query_params.get('max_lines', max_lines)
        min_complexity = self.query_params.get('min_complexity', min_complexity)
        max_complexity = self.query_params.get('max_complexity', max_complexity)
        min_functions = self.query_params.get('min_functions', min_functions)
        if self.path.is_file():
            return self._analyze_file(self.path)

        # Directory analysis
        file_stats = []
        for file_path in self._find_analyzable_files(self.path, code_only=code_only):
            stats = self._analyze_file(file_path)
            if stats and self._matches_filters(
                stats, min_lines, max_lines, min_complexity, max_complexity, min_functions
            ):
                file_stats.append(stats)

        # Aggregate statistics
        result = self._aggregate_stats(file_stats)

        # Add hotspots if requested
        if hotspots:
            result['hotspots'] = self._identify_hotspots(file_stats)

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

        return {
            'file': str(file_path.relative_to(self.path)) if file_path.is_relative_to(self.path) else str(file_path),
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

        Args:
            avg_complexity: Average cyclomatic complexity
            avg_func_length: Average function length in lines
            long_func_count: Number of functions >100 lines
            deep_nesting_count: Number of functions with depth >4
            total_functions: Total number of functions

        Returns:
            Quality score 0-100
        """
        score = 100.0

        # Penalize high complexity (target: <10)
        if avg_complexity > 10:
            score -= min(30, (avg_complexity - 10) * 3)

        # Penalize long functions (target: <50 lines avg)
        if avg_func_length > 50:
            score -= min(20, (avg_func_length - 50) / 2)

        # Penalize files with many long functions
        if total_functions > 0:
            long_func_ratio = long_func_count / total_functions
            score -= min(25, long_func_ratio * 50)

        # Penalize deep nesting
        if total_functions > 0:
            deep_nesting_ratio = deep_nesting_count / total_functions
            score -= min(25, deep_nesting_ratio * 50)

        return max(0, score)

    def _matches_filters(self,
                        stats: Dict[str, Any],
                        min_lines: Optional[int],
                        max_lines: Optional[int],
                        min_complexity: Optional[float],
                        max_complexity: Optional[float],
                        min_functions: Optional[int]) -> bool:
        """Check if file stats match filter criteria.

        Args:
            stats: File statistics
            min_lines: Minimum line count
            max_lines: Maximum line count
            min_complexity: Minimum avg complexity
            max_complexity: Maximum avg complexity
            min_functions: Minimum function count

        Returns:
            True if matches all filters
        """
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
