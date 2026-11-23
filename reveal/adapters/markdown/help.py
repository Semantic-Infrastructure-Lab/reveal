"""Help and schema documentation for the markdown noun (reveal markdown DIR; markdown://DIR takes the same flags)."""

from typing import Dict, Any

from ...utils.query_parser import param_schema
from .params import PARAM_SPECS



_SOURCE_ANALYSIS_SCHEMA = {
    'type': 'object',
    'description': 'Required source decisions before filtering, aggregation or pagination.',
    'required': ['candidate_files', 'analyzed_files', 'failed_files', 'discovery_failures'],
    'properties': {
        'candidate_files': {'type': 'integer', 'minimum': 0},
        'analyzed_files': {'type': 'integer', 'minimum': 0},
        'failed_files': {'type': 'integer', 'minimum': 0},
        'discovery_failures': {'type': 'integer', 'minimum': 0},
    },
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
                'analysis': _SOURCE_ANALYSIS_SCHEMA,
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
                'orphans': {'type': 'array', 'items': {'type': 'string'},
                            'description': 'Docs no other doc links to (isolated ones included)'},
                'isolated': {'type': 'array', 'items': {'type': 'string'},
                             'description': 'Docs with no link in or out'},
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
                'analysis': _SOURCE_ANALYSIS_SCHEMA,
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
                            'relevance_score': {'type': 'integer', 'description': 'Present when --match is given; higher = stronger match'},
                            'relevance_explain': {
                                'type': 'object',
                                'description': 'Present only with --explain — per-term score breakdown',
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
        'uri': 'markdown://.',
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
        'uri': 'markdown://sessions/ --where topics=reveal',
        'description': 'Find files where topics contains "reveal"',
        'path': 'sessions/',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://docs/ --where tags=python --where status=active',
        'description': 'Multiple filters (AND logic)',
        'output_type': 'markdown_query'
    },
    {
        'uri': "markdown://. --where '!topics'",
        'description': 'Find files missing topics field',
        'output_type': 'markdown_query'
    },
    {
        'uri': "markdown://. --where 'type=*guide*'",
        'description': 'Wildcard matching (case-insensitive)',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://docs/ --match nginx',
        'description': 'Body text search — files whose body mentions "nginx"',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://docs/ --match nginx --match ssl',
        'description': 'Body text search — AND logic, both terms must appear',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://docs/ --match authentication --explain',
        'description': 'Ranked body text search — best match first, with a per-term score breakdown',
        'output_type': 'markdown_query'
    },
    {
        'uri': 'markdown://docs/ --view aggregate --field type',
        'description': 'Frequency table of "type" field values across all docs',
        'output_type': 'markdown_aggregate'
    },
    {
        'uri': 'markdown://sessions/ --view aggregate --field beth_topics',
        'description': 'Topic distribution — list fields expanded per item',
        'output_type': 'markdown_aggregate'
    },
    {
        'uri': 'markdown://docs/ --view links',
        'description': 'Bidirectional link graph for every doc — forward links, backlinks, orphans',
        'output_type': 'markdown_link_graph'
    },
    {
        'uri': 'markdown://docs/ --backlinks auth.md',
        'description': 'Who links to auth.md — pre-edit staleness check before renaming/restructuring',
        'output_type': 'markdown_backlinks'
    },
    {
        'uri': 'markdown://docs/ --view lint',
        'description': 'Maintenance queue: malformed YAML frontmatter and files with no frontmatter at all',
        'output_type': 'markdown_frontmatter_lint'
    },
    {
        'uri': 'markdown://docs/ --view lint --lint-fields title,type',
        'description': 'Same lint queue, also flagging files missing required frontmatter fields',
        'output_type': 'markdown_frontmatter_lint'
    }
]

