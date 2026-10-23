"""calls:// adapter — cross-file call graph queries.

Supported URIs (one mode per request; ``reveal calls <path> --callers NAME`` is the same request):

    calls://src/?callers=validate_item           # who calls validate_item? (target= is its older name)
    calls://src/?callers=validate_item&depth=2  # callers-of-callers too
    calls://src/?callers=validate_item&format=dot  # graphviz dot output
    calls://src/?callees=validate_item&depth=2  # what it calls, level by level

The adapter builds a project-level callers index from the code under *path*,
then looks up the requested name.  Results are cached per-directory with
mtime-based invalidation.

Limitations (static analysis):
- Dynamic dispatch (callbacks, metaclasses) is not resolved.
- Method resolution order (MRO) is not considered.
- Builtins and stdlib calls appear in raw call lists but will rarely be
  targets anyone queries for.
"""

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from reveal.reveal_types import CONTRACT_VERSION, RevealResult

from ..base import ResourceAdapter, register_adapter, register_renderer
from .confidence import build_meta as _call_graph_meta
from .index import (find_callers, find_callees, find_uncalled, rank_by_callers, build_module_dependency_graph,
                    walk_callees, callee_levels, callee_source, CalleeWalk, _bare_callee_name, _split_root)
from ..ast.analysis import collect_structures
from ...core.definition_names import name_matches
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
                     role='operation', uri_codec='percent', names='symbol',
                     cli=CliBinding((f'--{name}',), metavar='NAME'))


def _flag_spec(name: str, description: str, role: str = 'analysis', dest: Optional[str] = None) -> ParamSpec:
    return ParamSpec(name, 'boolean', description, False, boolean_value, examples=(f'{name}=true',),
                     role=role, cli=CliBinding((f'--{name}',), dest=dest, action='store_true'))


_CALLERS = _name_spec('callers', 'Function name to find callers of (reverse lookup): a bare NAME, since the '
                      'callers index has no file filter (FILE:NAME exits 2); calls://<path>:<name> is shorthand '
                      'when no mode is given', 'callers=validate_item')
_TARGET = _name_spec('target', 'Retired name of callers=: the same mode and answer, with a replaced-by note',
                     'target=validate_item')
_CALLEES = _name_spec('callees', 'Function name, or FILE:NAME for one file\'s definitions, to find callees of: '
                      'at depth 1 what every definition calls (matches); at depth 2-5 a level-by-level walk '
                      '(levels, definitions), each definition expanded once at its shallowest level, every call '
                      'site an edge; builtins hidden', 'callees=validate_item')
_ROOT = _name_spec('root', 'Retired (use callees=NAME&depth=N, the same walk; prints a replaced-by note): '
                   'function name (or FILE:NAME) for a level-by-level callee walk: each definition is '
                   'expanded once, at the shallowest level it is reached, and every '
                   'call site of an expanded definition is an edge (call_expr), one to a definition already '
                   'reached with expanded: false. Totals count edges: total_edges = total_resolved (ambiguous '
                   'included, also counted in total_ambiguous) + total_unresolved', 'root=main')
