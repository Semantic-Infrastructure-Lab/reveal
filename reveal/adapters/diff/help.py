"""Help and schema documentation for diff adapter."""

from typing import Dict, Any
from ..help_data import load_help_data

_SCHEMA_COMPARISON_TYPES = [
    'File to file comparison',
    'Environment to environment comparison',
    'Database schema drift detection',
    'Configuration comparison',
    'Element-specific diff (functions, classes, etc.)'
]

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'diff_comparison',
        'description': 'Comparison result showing differences between resources',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'diff_comparison'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string', 'const': 'runtime'},
                'left': {'type': 'object', 'properties': {'uri': {'type': 'string'}, 'type': {'type': 'string'}}},
                'right': {'type': 'object', 'properties': {'uri': {'type': 'string'}, 'type': {'type': 'string'}}},
                'summary': {
                    'type': 'object',
                    'properties': {
                        'added': {'type': 'integer'},
                        'removed': {'type': 'integer'},
                        'modified': {'type': 'integer'},
                        'unchanged': {'type': 'integer'}
                    }
                },
                'diff_lines': {'type': 'array'}
            }
        },
        'example': {
            'contract_version': '1.0',
            'type': 'diff_comparison',
            'source': 'diff://app.py:backup/app.py',
            'source_type': 'runtime',
            'left': {'uri': 'app.py', 'type': 'file'},
            'right': {'uri': 'backup/app.py', 'type': 'file'},
            'summary': {'added': 5, 'removed': 3, 'modified': 2, 'unchanged': 100}
        }
    }
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'diff://app.py:backup/app.py', 'description': 'Compare two files', 'output_type': 'diff_comparison'},
    {
        'uri': 'diff://app.py:git://app.py@HEAD~1',
        'description': 'Compare current file to git version (1 commit ago)',
        'output_type': 'diff_comparison',
        'note': 'Git URIs use path@ref format, not ref:path'
    },
    {'uri': 'diff://git://app.py@main:git://app.py@develop', 'description': 'Compare file across two git branches', 'output_type': 'diff_comparison'},
    {'uri': 'diff://env://:env://production', 'description': 'Compare local environment to production', 'output_type': 'diff_comparison'},
    {'uri': 'diff://mysql://prod/db:mysql://staging/db', 'description': 'Database schema drift detection', 'output_type': 'diff_comparison'},
    {
        'uri': 'diff://app.py:old.py/handle_request',
        'description': 'Compare specific function across versions',
        'element': 'handle_request',
        'output_type': 'diff_comparison'
    }
]

_SCHEMA_NOTES = [
    'Supports any two reveal URIs that resolve to comparable structures',
    'Automatically detects resource types and adapts comparison strategy',
    'Element-specific diffs extract and compare individual functions/classes',
    'Works with files, databases, environments, and other adapters',
    'Git URIs use path@ref format: git://file.py@HEAD~1 (not git://HEAD~1:file.py)',
    'Git ref format matches git adapter syntax, not git CLI show command'
]


def get_schema() -> Dict[str, Any]:
    """Get machine-readable schema for diff:// adapter.

    Returns JSON schema for AI agent integration.
    """
    return {
        'adapter': 'diff',
        'description': 'Compare two reveal-compatible resources to detect changes, schema drift, or configuration differences',
        'uri_syntax': 'diff://<left-uri>:<right-uri>[/element]',
        'query_params': {},
        'elements': {},
        'cli_flags': [],
        'supports_batch': False,
        'supports_advanced': False,
        'comparison_types': _SCHEMA_COMPARISON_TYPES,
        'output_types': _SCHEMA_OUTPUT_TYPES,
        'example_queries': _SCHEMA_EXAMPLE_QUERIES,
        'notes': _SCHEMA_NOTES,
    }


def get_help() -> Dict[str, Any]:
    """Get help documentation for diff:// adapter.

    Help data loaded from reveal/adapters/help_data/diff.yaml
    to reduce function complexity.
    """
    return load_help_data('diff') or {}
