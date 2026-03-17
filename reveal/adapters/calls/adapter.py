"""calls:// adapter — cross-file call graph queries.

Supported URIs:

    calls://src/?target=validate_item           # who calls validate_item?
    calls://src/?target=validate_item&depth=2  # callers-of-callers too
    calls://src/?target=validate_item&format=dot  # graphviz dot output

The adapter builds a project-level callers index from the code under *path*,
then looks up the requested *target*.  Results are cached per-directory with
mtime-based invalidation.

Limitations (static analysis):
- Dynamic dispatch (callbacks, metaclasses) is not resolved.
- Method resolution order (MRO) is not considered.
- Builtins and stdlib calls appear in raw call lists but will rarely be
  targets anyone queries for.
"""

import os
from typing import Any, Dict, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from .index import PYTHON_BUILTINS, find_callers, find_callees, find_uncalled, rank_by_callers
from .renderer import render_calls_structure
from ...utils.query import parse_query_params
from ...utils.results import ResultBuilder

_HELP: Dict[str, Any] = {
    'name': 'calls',
    'description': 'Cross-file call graph queries — find callers or callees of any function.',
    'syntax': 'calls://<path>?target=<function>[&depth=N][&format=dot|json]\n'
              '         calls://<path>?callees=<function>\n'
              '         calls://<path>:<function>           # shorthand — infers ?target=<function>',
    'parameters': {
        'target':   'Function name to find callers of (reverse lookup)',
        'callees':  'Function name to find callees of — what does it call? (forward lookup)',
        'rank':     'Set to "callers" to rank all functions by in-degree (most-called first)',
        'uncalled': 'List all functions/methods with no callers (dead code candidates)',
        'top':      'Max results for ?rank=callers or ?uncalled (default: 10/?rank, unlimited/?uncalled)',
        'type':     'For ?uncalled: filter to "function" (module-level only) or "method"',
        'depth':    'Transitive caller depth (default 1, max 5) — applies to ?target only',
        'format':   'Output format: text (default), dot (Graphviz), or json',
        'builtins': 'Include Python builtins in callees output (default: false). '
                    'Use ?builtins=true to see len, str, sorted, ValueError, etc.',
    },
    'examples': [
        {'uri': 'calls://src/?target=validate_item',
         'description': 'Who calls validate_item? (reverse lookup)'},
        {'uri': 'calls://src/main.py:main',
         'description': 'Shorthand — who calls main? (colon infers ?target=main)'},
        {'uri': 'calls://src/?target=process_batch&depth=2',
         'description': 'Callers-of-callers too (transitive, 2 levels)'},
        {'uri': 'calls://src/?callees=validate_item',
         'description': 'What does validate_item call? (forward lookup, builtins hidden)'},
        {'uri': 'calls://src/?callees=validate_item&builtins=true',
         'description': 'Include builtins (len, str, sorted, exceptions, etc.)'},
        {'uri': 'calls://src/?rank=callers',
         'description': 'Top 10 most-called functions (coupling hotspot ranking)'},
        {'uri': 'calls://src/?rank=callers&top=20',
         'description': 'Top 20 most-called functions'},
        {'uri': 'calls://src/?uncalled',
         'description': 'Dead code candidates — all functions/methods with no callers'},
        {'uri': 'calls://src/?uncalled&type=function',
         'description': 'Dead code — module-level functions only (skip methods)'},
        {'uri': 'calls://src/?uncalled&top=20',
         'description': 'Top 20 most-recently-added uncalled functions'},
        {'uri': 'calls://src/?target=main&format=dot',
         'description': 'Output callers graph as Graphviz dot (pipe to dot -Tsvg)'},
        {'uri': 'calls://src/?target=main&format=json',
         'description': 'Machine-readable callers result'},
    ],
    'notes': [
        'Static analysis only — dynamic dispatch (callbacks, metaclasses) is not resolved.',
        'Results are cached per-directory; any file change triggers a full rebuild.',
        'Callee names are normalised: "self.foo" → "foo" for index lookup.',
        'depth=N expands callers transitively up to N levels (capped at 5).',
        '?callees=X finds every definition of X and shows what it calls — useful for multi-file functions.',
    ],
}

