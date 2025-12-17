"""Statistics adapter (stats://) for codebase metrics and hotspots."""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict

from .base import ResourceAdapter, register_adapter
from ..structure import TypedStructure
from ..registry import get_analyzer


@register_adapter('stats')
class StatsAdapter(ResourceAdapter):
    """Adapter for analyzing codebase statistics and identifying hotspots."""

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for stats:// adapter."""
        return {
            'name': 'stats',
            'description': 'Analyze codebase metrics, identify hotspots, and assess code quality',
            'syntax': 'stats://<path>[?<filters>]',
            'examples': [
                {
                    'uri': 'stats://./src',
                    'description': 'Get overview statistics for src directory'
                },
                {
                    'uri': 'stats://./src --hotspots',
                    'description': 'Show top 10 files with quality issues'
                },
                {
                    'uri': 'stats://./src/app.py',
                    'description': 'Get detailed statistics for a specific file'
                },
                {
                    'uri': 'stats://./src?min_lines=50',
                    'description': 'Filter files with 50+ lines'
                },
                {
                    'uri': 'stats://./src?max_complexity=10',
                    'description': 'Show files with average complexity <= 10'
                },
                {
                    'uri': 'stats://./src --format=json',
                    'description': 'JSON output for CI/CD integration'
                }
            ],
            'features': [
                'Aggregate codebase metrics (lines, functions, classes, complexity)',
                'Hotspot identification (largest/most complex files)',
                'Per-file statistics with quality scoring',
                'Filter by metrics (lines, complexity, function count)',
                'Multi-language support (Python, JS, Go, Rust, etc.)',
                'CI/CD friendly JSON output'
            ],
            'filters': {
                'min_lines': 'Minimum line count (e.g., ?min_lines=50)',
                'max_lines': 'Maximum line count (e.g., ?max_lines=500)',
                'min_complexity': 'Minimum avg complexity (e.g., ?min_complexity=5)',
                'max_complexity': 'Maximum avg complexity (e.g., ?max_complexity=10)',
                'min_functions': 'Minimum function count (e.g., ?min_functions=10)',
                'type': 'Filter by file type (e.g., ?type=python)',
            },
            'workflows': [
                {
                    'name': 'Find Refactoring Targets',
                    'scenario': 'Need to identify code that needs cleanup',
                    'steps': [
                        'stats://./src --hotspots              # See worst files',
                        'stats://./src?min_complexity=15      # High complexity files',
                        'reveal <hotspot-file> --check        # Analyze specific issues',
                    ],
                },
                {
                    'name': 'CI/CD Quality Gate',
                    'scenario': 'Fail build if complexity increases',
                    'steps': [
                        'stats://./src --format=json > before.json',
                        '# Make changes...',
                        'stats://./src --format=json > after.json',
                        'jq -r ".summary.avg_complexity" before.json after.json  # Compare',
                    ],
                },
                {
                    'name': 'Architecture Assessment',
                    'scenario': 'Understand codebase structure and size',
                    'steps': [
                        'stats://./src                        # Overall metrics',
                        'stats://./src/core                   # Core subsystem',
                        'stats://./src/plugins                # Plugins subsystem',
                        '# Compare metrics to identify imbalanced architecture',
                    ],
                },
            ],
            'anti_patterns': [
                {
                    'bad': 'find . -name "*.py" | xargs wc -l',
                    'good': 'stats://.',
                    'why': 'Provides context (functions, classes, complexity), not just line counts',
                },
                {
                    'bad': 'grep -r "def " | wc -l',
                    'good': 'stats://. --format=json | jq .summary.total_functions',
                    'why': 'Accurate parsing with structured output, not text munging',
                },
            ],
            'notes': [
                'Recursively analyzes all supported file types in directory',
                'Complexity calculated using cyclomatic complexity heuristic',
                'Hotspots ranked by: long functions, deep nesting, high complexity',
                'Use --hotspots flag to see top 10 worst files',
                'Quality score: 0-100 (higher is better)',
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal help://ast - Query code structure',
                'reveal --check - Run quality checks',
                'reveal help://tricks - Power user workflows',
            ]
        }

    def __init__(self, path: str):
        """Initialize stats adapter.

        Args:
            path: File or directory path to analyze
        """
        self.path = Path(path).resolve()
        if not self.path.exists():
            raise FileNotFoundError(f"Path not found: {path}")

    def get_structure(self,
                     hotspots: bool = False,
                     min_lines: Optional[int] = None,
                     max_lines: Optional[int] = None,
                     min_complexity: Optional[float] = None,
                     max_complexity: Optional[float] = None,
                     min_functions: Optional[int] = None,
                     **kwargs) -> Dict[str, Any]:
        """Get statistics for file or directory.

        Args:
            hotspots: If True, include hotspot analysis
            min_lines: Filter files with at least this many lines
            max_lines: Filter files with at most this many lines
            min_complexity: Filter files with avg complexity >= this
            max_complexity: Filter files with avg complexity <= this
            min_functions: Filter files with at least this many functions

        Returns:
            Dict containing statistics and optionally hotspots
        """
        if self.path.is_file():
            return self._analyze_file(self.path)

        # Directory analysis
        file_stats = []
        for file_path in self._find_analyzable_files(self.path):
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

    def _find_analyzable_files(self, directory: Path) -> List[Path]:
        """Find all files that can be analyzed.

        Args:
            directory: Directory to search

        Returns:
            List of analyzable file paths
        """
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
                if get_analyzer(str(file_path)):
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
