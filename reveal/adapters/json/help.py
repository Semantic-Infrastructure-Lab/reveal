"""Help and schema documentation for JSON adapter."""

from typing import Dict, List, Any


def get_path_syntax() -> Dict[str, str]:
    """Path syntax documentation."""
    return {
        '/key': 'Access object key',
        '/0': 'Access array index (0-based)',
        '/key/subkey': 'Navigate nested paths',
        '/arr[0:3]': 'Array slice (first 3 elements)',
        '/arr[-1]': 'Negative index (last element)',
    }


def get_queries_help() -> Dict[str, str]:
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


def get_examples() -> List[Dict[str, str]]:
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


def get_workflows() -> List[Dict[str, Any]]:
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


def get_anti_patterns() -> List[Dict[str, str]]:
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


def get_help() -> Dict[str, Any]:
    """Get help documentation for json:// adapter."""
    return {
        'name': 'json',
        'description': 'Navigate and query JSON files - path access, schema discovery, gron-style output',
        'syntax': 'json://<file>[/path/to/key][?query]',
        'path_syntax': get_path_syntax(),
        'queries': get_queries_help(),
        'examples': get_examples(),
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
        'workflows': get_workflows(),
        'anti_patterns': get_anti_patterns(),
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
