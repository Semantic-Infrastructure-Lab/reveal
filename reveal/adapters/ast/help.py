"""Help and schema documentation for AST query adapter."""

from typing import Dict, Any

from reveal.reveal_types import CONTRACT_VERSION


_HELP_EXAMPLES = [
    {
        'uri': 'reveal ast ./src',
        'description': 'All code structure in src directory'
    },
    {
        'uri': "reveal ast app.py --where 'lines>50'",
        'description': 'Functions with more than 50 lines'
    },
    {
        'uri': "reveal ast ./src --where 'complexity>10'",
        'description': 'Complex functions (high cyclomatic complexity)'
    },
    {
        'uri': 'reveal ast main.py --kind function',
        'description': 'Functions and methods (not classes); --kind method for methods only'
    },
    {
        'uri': "reveal ast . --kind 'class|function'",
        'description': 'Both classes and functions (OR logic)'
    },
    {
        'uri': "reveal ast . --where 'name=test_*'",
        'description': 'All functions/classes starting with test_'
    },
    {
        'uri': "reveal ast src/ --where 'name=*helper*'",
        'description': 'All functions/classes containing "helper" in name'
    },
    {
        'uri': "reveal ast . --where 'lines>30' --where 'complexity<5'",
        'description': 'Long but simple functions (low complexity)'
    },
    {
        'uri': "reveal ast ./src --where 'complexity>10' --format=json",
        'description': 'JSON output for scripting'
    },
    {
        'uri': 'reveal ast . --where decorator=property',
        'description': 'Find all @property decorated methods'
    },
    {
        'uri': "reveal ast . --where 'decorator=*cache*'",
        'description': 'Find all cached functions (@lru_cache, @cached_property, etc.)'
    },
    {
        'uri': 'reveal ast . --where decorator=staticmethod',
        'description': 'Find all @staticmethod methods'
    },
    {
        'uri': "reveal ast . --where decorator=property --where 'lines>10'",
        'description': 'Find complex properties (potential code smell)'
    },
    {
        'uri': "reveal ast . --where 'kind!=function'",
        'description': 'All non-function elements (!= operator)'
    },
    {
        'uri': "reveal ast . --where 'name~=^test_'",
        'description': 'Functions starting with test_ using regex (~= operator)'
    },
    {
        'uri': 'reveal ast . --where lines=50..200',
        'description': 'Functions between 50-200 lines (.. range operator)'
    },
    {
        'uri': "reveal ast . --where 'complexity>10' --sort=-complexity",
        'description': 'Most complex functions first'
    },
    {
        'uri': 'reveal ast . --kind function --sort lines --limit 10',
        'description': 'Top 10 shortest functions'
    },
    {
        'uri': "reveal ast . --where 'complexity>5' --sort=-lines --limit 20 --offset 10",
        'description': 'Complex functions, paginated results'
    },
    {
        'uri': "reveal ast src/ --where 'nesting_depth>4'",
        'description': 'Find deeply nested functions (exceeds C905 threshold)'
    },
    {
        'uri': 'reveal ast src/ --where has_annotations=false --kind function',
        'description': 'Find fully unannotated functions for type coverage audit'
    },
    {
        'uri': "reveal ast src/ --where 'callers>5' --where 'complexity>10'",
        'description': 'Find high-coupling AND high-complexity functions (prime refactor targets)'
    },
]