_SCHEMA: Dict[str, Any] = {
    'adapter': 'calls',
    'description': 'Cross-file call graph — who calls X (?target) or what does X call (?callees)?',
    'uri_syntax': 'calls://<path>?target=<name>[&depth=N][&format=text|dot|json]\n'
                  '             calls://<path>:<name>  # shorthand — infers ?target=<name>',
    'query_params': {
        'target':   {'type': 'string',  'description': 'Function name to find callers of (reverse lookup)'},
        'callees':  {'type': 'string',  'description': 'Function name to find callees of (forward lookup)'},
        'rank':     {'type': 'string',  'description': 'Set to "callers" to rank all functions by in-degree'},
        'uncalled': {'type': 'boolean', 'description': 'List all functions/methods with no callers (dead code candidates)'},
        'top':      {'type': 'integer', 'description': 'Max results for ?rank=callers or ?uncalled (default 10/?rank, unlimited/?uncalled)'},
        'type':     {'type': 'string',  'description': 'For ?uncalled: "function" (module-level only) or "method"'},
        'depth':    {'type': 'integer', 'description': 'Transitive depth 1-5 (default 1), applies to ?target'},
        'format':   {'type': 'string',  'description': 'Output format: text (default), dot (Graphviz), or json'},
        'builtins': {'type': 'boolean', 'description': 'Include Python builtins in callees output (default: false)'},
    },
    'elements': {},
    'supports_batch': False,
    'supports_advanced': False,
    'output_types': [
        {
            'type': 'calls_query',
            'description': 'Callers result — all functions/files that call the target',
            'schema': {
                'type': 'object',
                'properties': {
                    'target':        {'type': 'string'},
                    'depth':         {'type': 'integer'},
                    'total_callers': {'type': 'integer'},
                    'levels': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'level':   {'type': 'integer'},
                                'callers': {'type': 'array'},
                            },
                        },
                    },
                },
            },
            'example': {
                'target': 'validate_item',
                'depth': 1,
                'total_callers': 3,
                'levels': [{'level': 1, 'callers': [
                    {'file': 'app/routes.py', 'caller': 'post_item', 'line': 42, 'call_expr': 'validate_item'},
                    {'file': 'app/batch.py', 'caller': 'process_batch', 'line': 17, 'call_expr': 'validate_item'},
                ]}],
            },
        },
        {
            'type': 'calls_callees',
            'description': 'Callees result — functions/methods called by the target',
            'schema': {
                'type': 'object',
                'properties': {
                    'target':      {'type': 'string'},
                    'total_calls': {'type': 'integer'},
                    'matches': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'file':     {'type': 'string'},
                                'function': {'type': 'string'},
                                'line':     {'type': 'integer'},
                                'calls':    {'type': 'array', 'items': {'type': 'string'}},
                            },
                        },
                    },
                },
            },
            'example': {
                'target': 'validate_item',
                'total_calls': 4,
                'matches': [{'file': 'app/validators.py', 'function': 'validate_item', 'line': 55,
                             'calls': ['check_required', 'normalize_value', 'log_validation', 'raise_error']}],
            },
        },
    ],
    'example_queries': [
        {
            'uri': 'calls://src/?target=validate_item',
            'description': 'Who calls validate_item? (reverse lookup across whole project)',
            'output_type': 'calls_query',
        },
        {
            'uri': 'calls://src/?target=validate_item&depth=2',
            'description': 'Callers and callers-of-callers (transitive, 2 levels)',
            'output_type': 'calls_query',
        },
        {
            'uri': 'calls://src/?callees=validate_item',
            'description': 'What does validate_item call? (builtins hidden by default)',
            'output_type': 'calls_callees',
        },
        {
            'uri': 'calls://src/?callees=validate_item&builtins=true',
            'description': 'Include Python builtins (len, str, sorted, ValueError, etc.)',
            'output_type': 'calls_callees',
        },
        {
            'uri': 'calls://src/?target=main&format=dot',
            'description': 'Export callers graph as Graphviz dot format',
            'output_type': 'calls_query',
        },
        {
            'uri': 'calls://src/?target=main&format=json',
            'description': 'Machine-readable callers result',
            'output_type': 'calls_query',
        },
    ],
    'notes': [
        'Static analysis only — dynamic dispatch, callbacks, and metaclasses are not resolved.',
        'Results are cached per-directory; any file change triggers a full index rebuild.',
        'Callee names are normalised: "self.foo" → "foo" for lookup; full dotted form also indexed.',
        '?target depth=N expands callers transitively up to N levels (capped at 5).',
        '?callees=X scans all definitions of X — useful when the name appears in multiple files.',
        '?callees hides Python builtins by default (len, str, sorted, ValueError, etc.); use ?builtins=true to include them.',
    ],
}


