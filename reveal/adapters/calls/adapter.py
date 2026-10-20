"""calls:// adapter — cross-file call graph queries.

Supported URIs (one mode per request; ``reveal calls <path> --target NAME`` is the same request):

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
import sys
from typing import Any, Dict, List, Optional, Tuple
from reveal.reveal_types import CONTRACT_VERSION, RevealResult

from ..base import ResourceAdapter, register_adapter, register_renderer
from .confidence import build_meta as _call_graph_meta
from .index import (find_callers, find_callees, find_uncalled, rank_by_callers, build_module_dependency_graph,
                    walk_callees, callee_levels)
from .renderer import render_calls_structure
from ...utils.query_binding import bind_declared_params, boolean_value
from ...utils.query_parser import (CliBinding, ParamSpec, ParamValueError, QueryParams, ResourceSpec,
                                   clamped_whole, nonempty_scalar, nonnegative_display_limit, param_schema,
                                   peek_query_items)
from ...utils.results import ResultBuilder, note_truncation


def _name_value(name: str):
    """A function-name parameter: any nonempty string, never coerced (``target=123`` is a name)."""
    def convert(value: Any) -> str:
        if value is True:  # a bare `?callees` used to crash deep in the index (BACK-1488)
            raise ParamValueError(f"'{name}' needs a function name: {name}=<name>")
        return nonempty_scalar(value)
    return convert


def _calls_depth(value: Any) -> int:
    return clamped_whole(value, 1, 5)


def _calls_top(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('top requires a whole number, not a boolean')
    try:
        return nonnegative_display_limit(value)
    except ValueError as exc:  # its message names top and the rule (BACK-1839)
        raise ParamValueError(str(exc)) from None


def _name_spec(name: str, description: str, example: str) -> ParamSpec:
    return ParamSpec(name, 'string', description, None, _name_value(name), examples=(example,),
                     role='operation', uri_codec='percent', cli=CliBinding((f'--{name}',), metavar='NAME'))


def _flag_spec(name: str, description: str, role: str = 'analysis', dest: Optional[str] = None) -> ParamSpec:
    return ParamSpec(name, 'boolean', description, False, boolean_value, examples=(f'{name}=true',),
                     role=role, cli=CliBinding((f'--{name}',), dest=dest, action='store_true'))


_TARGET = _name_spec('target', 'Function name to find callers of (reverse lookup); calls://<path>:<name> is '
                     'shorthand when no other mode is given', 'target=validate_item')
_CALLEES = _name_spec('callees', 'Function name to find callees of: what every definition of it calls '
                      '(forward lookup, builtins hidden)', 'callees=validate_item')
_ROOT = _name_spec('root', 'Function name (or FILE:NAME) for a level-by-level callee walk, the walk trace:// '
                   'uses: each definition is expanded once, at the shallowest level it is reached, and every '
                   'call site of an expanded definition is an edge (call_expr), one to a definition already '
                   'reached with expanded: false. Totals count edges: total_edges = total_resolved (ambiguous '
                   'included, also counted in total_ambiguous) + total_unresolved', 'root=main')
_DEPTH = ParamSpec('depth', 'integer', 'Levels to walk, a signed whole integer clamped 1-5: callers for target '
                   '(default 1), the callee walk for root (default 2); other modes ignore it with a warning',
                   None, _calls_depth, examples=('depth=2',), role='analysis',
                   cli=CliBinding(('--depth',), metavar='N'))
_RANK = ParamSpec('rank', 'string', 'Rank every function by in-degree, most-called first (one value: callers)', None,
                  nonempty_scalar, examples=('rank=callers',), choices=('callers',), role='operation',
                  cli=CliBinding(('--rank',), metavar='callers'))
_TOP = ParamSpec('top', 'integer', 'Max entries for rank (default 10) or uncalled (default all); 0 = all; '
                 'other modes ignore it with a warning', None, _calls_top, examples=('top=20',), minimum=0,
                 zero_policy='all', role='analysis', cli=CliBinding(('--top',), metavar='N'))
_UNCALLED = _flag_spec('uncalled', 'List every function/method with no callers (dead-code candidates)',
                       role='operation')
_TYPE = ParamSpec('type', 'string', 'For uncalled: function (module-level functions only) or method', None,
                  nonempty_scalar, examples=('type=function',), choices=('function', 'method'), role='analysis',
                  cli=CliBinding(('--type',), metavar='KIND'))
_MODULES = _flag_spec('modules', 'Module-level dependency graph instead of function-level', role='operation')
_EXTERNAL = _flag_spec('external', 'Include external (non-project) modules in the modules graph')
_BUILTINS = _flag_spec('builtins', 'Include language builtins (len, str, ValueError, ...) in callees, root and '
                       'rank output (default: false)')
_TEST_FRAMEWORK = _flag_spec('test-framework', 'Include test-framework entrypoints: as callers in rank, and as '
                             'dead-code candidates in uncalled (default: false)', dest='test_framework')
_FORMAT = ParamSpec('format', 'string', 'URI output override: text, json or dot (Graphviz; dot has no --format '
                    'spelling)', None, nonempty_scalar, examples=('format=dot',), choices=('text', 'json', 'dot'),
                    role='presentation')

_RESOURCE = ResourceSpec(uri_codec='existing-path-first')
_PARAM_SPECS = (_TARGET, _CALLEES, _ROOT, _DEPTH, _RANK, _TOP, _UNCALLED, _TYPE, _MODULES, _EXTERNAL,
               _BUILTINS, _TEST_FRAMEWORK, _FORMAT)

# The mode selectors: exactly one per request. The order is the one messages name them in.
_MODES = ('target', 'callees', 'root', 'rank', 'uncalled', 'modules')
# The result type each mode answers with. A rejected request with several modes is typed by the
# first of them in this order, the precedence get_structure applied before modes were exclusive.
_MODE_TYPES = {'modules': 'calls_module_graph', 'rank': 'calls_ranking', 'uncalled': 'calls_uncalled',
               'root': 'calls_callees_recursive', 'callees': 'calls_callees', 'target': 'calls_query'}
_MISSING_MODE = ('Missing required parameter: target=<name>, callees=<name>, root=<name>, rank=callers, '
                 'uncalled or modules')


def _selects(name: str, value: Any) -> bool:
    """Whether a supplied mode key selects its mode: ``uncalled=false`` does not."""
    if name in ('uncalled', 'modules'):
        return not (value is False or isinstance(value, str) and value.strip().lower() in ('false', 'no', '0'))
    return True


def _selected_modes(params: Any) -> List[str]:
    """The modes a request selects, read without counting any key as applied."""
    supplied = dict(peek_query_items(params))
    return [name for name in _MODES if name in supplied and _selects(name, supplied[name])]


_HELP: Dict[str, Any] = {
    'name': 'calls',
    'description': 'Cross-file call graph queries — find callers or callees of any function.',
    'syntax': 'calls://<path>?target=<function>[&depth=N][&format=dot|json]\n'
              '         calls://<path>?callees=<function>\n'
              '         calls://<path>:<function>           # shorthand — infers ?target=<function>\n'
              '         reveal calls <path> --target NAME | --callees NAME | --root NAME [--depth N] | '
              '--rank callers [--top N] | --uncalled | --modules',
    'parameters': {spec.name: spec.description for spec in _PARAM_SPECS},
    'epilog': 'One mode per request: --target, --callees, --root, --rank, --uncalled or --modules '
              '(calls://<path>?target=NAME and the rest are the same request). Two modes exit 2.',
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
        'Callers indexes use directory-mtime and scope keys; these do not detect every file change.',
        'Callee names are normalised: "self.foo" → "foo" for index lookup.',
        'depth=N expands callers transitively up to N levels (capped at 5).',
        '?callees=X finds every definition of X and shows what it calls — useful for multi-file functions.',
        '?uncalled: web/CLI framework routes (Flask, FastAPI, Click, …) are dispatched by the '
        'framework, not a static call, so they false-flag as dead code by default. Declare '
        'project-specific entry-point decorators in .reveal.yaml to exclude them: '
        'adapters.calls.entry_points.decorators: [route, get, post, command].',
        'One mode per request: target, callees, root, rank, uncalled or modules; two exit 2 and name both. '
        'A malformed value (depth=abc, top=-1, rank=other) exits 2 naming the parameter; names are never '
        'coerced (target=123 is the name 123).',
        'Exit codes: 0 complete; 2 rejected before analysis (bad request, missing path); 3 required analysis '
        'or output incomplete (a file or directory could not be read; the answer is still printed). '
        '--fail-on accepts none only.',
    ],
    'see_also': [
        'reveal calls <path> --target NAME - CLI subcommand form, same parameters',
        'reveal help://patches - Test churn + call-graph together identifies blast radius',
        'dot -Tsvg - Render ?format=dot output with Graphviz (external tool)',
    ],
    'output_formats': ['text', 'json'],
}

_SCHEMA: Dict[str, Any] = {
    'adapter': 'calls',
    'description': 'Cross-file call graph — who calls X (?target) or what does X call (?callees)?',
    'uri_syntax': 'calls://<path>?target=<name>[&depth=N][&format=text|dot|json]\n'
                  '             calls://<path>:<name>  # shorthand — infers ?target=<name>\n'
                  '             reveal calls <path> --target NAME  # same request, generated from query_params',
    'resource': _RESOURCE.schema(),
    'execution_policy': {'default_fail_on': 'none', 'fail_on': ['none']},
    'query_params': param_schema(_PARAM_SPECS),
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
        {
            'type': 'calls_callees_recursive',
            'description': 'Callee walk from ?root: every edge by level, each definition expanded once at the '
                           'shallowest level it is reached',
            'schema': {
                'type': 'object',
                'properties': {
                    'root':             {'type': 'string'},
                    'depth':            {'type': 'integer'},
                    'total_edges':      {'type': 'integer'},
                    'total_resolved':   {'type': 'integer'},
                    'total_unresolved': {'type': 'integer'},
                    'total_ambiguous':  {'type': 'integer'},
                    'levels': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'level':   {'type': 'integer'},
                                'callees': {'type': 'array', 'items': {'type': 'object', 'properties': {
                                    'caller': {'type': 'string'}, 'caller_file': {'type': 'string'},
                                    'caller_line': {'type': 'integer'}, 'call_expr': {'type': 'string'},
                                    'callee': {'type': 'string'}, 'resolved': {'type': 'boolean'},
                                    'callee_file': {'type': 'string'}, 'callee_line': {'type': 'integer'},
                                    'expanded': {'type': 'boolean'}, 'ambiguous': {'type': 'boolean'},
                                    'candidates': {'type': 'array'}}}},
                            },
                        },
                    },
                },
            },
        },
        # BACK-1000: uncalled/rank/modules were live ResultBuilder result_types
        # (get_structure() above) with no matching output_types entry — any
        # recipe/consumer declaring these against the schema silently failed
        # validation. Minimal entries (no full example payload) close the gap;
        # expand if a consumer needs the detailed shape.
        {
            'type': 'calls_uncalled',
            'description': 'Statically-uncalled functions/files (?uncalled=true) — dead-code candidates',
        },
        {
            'type': 'calls_ranking',
            'description': 'Files/functions ranked by caller count (?rank=callers)',
        },
        {
            'type': 'calls_module_graph',
            'description': 'Module-level dependency graph derived from call relationships (?modules=true)',
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
        'Callers indexes use directory-mtime and scope keys; these do not detect every file change.',
        'Callee names are normalised: "self.foo" → "foo" for lookup; full dotted form also indexed.',
        '?target depth=N expands callers transitively up to N levels (capped at 5).',
        '?callees=X scans all definitions of X — useful when the name appears in multiple files.',
        '?callees hides Python builtins by default (len, str, sorted, ValueError, etc.); use ?builtins=true to include them.',
        '?root: every call site of an expanded definition is an edge with call_expr; expanded is false when its '
        'target was already reached at a shallower or earlier level. total_edges = total_resolved + total_unresolved; '
        'total_ambiguous counts the resolved edges with several candidate definitions.',
        'Exactly one mode per request (target, callees, root, rank, uncalled, modules), else exit 2 naming both. '
        'Exit 0 complete, 2 rejected before analysis, 3 required analysis or output failed or incomplete.',
    ],
}


# What each answer must carry for its renderer and for the D6 outcome: the name it answers for,
# its lists and its counts. The observation count tells usable incomplete evidence from none.
_ANSWER_FIELDS: Dict[str, Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]] = {
    'calls_query': (('target',), ('levels',), ('total_callers',)),
    'calls_callees': (('target',), ('matches',), ('total_calls',)),
    'calls_callees_recursive': (('root',), ('levels',),
                                ('total_edges', 'total_resolved', 'total_unresolved', 'total_ambiguous')),
    'calls_ranking': ((), ('entries',), ('total_unique_callees',)),
    'calls_uncalled': ((), ('entries',), ('total_uncalled',)),
    'calls_module_graph': ((), ('nodes', 'edges'), ('total_nodes', 'total_edges')),
}
# Required evidence lost to an unreadable file or directory (confidence.build_meta).
_LOSS_WARNINGS = frozenset({'analysis_failed', 'analysis_incomplete'})


def _calls_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _calls_usage_rejection(result: Dict[str, Any]) -> bool:
    """The adapter's own usage answer (no mode selected): an error and only invalid_request diagnostics."""
    meta = result.get('meta')
    errors = meta.get('errors') if isinstance(meta, dict) else None
    return (isinstance(result.get('error'), str) and bool(result['error']) and isinstance(errors, list)
            and bool(errors) and all(isinstance(e, dict) and e.get('code') == 'invalid_request' for e in errors))


