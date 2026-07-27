"""Help and schema documentation for markdown:// adapter."""

from typing import Dict, Any


_SCHEMA_QUERY_PARAMS = {
    'link-graph': 'Bidirectional cross-file link graph for every doc in the tree (forward links + backlinks + orphans).',
    'backlinks=path': 'Who links to a single doc (relative path or bare filename) — cheaper than link-graph for a pre-edit staleness check on one file.',
    'aggregate=field': 'Frequency table of values for a frontmatter field. List fields (e.g. beth_topics) are expanded per item.',
    'body-contains=term': 'Case-insensitive substring search in body text (after frontmatter). Multiple body-contains= params are AND\'d. Results rank best-first by relevance_score unless sort= is given.',
    'explain': 'With body-contains=, add a per-term score breakdown (term_counts, heading_hits) to each result alongside relevance_score.',
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
    'offset=M': 'Skip first M results',
    'fields=f1,f2': 'Append additional frontmatter fields as columns in listing output (e.g. fields=book,cohort)',
    'lint': 'Frontmatter maintenance queue: malformed YAML, missing frontmatter, and (with lint-fields=) missing required fields — one list, not one-file-at-a-time.',
    'lint-fields=f1,f2': 'With ?lint, also flag files whose frontmatter is missing any of these field names.',
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
        'type': 'markdown_link_graph',
        'description': 'Bidirectional cross-file link graph for every doc in the tree',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'markdown_link_graph'},
                'source': {'type': 'string'},
                'total_files': {'type': 'integer'},
                'total_edges': {'type': 'integer'},
                'nodes': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'links_to': {'type': 'array', 'items': {'type': 'string'}},
                            'linked_by': {'type': 'array', 'items': {'type': 'string'}},
                        }
                    }
                },
                'isolated': {'type': 'array', 'items': {'type': 'string'}},
            }
        }
    },
    {
        'type': 'markdown_backlinks',
        'description': 'Who links to a single target doc, plus what that doc links to',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'markdown_backlinks'},
                'source': {'type': 'string'},
                'target': {'type': 'string'},
                'found': {'type': 'boolean'},
                'linked_by': {'type': 'array', 'items': {'type': 'string'}},
                'links_to': {'type': 'array', 'items': {'type': 'string'}},
                'ambiguous': {'type': 'boolean'},
                'candidates': {'type': 'array', 'items': {'type': 'string'}},
                'total_files': {'type': 'integer'},
            }
        }
    },
    {
        'type': 'markdown_frontmatter_lint',
        'description': 'Frontmatter maintenance queue: malformed YAML, no frontmatter, missing required fields',
        'schema': {
            'type': 'object',
            'properties': {
                'type': {'type': 'string', 'const': 'markdown_frontmatter_lint'},
                'source': {'type': 'string'},
                'total_files': {'type': 'integer'},
                'issues_found': {'type': 'integer'},
                'issues': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'issue': {'type': 'string', 'enum': ['no_frontmatter', 'malformed_yaml', 'missing_fields']},
                            'detail': {'description': 'YAML parse error string (malformed_yaml), list of field names (missing_fields), or null (no_frontmatter)'},
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
                            'topics': {'type': 'array'},
                            'relevance_score': {'type': 'integer', 'description': 'Present when body-contains= is used; higher = stronger match'},
                            'relevance_explain': {
                                'type': 'object',
                                'description': 'Present only with ?explain — per-term score breakdown',
                                'properties': {
                                    'term_counts': {'type': 'object'},
                                    'heading_hits': {'type': 'object'},
                                }
                            }
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
        'uri': "markdown://docs/?body-contains=authentication&explain",
        'description': 'Ranked body text search — best match first, with a per-term score breakdown',
        'cli_flag': '?body-contains=authentication&explain',
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
    },
    {
        'uri': 'markdown://docs/?link-graph',
        'description': 'Bidirectional link graph for every doc — forward links, backlinks, orphans',
        'cli_flag': '?link-graph',
        'output_type': 'markdown_link_graph'
    },
    {
        'uri': 'markdown://docs/?backlinks=auth.md',
        'description': 'Who links to auth.md — pre-edit staleness check before renaming/restructuring',
        'cli_flag': '?backlinks=auth.md',
        'output_type': 'markdown_backlinks'
    },
    {
        'uri': 'markdown://docs/?lint',
        'description': 'Maintenance queue: malformed YAML frontmatter and files with no frontmatter at all',
        'cli_flag': '?lint',
        'output_type': 'markdown_frontmatter_lint'
    },
    {
        'uri': 'markdown://docs/?lint&lint-fields=title,type',
        'description': 'Same lint queue, also flagging files missing required frontmatter fields',
        'cli_flag': '?lint&lint-fields=title,type',
        'output_type': 'markdown_frontmatter_lint'
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
    {'uri': "markdown://docs/?body-contains=authentication&explain", 'description': 'Ranked multi-doc search — best match first, plus a score breakdown per hit'},
    {'uri': 'markdown://docs/?link-graph', 'description': 'Bidirectional link graph for every doc — forward links, backlinks, orphans'},
    {'uri': 'markdown://docs/?backlinks=auth.md', 'description': 'Who links to auth.md — pre-edit staleness check before renaming/restructuring'},
    {'uri': 'markdown://docs/?lint', 'description': 'Frontmatter maintenance queue — malformed YAML and files with no frontmatter, as one list'},
    {'uri': 'markdown://docs/?lint&lint-fields=title,type', 'description': 'Lint queue, also flagging files missing required frontmatter fields'},
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
    {
        'name': 'Pre-Edit Staleness Check',
        'scenario': 'About to rename or restructure a doc — see who references it first',
        'steps': [
            "reveal 'markdown://docs/?backlinks=auth.md'   # Who links to this doc",
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
            'Ranked search: multi-doc body-contains results sort best-first by relevance_score; add ?explain for a score breakdown',
            'Frontmatter lint: ?lint surfaces malformed YAML and missing frontmatter as one list; add &lint-fields=f1,f2 to also flag missing required fields',
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
            'body-contains= results are ranked by relevance_score (term frequency + heading boost) unless sort= overrides it; add ?explain for the term_counts/heading_hits breakdown',
            '?lint distinguishes malformed YAML from "no frontmatter at all" — extract_frontmatter() collapses both to None, lint tells you which',
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
