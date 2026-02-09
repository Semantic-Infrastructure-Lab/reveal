"""JSON navigation adapter (json://)."""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils.query import (
    parse_query_filters,
    parse_result_control,
    compare_values,
    ResultControl
)


class JsonRenderer:
    """Renderer for JSON navigation results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render JSON query results.

        Args:
            result: Query result dict from JsonAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ..rendering import render_json_result
        render_json_result(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error querying JSON: {error}", file=sys.stderr)


@register_adapter('json')
@register_renderer(JsonRenderer)
class JsonAdapter(ResourceAdapter):
    """Adapter for navigating and querying JSON files via json:// URIs.

    Provides path navigation, schema discovery, and gron-style flattening
    for JSON files - complementing the basic .json file handler.
    """

    @staticmethod
    def _get_path_syntax() -> Dict[str, str]:
        """Path syntax documentation."""
        return {
            '/key': 'Access object key',
            '/0': 'Access array index (0-based)',
            '/key/subkey': 'Navigate nested paths',
            '/arr[0:3]': 'Array slice (first 3 elements)',
            '/arr[-1]': 'Negative index (last element)',
        }

    @staticmethod
    def _get_queries_help() -> Dict[str, str]:
        """Query parameters documentation."""
        return {
            # Legacy query modes
            'schema': 'Show type structure of data',
            'flatten': 'Flatten to grep-able lines (gron-style output)',
            'gron': 'Alias for flatten (named after github.com/tomnomnom/gron)',
            'type': 'Show type at current path',
            'keys': 'List keys (objects) or length (arrays)',
            'length': 'Get array/string length or object key count',
            # Filtering and result control
            'field=value': 'Filter arrays by exact match',
            'field>value': 'Filter arrays by numeric comparison',
            'field~=pattern': 'Filter arrays by regex match',
            'sort=field': 'Sort array by field (ascending)',
            'sort=-field': 'Sort array by field (descending)',
            'limit=N': 'Limit results to N items',
            'offset=M': 'Skip first M items',
        }

    @staticmethod
    def _get_examples() -> List[Dict[str, str]]:
        """Usage examples."""
        return [
            {'uri': 'json://package.json', 'description': 'View entire JSON file (pretty-printed)'},
            {'uri': 'json://package.json/name', 'description': 'Get package name'},
            {'uri': 'json://package.json/scripts', 'description': 'Get all scripts'},
            {'uri': 'json://data.json/users/0', 'description': 'Get first user from array'},
            {'uri': 'json://data.json/users[0:3]', 'description': 'Get first 3 users (array slice)'},
            {'uri': 'json://config.json?schema', 'description': 'Show type structure of entire file'},
            {'uri': 'json://data.json/users?schema', 'description': 'Show schema of users array'},
            {'uri': 'json://config.json?flatten', 'description': 'Flatten to grep-able format (also: ?gron)'},
            {'uri': 'json://data.json/users?type', 'description': 'Get type at path (e.g., Array[Object])'},
            {'uri': 'json://package.json/dependencies?keys', 'description': 'List all dependency names'},
            # Filtering examples
            {'uri': 'json://data.json/users?age>25', 'description': 'Filter users older than 25'},
            {'uri': 'json://data.json/products?price=10..50', 'description': 'Products in price range $10-$50'},
            {'uri': 'json://data.json/users?name~=^John', 'description': 'Users with names starting with "John"'},
            {'uri': 'json://data.json/items?status!=inactive', 'description': 'Active items (exclude inactive)'},
            # Result control examples
            {'uri': 'json://data.json/users?sort=-age', 'description': 'Sort users by age descending'},
            {'uri': 'json://data.json/products?sort=price&limit=10', 'description': 'Top 10 cheapest products'},
            {'uri': 'json://data.json/users?age>21&sort=-age&limit=5', 'description': 'Top 5 oldest users over 21'},
        ]

    @staticmethod
    def _get_workflows() -> List[Dict[str, Any]]:
        """Scenario-based workflow patterns."""
        return [
            {
                'name': 'Explore Unknown JSON Structure',
                'scenario': 'Large JSON file, need to understand what\'s in it',
                'steps': [
                    "reveal json://data.json?schema       # See type structure",
                    "reveal json://data.json?keys         # Top-level keys",
                    "reveal json://data.json/users?schema # Drill into nested",
                    "reveal json://data.json/users/0      # Sample first element",
                ],
            },
            {
                'name': 'Search JSON Content',
                'scenario': 'Find specific values in a large JSON file',
                'steps': [
                    "reveal json://config.json?flatten | grep -i 'database'",
                    "reveal json://config.json?flatten | grep 'url'",
                ],
            },
        ]

    @staticmethod
    def _get_anti_patterns() -> List[Dict[str, str]]:
        """What NOT to do."""
        return [
            {
                'bad': "cat config.json | jq '.database.host'",
                'good': "reveal json://config.json/database/host",
                'why': "No jq dependency, consistent syntax with other reveal URIs",
            },
            {
                'bad': "cat large.json | python -c 'import json,sys; print(json.load(sys.stdin).keys())'",
                'good': "reveal json://large.json?keys",
                'why': "One command, handles errors gracefully",
            },
        ]

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for json:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'json',
            'description': 'JSON file navigation with path access, schema inference, and gron-style flattening',
            'uri_syntax': 'json://<file>[/path/to/key][?query]',
            'query_params': {
                'schema': {
                    'type': 'flag',
                    'description': 'Show type structure of data'
                },
                'flatten': {
                    'type': 'flag',
                    'description': 'Flatten to grep-able lines (gron-style output)'
                },
                'gron': {
                    'type': 'flag',
                    'description': 'Alias for flatten (named after github.com/tomnomnom/gron)'
                },
                'type': {
                    'type': 'flag',
                    'description': 'Show type at current path'
                },
                'keys': {
                    'type': 'flag',
                    'description': 'List keys (objects) or indices (arrays)'
                },
                'length': {
                    'type': 'flag',
                    'description': 'Get array/string length or object key count'
                }
            },
            'path_syntax': {
                '/key': 'Access object key',
                '/0': 'Access array index (0-based)',
                '/key/subkey': 'Navigate nested paths',
                '/arr[0:3]': 'Array slice (first 3 elements)',
                '/arr[-1]': 'Negative index (last element)'
            },
            'elements': {},  # Dynamic based on JSON structure
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'json_value',
                    'description': 'Raw JSON value at specified path',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'json_value'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'file'},
                            'file': {'type': 'string'},
                            'path': {'type': 'string'},
                            'value_type': {'type': 'string'},
                            'value': {}  # Any JSON type
                        }
                    }
                },
                {
                    'type': 'json_schema',
                    'description': 'Type structure inferred from data',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'json_schema'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'file'},
                            'file': {'type': 'string'},
                            'path': {'type': 'string'},
                            'schema': {}  # Inferred schema structure
                        }
                    }
                },
                {
                    'type': 'json_flatten',
                    'description': 'Gron-style flattened output for grep',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'json_flatten'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'file'},
                            'file': {'type': 'string'},
                            'path': {'type': 'string'},
                            'lines': {'type': 'array', 'items': {'type': 'string'}},
                            'line_count': {'type': 'integer'}
                        }
                    }
                },
                {
                    'type': 'json_keys',
                    'description': 'Object keys or array indices',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'json_keys'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'file'},
                            'file': {'type': 'string'},
                            'path': {'type': 'string'},
                            'keys': {'type': 'array', 'items': {'type': 'string'}},
                            'count': {'type': 'integer'}
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'json://package.json',
                    'description': 'View entire JSON file (pretty-printed)',
                    'output_type': 'json_value'
                },
                {
                    'uri': 'json://package.json/name',
                    'description': 'Get package name',
                    'output_type': 'json_value'
                },
                {
                    'uri': 'json://data.json/users/0',
                    'description': 'Get first user from array',
                    'output_type': 'json_value'
                },
                {
                    'uri': 'json://data.json/users[0:3]',
                    'description': 'Get first 3 users (array slice)',
                    'output_type': 'json_value'
                },
                {
                    'uri': 'json://config.json?schema',
                    'description': 'Show type structure of entire file',
                    'cli_flag': '?schema',
                    'output_type': 'json_schema'
                },
                {
                    'uri': 'json://config.json?flatten',
                    'description': 'Flatten to grep-able format (also: ?gron)',
                    'cli_flag': '?flatten',
                    'output_type': 'json_flatten'
                },
                {
                    'uri': 'json://package.json/dependencies?keys',
                    'description': 'List all dependency names',
                    'cli_flag': '?keys',
                    'output_type': 'json_keys'
                }
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for json:// adapter."""
        return {
            'name': 'json',
            'description': 'Navigate and query JSON files - path access, schema discovery, gron-style output',
            'syntax': 'json://<file>[/path/to/key][?query]',
            'path_syntax': JsonAdapter._get_path_syntax(),
            'queries': JsonAdapter._get_queries_help(),
            'examples': JsonAdapter._get_examples(),
            'features': [
                'Path navigation with dot notation support',
                'Array indexing and slicing (Python-style)',
                'Schema inference for understanding structure',
                'Gron-style flattening for grep/search workflows',
                'Type introspection at any path',
                'Array filtering with 8 operators (=, >, <, >=, <=, !=, ~=, ..)',
                'Result control (sort, limit, offset) for arrays',
                'Nested field access with dot notation (user.name)',
            ],
            'try_now': [
                "reveal json://package.json?schema",
                "reveal json://package.json/name",
                "reveal json://package.json?flatten | head -20",
            ],
            'workflows': JsonAdapter._get_workflows(),
            'anti_patterns': JsonAdapter._get_anti_patterns(),
            'operators': {
                'field=value': 'Exact match (case-insensitive for strings)',
                'field>value': 'Greater than (numeric)',
                'field<value': 'Less than (numeric)',
                'field>=value': 'Greater than or equal (numeric)',
                'field<=value': 'Less than or equal (numeric)',
                'field!=value': 'Not equal',
                'field~=pattern': 'Regex match',
                'field=min..max': 'Range (inclusive, numeric or string)',
            },
            'result_control': {
                'sort=field': 'Sort by field ascending',
                'sort=-field': 'Sort by field descending',
                'limit=N': 'Limit results to N items',
                'offset=M': 'Skip first M items (for pagination)',
            },
            'notes': [
                'Paths use / separator (like URLs)',
                'Array indices are 0-based',
                'Slices use [start:end] syntax (end exclusive)',
                'Schema shows inferred types from actual values',
                'Gron output can be piped to grep for searching',
                'Filtering applies to arrays of objects only',
                'Field names support dot notation (e.g., user.age)',
                'Result control enables pagination for large arrays',
            ],
            'output_formats': ['text', 'json'],
            'see_also': [
                'reveal file.json - Basic JSON structure view',
                'reveal help://ast - Query code as AST',
                'reveal help://tricks - Power user workflows',
            ]
        }

    def __init__(self, path: str, query_string: str = None):
        """Initialize JSON adapter.

        Args:
            path: File path, optionally with JSON path (file.json/path/to/key)
            query_string: Query parameters (schema, gron, type, keys, length, or filters)
        """
        self.query_string = query_string
        self.json_path = []
        self.slice_spec = None
        self.query_filters = []
        self.result_control = ResultControl()

        # Parse file path and JSON path
        self._parse_path(path)

        # Load JSON data
        self.data = self._load_json()

        # Parse query filters and result control
        if query_string:
            # Detect if this is a legacy query mode (single word flag)
            legacy_modes = {'schema', 'flatten', 'gron', 'type', 'keys', 'length'}
            is_legacy_mode = query_string.lower() in legacy_modes

            if not is_legacy_mode:
                # Parse result control first (removes sort/limit/offset from query)
                filter_query, self.result_control = parse_result_control(query_string)

                # Parse query filters if there's a filter query
                # (JSON adapter has no legacy filter syntax, so parse all non-legacy queries)
                if filter_query:
                    try:
                        self.query_filters = parse_query_filters(filter_query)
                    except Exception:
                        # If parsing fails, fall back to empty filters
                        self.query_filters = []

    def _parse_path(self, path: str) -> None:
        """Parse file path and JSON navigation path.

        Handles: file.json, file.json/key, file.json/arr[0:3]
        """
        # Expand ~ to home directory first
        import os
        path = os.path.expanduser(path)

        # Find the .json file boundary
        json_match = re.search(r'(.*?\.json[l]?)(/.+)?$', path, re.IGNORECASE)

        if json_match:
            self.file_path = Path(json_match.group(1))
            json_nav = json_match.group(2)

            if json_nav:
                # Parse JSON path: /key/0/subkey or /arr[0:3]
                self._parse_json_path(json_nav)
        else:
            # No .json extension found, treat entire path as file
            self.file_path = Path(path)

    def _parse_json_path(self, nav_path: str) -> None:
        """Parse JSON navigation path into components."""
        # Remove leading slash
        nav_path = nav_path.lstrip('/')

        # Check for array slice at end: key[0:3]
        slice_match = re.search(r'\[(-?\d*):(-?\d*)\]$', nav_path)
        if slice_match:
            start = int(slice_match.group(1)) if slice_match.group(1) else None
            end = int(slice_match.group(2)) if slice_match.group(2) else None
            self.slice_spec = (start, end)
            nav_path = nav_path[:slice_match.start()]

        # Check for single array index at end: key[0]
        index_match = re.search(r'\[(-?\d+)\]$', nav_path)
        if index_match and not self.slice_spec:
            # Convert [n] to path component
            nav_path = nav_path[:index_match.start()]
            if nav_path:
                self.json_path = nav_path.split('/')
            self.json_path.append(int(index_match.group(1)))
            return

        # Split path components
        if nav_path:
            for part in nav_path.split('/'):
                if part.isdigit() or (part.startswith('-') and part[1:].isdigit()):
                    self.json_path.append(int(part))
                else:
                    self.json_path.append(part)

    def _load_json(self) -> Any:
        """Load and parse JSON file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"JSON file not found: {self.file_path}")

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # Detect file type and provide helpful error message
            file_ext = self.file_path.suffix.lower()
            file_type_hints = {
                '.toml': ('TOML', 'a TOML configuration file'),
                '.yaml': ('YAML', 'a YAML file'),
                '.yml': ('YAML', 'a YAML file'),
                '.xml': ('XML', 'an XML file'),
                '.ini': ('INI', 'an INI configuration file'),
                '.cfg': ('Config', 'a configuration file'),
            }

            if file_ext in file_type_hints:
                file_type, description = file_type_hints[file_ext]
                raise ValueError(
                    f"Error: {self.file_path.name} is {description}, not JSON.\n"
                    f"Suggestion: Use 'reveal {self.file_path}' instead of 'reveal json://{self.file_path}'"
                ) from e
            else:
                raise ValueError(
                    f"Error: {self.file_path.name} is not valid JSON.\n"
                    f"Parse error at line {e.lineno}, column {e.colno}: {e.msg}\n"
                    f"Suggestion: Check file format or use 'reveal {self.file_path}' for structure analysis"
                ) from e

    def _get_field_value(self, obj: Any, field: str) -> Any:
        """Get field value from JSON object, supporting nested paths.

        Args:
            obj: JSON object (dict)
            field: Field name, supports dot notation (e.g., 'user.name')

        Returns:
            Field value or None if not found
        """
        if not isinstance(obj, dict):
            return None

        # Support nested field access with dot notation
        parts = field.split('.')
        current = obj

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        return current

    def _compare(self, field_value: Any, operator: str, target_value: str) -> bool:
        """Compare field value against target using operator.

        Uses unified compare_values() from query.py to eliminate duplication.

        Args:
            field_value: Value from JSON object
            operator: Comparison operator (=, >, <, >=, <=, !=, ~=, ..)
            target_value: Target value to compare against

        Returns:
            True if comparison passes, False otherwise
        """
        return compare_values(
            field_value,
            operator,
            target_value,
            options={
                'allow_list_any': True,
                'case_sensitive': False,
                'coerce_numeric': True,
                'none_matches_not_equal': True
            }
        )

    def _matches_all_filters(self, obj: Any) -> bool:
        """Check if object matches all query filters.

        Args:
            obj: JSON object to test

        Returns:
            True if matches all filters, False otherwise
        """
        if not self.query_filters:
            return True

        for qf in self.query_filters:
            field_value = self._get_field_value(obj, qf.field)
            if not self._compare(field_value, qf.op, qf.value):
                return False

        return True

    def _filter_array(self, arr: List[Any]) -> List[Any]:
        """Filter array elements based on query filters.

        Args:
            arr: Array to filter

        Returns:
            Filtered array
        """
        if not self.query_filters:
            return arr

        return [item for item in arr if self._matches_all_filters(item)]

    def _apply_result_control(self, arr: List[Any]) -> tuple[List[Any], Dict[str, Any]]:
        """Apply result control (sort, limit, offset) to array.

        Args:
            arr: Array to control

        Returns:
            Tuple of (controlled array, metadata dict)
        """
        metadata = {}
        total_matches = len(arr)
        controlled = arr

        # Sort
        if self.result_control.sort_field:
            try:
                field = self.result_control.sort_field
                reverse = self.result_control.sort_descending

                def sort_key(item):
                    """Extract sort key from item."""
                    value = self._get_field_value(item, field)
                    # Handle None values (sort to end)
                    if value is None:
                        return (1, '') if not reverse else (0, '')
                    return (0, value)

                controlled = sorted(controlled, key=sort_key, reverse=reverse)
            except Exception:
                # If sorting fails, continue without sorting
                pass

        # Offset
        if self.result_control.offset is not None and self.result_control.offset > 0:
            controlled = controlled[self.result_control.offset:]

        # Limit
        if self.result_control.limit is not None:
            controlled = controlled[:self.result_control.limit]

        # Add truncation warning if results were limited
        displayed = len(controlled)
        if displayed < total_matches:
            metadata['warnings'] = [{
                'type': 'truncated',
                'message': f'Results truncated: showing {displayed} of {total_matches} total matches'
            }]
            metadata['displayed_results'] = displayed
            metadata['total_matches'] = total_matches

        return controlled, metadata

    def _navigate_to_path(self, data: Any = None) -> Any:
        """Navigate to the specified JSON path."""
        if data is None:
            data = self.data

        current = data
        for key in self.json_path:
            if isinstance(current, dict):
                if str(key) not in current:
                    raise KeyError(f"Key not found: {key}")
                current = current[str(key)]
            elif isinstance(current, list):
                if not isinstance(key, int):
                    raise TypeError(f"Array index must be integer, got: {key}")
                if key >= len(current) or key < -len(current):
                    raise IndexError(f"Array index out of range: {key}")
                current = current[key]
            else:
                raise TypeError(f"Cannot navigate into {type(current).__name__}")

        # Apply slice if specified
        if self.slice_spec and isinstance(current, list):
            start, end = self.slice_spec
            current = current[start:end]

        return current

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get JSON data with optional query processing."""
        try:
            value = self._navigate_to_path()
        except (KeyError, IndexError, TypeError) as e:
            return {
                'contract_version': '1.0',
                'type': 'json_error',
                'source': str(self.file_path),
                'source_type': 'file',
                'file': str(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path),
                'error': str(e)
            }

        # Handle legacy query modes (schema, flatten, etc.)
        legacy_modes = {'schema', 'flatten', 'gron', 'type', 'keys', 'length'}
        if self.query_string and self.query_string.lower() in legacy_modes:
            return self._handle_query(value)

        # Check for unknown query (not legacy mode, no valid operators/result control)
        # Query parser treats single words as existence checks (?), which JSON adapter doesn't support
        has_only_existence_checks = (
            self.query_filters and
            all(qf.op == '?' for qf in self.query_filters)
        )
        has_no_result_control = (
            not self.result_control.sort_field and
            self.result_control.limit is None and
            (self.result_control.offset is None or self.result_control.offset == 0)
        )

        if self.query_string and (has_only_existence_checks or (not self.query_filters and has_no_result_control)):
            # Unknown query or unsupported syntax, return error
            return {
                'contract_version': '1.0',
                'type': 'json_error',
                'source': str(self.file_path),
                'source_type': 'file',
                'file': str(self.file_path),
                'error': f"Unknown query: {self.query_string}",
                'valid_queries': list(legacy_modes) + ['field=value', 'field>value', 'sort=field', 'limit=N']
            }

        # Apply filtering and result control to arrays
        metadata = {}
        has_result_control = (self.result_control.sort_field is not None or
                              self.result_control.limit is not None or
                              (self.result_control.offset is not None and self.result_control.offset > 0))

        if isinstance(value, list) and (self.query_filters or has_result_control):
            # Filter array elements
            if self.query_filters:
                value = self._filter_array(value)

            # Apply result control (sort, limit, offset)
            if has_result_control:
                value, metadata = self._apply_result_control(value)

        # Default: return the value
        result = {
            'contract_version': '1.0',
            'type': 'json_value',
            'source': str(self.file_path),
            'source_type': 'file',
            'file': str(self.file_path),
            'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
            'value_type': self._get_type_str(value),
            'value': value
        }

        # Add metadata if present
        if metadata:
            result.update(metadata)

        return result

    def _handle_query(self, value: Any) -> Dict[str, Any]:
        """Handle query parameters like ?schema, ?gron, ?type."""
        query = self.query_string.lower()

        if query == 'schema':
            return self._get_schema(value)
        elif query in ('flatten', 'gron'):  # gron is alias for flatten
            return self._get_flatten(value)
        elif query == 'type':
            return self._get_type_info(value)
        elif query == 'keys':
            return self._get_keys(value)
        elif query == 'length':
            return self._get_length(value)
        else:
            return {
                'type': 'json_error',
                'error': f"Unknown query: {query}",
                'valid_queries': ['schema', 'flatten', 'gron', 'type', 'keys', 'length']
            }

    def _get_type_str(self, value: Any) -> str:
        """Get human-readable type string for a value."""
        if value is None:
            return 'null'
        elif isinstance(value, bool):
            return 'bool'
        elif isinstance(value, int):
            return 'int'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, str):
            return 'str'
        elif isinstance(value, list):
            if not value:
                return 'Array[empty]'
            # Infer element type from first few elements
            types = set(self._get_type_str(v) for v in value[:5])
            if len(types) == 1:
                return f'Array[{types.pop()}]'
            return f'Array[mixed: {", ".join(sorted(types))}]'
        elif isinstance(value, dict):
            return f'Object[{len(value)} keys]'
        return type(value).__name__

    def _get_schema(self, value: Any, max_depth: int = 4) -> Dict[str, Any]:
        """Generate schema/type structure for value."""
        schema = self._infer_schema(value, max_depth)
        return {
            'contract_version': '1.0',
            'type': 'json_schema',
            'source': str(self.file_path),
            'source_type': 'file',
            'file': str(self.file_path),
            'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
            'schema': schema
        }

    def _infer_schema(self, value: Any, max_depth: int = 4, depth: int = 0) -> Any:
        """Recursively infer schema from value."""
        if depth > max_depth:
            return '...'

        if value is None:
            return 'null'
        elif isinstance(value, bool):
            return 'bool'
        elif isinstance(value, int):
            return 'int'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, str):
            return 'str'
        elif isinstance(value, list):
            if not value:
                return 'Array[empty]'
            # Sample first few elements to infer schema
            sample = value[:3]
            schemas = [self._infer_schema(v, max_depth, depth + 1) for v in sample]
            # Check if all same type
            if all(s == schemas[0] for s in schemas):
                return f'Array[{schemas[0]}]' if isinstance(schemas[0], str) else {'Array': schemas[0]}
            return {'Array': schemas[0]}  # Use first as representative
        elif isinstance(value, dict):
            return {k: self._infer_schema(v, max_depth, depth + 1) for k, v in value.items()}
        return type(value).__name__

    def _get_flatten(self, value: Any) -> Dict[str, Any]:
        """Generate flattened (gron-style) output for grep-able searching."""
        lines = []
        self._flatten_recursive(value, 'json', lines)
        return {
            'contract_version': '1.0',
            'type': 'json_flatten',
            'source': str(self.file_path),
            'source_type': 'file',
            'file': str(self.file_path),
            'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
            'lines': lines,
            'line_count': len(lines)
        }

    def _flatten_recursive(self, value: Any, path: str, lines: List[str]) -> None:
        """Recursively flatten JSON to assignment format."""
        if isinstance(value, dict):
            if not value:
                lines.append(f'{path} = {{}}')
            else:
                lines.append(f'{path} = {{}}')
                for k, v in value.items():
                    # Use dot notation for simple keys, bracket for complex
                    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k):
                        self._flatten_recursive(v, f'{path}.{k}', lines)
                    else:
                        self._flatten_recursive(v, f'{path}["{k}"]', lines)
        elif isinstance(value, list):
            lines.append(f'{path} = []')
            for i, v in enumerate(value):
                self._flatten_recursive(v, f'{path}[{i}]', lines)
        elif isinstance(value, str):
            lines.append(f'{path} = {json.dumps(value)}')
        elif isinstance(value, bool):
            lines.append(f'{path} = {str(value).lower()}')
        elif value is None:
            lines.append(f'{path} = null')
        else:
            lines.append(f'{path} = {value}')

    def _get_type_info(self, value: Any) -> Dict[str, Any]:
        """Get type information for value at path."""
        return {
            'contract_version': '1.0',
            'type': 'json_type',
            'source': str(self.file_path),
            'source_type': 'file',
            'file': str(self.file_path),
            'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
            'value_type': self._get_type_str(value),
            'is_container': isinstance(value, (dict, list)),
            'length': len(value) if isinstance(value, (dict, list, str)) else None
        }

    def _get_keys(self, value: Any) -> Dict[str, Any]:
        """Get keys for object or indices for array."""
        if isinstance(value, dict):
            return {
                'contract_version': '1.0',
                'type': 'json_keys',
                'source': str(self.file_path),
                'source_type': 'file',
                'file': str(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
                'keys': list(value.keys()),
                'count': len(value)
            }
        elif isinstance(value, list):
            return {
                'contract_version': '1.0',
                'type': 'json_keys',
                'source': str(self.file_path),
                'source_type': 'file',
                'file': str(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
                'indices': list(range(len(value))),
                'count': len(value)
            }
        else:
            return {
                'contract_version': '1.0',
                'type': 'json_error',
                'source': str(self.file_path),
                'source_type': 'file',
                'error': f'Cannot get keys from {type(value).__name__}'
            }

    def _get_length(self, value: Any) -> Dict[str, Any]:
        """Get length of array, object, or string."""
        if isinstance(value, (dict, list, str)):
            return {
                'contract_version': '1.0',
                'type': 'json_length',
                'source': str(self.file_path),
                'source_type': 'file',
                'file': str(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
                'length': len(value),
                'value_type': self._get_type_str(value)
            }
        else:
            return {
                'contract_version': '1.0',
                'type': 'json_error',
                'source': str(self.file_path),
                'source_type': 'file',
                'error': f'Cannot get length of {type(value).__name__}'
            }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific element by name (for direct key access)."""
        try:
            if isinstance(self.data, dict) and element_name in self.data:
                return {
                    'name': element_name,
                    'value': self.data[element_name],
                    'type': self._get_type_str(self.data[element_name])
                }
        except Exception:
            pass
        return None

    def get_metadata(self) -> Dict[str, Any]:
        """Get JSON file metadata."""
        return {
            'file': str(self.file_path),
            'exists': self.file_path.exists(),
            'size': self.file_path.stat().st_size if self.file_path.exists() else 0,
            'root_type': self._get_type_str(self.data)
        }