_HELP_EXAMPLES = [
    {'uri': 'reveal markdown', 'description': 'List all markdown files in current directory'},
    {'uri': 'reveal markdown docs/', 'description': 'List all markdown files in docs/ directory'},
    {'uri': 'reveal markdown sessions/ --where topics=reveal', 'description': 'Find files where topics contains "reveal"'},
    {'uri': 'reveal markdown docs/ --where tags=python --where status=active', 'description': 'Multiple filters (AND logic)'},
    {'uri': "reveal markdown --where '!topics'", 'description': 'Find files missing topics field'},
    {'uri': "reveal markdown --where 'type=*guide*'", 'description': 'Wildcard matching (case-insensitive)'},
    {'uri': "reveal markdown --where 'priority>10'", 'description': 'Numeric comparison (greater than)'},
    {'uri': 'reveal markdown --where priority=5..15', 'description': 'Numeric range (5 to 15 inclusive)'},
    {'uri': "reveal markdown --where 'title~=^API'", 'description': 'Regex matching (titles starting with "API")'},
    {'uri': 'reveal markdown --sort=-priority', 'description': 'Sort by priority descending'},
    {'uri': "reveal markdown --where 'priority>5' --sort=-priority --limit 10", 'description': 'Filter, sort, and limit results'},
    {'uri': 'reveal markdown docs/ --where status=active --format json', 'description': 'JSON output for scripting'},
    {'uri': 'reveal markdown docs/ --match nginx', 'description': 'Find docs whose body mentions nginx (case-insensitive)'},
    {'uri': 'reveal markdown docs/ --where type=guide --match nginx --limit 5', 'description': 'Combine body text search with frontmatter filter and limit'},
    {'uri': 'reveal markdown docs/ --match authentication --explain', 'description': 'Ranked multi-doc search — best match first, plus a score breakdown per hit'},
    {'uri': 'reveal markdown docs/ --view links', 'description': 'Bidirectional link graph for every doc — forward links, backlinks, orphans'},
    {'uri': 'reveal markdown docs/ --backlinks auth.md', 'description': 'Who links to auth.md — pre-edit staleness check before renaming/restructuring'},
    {'uri': 'reveal markdown docs/ --view lint', 'description': 'Frontmatter maintenance queue — malformed YAML and files with no frontmatter, as one list'},
    {'uri': 'reveal markdown docs/ --view lint --lint-fields title,type', 'description': 'Lint queue, also flagging files missing required frontmatter fields'},
]

_HELP_WORKFLOWS = [
    {
        'name': 'Find Undocumented Files',
        'scenario': 'Identify files missing required metadata',
        'steps': [
            "reveal markdown . --where '!topics'      # Missing topics",
            "reveal markdown . --where '!status'      # Missing status",
        ],
    },
    {
        'name': 'Explore Knowledge Graph',
        'scenario': 'Find and traverse related documents',
        'steps': [
            "reveal markdown sessions/ --where topics=reveal",
            "reveal <found-file> --related-all    # Follow links",
        ],
    },
    {
        'name': 'Pre-Edit Staleness Check',
        'scenario': 'About to rename or restructure a doc — see who references it first',
        'steps': [
            "reveal markdown docs/ --backlinks auth.md   # Who links to this doc",
        ],
    },
]


# The --where operators (values of where, parsed by the shared filter parser; ruling Q6).
_WHERE_OPERATORS = {
    'field=value': 'Equal, case-insensitive (a list field matches when one item is equal)',
    'field>value': 'Greater than (numeric)',
    'field<value': 'Less than (numeric)',
    'field>=value': 'Greater than or equal (numeric)',
    'field<=value': 'Less than or equal (numeric)',
    'field!=value': 'Not equal',
    'field~=pattern': 'Regex match',
    'field=min..max': 'Range (inclusive)',
    'field=*pattern*': 'Wildcard: * is any run of characters, case-insensitive',
    'field': 'Field is present and not empty',
    '!field': 'Field is missing',
}


def get_schema() -> Dict[str, Any]:
    """Get machine-readable schema for markdown:// adapter.

    Returns JSON schema for AI agent integration.
    """
    return {
        'adapter': 'markdown',
        'description': 'Query markdown files by frontmatter fields (exact match, wildcards, missing fields) and body text',
        'uri_syntax': ('markdown://[path/] [--where EXPR]... [--match TERM]... [--view list|links|aggregate|lint] '
                       '[--field FIELD] [--backlinks DOC] [--lint-fields A,B] [--columns A,B] [--explain] [--sort [-]FIELD] '
                       '[--limit N] [--offset N]'),
        'query_params': param_schema(PARAM_SPECS),
        'where_operators': _WHERE_OPERATORS,
        'supports_batch': True,
        'supports_advanced': True,
        'output_types': _SCHEMA_OUTPUT_TYPES,
        'notes': [
            'Searches recursively in the specified directory (or current dir if omitted)',
            '--match searches body text after frontmatter; repeated terms are AND\'d',
            'Direct directory queries in every view exit 0 when complete, 2 for invalid requests, and 3 for required source/output loss; partial results and source-decision counts survive.',
            "--where '!field' finds files missing a specific frontmatter field — useful for doc quality audits",
            'List fields match if any item in the list matches (e.g., --where tags=python matches [python, web])',
            'All filter conditions are AND\'d; OR logic across different fields is not supported',
            'Numeric comparisons (>, <, >=, <=, ..) require numeric frontmatter field values',
            'Files without frontmatter are included in results unless a frontmatter filter is applied',
        ],
        'example_queries': _SCHEMA_EXAMPLE_QUERIES
    }


