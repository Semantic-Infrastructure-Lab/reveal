"""AST query adapter (ast://)."""

import os
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import ResourceAdapter, register_adapter, register_renderer
from ..core import suppress_treesitter_warnings

# Suppress tree-sitter warnings (centralized in core module)
suppress_treesitter_warnings()


class AstRenderer:
    """Renderer for AST query results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render AST query results.

        Args:
            result: Query result dict from AstAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering import render_ast_structure
        render_ast_structure(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error querying AST: {error}", file=sys.stderr)


@register_adapter('ast')
@register_renderer(AstRenderer)
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
                'complexity': 'McCabe cyclomatic complexity (industry threshold: >10 needs refactoring, >20 is high risk)',
                'type': 'Element type: function, class, method. Supports OR with | or , (e.g., type=function, type=class|function)',
                'name': 'Element name pattern with wildcards (e.g., name=test_*, name=*helper*, name=get_?)',
                'decorator': 'Decorator pattern - find decorated functions/classes (e.g., decorator=property, decorator=*cache*)'
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
                    'uri': "ast://./src?complexity>10 --format=json",
                    'description': 'JSON output for scripting'
                },
                {
                    'uri': 'ast://.?decorator=property',
                    'description': 'Find all @property decorated methods'
                },
                {
                    'uri': 'ast://.?decorator=*cache*',
                    'description': 'Find all cached functions (@lru_cache, @cached_property, etc.)'
                },
                {
                    'uri': 'ast://.?decorator=staticmethod',
                    'description': 'Find all @staticmethod methods'
                },
                {
                    'uri': 'ast://.?decorator=property&lines>10',
                    'description': 'Find complex properties (potential code smell)'
                }
            ],
            # Executable examples for current directory
            'try_now': [
                "reveal 'ast://.?complexity>10'",
                "reveal 'ast://.?name=test_*'",
                "reveal 'ast://.?decorator=property'",
                "reveal 'ast://.?decorator=*cache*'",
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
                {
                    'name': 'Analyze Decorator Patterns',
                    'scenario': 'Understand caching, properties, and API surface',
                    'steps': [
                        "reveal 'ast://.?decorator=property'            # All properties",
                        "reveal 'ast://.?decorator=*cache*'             # All cached/memoized functions",
                        "reveal 'ast://.?decorator=staticmethod'        # Static methods (might not need class)",
                        "reveal 'ast://.?decorator=abstractmethod'      # Abstract interface",
                        "reveal 'ast://.?decorator=property&lines>10'   # Complex properties (code smell)",
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
            'contract_version': '1.0',
            'type': 'ast_query',
            'source': self.path,
            'source_type': 'directory' if Path(self.path).is_dir() else 'file',
            'path': self.path,
            'query': self._format_query(self.query),
            'total_files': len(structures),
            'total_results': len(filtered),
            'results': filtered
        }

    def _parse_equality_value(self, key: str, value: str) -> Dict[str, Any]:
        """Parse equality parameter value based on content.

        Args:
            key: Parameter key (e.g., 'type', 'name')
            value: Parameter value to parse

        Returns:
            Filter dict with operator and parsed value
        """
        # Check for OR logic (| or , separator) for type filters
        if key == 'type' and ('|' in value or ',' in value):
            separator = '|' if '|' in value else ','
            types = [t.strip() for t in value.split(separator)]
            return {'op': 'in', 'value': types}

        # Check if value contains wildcards
        if '*' in value or '?' in value:
            return {'op': 'glob', 'value': value}

        # Try to parse as int, otherwise keep as string
        try:
            return {'op': '==', 'value': int(value)}
        except ValueError:
            return {'op': '==', 'value': value}

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
            # Handle comparison operators (order matters: >= before >)
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
                filters[key] = self._parse_equality_value(key, value)

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

    def _try_add_file_structure(self, file_path: str, structures: List[Dict[str, Any]]) -> None:
        """Analyze file and add its structure to list if successful.

        Args:
            file_path: Path to file to analyze
            structures: List to append structure to
        """
        structure = self._analyze_file(file_path)
        if structure:
            structures.append(structure)

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
            self._try_add_file_structure(str(path_obj), structures)
        elif path_obj.is_dir():
            # Recursively find all code files
            for file_path in path_obj.rglob('*'):
                if file_path.is_file() and self._is_code_file(file_path):
                    self._try_add_file_structure(str(file_path), structures)

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

    def _create_element_dict(
        self,
        file_path: str,
        category: str,
        item: Dict[str, Any],
        analyzer
    ) -> Dict[str, Any]:
        """Create element dict from analyzer item.

        Args:
            file_path: Source file path
            category: Element category (functions, classes, etc.)
            item: Item dict from analyzer
            analyzer: Analyzer instance for complexity calculation

        Returns:
            Element dict with standardized fields
        """
        # Calculate line_count - functions have it, classes need computation
        line_count = item.get('line_count')
        if not line_count and item.get('line_end'):
            line_count = item.get('line_end', 0) - item.get('line', 0) + 1
        else:
            line_count = line_count or 0

        element = {
            'file': file_path,
            'category': category,
            'name': item.get('name', ''),
            'line': item.get('line', 0),
            'line_count': line_count,
            'signature': item.get('signature', ''),
            'decorators': item.get('decorators', []),
        }

        # Add complexity for functions/methods
        if category in ('functions', 'methods'):
            # Use complexity from item if available (tree-sitter calculated)
            # Otherwise calculate with heuristic
            element['complexity'] = item.get('complexity') or self._calculate_complexity(item, analyzer)

        return element

    def _analyze_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Analyze a single file and extract structure.

        Args:
            file_path: Path to file

        Returns:
            Dict with file structure, or None if analysis fails
        """
        from ..registry import get_analyzer

        try:
            analyzer_class = get_analyzer(file_path)
            if not analyzer_class:
                return None

            analyzer = analyzer_class(file_path)
            structure = analyzer.get_structure()
            if not structure:
                return None

            # Flatten all elements from structure
            result = {'file': file_path, 'elements': []}

            for category, items in structure.items():
                for item in items:
                    element = self._create_element_dict(file_path, category, item, analyzer)
                    result['elements'].append(element)

            return result

        except Exception as e:
            # Skip files we can't analyze
            print(f"Warning: Failed to analyze {file_path}: {e}", file=sys.stderr)
            return None

    def _calculate_complexity(self, element: Dict[str, Any], analyzer) -> int:
        """Calculate cyclomatic complexity for a function.

        NOTE: This is a fallback heuristic for non-tree-sitter analyzers.
        Tree-sitter analyzers calculate proper McCabe complexity.

        Args:
            element: Function element dict
            analyzer: FileAnalyzer instance

        Returns:
            Complexity score (1 = simple, higher = more complex)
        """
        # Fallback heuristic based on line count
        # Used only when tree-sitter complexity is not available
        line_count = element.get('line_count', 0)

        # Very rough heuristic:
        # - Simple function (1-10 lines) = 1-2
        # - Medium function (11-30 lines) = 3-5
        # - Complex function (31-50 lines) = 6-8
        # - Very complex (50+) = proportional to lines

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
            # No cap! Let it scale with line count
            return line_count // 10

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
            elif key == 'decorator':
                # Special handling: check if any decorator matches
                decorators = element.get('decorators', [])
                if not self._matches_decorator(decorators, condition):
                    return False
                continue  # Already handled, skip normal comparison
            else:
                value = element.get(key)

            if value is None:
                return False

            if not self._compare(value, condition):
                return False

        return True

    def _matches_decorator(self, decorators: List[str], condition: Dict[str, Any]) -> bool:
        """Check if any decorator matches the condition.

        Supports:
        - Exact match: decorator=property
        - Wildcard: decorator=*cache* (matches @lru_cache, @cached_property, etc.)

        Args:
            decorators: List of decorator strings (e.g., ['@property', '@lru_cache(maxsize=100)'])
            condition: Condition dict with 'op' and 'value'

        Returns:
            True if any decorator matches
        """
        if not decorators:
            return False

        target = condition['value']
        op = condition['op']

        # Normalize target - add @ if not present
        if not target.startswith('@') and not target.startswith('*'):
            target = f'@{target}'

        for dec in decorators:
            # Exact match
            if op == '==':
                # Match decorator name (ignore args)
                # @lru_cache(maxsize=100) should match @lru_cache
                dec_name = dec.split('(')[0]
                if dec_name == target or dec == target:
                    return True
            # Wildcard match
            elif op == 'glob':
                if fnmatch(dec, target) or fnmatch(dec, f'@{target}'):
                    return True

        return False

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