def _calls_proof_error(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return 'Calls required answer must be an object'
    if _calls_usage_rejection(result):
        return None
    fields = _ANSWER_FIELDS.get(str(result.get('type')))
    if fields is None or result.get('error'):
        return 'Calls answer is not a completed calls result'
    names, lists, counts = fields
    if not all(isinstance(result.get(field), str) and result[field] for field in names):
        return 'Calls required name identity is missing or malformed'
    if not all(isinstance(result.get(field), list) for field in lists):
        return 'Calls required result lists are missing or malformed'
    if not all(_calls_count(result.get(field)) for field in counts):
        return 'Calls required totals are missing or malformed'
    if 'depth' in result and not (type(result['depth']) is int and 1 <= result['depth'] <= 5):
        return 'Calls required depth is missing or malformed'
    return None


def _calls_observations(result: Dict[str, Any]) -> int:
    if result['type'] == 'calls_callees':
        return len(result['matches'])
    count: int = result[_ANSWER_FIELDS[result['type']][2][0]]
    return count


def _calls_missing_evidence(result: Dict[str, Any]) -> bool:
    meta = result.get('meta') or {}
    if not isinstance(meta, dict):
        return True
    errors, warnings = meta.get('errors', []), meta.get('warnings', [])
    if not isinstance(errors, list) or not isinstance(warnings, list):
        return True
    return bool(errors) or any(isinstance(w, dict) and w.get('type') in _LOSS_WARNINGS for w in warnings)


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


@register_adapter('calls')
@register_renderer(CallsRenderer)
class CallsAdapter(ResourceAdapter):
    """Adapter for cross-file call graph queries via calls:// URIs.

    Examples:
        calls://src/?target=validate_item
        calls://src/?target=process_batch&depth=2
        calls://src/?target=main&format=dot
    """
    HELP_CLUSTER = 'Code Analysis'
    QUICK_RANK = 1

    BUDGET_LIST_FIELD = ('levels', 'entries')  # ?target= depth levels; ?rank=callers / ?uncalled entries (BACK-1497)
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    CLI_QUERY_FLAGS = {'all': 'top=1000000', 'limit': 'top={value}', 'respect_gitignore': 'respect_gitignore=false'}  # top= caps ?rank=callers/?uncalled (default 10; BACK-1379, BACK-1496)

    RESULT_TYPE = 'calls_query'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = _RESOURCE
    PARAM_SPECS = _PARAM_SPECS

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for calls:// adapter."""
        return _HELP

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for calls:// adapter."""
        return _SCHEMA

    def __init__(self, resource: str, query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        expanded = os.path.expanduser(resource)  # raises TypeError for non-str path (contract)
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(
                self.PARAM_SPECS, query if isinstance(query, str) else '', transport='uri')
        self._warn_unknown_query_params(self.query_params)  # BACK-507
        path, name = self._split_name_shorthand(expanded)
        if name and not _selected_modes(self.query_params):  # an explicit mode wins over path:name
            self.query_params.set_normalized(_TARGET, _TARGET.validate(name))
        self.path = path

    @staticmethod
    def result_type_for(params: Any) -> str:
        """The answer type the selected mode produces, from key presence before conversion."""
        modes = _selected_modes(params)
        return next((_MODE_TYPES[name] for name in _MODE_TYPES if name in modes), 'calls_query')

    @staticmethod
    def validate_request(params: Any, args: Any = None) -> None:
        """Exactly one mode per request: two used to resolve by a hidden precedence (BACK-2066)."""
        modes = _selected_modes(params)
        if len(modes) > 1:
            named = ', '.join(modes[:-1]) + ' and ' + modes[-1]
            raise ValueError(f'calls takes one mode per request, got {named}: choose one of '
                             f'{", ".join(_MODES)}')

    def answer_requirement_error(self, result: Any, expected_type: str, prior_facts: Any = None) -> Optional[str]:
        error = _calls_proof_error(result)
        if error or _calls_usage_rejection(result):
            return error
        supplied = dict(peek_query_items(self.query_params))
        kind = result['type']
        requested = {'calls_query': ('target', 'target', 1), 'calls_callees': ('target', 'callees', None),
                     'calls_callees_recursive': ('root', 'root', 2)}.get(kind)
        if requested is not None:
            field, key, depth = requested
            if result[field] != supplied.get(key) or (
                    depth is not None and result['depth'] != supplied.get('depth', depth)):
                return 'Calls answer identity differs from the validated request'
        return None

    @staticmethod
    def public_diagnostic(result: Dict[str, Any]) -> Optional[str]:
        return result['error'] if _calls_usage_rejection(result) else None

    @staticmethod
    def execution_facts(result: Any):
        from ...utils.results import (AnalysisCompleteness, FailureCause, failure_execution_facts,
                                      result_execution_facts)
        if _calls_proof_error(result):
            return failure_execution_facts(FailureCause.ANALYSIS)
        if _calls_usage_rejection(result):
            return failure_execution_facts(FailureCause.INVALID_REQUEST)
        state = AnalysisCompleteness.COMPLETE
        if _calls_missing_evidence(result):
            # The answer is a lower bound: usable when it still lists something, failed when not.
            state = (AnalysisCompleteness.INCOMPLETE if _calls_observations(result)
                     else AnalysisCompleteness.FAILED)
        return result_execution_facts(result, completeness=state)

    @staticmethod
    def _split_name_shorthand(resource: str) -> Tuple[str, Optional[str]]:
        """Split the 'path:target' colon shorthand (calls://src/file.py:my_fn).

        Only when the part before ':' is an existing path and the part after it
        looks like a bare name (no slashes, so not a file path)."""
        if ':' in resource and '?' not in resource:
            before, _, after = resource.rpartition(':')
            if after and '/' not in after and os.path.exists(before):
                return before, after
        return resource, None

    @classmethod
    def resource_path(cls, resource: str) -> str:
        """The path part of `path:name`, so the router's missing-path check does
        not reject the shorthand (BACK-1499)."""
        return cls._split_name_shorthand(os.path.expanduser(resource))[0]

    def _warn_top_ignored(self) -> None:
        """top= caps only ?rank=callers and ?uncalled; say so instead of ignoring it in
        silence -- `--limit N` arrives as top=N in every mode (BACK-1496). --all's own
        top= is exempt: lifting a cap the mode does not have is not worth a warning."""
        top = self.query_params.get('top')
        if top is None or str(top) == type(self).CLI_QUERY_FLAGS['all'].partition('=')[2]:
            return
        print("⚠ Query param 'top' (--limit) for calls:// only caps ?rank=callers and "
              "?uncalled — ignored; every result is shown.", file=sys.stderr)

    def _warn_depth_ignored(self, mode: str) -> None:
        """depth= walks ?target (callers) and ?root (callee tree) only; in any other
        mode it was dropped in silence, so `?callees=X&depth=3` read as a transitive
        answer (BACK-1504)."""
        if self.query_params.get('depth') is None:
            return
        hint = " -- use ?root=<name>&depth=N for callees level by level" if mode == 'callees' else ''
        print(f"⚠ Query param 'depth' for calls:// applies to ?target and ?root only, "
              f"not ?{mode} — ignored{hint}.", file=sys.stderr)

    def get_structure(self, **kwargs) -> RevealResult:
        self.validate_request(self.query_params)
        params = self.query_params
        # Every mode key is read here, whichever mode answers: the flag ledger counts each as applied.
        target, callees_target, root, rank = (spec.read(params) or '' for spec in (_TARGET, _CALLEES, _ROOT, _RANK))
        uncalled, modules = _UNCALLED.read(params), _MODULES.read(params)
        if modules:
            return self._module_graph()
        if rank == 'callers':
            return self._ranking()
        if uncalled:
            return self._uncalled()
        if root:
            return self._callee_walk(root)
        if not target and not callees_target:
            return self._missing_mode()
        query_format = _FORMAT.read(params) or ''
        self._warn_top_ignored()
        if callees_target:
            return self._callees(callees_target, query_format)
        return self._callers(target, query_format)

    def _answer(self, result_type: str, data: Dict[str, Any], *, query_format: str = '',
                uncalled: bool = False) -> RevealResult:
        """One envelope for every mode: the index's loss evidence becomes the shared meta warnings."""
        if query_format:
            # Query-string format= (dot/json) applies whatever the CLI --format flag says.
            data['_query_format'] = query_format
        return ResultBuilder.create(
            result_type=result_type,
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=data,
            **_call_graph_meta(self.path, uncalled=uncalled, skipped=data.pop('analysis_skipped', ()),
                               traversal_failures=data.pop('analysis_traversal_failures', ())),
        )

    def _module_graph(self) -> RevealResult:
        self._warn_top_ignored()
        self._warn_depth_ignored('modules')
        data = build_module_dependency_graph(self.path, include_external=_EXTERNAL.read(self.query_params))
        return self._answer('calls_module_graph', data, query_format=_FORMAT.read(self.query_params) or '')

    def _ranking(self) -> RevealResult:
        self._warn_depth_ignored('rank')
        params = self.query_params
        top = _TOP.read(params)
        data = rank_by_callers(self.path, top=10 if top is None else top,
                               include_builtins=_BUILTINS.read(params),
                               include_test_framework=_TEST_FRAMEWORK.read(params))
        data['path'] = self.path
        result = self._answer('calls_ranking', data)
        # BACK-1543: 'top'/'total_unique_callees' said it; the marker is what gets printed.
        note_truncation(result, 'entries', len(data['entries']), data['total_unique_callees'], 'limit',
                        hint='raise ?top=N')
        return result

    def _uncalled(self) -> RevealResult:
        self._warn_depth_ignored('uncalled')
        params = self.query_params
        top = _TOP.read(params)
        data = find_uncalled(self.path, only_functions=_TYPE.read(params) == 'function',
                             top=0 if top is None else top,
                             include_test_framework=_TEST_FRAMEWORK.read(params))
        result = self._answer('calls_uncalled', data, query_format=_FORMAT.read(params) or '', uncalled=True)
        note_truncation(result, 'entries', len(data['entries']), data['total_uncalled'], 'limit',
                        hint='raise ?top=N')
        return result

    def _callee_walk(self, root: str) -> RevealResult:
        self._warn_top_ignored()
        params = self.query_params
        depth = _DEPTH.read(params)
        data = callee_levels(walk_callees(self.path, root, depth=2 if depth is None else depth,
                                          include_builtins=_BUILTINS.read(params)))
        data['path'] = self.path
        return self._answer('calls_callees_recursive', data, query_format=_FORMAT.read(params) or '')

    def _missing_mode(self) -> RevealResult:
        """Usage, not analysis: D6 exits 2 (it exited 1 before calls was declared, BACK-2066)."""
        return ResultBuilder.create(
            result_type='calls_query',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data={'path': self.path, 'error': _MISSING_MODE,
                  'example': f"calls://{self.path}?target=my_function"},
            errors=[{'code': 'invalid_request', 'message': _MISSING_MODE}],
            **_call_graph_meta(self.path),
        )

    def _callees(self, name: str, query_format: str) -> RevealResult:
        self._warn_depth_ignored('callees')
        data = find_callees(self.path, name, include_builtins=_BUILTINS.read(self.query_params))
        data['path'] = self.path
        return self._answer('calls_callees', data, query_format=query_format)

    def _callers(self, name: str, query_format: str) -> RevealResult:
        depth = _DEPTH.read(self.query_params)
        data = find_callers(self.path, name, depth=1 if depth is None else depth)
        data['path'] = self.path
        return self._answer('calls_query', data, query_format=query_format)