class CallsRenderer:
    """Renderer shim so the adapter works with the standard render pipeline.

    Note: render_structure / render_element are called as *class methods* by
    the routing layer (``renderer_class.render_structure(result, args.format)``),
    so the first positional parameter is the result dict, NOT ``self``.  This
    mirrors the pattern used by ImportsRenderer and other adapters.

    The ``format=dot`` query-string parameter takes precedence over the CLI
    ``--format`` flag for calls:// because ``dot`` is a calls://-specific
    format that has no CLI-flag equivalent.  The adapter stores the chosen
    format in result[``_query_format``] so the renderer can pick it up.
    """

    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:  # noqa: N805
        # Query-string format= (e.g. format=dot) takes precedence over CLI --format
        effective_format = result.get('_query_format') or format
        render_calls_structure(result, effective_format)

    def render_element(result: Dict[str, Any], format: str = 'text') -> None:  # noqa: N805
        effective_format = result.get('_query_format') or format
        render_calls_structure(result, effective_format)

    def render_error(error: Exception) -> None:  # noqa: N805
        print(f"Error: {error}")


@register_adapter('calls')
@register_renderer(CallsRenderer)
class CallsAdapter(ResourceAdapter):
    """Adapter for cross-file call graph queries via calls:// URIs.

    Examples:
        calls://src/?target=validate_item
        calls://src/?target=process_batch&depth=2
        calls://src/?target=main&format=dot
    """

    BUDGET_LIST_FIELD = 'levels'

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for calls:// adapter."""
        return _HELP

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for calls:// adapter."""
        return _SCHEMA

    def __init__(self, path: str, query_string: Optional[str] = None):
        expanded = os.path.expanduser(path)  # raises TypeError for non-str path (contract)
        qs = query_string if isinstance(query_string, str) else ''
        self.query_params = parse_query_params(qs, coerce=True)
        # Support 'path:target' colon shorthand (e.g. calls://src/file.py:my_fn).
        # Only apply when the portion before ':' is an existing path and the portion
        # after ':' looks like a bare name (no slashes → not a file path).
        if ':' in expanded and '?' not in expanded:
            before, _, after = expanded.rpartition(':')
            if after and '/' not in after and os.path.exists(before):
                if not self.query_params.get('target') and not self.query_params.get('callees'):
                    self.query_params['target'] = after
                self.path = before
                return
        self.path = expanded

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        target = self.query_params.get('target', '')
        callees_target = self.query_params.get('callees', '')
        rank = self.query_params.get('rank', '')
        uncalled = self.query_params.get('uncalled', False)

        if rank == 'callers':
            top = int(self.query_params.get('top', 10))
            include_builtins = bool(self.query_params.get('builtins', False))
            result_data = rank_by_callers(self.path, top=top, include_builtins=include_builtins)
            result_data['path'] = self.path
            return ResultBuilder.create(
                result_type='calls_ranking',
                source=self.path,
                contract_version='1.1',
                data=result_data,
            )

        if uncalled:
            top = int(self.query_params.get('top', 0))
            type_filter = self.query_params.get('type', '')
            only_functions = type_filter == 'function'
            result_data = find_uncalled(self.path, only_functions=only_functions, top=top)
            query_format = self.query_params.get('format', '')
            if query_format:
                result_data['_query_format'] = query_format
            return ResultBuilder.create(
                result_type='calls_uncalled',
                source=self.path,
                contract_version='1.1',
                data=result_data,
            )

        if not target and not callees_target:
            return ResultBuilder.create(
                result_type='calls_query',
                source=self.path,
                contract_version='1.1',
                data={
                    'path': self.path,
                    'error': "Missing required parameter: target=<name>, callees=<name>, or rank=callers",
                    'example': f"calls://{self.path}?target=my_function",
                }
            )

        query_format = self.query_params.get('format', '')

        if callees_target:
            include_builtins = bool(self.query_params.get('builtins', False))
            result_data = find_callees(self.path, callees_target, include_builtins=include_builtins)
            result_data['path'] = self.path
            if query_format:
                result_data['_query_format'] = query_format
            return ResultBuilder.create(
                result_type='calls_callees',
                source=self.path,
                contract_version='1.1',
                data=result_data,
            )

        depth = int(self.query_params.get('depth', '1'))
        depth = max(1, min(depth, 5))  # cap at 5 to avoid runaway transitive walks
        result_data = find_callers(self.path, target, depth=depth)
        result_data['path'] = self.path

        # Store query-string format so renderer can apply dot/json regardless
        # of what the CLI --format flag is set to.
        if query_format:
            result_data['_query_format'] = query_format

        return ResultBuilder.create(
            result_type='calls_query',
            source=self.path,
            contract_version='1.1',
            data=result_data,
        )