_HELP_WORKFLOWS = [
    {
        'name': 'Find Refactoring Targets',
        'scenario': 'Codebase feels messy, need to find problem areas',
        'steps': [
            "reveal ast ./src --where 'complexity>10'        # Find complex functions",
            "reveal ast ./src --where 'lines>100'            # Find oversized functions",
            "reveal src/problem_file.py --outline      # Understand structure",
            "reveal src/problem_file.py big_function   # Extract for refactoring",
        ]
    },
    {
        'name': 'Explore Unknown Codebase',
        'scenario': 'New project, need to find entry points and structure',
        'steps': [
            "reveal ast . --where 'name=main*'               # Find entry points",
            "reveal ast . --where 'name=*cli*|*command*'     # Find CLI handlers",
            "reveal ast . --kind class               # See class hierarchy",
            "reveal src/core.py --outline              # Drill into key file",
        ]
    },
    {
        'name': 'Pre-PR Review',
        'scenario': 'About to review changes, want quick quality check',
        'steps': [
            "git diff --name-only | grep '\\.py$' | xargs -I{} reveal ast {} --where 'complexity>8'",
            "git diff --name-only | reveal --stdin --check",
        ]
    },
    {
        'name': 'Trace Function Call Graph',
        'scenario': 'Understand what calls what — trace execution paths and identify hotspots',
        'steps': [
            "reveal ast src/ --kind function --format json      # calls[] and called_by[] on every function",
            "reveal calls src/ --callers validate_item             # Cross-file: who calls validate_item project-wide?",
            "reveal calls src/ --callees validate_item             # Cross-file: what does validate_item call?",
            "reveal calls src/ --callers validate_item --depth 2   # Callers-of-callers (transitive, 2 levels)",
            "reveal calls src/ --callers main --format dot | dot -Tsvg > call_graph.svg  # Graphviz SVG",
        ]
    },
    {
        'name': 'Analyze Decorator Patterns',
        'scenario': 'Understand caching, properties, and API surface',
        'steps': [
            "reveal ast . --where decorator=property            # All properties",
            "reveal ast . --where 'decorator=*cache*'             # All cached/memoized functions",
            "reveal ast . --where decorator=staticmethod        # Static methods (might not need class)",
            "reveal ast . --where decorator=abstractmethod      # Abstract interface",
            "reveal ast . --where decorator=property --where 'lines>10'   # Complex properties (code smell)",
        ]
    },
    {
        'name': 'Find Implicit Dict Contracts (Python)',
        'scenario': 'Dict[str, Any] records passed between modules with no declared shape',
        'steps': [
            "reveal ast src/ --view dict-schemas      # Shapes read in several places + TypedDict drift",
            "reveal ast src/ --view dict-heatmap      # Every untyped-dict name, most keys first",
            "reveal check src/ --select T006            # Params that should take an existing TypedDict",
            "reveal ast src/ --reveal-type elem       # Where one variable's shape comes from",
        ]
    },
]

_HELP_ANTI_PATTERNS = [
    {
        'bad': "grep -r 'class UserManager' .",
        'good': "reveal ast . --where name=UserManager --kind class",
        'why': 'Semantic search vs text matching - no false positives from comments/strings'
    },
    {
        'bad': "find . -name '*.py' -exec grep -l 'def process' {} \\;",
        'good': "reveal ast . --where 'name=process*' --kind function",
        'why': 'One command, structured output with line numbers and complexity'
    },
    {
        'bad': "grep -rn 'def test_' tests/",
        'good': "reveal ast tests/ --where 'name=test_*'",
        'why': 'Wildcard matching + metadata (find long tests with lines>50)'
    },
]

