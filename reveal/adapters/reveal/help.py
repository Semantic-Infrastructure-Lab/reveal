"""Help and schema documentation for reveal:// adapter."""

from typing import Dict, Any


def get_schema() -> Dict[str, Any]:
    """Get machine-readable schema for reveal:// adapter.

    Returns JSON schema for AI agent integration.
    """
    return {
        'adapter': 'reveal',
        'description': 'Self-inspection of reveal\'s own codebase and configuration with validation rules',
        'uri_syntax': 'reveal://[path][/element]',
        'query_params': {},  # No query parameters
        'elements': {
            'config': 'Active configuration with sources and precedence',
            'analyzers': 'List all registered analyzers',
            'rules': 'List all available validation rules',
            'adapters': 'List all registered adapters'
        },
        'cli_flags': [
            '--check',  # Run validation rules
            '--select=<rules>',  # Select specific rules (e.g., V001,V002)
            '--only-failures'  # Show only failed checks
        ],
        'supports_batch': False,
        'supports_advanced': False,
        'validation_rules': {
            'V001': 'Help documentation completeness',
            'V002': 'Analyzer registration validation',
            'V003': 'Feature matrix coverage',
            'V004': 'Test coverage gaps',
            'V005': 'Static help file sync',
            'V006': 'Output format support',
            'V016': 'Output Contract compliance'
        },
        'output_types': [
            {
                'type': 'reveal_structure',
                'description': 'Overview of reveal\'s internal structure',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'contract_version': {'type': 'string'},
                        'type': {'type': 'string', 'const': 'reveal_structure'},
                        'source': {'type': 'string'},
                        'source_type': {'type': 'string'},
                        'adapters': {'type': 'array'},
                        'analyzers': {'type': 'array'},
                        'rules': {'type': 'array'}
                    }
                }
            },
            {
                'type': 'reveal_check',
                'description': 'Validation check results',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'contract_version': {'type': 'string'},
                        'type': {'type': 'string', 'const': 'reveal_check'},
                        'source': {'type': 'string'},
                        'source_type': {'type': 'string'},
                        'detections': {'type': 'array'},
                        'passed': {'type': 'integer'},
                        'failed': {'type': 'integer'},
                        'total': {'type': 'integer'}
                    }
                }
            }
        ],
        'example_queries': [
            {
                'uri': 'reveal://',
                'description': 'Show reveal\'s internal structure (analyzers, rules, adapters)',
                'output_type': 'reveal_structure'
            },
            {
                'uri': 'reveal://config',
                'description': 'Show active configuration with full transparency',
                'element': 'config',
                'output_type': 'reveal_structure'
            },
            {
                'uri': 'reveal://analyzers',
                'description': 'List all registered analyzers',
                'element': 'analyzers',
                'output_type': 'reveal_structure'
            },
            {
                'uri': 'reveal://rules',
                'description': 'List all available validation rules',
                'element': 'rules',
                'output_type': 'reveal_structure'
            },
            {
                'uri': 'reveal:// --check',
                'description': 'Run all validation rules (V-series)',
                'cli_flag': '--check',
                'output_type': 'reveal_check'
            },
            {
                'uri': 'reveal:// --check --select V001,V002',
                'description': 'Run specific validation rules',
                'cli_flag': '--check --select',
                'output_type': 'reveal_check'
            },
            {
                'uri': 'reveal://adapters/reveal.py get_element',
                'description': 'Extract specific function from reveal\'s source',
                'output_type': 'code_element'
            }
        ]
    }


def get_help() -> Dict[str, Any]:
    """Get help documentation for reveal:// adapter."""
    return {
        'name': 'reveal',
        'description': 'Inspect reveal\'s own codebase - validate configuration, check completeness',
        'syntax': 'reveal://[path] [element]',
        'examples': [
            {
                'uri': 'reveal reveal://',
                'description': 'Show reveal\'s internal structure (analyzers, rules, adapters)'
            },
            {
                'uri': 'reveal reveal://config',
                'description': 'Show active configuration with full transparency (sources, precedence)'
            },
            {
                'uri': 'reveal reveal://analyzers',
                'description': 'List all registered analyzers'
            },
            {
                'uri': 'reveal reveal://rules',
                'description': 'List all available validation rules'
            },
            {
                'uri': 'reveal reveal://adapters/reveal.py get_element',
                'description': 'Extract specific function from reveal\'s source (element extraction)'
            },
            {
                'uri': 'reveal reveal://analyzers/markdown.py MarkdownAnalyzer',
                'description': 'Extract class from reveal\'s source'
            },
            {
                'uri': 'reveal reveal:// --check',
                'description': 'Run all validation rules (V-series)'
            },
            {
                'uri': 'reveal reveal:// --check --select V001,V002',
                'description': 'Run specific validation rules'
            },
        ],
        'features': [
            'Self-inspection of reveal codebase',
            'Element extraction from reveal source files',
            'Validation rules for completeness checks',
            'Analyzer and rule discovery',
            'Configuration validation',
            'Test coverage analysis'
        ],
        'validation_rules': {
            'V001': 'Help documentation completeness (every file type has help)',
            'V002': 'Analyzer registration validation',
            'V003': 'Feature matrix coverage',
            'V004': 'Test coverage gaps',
            'V005': 'Static help file sync',
            'V006': 'Output format support'
        },
        'try_now': [
            "reveal reveal://",
            "reveal reveal://config",
            "reveal reveal:// --check",
            "reveal reveal://analyzers",
        ],
        'workflows': [
            {
                'name': 'Validate Reveal Configuration',
                'scenario': 'Before committing changes, ensure reveal is properly configured',
                'steps': [
                    "reveal reveal:// --check                # Run all validation rules",
                    "reveal reveal:// --check --select V001  # Check help completeness",
                    "reveal reveal://analyzers               # Review registered analyzers",
                ],
            },
            {
                'name': 'Extract Reveal Source Code',
                'scenario': 'Study reveal\'s implementation by extracting specific functions/classes',
                'steps': [
                    "reveal reveal://analyzers/markdown.py MarkdownAnalyzer  # Extract class",
                    "reveal reveal://rules/links/L001.py _extract_anchors_from_markdown  # Extract function",
                    "reveal reveal://adapters/reveal.py get_element  # Self-referential extraction",
                ],
            },
            {
                'name': 'Check Test Coverage',
                'scenario': 'Added new analyzer, verify tests exist',
                'steps': [
                    "reveal reveal:// --check --select V004  # Test coverage validation",
                    "reveal reveal://analyzers               # See all analyzers",
                ],
            },
        ],
        'anti_patterns': [
            {
                'bad': "grep -r 'register' reveal/analyzers/",
                'good': "reveal reveal://analyzers",
                'why': "Shows registered analyzers with their file patterns and metadata",
            },
        ],
        'notes': [
            'Validation rules (V-series) check reveal\'s own codebase for completeness',
            'These rules prevent issues like missing documentation or forgotten test files',
            'Run reveal:// --check as part of CI to catch configuration issues'
        ],
        'output_formats': ['text', 'json'],
        'see_also': [
            'reveal --rules - List all pattern detection rules',
            'reveal help://ast - Query code as database',
            'reveal help:// - List all help topics'
        ]
    }
