"""Help and schema documentation for AST query adapter."""

from typing import Dict, Any


_HELP_EXAMPLES = [
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
    },
    {
        'uri': 'ast://.?type!=function',
        'description': 'All non-function elements (NEW: != operator)'
    },
    {
        'uri': 'ast://.?name~=^test_',
        'description': 'Functions starting with test_ using regex (NEW: ~= operator)'
    },
    {
        'uri': 'ast://.?lines=50..200',
        'description': 'Functions between 50-200 lines (NEW: .. range operator)'
    },
    {
        'uri': 'ast://.?complexity>10&sort=-complexity',
        'description': 'Most complex functions first (NEW: sort)'
    },
    {
        'uri': 'ast://.?type=function&sort=lines&limit=10',
        'description': 'Top 10 shortest functions (NEW: sort + limit)'
    },
    {
        'uri': 'ast://.?complexity>5&sort=-lines&limit=20&offset=10',
        'description': 'Complex functions, paginated results (NEW: full result control)'
    },
    {
        'uri': 'ast://src/?calls=validate_item --format=json',
        'description': 'Find all functions that call validate_item (JSON includes calls + resolved_calls)'
    },
    {
        'uri': 'ast://src/?callee_of=process_batch',
        'description': 'Find functions called by process_batch (within-file)'
    },
    {
        'uri': 'ast://src/?show=calls',
        'description': 'Show call graph view for all functions in src/ (calls + called_by)'
    },
    {
        'uri': "ast://src/?depth>4",
        'description': 'Find deeply nested functions (exceeds C905 threshold)'
    },
    {
        'uri': "ast://src/?has_annotations=false&type=function",
        'description': 'Find fully unannotated functions for type coverage audit'
    },
    {
        'uri': "ast://src/?callers>5&complexity>10",
        'description': 'Find high-coupling AND high-complexity functions (prime refactor targets)'
    },
]

