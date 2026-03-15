"""Help and schema documentation for markdown:// adapter."""

from typing import Dict, Any


_SCHEMA_QUERY_PARAMS = {
    'aggregate=field': 'Frequency table of values for a frontmatter field. List fields (e.g. beth_topics) are expanded per item.',
    'body-contains=term': 'Case-insensitive substring search in body text (after frontmatter). Multiple body-contains= params are AND\'d.',
    'field=value': 'Exact match (or substring for list fields)',
    'field=*pattern*': 'Glob-style wildcard matching',
    '!field': 'Find files missing this field',
    'field>value': 'Numeric greater than',
    'field<value': 'Numeric less than',
    'field>=value': 'Numeric greater than or equal',
    'field<=value': 'Numeric less than or equal',
    'field!=value': 'Not equal',
    'field~=pattern': 'Regex matching',
    'field=min..max': 'Numeric range (inclusive)',
    'sort=field': 'Sort results by field',
    'sort=-field': 'Sort descending',
    'limit=N': 'Limit results to N',
    'offset=M': 'Skip first M results'
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'markdown_aggregate',
        'description': 'Frequency table of frontmatter field values across matched files',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'markdown_aggregate'},
                'field': {'type': 'string'},
                'source': {'type': 'string'},
                'total_files': {'type': 'integer'},
                'matched_files': {'type': 'integer'},
                'files_missing_field': {'type': 'integer'},
                'aggregate': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'value': {'type': 'string'},
                            'count': {'type': 'integer'},
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'markdown_query',
        'description': 'List of markdown files matching query filters',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'markdown_query'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'base_path': {'type': 'string'},
                'query': {'type': 'string'},
                'total_files': {'type': 'integer'},
                'matched_files': {'type': 'integer'},
                'results': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'path': {'type': 'string'},
                            'relative_path': {'type': 'string'},
                            'has_frontmatter': {'type': 'boolean'},
                            'title': {'type': 'string'},
                            'type': {'type': 'string'},
                            'status': {'type': 'string'},
                            'tags': {'type': 'array'},
                            'topics': {'type': 'array'}
                        }
                    }
                }
            }
        }
    }
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'markdown://',
        'description': 'List all markdown files in current directory',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://docs/',
        'description': 'List all markdown files in docs/ directory',
        'path': 'docs/',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://sessions/?topics=reveal',
        'description': 'Find files where topics contains "reveal"',
        'path': 'sessions/',
        'cli_flag': '?topics=reveal',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://docs/?tags=python&status=active',
        'description': 'Multiple filters (AND logic)',
        'cli_flag': '?tags=python&status=active',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://?!topics',
        'description': 'Find files missing topics field',
        'cli_flag': '?!topics',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://?type=*guide*',
        'description': 'Wildcard matching (glob-style)',
        'cli_flag': '?type=*guide*',
        'output_type': 'markdown_query'
    },
    {
        'uri': "markdown://docs/?body-contains=nginx",
        'description': 'Body text search — files whose body mentions "nginx"',
        'cli_flag': '?body-contains=nginx',
        'output_type': 'markdown_query'
    },
    {
        'uri': "markdown://docs/?body-contains=nginx&body-contains=ssl",
        'description': 'Body text search — AND logic, both terms must appear',
        'cli_flag': '?body-contains=nginx&body-contains=ssl',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://docs/?aggregate=type',
        'description': 'Frequency table of "type" field values across all docs',
        'cli_flag': '?aggregate=type',
        'output_type': 'markdown_aggregate'
    },
    {
        'uri': 'markdown://sessions/?aggregate=beth_topics',
        'description': 'Topic distribution — list fields expanded per item',
        'cli_flag': '?aggregate=beth_topics',
        'output_type': 'markdown_aggregate'
    }
]

_HELP_EXAMPLES = [
    {'uri': 'markdown://', 'description': 'List all markdown files in current directory'},
    {'uri': 'markdown://docs/', 'description': 'List all markdown files in docs/ directory'},
    {'uri': 'markdown://sessions/?topics=reveal', 'description': 'Find files where topics contains "reveal"'},
    {'uri': 'markdown://docs/?tags=python&status=active', 'description': 'Multiple filters (AND logic)'},
    {'uri': 'markdown://?!topics', 'description': 'Find files missing topics field'},
    {'uri': 'markdown://?type=*guide*', 'description': 'Wildcard matching (glob-style)'},
    {'uri': 'markdown://?priority>10', 'description': 'Numeric comparison (greater than)'},
    {'uri': 'markdown://?priority=5..15', 'description': 'Numeric range (5 to 15 inclusive)'},
    {'uri': 'markdown://?title~=^API', 'description': 'Regex matching (titles starting with "API")'},
    {'uri': 'markdown://?sort=-priority', 'description': 'Sort by priority descending'},
    {'uri': 'markdown://?priority>5&sort=-priority&limit=10', 'description': 'Filter, sort, and limit results'},
    {'uri': 'markdown://docs/?status=active --format=json', 'description': 'JSON output for scripting'},
    {'uri': "markdown://docs/?body-contains=nginx", 'description': 'Find docs whose body mentions nginx (case-insensitive)'},
    {'uri': "markdown://docs/?type=guide&body-contains=nginx&limit=5", 'description': 'Combine body text search with frontmatter filter and limit'},
]