_DEPTH = ParamSpec('depth', 'integer', 'Levels to walk, a signed whole integer clamped 1-5: callers (default 1), '
                   'callees (default 1; beyond 1 is not measured, W-CALLS-9), the retired root '
                   '(default 2); other modes ignore it with a warning',
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
_BUILTINS = _flag_spec('builtins', 'Include language builtins (len, str, ValueError, ...) in callees (every '
                       'depth), root and rank output (default: false)')
_DETAIL = _flag_spec('detail', 'Callees only: add params and effects to every definition the walk reaches '
                     '(not measured, W-CALLS-9); with another mode it exits 2')
_TEST_FRAMEWORK = _flag_spec('test-framework', 'Include test-framework entrypoints: as callers in rank, and as '
                             'dead-code candidates in uncalled (default: false)', dest='test_framework')
_FORMAT = ParamSpec('format', 'string', 'URI output override: text, json or dot (Graphviz; dot has no --format '
                    'spelling)', None, nonempty_scalar, examples=('format=dot',), choices=('text', 'json', 'dot'),
                    role='presentation')

_RESOURCE = ResourceSpec(uri_codec='existing-path-first')
_PARAM_SPECS = (_CALLERS, _TARGET, _CALLEES, _ROOT, _DEPTH, _DETAIL, _RANK, _TOP, _UNCALLED, _TYPE, _MODULES,
                _EXTERNAL, _BUILTINS, _TEST_FRAMEWORK, _FORMAT)

# The mode selectors: exactly one per request. The order is the one messages name them in;
# target is callers under its older name, and naming both is two selectors too.
_MODES = ('callers', 'target', 'callees', 'root', 'rank', 'uncalled', 'modules')
# The result type each mode answers with. A rejected request with several modes is typed by the
# first of them in this order, the precedence get_structure applied before modes were exclusive.
_MODE_TYPES = {'modules': 'calls_module_graph', 'rank': 'calls_ranking', 'uncalled': 'calls_uncalled',
               'root': 'calls_callees_recursive', 'callees': 'calls_callees', 'target': 'calls_query',
               'callers': 'calls_query'}
_MISSING_MODE = ('Missing required parameter: callers=<name> (or target=<name>), callees=<name>, root=<name>, '
                 'rank=callers, uncalled or modules')
_PRESENCE_FLAGS = ('uncalled', 'modules', 'detail')


def _selects(name: str, value: Any) -> bool:
    """Whether a supplied mode key selects its mode: ``uncalled=false`` does not."""
    if name in _PRESENCE_FLAGS:
        return not (value is False or isinstance(value, str) and value.strip().lower() in ('false', 'no', '0'))
    return True


def _selected_modes(params: Any) -> List[str]:
    """The modes a request selects, read without counting any key as applied."""
    supplied = dict(peek_query_items(params))
    return [name for name in _MODES if name in supplied and _selects(name, supplied[name])]


_HELP: Dict[str, Any] = {
    'name': 'calls',
    'description': 'Cross-file call graph queries — find callers or callees of any function.',
    'syntax': 'calls://<path>?callers=<function>[&depth=N][&format=dot|json]\n'
              '         calls://<path>?callees=<function>|<file>:<function>[&depth=N][&detail]\n'
              '         calls://<path>:<function>           # shorthand — infers ?callers=<function>\n'
              '         reveal calls <path> --callers NAME [--depth N] | --callees NAME [--depth N] [--detail] | '
              '--rank callers [--top N] | --uncalled | --modules',
    'parameters': {spec.name: spec.description for spec in _PARAM_SPECS},
    'epilog': 'One mode per request: --callers, --callees, --rank, --uncalled or --modules '
              '(calls://<path>?callers=NAME and the rest are the same request). Two modes exit 2. A callee '
              'walk beyond depth 1 and --detail are not measured (W-CALLS-9). The retired --target and --root '
              '(?target=, ?root=) still answer, with a note naming --callers and --callees NAME --depth N.',
    'examples': [
        {'uri': 'calls://src/?callers=validate_item',
         'description': 'Who calls validate_item? (reverse lookup)'},
        {'uri': 'calls://src/main.py:main',
         'description': 'Shorthand — who calls main? (colon infers ?callers=main)'},
        {'uri': 'calls://src/?callers=process_batch&depth=2',
         'description': 'Callers-of-callers too (transitive, 2 levels)'},
        {'uri': 'calls://src/?callees=validate_item',
         'description': 'What does validate_item call? (forward lookup, builtins hidden)'},
        {'uri': 'calls://src/?callees=validate_item&depth=2&detail',
         'description': 'What those call too, level by level, with params and effects (not measured: W-CALLS-9)'},
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
        {'uri': 'calls://src/?callers=main&format=dot',
         'description': 'Output callers graph as Graphviz dot (pipe to dot -Tsvg)'},
        {'uri': 'calls://src/?callers=main&format=json',
         'description': 'Machine-readable callers result'},
    ],
    'notes': [
        'Static analysis only — dynamic dispatch (callbacks, metaclasses) is not resolved.',
        'Callers indexes use directory-mtime and scope keys; these do not detect every file change.',
        'Callee names are normalised: "self.foo" → "foo" for index lookup.',
        'depth=N expands callers transitively up to N levels (capped at 5).',
        '?callees=X finds every definition of X and shows what it calls — useful for multi-file functions. '
        'depth=2-5 walks level by level under the same calls_callees type (levels, definitions, edge totals, '
        'walk_rule and a Rule: line); &detail adds params and effects. Neither is measured in any language '
        '(W-CALLS-9).',
        'A scanned language that yields call sources and has no recall snapshot (Elixir, Objective-C) withholds '
        'meta.confidence and is named (W-CALLS-10); shell, SQL and other files with no call edges do not. '
        '?uncalled over JavaScript, TypeScript or TSX withholds it too (W-CALLS-11): dead-code precision was '
        'measured low there.',
        '?uncalled: web/CLI framework routes (Flask, FastAPI, Click, …) are dispatched by the '
        'framework, not a static call, so they false-flag as dead code by default. Declare '
        'project-specific entry-point decorators in .reveal.yaml to exclude them: '
        'adapters.calls.entry_points.decorators: [route, get, post, command].',
        'One mode per request: callers (or target, its older name), callees, root, rank, uncalled or modules; '
        'two exit 2 and name both, and so does the path:name shorthand with an explicit mode. '
        'A malformed value (depth=abc, top=-1, rank=other), callers=FILE:NAME or detail outside callees exits 2 '
        'naming the parameter; names are never coerced (callers=123 is the name 123).',
        'Exit codes: 0 complete; 2 rejected before analysis (bad request, missing path) or a name that names '
        'nothing (callees: no definition; callers: no definition and no call site); 3 required analysis '
        'or output incomplete (a file or directory could not be read; the answer is still printed). '
        '--fail-on accepts none only.',
    ],
    'see_also': [
        'reveal calls <path> --callers NAME - CLI subcommand form, same parameters',
        'reveal help://patches - Test churn + call-graph together identifies blast radius',
        'dot -Tsvg - Render ?format=dot output with Graphviz (external tool)',
    ],
    'output_formats': ['text', 'json'],
}

_SCHEMA: Dict[str, Any] = {
    'adapter': 'calls',
    'description': 'Cross-file call graph — who calls X (?callers) or what does X call (?callees)?',
    'uri_syntax': 'calls://<path>?callers=<name>[&depth=N][&format=text|dot|json]\n'
                  '             calls://<path>?callees=<name>|<file>:<name>[&depth=N][&detail]\n'
                  '             calls://<path>:<name>  # shorthand — infers ?callers=<name>\n'
                  '             reveal calls <path> --callers NAME  # same request, generated from query_params',
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
            'description': 'Callees result — functions/methods called by the target. depth 1: matches only; '
                           'depth 2-5 or detail add the callee walk (depth, levels, definitions, edge totals, '
                           'walk_rule), each definition expanded once at its shallowest level',
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
                    'depth':            {'type': 'integer'},
                    'levels':           {'type': 'array', 'items': {'type': 'object', 'properties': {
                        'level': {'type': 'integer'}, 'callees': {'type': 'array'}}}},
                    'definitions':      {'type': 'array', 'items': {'type': 'object', 'properties': {
                        'name': {'type': 'string'}, 'file': {'type': 'string'}, 'line': {'type': 'integer'},
                        'level': {'type': 'integer'}, 'expanded': {'type': 'boolean'},
                        'params': {'type': 'array'}, 'effects': {'type': 'array'}}}},
                    'total_edges':      {'type': 'integer'},
                    'total_resolved':   {'type': 'integer'},
                    'total_unresolved': {'type': 'integer'},
                    'total_ambiguous':  {'type': 'integer'},
                    'walk_rule':        {'type': 'object', 'properties': {
                        'direction': {'type': 'string'}, 'expansion': {'type': 'string'},
                        'edges': {'type': 'string'}, 'resolution': {'type': 'array'},
                        'builtins': {'type': 'string'}, 'depth': {'type': 'integer'},
                        'measured': {'type': 'object'}, 'unmeasured_languages': {'type': 'array'},
                        'text': {'type': 'string'}}},
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
            'description': 'Callee walk from the retired ?root (use ?callees=X&depth=N): every edge by level, '
                           'each definition expanded once at the '
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
            'uri': 'calls://src/?callers=validate_item',
            'description': 'Who calls validate_item? (reverse lookup across whole project)',
            'output_type': 'calls_query',
        },
        {
            'uri': 'calls://src/?callers=validate_item&depth=2',
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
            'uri': 'calls://src/?callees=validate_item&depth=3',
            'description': 'Callee walk, level by level (not measured beyond depth 1: W-CALLS-9)',
            'output_type': 'calls_callees',
        },
        {
            'uri': 'calls://src/?callers=main&format=dot',
            'description': 'Export callers graph as Graphviz dot format',
            'output_type': 'calls_query',
        },
        {
            'uri': 'calls://src/?callers=main&format=json',
            'description': 'Machine-readable callers result',
            'output_type': 'calls_query',
        },
    ],
    'notes': [
        'Static analysis only — dynamic dispatch, callbacks, and metaclasses are not resolved.',
        'Callers indexes use directory-mtime and scope keys; these do not detect every file change.',
        'Callee names are normalised: "self.foo" → "foo" for lookup; full dotted form also indexed.',
        '?callers depth=N expands callers transitively up to N levels (capped at 5).',
        'Every callers and callees answer carries walk_rule (its counting rule; text is the Rule: line); '
        'callers measure levels 1 and 2, callees level 1.',
        '?callees=X scans all definitions of X — useful when the name appears in multiple files.',
        '?callees hides Python builtins by default (len, str, sorted, ValueError, etc.); use ?builtins=true to include them.',
        '?root (retired; ?callees=X&depth=N is the same walk): every call site of an expanded definition is an '
        'edge with call_expr; expanded is false when its '
        'target was already reached at a shallower or earlier level. total_edges = total_resolved + total_unresolved; '
        'total_ambiguous counts the resolved edges with several candidate definitions.',
        '?callees depth=2-5 and detail: the callee walk under calls_callees, every call site of an expanded '
        'definition an edge; not measured in any language (W-CALLS-9 in meta.warnings, walk_rule.measured).',
        'A call-source language with no recall snapshot in scope: no meta.confidence, W-CALLS-10 names it (languages). '
        '?uncalled over JS/TS/TSX: no meta.confidence, W-CALLS-11 names the language and the measured precision.',
        'Exactly one mode per request (callers, callees, rank, uncalled, modules, or the retired target and '
        'root), else exit 2 '
        'naming both. Exit 0 complete, 2 rejected before analysis or a name with no definition (callers: and '
        'no call site), 3 required analysis or output failed or incomplete.',
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
# A name answer that can prove absence: the field it names and its observation count.
_ABSENCE_TYPES = frozenset({'calls_query', 'calls_callees'})
_WALK_TOTALS = ('total_edges', 'total_resolved', 'total_unresolved', 'total_ambiguous')


def _calls_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _calls_usage_rejection(result: Dict[str, Any]) -> bool:
    """The adapter's own usage answer (no mode selected): an error and only invalid_request diagnostics."""
    meta = result.get('meta')
    errors = meta.get('errors') if isinstance(meta, dict) else None
    return (isinstance(result.get('error'), str) and bool(result['error']) and isinstance(errors, list)
            and bool(errors) and all(isinstance(e, dict) and e.get('code') == 'invalid_request' for e in errors))


def _calls_absence_message(result: Dict[str, Any]) -> str:
    return f"Function '{result['target']}' not found in {result['path']}"


def _calls_proof_error(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return 'Calls required answer must be an object'
    if _calls_usage_rejection(result):
        return None
    fields = _answer_fields(result)
    if fields is None:
        return 'Calls answer is not a completed calls result'
    names, lists, counts = fields
    if not all(isinstance(result.get(field), str) and result[field] for field in names):
        return 'Calls required name identity is missing or malformed'
    if not all(isinstance(result.get(field), list) for field in lists):
        return 'Calls required result lists are missing or malformed'
    if not all(_calls_count(result.get(field)) for field in counts):
        return 'Calls required totals are missing or malformed'
    return _calls_depth_or_error(result)


def _calls_depth_or_error(result: Dict[str, Any]) -> Optional[str]:
    """A depth outside 1-5, or an error that is not the canonical absence of the answer's name."""
    if 'depth' in result and not (type(result['depth']) is int and 1 <= result['depth'] <= 5):
        return 'Calls required depth is missing or malformed'
    if result.get('error') and not _calls_absence_claimed(result):
        return 'Calls answer is not a completed calls result'
    return None


def _answer_fields(result: Dict[str, Any]) -> Optional[Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[str, ...]]]:
    """The names, lists and counts this answer type must carry; the callee walk (depth 2-5,
    detail) adds its levels, definitions and edge totals to calls_callees."""
    fields = _ANSWER_FIELDS.get(str(result.get('type')))
    if fields is None or result.get('type') != 'calls_callees' or 'levels' not in result:
        return fields
    names, lists, counts = fields
    return names, (*lists, 'levels', 'definitions'), (*counts, *_WALK_TOTALS)


def _calls_absence_claimed(result: Dict[str, Any]) -> bool:
    """The answer says its name has no definition: the canonical message on an empty answer."""
    return (result.get('type') in _ABSENCE_TYPES and isinstance(result.get('path'), str)
            and result.get('error') == _calls_absence_message(result) and _calls_observations(result) == 0)


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


def _calls_absent(result: Any) -> bool:
    """A complete answer for a name with no definition (decision d, trace's BACK-1996 rule): usage, exit 2.
    Lost evidence keeps it a failed answer (exit 3); a tree gitignore hid is never absent."""
    if _calls_proof_error(result) or _calls_usage_rejection(result) or not _calls_absence_claimed(result):
        return False
    hidden = any(isinstance(w, dict) and w.get('type') == 'scope_hidden'
                 for w in (result.get('meta') or {}).get('warnings', []))
    return not hidden and not _calls_missing_evidence(result)


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
        calls://src/?callers=validate_item
        calls://src/?callers=process_batch&depth=2
        calls://src/?callees=main&depth=2&detail
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
        # path:name is the callers mode: with an explicit mode it is a second one (BACK-2102).
        self._shorthand_conflict = resource if name and _selected_modes(self.query_params) else None
        if name and not self._shorthand_conflict:
            self.query_params.set_normalized(_TARGET, _TARGET.validate(name))
        self.path = path

    @staticmethod
    def result_type_for(params: Any) -> str:
        """The answer type the selected mode produces, from key presence before conversion."""
        modes = _selected_modes(params)
        return next((_MODE_TYPES[name] for name in _MODE_TYPES if name in modes), 'calls_query')

    @staticmethod
    def validate_request(params: Any, args: Any = None) -> None:
        """Exactly one mode per request: two used to resolve by a hidden precedence (BACK-2066).
        callers takes no FILE:NAME and detail belongs to callees: both would be new capabilities."""
        modes = _selected_modes(params)
        if len(modes) > 1:
            named = ', '.join(modes[:-1]) + ' and ' + modes[-1]
            raise ValueError(f'calls takes one mode per request, got {named}: choose one of '
                             f'{", ".join(_MODES)} (target is the older name of callers)')
        supplied = dict(peek_query_items(params))
        for key in ('callers', 'target'):
            value = supplied.get(key)
            if isinstance(value, str) and _split_root(value)[0]:
                raise ValueError(f'{key}={value}: callers takes a bare NAME, not FILE:NAME; the callers index '
                                 f'has no file filter (callees=FILE:NAME selects one file\'s definitions)')
        if modes and modes[0] != 'callees' and 'detail' in supplied and _selects('detail', supplied['detail']):
            raise ValueError(f'detail applies to callees only, not {modes[0]}: '
                             f'calls://<path>?callees=NAME&detail adds params and effects')

    def answer_requirement_error(self, result: Any, expected_type: str, prior_facts: Any = None) -> Optional[str]:
        error = _calls_proof_error(result)
        if error or _calls_usage_rejection(result):
            return error
        from ...utils.results import AnalysisCompleteness, FailureCause
        supplied = dict(peek_query_items(self.query_params))
        kind = result['type']
        requested = {'calls_query': ('target', ('callers', 'target'), 1), 'calls_callees': ('target', ('callees',), 1),
                     'calls_callees_recursive': ('root', ('root',), 2)}.get(kind)
        if requested is not None:
            field, keys, depth = requested
            name = next((supplied[key] for key in keys if key in supplied), None)
            if result[field] != name or ('depth' in result and result['depth'] != supplied.get('depth', depth)):
                return 'Calls answer identity differs from the validated request'
        if _calls_absent(result) and prior_facts is not None:
            prior_usage = (prior_facts.completeness is AnalysisCompleteness.COMPLETE
                           and prior_facts.failures == frozenset({FailureCause.INVALID_REQUEST}))
            if not prior_usage:
                return 'Calls postprocessing cannot establish an absent name from prior analysis'
        return None

    @staticmethod
    def public_diagnostic(result: Dict[str, Any]) -> Optional[str]:
        if _calls_usage_rejection(result) or _calls_absent(result):
            return str(result['error'])
        return None

    @staticmethod
    def execution_facts(result: Any):
        from ...utils.results import (AnalysisCompleteness, ExecutionFacts, FailureCause, failure_execution_facts,
                                      result_execution_facts)
        if _calls_proof_error(result):
            return failure_execution_facts(FailureCause.ANALYSIS)
        if _calls_usage_rejection(result):
            return failure_execution_facts(FailureCause.INVALID_REQUEST)
        if _calls_absent(result):
            return ExecutionFacts(AnalysisCompleteness.COMPLETE, failures=frozenset({FailureCause.INVALID_REQUEST}))
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
        """depth= walks callers, callees and ?root only; in any other mode it was dropped
        in silence (BACK-1504)."""
        if self.query_params.get('depth') is None:
            return
        print(f"⚠ Query param 'depth' for calls:// applies to ?callers, ?callees and ?root only, "
              f"not ?{mode} — ignored.", file=sys.stderr)

    def get_structure(self, **kwargs) -> RevealResult:
        self.validate_request(self.query_params)
        params = self.query_params
        # Every mode key is read here, whichever mode answers: the flag ledger counts each as applied.
        callers, target, callees_target, root, rank = (spec.read(params) or ''
                                                       for spec in (_CALLERS, _TARGET, _CALLEES, _ROOT, _RANK))
        uncalled, modules, detail = _UNCALLED.read(params), _MODULES.read(params), _DETAIL.read(params)
        if self._shorthand_conflict:
            return self._usage(f'calls://{self._shorthand_conflict} is shorthand for callers=NAME, so with '
                               f'{_selected_modes(params)[0]}= it names two modes: calls takes one mode per request')
        if modules:
            return self._module_graph()
        if rank == 'callers':
            return self._ranking()
        if uncalled:
            return self._uncalled()
        if root:
            return self._callee_walk(root)
        if not (callers or target) and not callees_target:
            return self._usage(_MISSING_MODE)
        query_format = _FORMAT.read(params) or ''
        self._warn_top_ignored()
        if callees_target:
            return self._callees(callees_target, query_format, detail)
        return self._callers(callers or target, query_format)

    def _answer(self, result_type: str, data: Dict[str, Any], *, query_format: str = '',
                uncalled: bool = False, unmeasured_walk: bool = False,
                census: Optional[Dict[str, int]] = None,
                absent: Optional[Callable[[], bool]] = None,
                rule: Optional[Callable[[List[str]], Dict[str, Any]]] = None) -> RevealResult:
        """One envelope for every mode: the index's loss evidence becomes the shared meta warnings.

        *absent* says whether an empty name answer's name has no definition; it is asked only when the
        evidence is complete and nothing was hidden, and a yes is the canonical absence error (exit 2).
        *rule* builds the answer's ``walk_rule`` from the languages the confidence declined.
        *census* is the language census a stored callee source already holds for this path (BACK-2132)."""
        if query_format:
            # Query-string format= (dot/json) applies whatever the CLI --format flag says.
            data['_query_format'] = query_format
        meta = _call_graph_meta(self.path, uncalled=uncalled, unmeasured_walk=unmeasured_walk,
                                skipped=data.pop('analysis_skipped', ()),
                                traversal_failures=data.pop('analysis_traversal_failures', ()),
                                census=census)
        if rule is not None:
            declined: List[str] = next((w['languages'] for w in meta['warnings'] if w.get('code') == 'W-CALLS-10'), [])
            data['walk_rule'] = rule(declined)
        clean = not any(w.get('type') in (*_LOSS_WARNINGS, 'scope_hidden') for w in meta['warnings'])
        if absent is not None and clean and absent():
            data['error'] = _calls_absence_message(data)
        return ResultBuilder.create(
            result_type=result_type,
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=data,
            **meta,
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
        source = callee_source(self.path)
        data = callee_levels(walk_callees(self.path, root, depth=2 if depth is None else depth,
                                          include_builtins=_BUILTINS.read(params), source=source))
        data['path'] = self.path
        return self._answer('calls_callees_recursive', data, query_format=_FORMAT.read(params) or '',
                            census=source.language_census(self.path))

    def _usage(self, message: str) -> RevealResult:
        """Usage, not analysis: D6 exits 2 (it exited 1 before calls was declared, BACK-2066)."""
        return ResultBuilder.create(
            result_type=self.result_type_for(self.query_params),
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data={'path': self.path, 'error': message,
                  'example': f"calls://{self.path}?callers=my_function"},
            errors=[{'code': 'invalid_request', 'message': message}],
            **_call_graph_meta(self.path),
        )

    def _directory(self) -> Path:
        """The directory every engine scans for this path (a file scans its parent)."""
        path = Path(self.path)
        return path if path.is_dir() else path.parent

    def _callees(self, name: str, query_format: str, detail: bool) -> RevealResult:
        """Depth 1 is find_callees' per-definition answer, as before; depth 2-5 and detail add the
        callee walk (walk_callees) to the same answer type, read from one callee_source."""
        params = self.query_params
        depth = _DEPTH.read(params) or 1
        include_builtins = _BUILTINS.read(params)
        walked = depth > 1 or detail
        file_filter, bare = _split_root(name)
        source = callee_source(self.path)
        if not walked and not file_filter:
            data = find_callees(self.path, name, include_builtins=include_builtins, source=source)
        else:
            data = find_callees(self.path, bare, include_builtins=include_builtins,
                                source=source.in_file(file_filter) if file_filter else source)
            data['target'] = name
            if walked:
                data.update(_walk_view(walk_callees(self.path, name, depth=depth, include_builtins=include_builtins,
                                                    source=source), detail))
        data['path'] = self.path
        return self._answer('calls_callees', data, query_format=query_format, unmeasured_walk=walked,
                            census=source.language_census(self.path),
                            absent=lambda: not data['matches'],
                            rule=lambda declined: _callees_rule(depth, include_builtins, declined))

    def _callers(self, name: str, query_format: str) -> RevealResult:
        depth = _DEPTH.read(self.query_params) or 1
        data = find_callers(self.path, name, depth=depth)
        data['path'] = self.path
        # No caller and no definition: the name names nothing here. A name with call sites and
        # no definition (a library function) has an answer.
        return self._answer('calls_query', data, query_format=query_format,
                            absent=lambda: data['total_callers'] == 0 and not self._defines(name),
                            rule=lambda declined: _callers_rule(name, depth, declined))

    def _defines(self, name: str) -> bool:
        """Any element of any kind (a class too: `Foo()` calls it) is named *name* or its bare tail."""
        wanted = {name, _bare_callee_name(name)}
        return any(name_matches(elem.get('name'), want)
                   for file_struct in collect_structures(str(self._directory()))
                   for elem in file_struct.get('elements', []) for want in wanted)


def _walk_view(walk: CalleeWalk, detail: bool) -> Dict[str, Any]:
    """The callee walk's fields of a calls_callees answer: every edge by level, every definition it
    reached (roots at level 0) and the edge totals. *detail* adds params and effects."""
    view = callee_levels(walk)
    definitions: List[Dict[str, Any]] = []
    queue = list(walk.roots)
    for node in queue:  # breadth first: the walk places each definition at its shallowest level
        entry: Dict[str, Any] = {'name': node.name, 'file': node.file, 'line': node.line,
                                 'level': node.level, 'expanded': node.expanded}
        if detail:
            entry.update(params=node.params, effects=node.effects)
        definitions.append(entry)
        queue.extend(child for _edge, child in node.edges if child is not None)
    return {'depth': walk.depth, 'levels': view['levels'], 'definitions': definitions,
            **{key: view[key] for key in _WALK_TOTALS}}


def _callers_rule(name: str, depth: int, declined: List[str]) -> Dict[str, Any]:
    """find_callers' rule, for its JSON and its ``Rule:`` line (ground rule 4). The callers
    and depth-2 snapshots measure levels 1 and 2."""
    text = (f"Rule: callers whose body calls {name} by bare name or import alias; level k+1 looks each caller "
            f"up by name, so same-named functions' callers join; each (file, caller) once; depth {depth} "
            "(clamped 1-5). Measured: levels 1 and 2.")
    if declined:
        text += f" No recall snapshot: {', '.join(declined)}."
    return {
        'direction': 'callers',
        'match': 'bare_name_or_import_alias',
        'expansion': 'by_name',
        'once_per': 'file_caller',
        'depth': depth,
        'measured': {'depth_1': True, 'depth_2': True, 'beyond_depth_2': False},
        'unmeasured_languages': declined,
        'text': text,
    }


def _callees_rule(depth: int, include_builtins: bool, declined: List[str]) -> Dict[str, Any]:
    """The callee walk's rule, for its JSON and its ``Rule:`` line (ground rule 4)."""
    builtins = 'included' if include_builtins else 'hidden'
    text = ("Rule: callees by definition: each definition of the name, then each definition a call reaches, "
            "is expanded once, at its shallowest level; every call site of an expanded definition is an edge "
            "(call text de-duplicated per definition); a call resolves within the caller's language family to "
            "its one definition, else a same-file one or the one its imports name, else it is ambiguous and "
            f"not expanded; builtins {builtins}{'' if include_builtins else ' (builtins=true shows them)'}; "
            f"depth {depth} (clamped 1-5). Measured: depth-1 call lists only.")
    if declined:
        text += f" No recall snapshot: {', '.join(declined)}."
    return {
        'direction': 'callees',
        'expansion': 'by_definition_shallowest',
        'edges': 'every_call_site_per_definition',
        'resolution': ['language_family', 'same_file_or_import', 'ambiguous'],
        'builtins': builtins,
        'depth': depth,
        'measured': {'depth_1': True, 'beyond_depth_1': False, 'detail': False},
        'unmeasured_languages': declined,
        'text': text,
    }
