"""JSON navigation adapter (json://)."""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from .base import ResourceAdapter, register_adapter


@register_adapter('json')
class JsonAdapter(ResourceAdapter):
    """Adapter for navigating and querying JSON files via json:// URIs.

    Provides path navigation, schema discovery, and gron-style flattening
    for JSON files - complementing the basic .json file handler.
    """

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for json:// adapter."""
        return {
            'name': 'json',
            'description': 'Navigate and query JSON files - path access, schema discovery, gron-style output',
            'syntax': 'json://<file>[/path/to/key][?query]',
            'path_syntax': {
                '/key': 'Access object key',
                '/0': 'Access array index (0-based)',
                '/key/subkey': 'Navigate nested paths',
                '/arr[0:3]': 'Array slice (first 3 elements)',
                '/arr[-1]': 'Negative index (last element)',
            },
            'queries': {
                'schema': 'Show type structure of data',
                'flatten': 'Flatten to grep-able lines (gron-style output)',
                'gron': 'Alias for flatten (named after github.com/tomnomnom/gron)',
                'type': 'Show type at current path',
                'keys': 'List keys (objects) or length (arrays)',
                'length': 'Get array/string length or object key count',
            },
            'examples': [
                {
                    'uri': 'json://package.json',
                    'description': 'View entire JSON file (pretty-printed)'
                },
                {
                    'uri': 'json://package.json/name',
                    'description': 'Get package name'
                },
                {
                    'uri': 'json://package.json/scripts',
                    'description': 'Get all scripts'
                },
                {
                    'uri': 'json://data.json/users/0',
                    'description': 'Get first user from array'
                },
                {
                    'uri': 'json://data.json/users[0:3]',
                    'description': 'Get first 3 users (array slice)'
                },
                {
                    'uri': 'json://config.json?schema',
                    'description': 'Show type structure of entire file'
                },
                {
                    'uri': 'json://data.json/users?schema',
                    'description': 'Show schema of users array'
                },
                {
                    'uri': 'json://config.json?flatten',
                    'description': 'Flatten to grep-able format (also: ?gron)'
                },
                {
                    'uri': 'json://data.json/users?type',
                    'description': 'Get type at path (e.g., Array[Object])'
                },
                {
                    'uri': 'json://package.json/dependencies?keys',
                    'description': 'List all dependency names'
                },
            ],
            'features': [
                'Path navigation with dot notation support',
                'Array indexing and slicing (Python-style)',
                'Schema inference for understanding structure',
                'Gron-style flattening for grep/search workflows',
                'Type introspection at any path',
            ],
            # Executable examples (assumes package.json exists)
            'try_now': [
                "reveal json://package.json?schema",
                "reveal json://package.json/name",
                "reveal json://package.json?flatten | head -20",
            ],
            # Scenario-based workflow patterns
            'workflows': [
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
            ],
            # What NOT to do
            'anti_patterns': [
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
            ],
            'notes': [
                'Paths use / separator (like URLs)',
                'Array indices are 0-based',
                'Slices use [start:end] syntax (end exclusive)',
                'Schema shows inferred types from actual values',
                'Gron output can be piped to grep for searching',
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
            query_string: Query parameters (schema, gron, type, keys, length)
        """
        self.query_string = query_string
        self.json_path = []
        self.slice_spec = None

        # Parse file path and JSON path
        self._parse_path(path)

        # Load JSON data
        self.data = self._load_json()

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

        with open(self.file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

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
                'type': 'json-error',
                'file': str(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path),
                'error': str(e)
            }

        # Handle query parameters
        if self.query_string:
            return self._handle_query(value)

        # Default: return the value
        return {
            'type': 'json-value',
            'file': str(self.file_path),
            'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
            'value_type': self._get_type_str(value),
            'value': value
        }

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
                'type': 'json-error',
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
            'type': 'json-schema',
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
            'type': 'json-flatten',
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
            'type': 'json-type',
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
                'type': 'json-keys',
                'file': str(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
                'keys': list(value.keys()),
                'count': len(value)
            }
        elif isinstance(value, list):
            return {
                'type': 'json-keys',
                'file': str(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
                'indices': list(range(len(value))),
                'count': len(value)
            }
        else:
            return {
                'type': 'json-error',
                'error': f'Cannot get keys from {type(value).__name__}'
            }

    def _get_length(self, value: Any) -> Dict[str, Any]:
        """Get length of array, object, or string."""
        if isinstance(value, (dict, list, str)):
            return {
                'type': 'json-length',
                'file': str(self.file_path),
                'path': '/'.join(str(p) for p in self.json_path) if self.json_path else '(root)',
                'length': len(value),
                'value_type': self._get_type_str(value)
            }
        else:
            return {
                'type': 'json-error',
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