_SCHEMA_QUERY_PARAMS = {
    'lines': {
        'type': 'integer',
        'description': 'Number of lines in function/class',
        'operators': ['>', '<', '>=', '<=', '=='],
        'examples': ['lines>50', 'lines<20', 'lines==100']
    },
    'complexity': {
        'type': 'integer',
        'description': 'McCabe cyclomatic complexity (>10 needs refactoring, >20 high risk)',
        'operators': ['>', '<', '>=', '<=', '=='],
        'examples': ['complexity>10', 'complexity<5']
    },
    'kind': {
        'type': 'string',
        'description': ('Element kind (also --kind; type is its noted legacy word). function matches every function, methods included; '
                        'method only members of a class, struct, impl, trait or interface (not a mod/namespace or nested function); '
                        'also struct, import, interface (trait), module, namespace, test'),
        'operators': ['==', '!=', '|'],
        'examples': ['kind=function', 'kind=method', 'kind=class|function'],
        'valid_values': ['function', 'class', 'method', 'struct', 'import', 'interface',
                         'trait', 'module', 'namespace', 'test']
    },
    'name': {
        'type': 'string',
        'description': 'Element name with wildcard support (* = any chars, ? = one char)',
        'operators': ['==', '~='],
        'examples': ['name=main', 'name=test_*', 'name=*helper*', 'name=get_?']
    },
    'decorator': {
        'type': 'string',
        'description': ('Decorator/annotation/attribute by name: @property, @Override, C# [HttpGet], '
                        'PHP #[Route("/x")] and Rust #[derive(...)] all match their bare name; each '
                        'attribute of a group like [HttpGet, Authorize] matches on its own; a qualified '
                        'name matches by its trailing segments (Obsolete or System.Obsolete); '
                        'a comma list is OR; wildcard support (* matches source text too)'),
        'operators': ['==', '!=', '~='],
        'examples': ['decorator=property', 'decorator=*cache*', 'decorator=HttpGet', 'decorator=derive']
    },
    'param_type': {
        'type': 'string',
        'description': 'Find functions where any parameter has a given type annotation. Parses the signature string; glob patterns supported. Bare type name matches generics too (Dict* matches Dict[str, Any]).',
        'operators': ['==', 'glob', '~='],
        'examples': ['param_type=dict', 'param_type=Dict*', 'param_type=Optional*']
    },
    'return_type': {
        'type': 'string',
        'description': 'Find functions with a given return type annotation. Parses the -> TYPE suffix of the signature. Glob patterns supported.',
        'operators': ['==', 'glob', '~='],
        'examples': ['return_type=bool', 'return_type=None', 'return_type=List*', 'return_type=Dict*']
    },
    'nesting_depth': {
        'type': 'integer',
        'description': ('Maximum nesting depth within the function (same metric as C905 rule; depth is its noted legacy '
                        'word). nesting_depth>4 is the C905 threshold; nesting_depth>6 is severe.'),
        'operators': ['>', '<', '>=', '<=', '=='],
        'examples': ['nesting_depth>4', 'nesting_depth>6', 'nesting_depth<=2']
    },
    'has_annotations': {
        'type': 'boolean',
        'description': 'Filter by presence of type annotations. has_annotations=false finds fully unannotated functions (no param or return hints). Combine with --kind function for a codebase annotation coverage audit.',
        'operators': ['=='],
        'examples': ['has_annotations=false', 'has_annotations=true']
    },
    'callers': {
        'type': 'integer',
        'description': 'Number of inbound callers in the same file (length of called_by list); for project-wide callers use reveal calls <path> --callers NAME. callers>5 finds high-coupling functions; combine with complexity>10 for refactor priorities.',
        'operators': ['>', '<', '>=', '<=', '=='],
        'examples': ['callers>5', 'callers>3', 'callers==0']
    },
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'ast_query',
        'description': 'Query results with matched functions/classes',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'ast_query'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string', 'enum': ['file', 'directory']},
                'path': {'type': 'string'},
                'query': {'type': 'string'},
                'total_files': {'type': 'integer'},
                'total_results': {'type': 'integer'},
                'results': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'symbol': {'type': 'string'},
                            'type': {'type': 'string'},
                            'line': {'type': 'integer'},
                            'lines': {'type': 'integer'},
                            'complexity': {'type': 'integer'},
                            'decorators': {'type': 'array'}
                        }
                    }
                }
            }
        },
        'example': {
            'contract_version': CONTRACT_VERSION,
            'type': 'ast_query',
            'source': './src',
            'source_type': 'directory',
            'path': './src',
            'query': 'complexity>10',
            'total_files': 15,
            'total_results': 3,
            'results': [
                {
                    'file': 'src/core.py',
                    'symbol': 'process_data',
                    'type': 'function',
                    'line': 42,
                    'lines': 87,
                    'complexity': 15,
                    'decorators': []
                }
            ]
        }
    },
    {
        'type': 'ast_dict_heatmap',
        'description': '--view dict-heatmap: untyped-dict names ranked by distinct string keys read',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'ast_dict_heatmap'},
                'path': {'type': 'string'},
                'total_results': {'type': 'integer'},
                'unsupported_language': {'type': 'string'},
                'results': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'function': {'type': 'string'},
                            'line': {'type': 'integer'},
                            'param': {'type': 'string', 'description': 'variable name'},
                            'source': {'type': 'string', 'enum': [
                                'annotated_param', 'unannotated_param', 'loop_var',
                                'local', 'attribute',
                            ]},
                            'annotation': {'type': 'string'},
                            'iterable': {'type': 'string', 'description': 'loop_var only'},
                            'key_count': {'type': 'integer'},
                            'access_count': {'type': 'integer'},
                            'keys': {'type': 'array', 'items': {'type': 'string'}},
                            'suggested_name': {'type': 'string'},
                        }
                    }
                }
            }
        },
        'example': {
            'contract_version': CONTRACT_VERSION,
            'type': 'ast_dict_heatmap',
            'path': './src',
            'total_results': 1,
            'unsupported_language': '',
            'results': [{
                'file': 'src/render.py', 'function': 'render', 'line': 12,
                'param': 'elem', 'source': 'loop_var', 'annotation': '',
                'iterable': "structure['functions']", 'key_count': 3, 'access_count': 4,
                'keys': ['calls', 'line', 'name'], 'suggested_name': 'ElemState',
            }]
        }
    },
    {
        'type': 'ast_dict_schemas',
        'description': (
            '--view dict-schemas: untyped dict shapes read in 2+ functions, with any '
            'existing TypedDict that covers them and the keys it does not declare'
        ),
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'ast_dict_schemas'},
                'path': {'type': 'string'},
                'total_results': {'type': 'integer'},
                'unsupported_language': {'type': 'string'},
                'results': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'suggested_name': {'type': 'string'},
                            'consumer_count': {'type': 'integer'},
                            'file_count': {'type': 'integer'},
                            'seed_keys': {'type': 'array', 'items': {'type': 'string'}},
                            'keys': {'type': 'array', 'description': '[{key, consumers}]'},
                            'variable_names': {'type': 'array', 'items': {'type': 'string'}},
                            'sources': {'type': 'object', 'description': 'source -> count'},
                            'typeddict_matches': {
                                'type': 'array',
                                'description': '[{name, file, line, coverage, undeclared_keys}]',
                            },
                            'consumers': {
                                'type': 'array',
                                'description': '[{file, line, function, param, source}]',
                            },
                        }
                    }
                }
            }
        },
        'example': {
            'contract_version': CONTRACT_VERSION,
            'type': 'ast_dict_schemas',
            'path': './src',
            'total_results': 1,
            'unsupported_language': '',
            'results': [{
                'suggested_name': 'ElemState', 'consumer_count': 2, 'file_count': 2,
                'seed_keys': ['calls', 'line', 'line_end', 'name'],
                'keys': [{'key': 'name', 'consumers': 2}, {'key': 'line', 'consumers': 2},
                         {'key': 'calls', 'consumers': 2}, {'key': 'line_end', 'consumers': 1}],
                'variable_names': ['elem'],
                'sources': {'loop_var': 1, 'annotated_param': 1},
                'typeddict_matches': [{
                    'name': 'Element', 'file': 'src/types.py', 'line': 8,
                    'coverage': 1.0, 'undeclared_keys': ['line_end'],
                }],
                'consumers': [
                    {'file': 'src/render.py', 'line': 12, 'function': 'render',
                     'param': 'elem', 'source': 'loop_var'},
                    {'file': 'src/rank.py', 'line': 30, 'function': 'rank',
                     'param': 'elem', 'source': 'annotated_param'},
                ],
            }]
        }
    },
    {
        'type': 'ast_reveal_type',
        'description': '--reveal-type NAME: every annotation, assignment shape and loop binding of one variable',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'ast_reveal_type'},
                'path': {'type': 'string'},
                'var_name': {'type': 'string'},
                'analysis': {'type': 'object', 'description': 'candidate, analyzed, failed and recovered file counts'},
                'total_results': {'type': 'integer'},
                'results': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'function': {'type': 'string'},
                            'func_line': {'type': 'integer'},
                            'line': {'type': 'integer'},
                            'kind': {'type': 'string', 'enum': ['param', 'assign', 'for']},
                            'annotation': {'type': 'string'},
                            'shape': {'type': 'string'},
                        }
                    }
                }
            }
        },
        'example': {
            'contract_version': CONTRACT_VERSION,
            'type': 'ast_reveal_type',
            'path': 'src',
            'var_name': 'elem',
            'total_results': 1,
            'results': [{'file': 'src/render.py', 'function': 'render', 'func_line': 12, 'line': 12,
                         'kind': 'param', 'annotation': 'dict', 'shape': ''}],
        }
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'reveal ast ./src',
        'description': 'All code structure in src directory',
        'output_type': 'ast_query'
    },
    {
        'uri': "reveal ast ./src --where 'lines>50'",
        'description': 'Functions with more than 50 lines',
        'output_type': 'ast_query'
    },
    {
        'uri': "reveal ast ./src --where 'complexity>10'",
        'description': 'Complex functions (high cyclomatic complexity)',
        'output_type': 'ast_query'
    },
    {
        'uri': 'reveal ast main.py --kind function',
        'description': 'Functions and methods (not classes); --kind method for methods only',
        'output_type': 'ast_query'
    },
    {
        'uri': "reveal ast . --where 'name=test_*'",
        'description': 'All functions/classes starting with test_',
        'output_type': 'ast_query'
    },
    {
        'uri': 'reveal ast . --where decorator=property',
        'description': 'Find all @property decorated methods',
        'output_type': 'ast_query'
    },
    {
        'uri': "reveal ast . --where 'lines>30' --where 'complexity<5'",
        'description': 'Long but simple functions',
        'output_type': 'ast_query'
    },
    {
        'uri': 'reveal ast src/ --view dict-heatmap',
        'description': 'Untyped dicts (params, loop vars, locals) ranked by keys read',
        'output_type': 'ast_dict_heatmap'
    },
    {
        'uri': 'reveal ast src/ --view dict-schemas',
        'description': 'Dict shapes read in several places, and TypedDicts that already cover them',
        'output_type': 'ast_dict_schemas'
    },
]