_HELP_WORKFLOWS = [
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
        'name': 'Trace Function Call Graph',
        'scenario': 'Understand what calls what — trace execution paths and identify hotspots',
        'steps': [
            "reveal 'ast://src/?show=calls'                        # Compact call graph: all functions + their calls",
            "reveal 'ast://src/?calls=validate_item'               # Which functions call validate_item? (within-file)",
            "reveal 'calls://src/?target=validate_item'            # Cross-file: who calls validate_item project-wide?",
            "reveal 'calls://src/?callees=validate_item'           # Cross-file: what does validate_item call?",
            "reveal 'calls://src/?target=validate_item&depth=2'    # Callers-of-callers (transitive, 2 levels)",
            "reveal 'calls://src/?target=main&format=dot' | dot -Tsvg > call_graph.svg  # Graphviz SVG",
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
]

_HELP_ANTI_PATTERNS = [
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
    'type': {
        'type': 'string',
        'description': 'Element type (function, class, method)',
        'operators': ['==', '|'],
        'examples': ['type=function', 'type=class|function'],
        'valid_values': ['function', 'class', 'method']
    },
    'name': {
        'type': 'string',
        'description': 'Element name with wildcard support (* = any chars, ? = one char)',
        'operators': ['==', '~='],
        'examples': ['name=main', 'name=test_*', 'name=*helper*', 'name=get_?']
    },
    'decorator': {
        'type': 'string',
        'description': 'Decorator pattern with wildcard support',
        'operators': ['==', '~='],
        'examples': ['decorator=property', 'decorator=*cache*', 'decorator=staticmethod']
    },
    'calls': {
        'type': 'string',
        'description': 'Find functions/methods that call a given name (wildcard supported). Matches against the calls list extracted from function bodies.',
        'operators': ['==', '~='],
        'examples': ['calls=validate_item', 'calls=*send*', 'calls=db.*']
    },
    'callee_of': {
        'type': 'string',
        'description': 'Find functions that are called by a given function name (within-file reverse direction). Matches against the called_by list.',
        'operators': ['==', '~='],
        'examples': ['callee_of=main', 'callee_of=process_batch', 'callee_of=*handler*']
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
    'depth': {
        'type': 'integer',
        'description': 'Maximum nesting depth within the function (same metric as C905 rule). depth>4 is the C905 threshold; depth>6 is severe.',
        'operators': ['>', '<', '>=', '<=', '=='],
        'examples': ['depth>4', 'depth>6', 'depth<=2']
    },
    'has_annotations': {
        'type': 'boolean',
        'description': 'Filter by presence of type annotations. has_annotations=false finds fully unannotated functions (no param or return hints). Combine with type=function for a codebase annotation coverage audit.',
        'operators': ['=='],
        'examples': ['has_annotations=false', 'has_annotations=true']
    },
    'callers': {
        'type': 'integer',
        'description': 'Number of inbound callers within the scanned files (length of called_by list). callers>5 finds high-coupling functions; combine with complexity>10 for refactor priorities.',
        'operators': ['>', '<', '>=', '<=', '=='],
        'examples': ['callers>5', 'callers>3&complexity>10', 'callers==0']
    },
    'reveal_type': {
        'type': 'string',
        'description': (
            'Show all type evidence for a named variable: every parameter annotation, '
            'assignment with inferred RHS shape (dict literal keys, call return, etc.), '
            'and for-loop binding. Works on unannotated code — no source edits needed. '
            'Replaces the mypy reveal_type() workflow non-destructively.'
        ),
        'operators': ['=='],
        'examples': ['reveal_type=trade', 'reveal_type=result', 'reveal_type=config']
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
            'contract_version': '1.0',
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
    }
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'ast://./src',
        'description': 'All code structure in src directory',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://./src?lines>50',
        'description': 'Functions with more than 50 lines',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://./src?complexity>10',
        'description': 'Complex functions (high cyclomatic complexity)',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://main.py?type=function',
        'description': 'Only functions (not classes or methods)',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://.?name=test_*',
        'description': 'All functions/classes starting with test_',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://.?decorator=property',
        'description': 'Find all @property decorated methods',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://.?lines>30&complexity<5',
        'description': 'Long but simple functions',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://src/?calls=validate_item',
        'description': 'Find functions that call validate_item (within-file)',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://src/?callee_of=main',
        'description': 'Find functions called by main (within-file)',
        'output_type': 'ast_query'
    },
    {
        'uri': 'ast://src/?show=calls',
        'description': 'Compact call graph view for all functions in src/',
        'output_type': 'ast_query'
    },
]


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
            '==': 'Equal to',
            '!=': 'Not equal to (NEW)',
            '~=': 'Regex match (NEW)',
            '..': 'Range (e.g., lines=50..200) (NEW)'
        },
        'filters': {
            'lines': 'Number of lines in function/class (e.g., lines>50, lines=10..100)',
            'complexity': 'McCabe cyclomatic complexity (industry threshold: >10 needs refactoring, >20 is high risk)',
            'type': 'Element type: function, class, method. Supports OR with | or , (e.g., type=function, type=class|function)',
            'name': 'Element name pattern with wildcards or regex (e.g., name=test_*, name~=^test_)',
            'decorator': 'Decorator pattern - find decorated functions/classes (e.g., decorator=property, decorator!=property)',
            'calls': 'Find functions that call a given name (e.g., calls=validate_item, calls=*send*)',
            'callee_of': 'Find functions called by a given function (within-file reverse, e.g., callee_of=main)',
            'param_type': 'Find functions where any param has this type annotation (e.g., param_type=dict, param_type=Dict*)',
            'return_type': 'Find functions with this return annotation (e.g., return_type=bool, return_type=None)',
            'reveal_type': 'Show type evidence for a variable: params, assignments, for-loops across the file (e.g., reveal_type=trade)',
            'show': 'Display mode: show=calls renders call graph, show=dict-heatmap ranks bare-dict params by key access count (TypedDict migration priority list)'
        },
        'result_control': {
            'sort': 'Sort results by field (e.g., sort=complexity, sort=-lines for descending)',
            'limit': 'Limit number of results (e.g., limit=10)',
            'offset': 'Skip first N results (e.g., offset=5)'
        },
        'examples': _HELP_EXAMPLES,
        # Executable examples for current directory
        'try_now': [
            "reveal 'ast://.?complexity>10'",
            "reveal 'ast://.?name=test_*'",
            "reveal 'ast://.?decorator=property'",
            "reveal 'ast://.?decorator=*cache*'",
            "reveal 'ast://.?show=calls'",
        ],
        # Scenario-based workflow patterns
        'workflows': _HELP_WORKFLOWS,
        # What NOT to do
        'anti_patterns': _HELP_ANTI_PATTERNS,
        'notes': [
            'Quote URIs with > or < operators: \'ast://path?lines>50\' (shell interprets > as redirect)',
            'NEW operators: != (not equals), ~= (regex), .. (range)',
            'NEW result control: sort=field (or sort=-field for descending), limit=N, offset=M',
            'Result control enables efficient pagination for AI agents and large codebases',
            'Complexity is proper McCabe cyclomatic complexity for tree-sitter languages; falls back to line-count heuristic',
            'Scans all code files in directory recursively',
            'Supports Python, JS, TS, Rust, Go, and 50+ languages via tree-sitter',
            'Use --format=json for programmatic filtering with jq',
            'Call graph: calls= and callee_of= filters work within a file; use calls:// for cross-file callers (?target=X) and callees (?callees=X)',
            'JSON output includes calls[], called_by[], and resolved_calls[] fields on each function/method',
        ],
        'output_formats': ['text', 'json', 'grep'],
        'see_also': [
            'reveal help://python - Runtime environment inspection',
            'reveal help://tricks - Power user workflows',
            'reveal file.py --check - Code quality checks',
            'reveal help://calls - Cross-file call graph queries (calls:// adapter)',
        ]
    }


