"""AST query adapter (ast://)."""

import os
import sys
import warnings
from fnmatch import fnmatch
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
                'type': 'Element type: function, class, method. Supports OR with | or , (e.g., type=function, type=class|function)',
                'name': 'Element name pattern with wildcards (e.g., name=test_*, name=*helper*, name=get_?)'
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
                    'uri': 'ast://.?type=class|function',
                    'description': 'Both classes and functions (OR logic)'
                },
                {
                    'uri': 'ast://.?name=test_*',
                    'description': 'All functions/classes starting with test_'
                },
                {
                    'uri': 'ast://src/?name=*helper*',
                    'description': 'All functions/classes containing "helper" in name'
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
            # Executable examples for current directory
            'try_now': [
                "reveal 'ast://.?complexity>5'",
                "reveal 'ast://.?name=test_*'",
                "reveal 'ast://.?type=class'",
            ],
            # Scenario-based workflow patterns
            'workflows': [
                {
                    'name': 'Find Refactoring Targets',
                    'scenario': 'Codebase feels messy, need to find problem areas',
                    'steps': [
                        "reveal 'ast://./src?complexity>10'        # Find complex functions",
                        "reveal 'ast://./src?lines>100'            # Find oversized functions",
                        "reveal src/problem_file.py --outline      # Understand structure",
                        "reveal src/problem_file.py big_function   # Extract for refactoring",
                    ]
                },
                {
                    'name': 'Explore Unknown Codebase',
                    'scenario': 'New project, need to find entry points and structure',
                    'steps': [
                        "reveal 'ast://.?name=main*'               # Find entry points",
                        "reveal 'ast://.?name=*cli*|*command*'     # Find CLI handlers",
                        "reveal 'ast://.?type=class'               # See class hierarchy",
                        "reveal src/core.py --outline              # Drill into key file",
                    ]
                },
                {
                    'name': 'Pre-PR Review',
                    'scenario': 'About to review changes, want quick quality check',
                    'steps': [
                        "git diff --name-only | grep '\\.py$' | xargs -I{} reveal 'ast://{}?complexity>8'",
                        "git diff --name-only | reveal --stdin --check",
                    ]
                },
            ],
            # What NOT to do
            'anti_patterns': [
                {
                    'bad': "grep -r 'class UserManager' .",
                    'good': "reveal 'ast://.?name=UserManager&type=class'",
                    'why': 'Semantic search vs text matching - no false positives from comments/strings'
                },
                {
                    'bad': "find . -name '*.py' -exec grep -l 'def process' {} \\;",
                    'good': "reveal 'ast://.?name=process*&type=function'",
                    'why': 'One command, structured output with line numbers and complexity'
                },
                {
                    'bad': "grep -rn 'def test_' tests/",
                    'good': "reveal 'ast://tests/?name=test_*'",
                    'why': 'Wildcard matching + metadata (find long tests with lines>50)'
                },
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
                'reveal help://python - Runtime environment inspection',
                'reveal help://tricks - Power user workflows',
                'reveal file.py --check - Code quality checks'
            ]
        }

    def __init__(self, path: str, query_string: str = None):
        """Initialize AST adapter.

        Args:
            path: File or directory path to analyze
            query_string: Query parameters (e.g., "lines>50&complexity>10")
        """
        # Expand ~ to home directory
        self.path = os.path.expanduser(path)
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
                # Check for OR logic (| or , separator) for type filters
                if key == 'type' and ('|' in value or ',' in value):
                    separator = '|' if '|' in value else ','
                    types = [t.strip() for t in value.split(separator)]
                    filters[key] = {'op': 'in', 'value': types}
                # Check if value contains wildcards
                elif '*' in value or '?' in value:
                    # Use glob pattern matching
                    filters[key] = {'op': 'glob', 'value': value}
                else:
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
            if op == 'in':
                # Format OR logic nicely: type=class|function
                parts.append(f"{key}=={'|'.join(val)}")
            else:
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
                    # Calculate line_count - functions have it, classes need computation from line_end
                    line_count = item.get('line_count') or (
                        item.get('line_end', 0) - item.get('line', 0) + 1
                        if item.get('line_end') else 0
                    )
                    element = {
                        'file': file_path,
                        'category': category,
                        'name': item.get('name', ''),
                        'line': item.get('line', 0),
                        'line_count': line_count,
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
                # Normalize singular/plural for type filter
                # Categories are plural (functions, classes) but users may type singular
                condition = self._normalize_type_condition(condition)
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

    def _normalize_type_condition(self, condition: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize type condition to handle singular/plural forms.

        Args:
            condition: Condition dict with 'op' and 'value'

        Returns:
            Normalized condition (singular -> plural)
        """
        # Map singular forms to plural (matching category values)
        singular_to_plural = {
            'function': 'functions',
            'class': 'classes',
            'method': 'methods',
            'struct': 'structs',
            'import': 'imports',
        }

        # Handle 'in' operator (OR logic) - normalize each type
        if condition.get('op') == 'in' and isinstance(condition.get('value'), list):
            normalized = [singular_to_plural.get(t.lower(), t.lower()) for t in condition['value']]
            return {'op': 'in', 'value': normalized}

        # Handle single type
        if condition.get('op') == '==' and isinstance(condition.get('value'), str):
            value = condition['value'].lower()
            if value in singular_to_plural:
                return {'op': '==', 'value': singular_to_plural[value]}

        return condition

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
        elif op == 'in':
            # OR logic: check if value matches any in target list
            return str(value) in [str(t) for t in target]
        elif op == 'glob':
            # Wildcard pattern matching (case-sensitive)
            return fnmatch(str(value), str(target))

        return False
