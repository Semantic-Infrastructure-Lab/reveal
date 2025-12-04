"""AST query adapter (ast://)."""

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import ResourceAdapter, register_adapter

# Suppress tree-sitter warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='tree_sitter')


@register_adapter('ast')
class AstAdapter(ResourceAdapter):
    """Adapter for querying code as an AST database via ast:// URIs.

    Examples:
        ast://./src                      # All code structure
        ast://./src?lines>50             # Functions with >50 lines
        ast://./src?complexity>10        # Complex functions
        ast://app.py?type=function       # Only functions
        ast://.?lines>20&complexity<5    # Long but simple functions
    """

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for ast:// adapter."""
        return {
            'name': 'ast',
            'description': 'Query code as an AST database - find functions by complexity, size, type',
            'syntax': 'ast://<path>?<filter1>&<filter2>&...',
            'operators': {
                '>': 'Greater than',
                '<': 'Less than',
                '>=': 'Greater than or equal',
                '<=': 'Less than or equal',
                '==': 'Equal to'
            },
            'filters': {
                'lines': 'Number of lines in function/class (e.g., lines>50)',
                'complexity': 'Cyclomatic complexity score 1-10 (e.g., complexity>5)',
                'type': 'Element type: function, class, method (e.g., type=function)',
                'name': 'Element name pattern - future feature (e.g., name=test_*)'
            },
            'examples': [
                {
                    'uri': 'ast://./src',
                    'description': 'All code structure in src directory'
                },
                {
                    'uri': 'ast://app.py?lines>50',
                    'description': 'Functions with more than 50 lines'
                },
                {
                    'uri': 'ast://./src?complexity>10',
                    'description': 'Complex functions (high cyclomatic complexity)'
                },
                {
                    'uri': 'ast://main.py?type=function',
                    'description': 'Only functions (not classes or methods)'
                },
                {
                    'uri': 'ast://.?lines>30&complexity<5',
                    'description': 'Long but simple functions (low complexity)'
                },
                {
                    'uri': "ast://./src?complexity>5 --format=json",
                    'description': 'JSON output for scripting'
                }
            ],
            'notes': [
                'Quote URIs with > or < operators: \'ast://path?lines>50\' (shell interprets > as redirect)',
                'Complexity is currently heuristic-based (line count). Tree-sitter-based calculation coming soon.',
                'Scans all code files in directory recursively',
                'Supports Python, JS, TS, Rust, Go, and 50+ languages via tree-sitter',
                'Use --format=json for programmatic filtering with jq'
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal help://env - Environment variable adapter',
                'reveal --agent-help - Agent usage patterns',
                'reveal file.py --check - Code quality checks'
            ]
        }

    def __init__(self, path: str, query_string: str = None):
        """Initialize AST adapter.

        Args:
            path: File or directory path to analyze
            query_string: Query parameters (e.g., "lines>50&complexity>10")
        """
        self.path = path
        self.query = self._parse_query(query_string) if query_string else {}
        self.results = []

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get filtered AST structure based on query.

        Returns:
            Dict containing query results with metadata
        """
        # Collect all structures from path (file or directory)
        structures = self._collect_structures(self.path)

        # Apply filters
        filtered = self._apply_filters(structures)

        return {
            'type': 'ast-query',
            'path': self.path,
            'query': self._format_query(self.query),
            'total_files': len(structures),
            'total_results': len(filtered),
            'results': filtered
        }

    def _parse_query(self, query_string: str) -> Dict[str, Any]:
        """Parse query string into filter conditions.

        Args:
            query_string: URL query string (e.g., "lines>50&type=function")

        Returns:
            Dict of filter conditions
        """
        if not query_string:
            return {}

        filters = {}
        for param in query_string.split('&'):
            # Handle different operators
            if '>=' in param:
                key, value = param.split('>=', 1)
                filters[key] = {'op': '>=', 'value': int(value)}
            elif '<=' in param:
                key, value = param.split('<=', 1)
                filters[key] = {'op': '<=', 'value': int(value)}
            elif '>' in param:
                key, value = param.split('>', 1)
                filters[key] = {'op': '>', 'value': int(value)}
            elif '<' in param:
                key, value = param.split('<', 1)
                filters[key] = {'op': '<', 'value': int(value)}
            elif '=' in param:
                key, value = param.split('=', 1)
                # Try to parse as int, otherwise keep as string
                try:
                    filters[key] = {'op': '==', 'value': int(value)}
                except ValueError:
                    filters[key] = {'op': '==', 'value': value}

        return filters

    def _format_query(self, query: Dict[str, Any]) -> str:
        """Format query dict back to readable string."""
        if not query:
            return "none"

        parts = []
        for key, condition in query.items():
            op = condition['op']
            val = condition['value']
            parts.append(f"{key}{op}{val}")
        return " AND ".join(parts)

    def _collect_structures(self, path: str) -> List[Dict[str, Any]]:
        """Collect structure data from file(s).

        Args:
            path: File or directory path

        Returns:
            List of structure dicts with file metadata
        """
        structures = []
        path_obj = Path(path)

        if path_obj.is_file():
            structure = self._analyze_file(str(path_obj))
            if structure:
                structures.append(structure)
        elif path_obj.is_dir():
            # Recursively find all code files
            for file_path in path_obj.rglob('*'):
                if file_path.is_file() and self._is_code_file(file_path):
                    structure = self._analyze_file(str(file_path))
                    if structure:
                        structures.append(structure)

        return structures

    def _is_code_file(self, path: Path) -> bool:
        """Check if file is a code file we can analyze."""
        # Common code extensions
        code_exts = {
            '.py', '.js', '.ts', '.jsx', '.tsx', '.rs', '.go',
            '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.rb',
            '.php', '.swift', '.kt', '.scala', '.sh', '.bash'
        }
        return path.suffix.lower() in code_exts

    def _analyze_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Analyze a single file and extract structure.

        Args:
            file_path: Path to file

        Returns:
            Dict with file structure, or None if analysis fails
        """
        from ..base import get_analyzer

        try:
            analyzer_class = get_analyzer(file_path)
            if not analyzer_class:
                return None

            analyzer = analyzer_class(file_path)
            structure = analyzer.get_structure()
            if not structure:
                return None

            # Add file metadata to each element
            result = {
                'file': file_path,
                'elements': []
            }

            # Flatten all elements from structure
            for category, items in structure.items():
                for item in items:
                    element = {
                        'file': file_path,
                        'category': category,
                        'name': item.get('name', ''),
                        'line': item.get('line', 0),
                        'line_count': item.get('line_count', 0),
                        'signature': item.get('signature', ''),
                    }

                    # Add complexity if we can calculate it
                    if category in ('functions', 'methods'):
                        element['complexity'] = self._calculate_complexity(item, analyzer)

                    result['elements'].append(element)

            return result

        except Exception as e:
            # Skip files we can't analyze
            print(f"Warning: Failed to analyze {file_path}: {e}", file=sys.stderr)
            return None

    def _calculate_complexity(self, element: Dict[str, Any], analyzer) -> int:
        """Calculate cyclomatic complexity for a function.

        Args:
            element: Function element dict
            analyzer: FileAnalyzer instance

        Returns:
            Complexity score (1 = simple, higher = more complex)
        """
        # For now, use a simple heuristic based on line count
        # TODO: Implement proper tree-sitter based complexity
        line_count = element.get('line_count', 0)

        # Very rough heuristic:
        # - Simple function (1-10 lines) = 1-2
        # - Medium function (11-30 lines) = 3-5
        # - Complex function (31-50 lines) = 6-8
        # - Very complex (50+) = 9+

        if line_count <= 10:
            return 1
        elif line_count <= 20:
            return 2
        elif line_count <= 30:
            return 3
        elif line_count <= 40:
            return 5
        elif line_count <= 60:
            return 7
        else:
            return min(10, line_count // 10)

    def _apply_filters(self, structures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply query filters to collected structures.

        Args:
            structures: List of file structures

        Returns:
            Filtered list of matching elements
        """
        results = []

        for structure in structures:
            for element in structure.get('elements', []):
                if self._matches_filters(element):
                    results.append(element)

        return results

    def _matches_filters(self, element: Dict[str, Any]) -> bool:
        """Check if element matches all query filters.

        Args:
            element: Element dict

        Returns:
            True if element matches all filters
        """
        for key, condition in self.query.items():
            # Handle special key mappings
            if key == 'type':
                # Map 'type' to 'category'
                value = element.get('category', '')
            elif key == 'lines':
                # Map 'lines' to 'line_count'
                value = element.get('line_count', 0)
            else:
                value = element.get(key)

            if value is None:
                return False

            if not self._compare(value, condition):
                return False

        return True

    def _compare(self, value: Any, condition: Dict[str, Any]) -> bool:
        """Compare value against condition.

        Args:
            value: Actual value
            condition: Condition dict with 'op' and 'value'

        Returns:
            True if comparison passes
        """
        op = condition['op']
        target = condition['value']

        if op == '>':
            return value > target
        elif op == '<':
            return value < target
        elif op == '>=':
            return value >= target
        elif op == '<=':
            return value <= target
        elif op == '==':
            return str(value) == str(target)

        return False