def get_schema() -> Dict[str, Any]:
    """Get machine-readable schema for ast:// adapter.

    Returns JSON schema for AI agent integration.
    """
    return {
        'adapter': 'ast',
        'description': 'Query code as an AST database - find functions, classes, methods by properties',
        'uri_syntax': 'ast://<path>?<filter1>&<filter2>&...',
        'query_params': _SCHEMA_QUERY_PARAMS,
        'operators': {
            '>': 'Greater than (numeric)',
            '<': 'Less than (numeric)',
            '>=': 'Greater than or equal (numeric)',
            '<=': 'Less than or equal (numeric)',
            '==': 'Equal to (exact match)',
            '~=': 'Pattern match (with wildcards)',
            '&': 'AND (combine filters)',
            '|': 'OR (alternate values)'
        },
        'elements': {},  # AST adapter doesn't use element-based queries
        'cli_flags': ['--format=json', '--format=grep', '--outline'],
        'supports_batch': False,
        'supports_advanced': False,
        'output_types': _SCHEMA_OUTPUT_TYPES,
        'example_queries': _SCHEMA_EXAMPLE_QUERIES,
        'notes': [
            "Quote URIs with > or < operators: 'ast://path?lines>50' (shell interprets > as redirect)",
            'Operators: = (equals), != (not equals), > < (numeric), ~= (regex/glob), .. (range)',
            'Result control: sort=field, sort=-field (descending), limit=N, offset=M',
            'Sort note: text output groups results by file; use --format=json or --format=grep for globally sorted output',
            'Supports 50+ languages via tree-sitter (Python, JS, TS, Rust, Go, Java, C, C++, ...)',
            'Complexity is proper McCabe cyclomatic complexity for tree-sitter languages; falls back to line-count heuristic for unsupported languages',
            'type= shorthand: ?functions → ?type=function, ?classes → ?type=class, ?methods → ?type=method',
            'Call graph fields on functions/methods in JSON: calls[] (outgoing), called_by[] (within-file incoming), resolved_calls[] (cross-file resolved entries)',
            'calls= and callee_of= filters search within-file call lists; for project-wide callers use calls:// adapter',
            'show=calls renders a compact call graph view (arrow diagram) instead of the standard element list',
        ]
    }