def get_help() -> Dict[str, Any]:
    """Get help documentation for ast:// adapter."""
    return {
        'name': 'ast',
        'description': 'Query code as an AST database - find functions by complexity, size, type',
        'syntax': 'reveal ast <path> [--where EXPR]... [--kind KIND] [--sort [-]FIELD] [--limit N|--all] [--offset N] '
                  '| --view dict-heatmap|dict-schemas | --reveal-type NAME',
        'epilog': ('The deprecated ast:// URI takes the same flags until 1.0, with a replaced-by note; so does its '
                   'legacy query string (?complexity>10&kind=function).'),
        'operators': {
            '>': 'Greater than',
            '<': 'Less than',
            '>=': 'Greater than or equal',
            '<=': 'Less than or equal',
            '==': 'Equal to',
            '!=': 'Not equal to',
            '~=': 'Regex match',
            '..': "Range (e.g., --where lines=50..200)"
        },
        'filters': {
            'lines': "Number of lines in function/class (e.g., --where 'lines>50', --where lines=10..100)",
            'complexity': 'McCabe cyclomatic complexity (industry threshold: >10 needs refactoring, >20 is high risk)',
            'kind': ('Element kind, also --kind: function (methods included), method (members of a type), class, struct, '
                     "import, interface, module, namespace, test. OR with | or , (--kind function, --kind 'class|function'); "
                     'type is its noted legacy word'),
            'name': "Element name pattern with wildcards or regex (e.g., --where 'name=test_*', --where 'name~=^test_')",
            'decorator': ('Decorator, annotation or attribute name - find decorated functions/classes '
                          '(e.g., --where decorator=property, decorator=HttpGet for C# [HttpGet], decorator=derive '
                          "for Rust #[derive(Debug)], --where 'decorator!=property')"),
            'param_type': 'Find functions where any param has this type annotation (e.g., --where param_type=dict)',
            'return_type': 'Find functions with this return annotation (e.g., --where return_type=bool)',
            'nesting_depth': "Maximum nesting depth (e.g., --where 'nesting_depth>4'); depth is its noted legacy word",
            'has_annotations': 'Annotation presence (e.g., --where has_annotations=false)',
            'callers': "Inbound callers in the same file (e.g., --where 'callers>5')",
        },
        'cli_flags': [
            {'flag': '--where EXPR', 'description': 'A filter over the fields above; repeat to AND'},
            {'flag': '--kind KIND', 'description': 'Element kind (the kind field)'},
            {'flag': '--view dict-heatmap|dict-schemas',
             'description': ('Untyped dicts ranked by keys read, or clustered into shared shapes (Python only; '
                             'reads no row control)')},
            {'flag': '--reveal-type NAME',
             'description': ('Type evidence for one variable (Python only; reads no row control); a name with no '
                             'occurrence exits 2')},
            {'flag': '--sort [-]FIELD', 'description': 'Sort the listing; text keeps the sorted order'},
            {'flag': '--limit N | --all', 'description': 'Listing rows (default cap 200; --limit 0 or --all is every row)'},
            {'flag': '--offset N', 'description': 'Listing rows skipped after sorting'},
            {'flag': '--builtins', 'description': 'Keep builtin names in calls[]'},
        ],
        'examples': _HELP_EXAMPLES,
        # Executable examples for current directory
        'try_now': [
            "reveal ast . --where 'complexity>10'",
            "reveal ast . --where 'name=test_*'",
            "reveal ast . --where decorator=property",
            "reveal ast . --where 'decorator=*cache*'",
        ],
        # Scenario-based workflow patterns
        'workflows': _HELP_WORKFLOWS,
        # What NOT to do
        'anti_patterns': _HELP_ANTI_PATTERNS,
        'notes': [
            'Ordinary filter queries exit 2 for invalid requests and 3 for required analysis/output loss; healthy empty results and display cuts exit 0. Dict/type-evidence modes, checks and mixed batches keep their legacy policy.',
            "Quote --where expressions with > or < operators: --where 'lines>50' (the shell reads > as a redirect)",
            'Operators: != (not equals), ~= (regex), .. (range)',
            'Result control: --sort FIELD (or --sort=-FIELD for descending), --limit N, --offset M',
            'Result control enables efficient pagination for AI agents and large codebases',
            'Complexity is proper McCabe cyclomatic complexity for tree-sitter languages; falls back to a keyword-count estimate (shared with metrics:// and C901)',
            'Scans all code files in directory recursively',
            'Supports Python, JS, TS, Rust, Go and more via tree-sitter (reveal --languages)',
            'Use --format=json for programmatic filtering with jq',
            "Call graph: the calls= and callee_of= fields and the calls view are retired (each prints a note); use reveal calls <path> --callers X / --callees X, or --grep for a text pattern",
            'JSON output includes calls[] and called_by[] fields on each function/method; where a call lands across files is reveal calls <path> --callees FILE:NAME --depth 2',
        ],
        'output_formats': ['text', 'json', 'grep'],
        'see_also': [
            'reveal help://tricks - Power user workflows',
            'reveal file.py --check - Code quality checks',
        ]
    }