_HELP_WORKFLOWS = [
    {
        'name': 'Find Undocumented Files',
        'scenario': 'Identify files missing required metadata',
        'steps': [
            "reveal markdown://?!topics      # Missing topics",
            "reveal markdown://?!status           # Missing status",
        ],
    },
    {
        'name': 'Explore Knowledge Graph',
        'scenario': 'Find and traverse related documents',
        'steps': [
            "reveal markdown://sessions/?topics=reveal",
            "reveal <found-file> --related-all    # Follow links",
        ],
    },
]


def get_schema() -> Dict[str, Any]:
    """Get machine-readable schema for markdown:// adapter.

    Returns JSON schema for AI agent integration.
    """
    return {
        'adapter': 'markdown',
        'description': 'Query markdown files by frontmatter fields (exact match, wildcards, missing fields) and body text',
        'uri_syntax': 'markdown://[path/]?[filters]',
        'query_params': _SCHEMA_QUERY_PARAMS,
        'supports_batch': True,
        'supports_advanced': True,
        'output_types': _SCHEMA_OUTPUT_TYPES,
        'notes': [
            'Searches recursively in the specified directory (or current dir if omitted)',
            'body-contains= searches body text after frontmatter; multiple values are AND\'d',
            '!field finds files missing a specific frontmatter field — useful for doc quality audits',
            'List fields match if any item in the list matches (e.g., tags=python matches [python, web])',
            'All filter conditions are AND\'d; OR logic across different fields is not supported',
            'Numeric comparisons (>, <, >=, <=, ..) require numeric frontmatter field values',
            'Files without frontmatter are included in results unless a frontmatter filter is applied',
        ],
        'example_queries': _SCHEMA_EXAMPLE_QUERIES
    }


def get_help() -> Dict[str, Any]:
    """Get help documentation for markdown:// adapter."""
    return {
        'name': 'markdown',
        'description': 'Query markdown files by front matter fields',
        'syntax': 'markdown://[path/]?[field=value][&field2=value2]',
        'examples': _HELP_EXAMPLES,
        'features': [
            'Recursive directory traversal',
            'Body text search: body-contains=term (case-insensitive substring, AND across multiple)',
            'Exact match: field=value',
            'Wildcard match: field=*pattern* (glob-style)',
            'Missing field: !field',
            'Numeric comparisons: field>value, field<value, field>=value, field<=value',
            'Range queries: field=min..max',
            'Regex matching: field~=pattern',
            'List fields: matches if value in list',
            'Multiple filters: field1=val1&field2=val2 (AND)',
            'Result control: sort=field, sort=-field (descending)',
            'Pagination: limit=N, offset=M',
            'JSON output for tooling integration',
        ],
        'operators': {
            'field=value': 'Exact match (or substring for lists)',
            'field>value': 'Greater than (numeric)',
            'field<value': 'Less than (numeric)',
            'field>=value': 'Greater than or equal (numeric)',
            'field<=value': 'Less than or equal (numeric)',
            'field!=value': 'Not equal',
            'field~=pattern': 'Regex match',
            'field=min..max': 'Range (inclusive)',
            'field=*pattern*': 'Glob-style wildcard',
            '!field': 'Field is missing',
        },
        'result_control': {
            'sort=field': 'Sort results by field (ascending)',
            'sort=-field': 'Sort results by field (descending)',
            'limit=N': 'Limit to N results',
            'offset=M': 'Skip first M results',
        },
        'notes': [
            'Searches recursively in specified directory',
            'body-contains= searches text after frontmatter (body), not frontmatter fields',
            'body-contains= is case-insensitive; multiple values are AND\'d',
            'body-contains= matches files without frontmatter too',
            'Only frontmatter fields require valid YAML frontmatter to filter',
            'Field values in lists are matched if any item matches',
            'Numeric comparisons work on numeric frontmatter fields',
            'Use sort/limit/offset for pagination and result control',
            'Combine with reveal --related for graph exploration',
        ],
        'try_now': [
            'reveal markdown://',
            'reveal markdown://?!title',
        ],
        'workflows': _HELP_WORKFLOWS,
        'output_formats': ['text', 'json', 'grep'],
        'see_also': [
            'reveal file.md --related - Follow related documents',
            'reveal file.md --frontmatter - Show frontmatter',
            'reveal help://knowledge-graph - Knowledge graph guide',
        ]
    }