def get_help() -> Dict[str, Any]:
    """Get help documentation for the markdown noun."""
    return {
        'name': 'markdown',
        'description': 'Query markdown files by front matter and body text; backlinks, link graph, front-matter lint',
        'syntax': ('reveal markdown [path/] [--where EXPR]... [--match TERM]... [--view list|links|aggregate|lint] '
                   '[--field FIELD] [--backlinks DOC] [--lint-fields A,B] [--columns A,B] [--explain] [--sort [-]FIELD] '
                   '[--limit N] [--offset N]'),
        'examples': _HELP_EXAMPLES,
        'features': [
            'Recursive directory traversal',
            'Body text search: --match TERM (case-insensitive substring; repeat for AND)',
            'Ranked search: a multi-doc --match sorts best-first by relevance_score; add --explain for a score breakdown',
            'Link graph: --view links; who links to one doc: --backlinks DOC',
            'Frequency table: --view aggregate --field FIELD (list fields counted per item)',
            'Frontmatter lint: --view lint surfaces malformed YAML and missing frontmatter as one list; add --lint-fields f1,f2 to also flag missing required fields',
            'Equality: --where field=value (case-insensitive)',
            "Wildcard match: --where 'field=*pattern*' (* is any run of characters, case-insensitive)",
            "Missing field: --where '!field'",
            "Numeric comparisons: --where 'field>value' (also <, >=, <=)",
            'Range queries: --where field=min..max',
            "Regex matching: --where 'field~=pattern'",
            'List fields: matches if value in list',
            'Existence: --where field (the field is present and not empty)',
            'Multiple filters: repeat --where (AND)',
            'Result control: --sort field, --sort=-field (descending)',
            'Pagination: --limit N, --offset M',
            'JSON output for tooling integration',
        ],
        'operators': _WHERE_OPERATORS,
        'result_control': {
            '--sort FIELD': 'Sort results by a row or front-matter field (ascending)',
            '--sort=-FIELD': 'Sort results by field (descending)',
            '--limit N': 'Limit to N results (0 = no cap)',
            '--offset M': 'Skip first M results',
        },
        'notes': [
            'Searches recursively in specified directory',
            '--match searches text after frontmatter (body), not frontmatter fields',
            '--match is case-insensitive; repeated terms are AND\'d',
            '--match matches files without frontmatter too',
            '--match results are ranked by relevance_score (term frequency + heading boost) unless --sort overrides it; --explain adds the term_counts/heading_hits breakdown (it needs --match)',
            'All direct directory-query views report required source decisions before selection or paging. Complete empty answers succeed; required source/output loss exits 3, with partial evidence retained.',
            'Aggregate matched/missing-field counts exclude unreadable files; readable missing or malformed frontmatter keeps its existing missing-field meaning.',
            '--view lint distinguishes malformed YAML from "no frontmatter at all" — extract_frontmatter() collapses both to None, lint tells you which',
            'Only frontmatter fields require valid YAML frontmatter to filter',
            'Field values in lists are matched if any item matches',
            'Numeric comparisons work on numeric frontmatter fields',
            'Use --sort/--limit/--offset for pagination and result control',
            'Combine with reveal --related for graph exploration',
        ],
        'try_now': [
            'reveal markdown .',
            "reveal markdown . --where '!title'",
        ],
        'workflows': _HELP_WORKFLOWS,
        'output_formats': ['text', 'json', 'grep'],
        'see_also': [
            'reveal file.md --related - Follow related documents',
            'reveal file.md --frontmatter - Show frontmatter',
        ]
    }