def get_schema() -> Dict[str, Any]:
    """Get machine-readable schema for ast:// adapter.

    Returns JSON schema for AI agent integration.
    """
    return {
        'adapter': 'ast',
        'description': 'Query code as an AST database - find functions, classes, methods by properties',
        'uri_syntax': 'reveal ast <path> [--where EXPR]... [--kind KIND] [--view VIEW] [--reveal-type NAME] [--sort FIELD] [--limit N]',
        'query_params': _SCHEMA_QUERY_PARAMS,
        'operators': {
            '>': 'Greater than (numeric)',
            '<': 'Less than (numeric)',
            '>=': 'Greater than or equal (numeric)',
            '<=': 'Less than or equal (numeric)',
            '==': 'Equal to (exact match)',
            '~=': 'Pattern match (with wildcards)',
            '--where ... --where': 'AND (combine filters)',
            '|': 'OR (alternate values)'
        },
        'elements': {},  # AST adapter doesn't use element-based queries
        'cli_flags': ['--where', '--kind', '--view', '--reveal-type', '--builtins', '--sort', '--limit', '--all',
                      '--offset', '--format=json', '--format=grep'],
        'supports_batch': False,
        'supports_advanced': False,
        'output_types': _SCHEMA_OUTPUT_TYPES,
        'example_queries': _SCHEMA_EXAMPLE_QUERIES,
        'notes': [
            "Quote --where expressions with > or < operators: --where 'lines>50' (shell interprets > as redirect)",
            'Operators: = (equals), != (not equals), > < (numeric), ~= (regex/glob), .. (range)',
            'Result control: --sort FIELD, --sort=-FIELD (descending), --limit N, --offset M',
            'Sort note: text keeps the sorted order -- rows sit under a File heading while each file\'s rows are consecutive, '
            'and print one per line with their file when the sort interleaves files',
            'Supports the tree-sitter languages listed by reveal --languages (Python, JS, TS, Rust, Go, Java, C, C++, ...)',
            'Complexity is proper McCabe cyclomatic complexity for tree-sitter languages; falls back to a keyword-count estimate (shared with metrics:// and C901) for unsupported languages',
            'Call graph fields on functions/methods in JSON: calls[] (outgoing), called_by[] (within-file incoming); cross-file targets: reveal calls <path> --callees FILE:NAME --depth 2 (resolved_calls[] is retired, BACK-2566)',
            'The calls= and callee_of= fields and the calls view are retired spellings (a replaced-by note until the cut): '
            "use reveal calls <path> --callers NAME or --callees NAME, or --grep 'PATTERN' for a text pattern",
            '--view dict-heatmap / --view dict-schemas and --reveal-type are Python-only and return their own '
            'result types (ast_dict_heatmap / ast_dict_schemas / ast_reveal_type), not ast_query; TypedDicts '
            'are matched only if defined under the scanned path. The rule form is T006: '
            'reveal check <path> --select T006',
        ]
    }
