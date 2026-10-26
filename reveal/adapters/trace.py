"""trace:// adapter - execution narrative from an entry-point function.

Walks the call graph from a named entry point, one frame per definition, and
builds a depth-indented narrative: each frame shows the function location,
its parameters, classified side-effects, and what it calls next.
The walk is calls.index.walk_callees, the one calls://?callees=&depth= answers from:
each definition is expanded once, at the shallowest depth it is reached.
Scan/render logic and required-answer proof live here; CLI, URI and MCP use the
same declared binding and canonical outcome path.

Retired (BACK-2066): ``reveal trace`` and ``trace://`` print a replaced-by note from the
RETIREMENTS table and keep this frames shape until the cut (decision c); the MCP tool
reveal_trace keeps its name until Phase 7 (decision g).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from .calls.index import CalleeNode, CalleeSource, walk_callees
from ..utils import print_json_result
from ..utils.query_binding import bind_declared_params
from ..utils.query_parser import (CliBinding, ParamSpec, QueryParams, ResourceSpec, clamped_whole,
                                  nonempty_scalar, param_schema, peek_query_items)
from ..utils.path_utils import to_posix
from ..utils.results import ResultBuilder
from ..reveal_types import PathFailure



def _trace_problem(problems: List[Dict[str, str]], file: str, message: str) -> None:
    """Local validation facts; TraceAdapter applies existing composition attribution."""
    problems.append({'file': to_posix(file), 'message': message})


def _trace_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _trace_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


def _trace_callable_valid(element: Dict[str, Any]) -> bool:
    return (isinstance(element.get('name'), str) and bool(element['name'])
            and _trace_count(element.get('line')) and _trace_strings(element.get('calls'))
            and isinstance(element.get('signature', ''), str)
            and _trace_strings(element.get('reference_only_calls', [])))



def _trace_callable_references(element: Dict[str, Any], file: str,
                               problems: List[Dict[str, str]]) -> Dict[str, Any]:
    if 'references' not in element:
        return element
    references = element['references']
    usable = [] if not isinstance(references, list) else [
        reference for reference in references if isinstance(reference, dict)
        and isinstance(reference.get('callee'), str) and reference['callee']]
    if not isinstance(references, list) or len(usable) != len(references):
        _trace_problem(problems, file, 'Trace callable references are malformed')
    return {**element, 'references': usable}

def _trace_projection_calls_valid(element: Dict[str, Any], references: List[Dict[str, Any]]) -> bool:
    matched = any(reference['owner'] == element.get('name')
                  and reference['owner_line'] == element.get('line') for reference in references)
    return not matched or _trace_strings(element.get('calls', []))


def _trace_elements(values: Any, file: str, problems: List[Dict[str, str]],
                    references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        _trace_problem(problems, file, 'Required trace elements collection is missing or malformed')
        return []
    usable = []
    for element in values:
        if not isinstance(element, dict) or not isinstance(element.get('category'), str):
            _trace_problem(problems, file, 'Required trace element is malformed')
            continue
        if not _trace_projection_calls_valid(element, references):
            _trace_problem(problems, file, 'Trace JSX projection consumes malformed element calls')
            continue
        if element['category'] in ('functions', 'methods', 'tests', 'modules', 'class_fields'):
            if not _trace_callable_valid(element):
                _trace_problem(problems, file, 'Required trace callable name, line or calls are missing or malformed')
                continue
            element = _trace_callable_references(element, file, problems)
        usable.append(element)
    return usable


def _trace_site_valid(site: Any, owner: bool) -> bool:
    if not isinstance(site, dict):
        return False
    valid = isinstance(site.get('callee'), str) and bool(site['callee']) and _trace_count(site.get('line'))
    return valid and (not owner or (isinstance(site.get('owner'), str) and _trace_count(site.get('owner_line'))))


def _trace_sites(file: Dict[str, Any], problems: List[Dict[str, str]]) -> None:
    """Validate the script/JSX call fields consumed by call_sources, if present."""
    for field in ('module_call_sites', 'jsx_references', 'jsx_call_sites'):
        if field not in file:
            continue
        values = file[field]
        if not isinstance(values, list):
            _trace_problem(problems, file['file'], f'Trace {field} is malformed')
            file[field] = []
            continue
        usable = [site for site in values if _trace_site_valid(site, field != 'module_call_sites')]
        if len(usable) != len(values):
            _trace_problem(problems, file['file'], f'Trace {field} contains malformed call evidence')
        file[field] = usable


def _trace_file(value: Any, path: str, problems: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get('file'), str) or not value['file']:
        _trace_problem(problems, path, 'Required trace file identity is missing or malformed')
        return None
    file = dict(value)
    _trace_sites(file, problems)
    file['elements'] = _trace_elements(file.get('elements'), file['file'], problems, file.get('jsx_references', []))
    if 'parse_recovered' in file and type(file['parse_recovered']) is not bool:
        _trace_problem(problems, file['file'], 'Trace recovered-parse evidence is malformed')
        file.pop('parse_recovered')
    return file


def _trace_skipped(values: Any, path: str, problems: List[Dict[str, str]]) -> List[Tuple[str, str]]:
    if not isinstance(values, list):
        _trace_problem(problems, path, 'Required trace skipped-input evidence is missing or malformed')
        return []
    usable = []
    for entry in values:
        if (isinstance(entry, (tuple, list)) and len(entry) == 2
                and all(isinstance(value, str) and value for value in entry)):
            usable.append((entry[0], entry[1]))
        else:
            _trace_problem(problems, path, 'Trace skipped-input entry is malformed')
    return usable


def _trace_traversal(values: Any, path: str,
                     problems: List[Dict[str, str]]) -> List[PathFailure]:
    """Validate directory loss separately: unlike file evidence, attribution may be unknown."""
    if not isinstance(values, list):
        _trace_problem(problems, path, 'Required trace traversal evidence is malformed')
        return []
    usable = []
    for entry in values:
        if (isinstance(entry, (tuple, list)) and len(entry) == 2
                and (entry[0] is None or isinstance(entry[0], str) and bool(entry[0]))
                and isinstance(entry[1], str) and bool(entry[1])):
            usable.append(PathFailure(entry[0], entry[1]))
        else:
            _trace_problem(problems, path, 'Trace traversal entry is malformed')
    return usable


def _trace_collection(values: Any, path: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Retain usable input rows and structured evidence without collecting again."""
    from .ast.analysis import (StructureList, analysis_skipped_warning, parse_recovered_warning,
                               traversal_failed_warning)
    structures = StructureList()
    problems: List[Dict[str, str]] = []
    if isinstance(values, list):
        structures.skipped = _trace_skipped(getattr(values, 'skipped', None), path, problems)
        structures.traversal_failures = _trace_traversal(
            getattr(values, 'traversal_failures', []), path, problems)
        for value in values:
            file = _trace_file(value, path, problems)
            if file is not None:
                structures.append(file)
    else:
        _trace_problem(problems, path, 'Required trace structures collection is malformed')
    warnings = [entry for entry in (
        analysis_skipped_warning(structures.skipped, None, 'analysis is incomplete; some functions may be missing from the trace'),
        traversal_failed_warning(structures.traversal_failures),
        parse_recovered_warning(structures),
    ) if entry is not None]
    meta = {'warnings': warnings, 'errors': problems} if warnings or problems else {}
    return structures, meta

def _build_trace(path: str, root: str, depth: int) -> Dict[str, Any]:
    """Build a trace report from the shared callee walk (calls.index.walk_callees).

    One frame per *definition* (file:line), never per name (BACK-1399): two unrelated
    `run()`s never report each other's callees. A definition is expanded once, at the
    shallowest depth the walk reaches it (BACK-2096), and its frame is listed in pre-order
    under the call that first reaches it; a later call to it is named in its caller's
    `calls` without a second frame. `root` may be `path/to/file.py:name` to pick one
    definition; an ambiguous bare name traces each definition separately.
    """
    from reveal.adapters.ast.analysis import collect_structures

    structures, meta = _trace_collection(collect_structures(path), path)
    walk = walk_callees(path, root, depth, source=CalleeSource.from_structures(structures))
    roots, root_name = walk.roots, walk.root_name

    warnings: List[str] = [entry['message'] for entry in meta.get('warnings', [])]
    if len(roots) > 1:
        where = ', '.join(f"{_relpath(d.file, path)}:{d.line}" for d in roots[:5])
        more = f" (+{len(roots) - 5} more)" if len(roots) > 5 else ''
        warnings.append(
            f"'{root_name}' has {len(roots)} definitions ({where}{more}); each is traced "
            f"separately -- pick one with --from <file>:{root_name}"
        )

    projection = _TraceFrames()
    for node in roots:
        projection.visit(node)
    frames = projection.frames or [_frame(root, None, 0)]
    if any(frame.get('references') for frame in frames):
        warnings.append('JSX edges are component-use references; runtime render scheduling is not resolved.')
    if projection.ambiguous_names:
        warnings.append(
            f"{len(projection.ambiguous_names)} callee name(s) match several definitions and are "
            f"not expanded: {', '.join(sorted(projection.ambiguous_names)[:5])}"
        )

    return {
        'root': root,
        'path': path,
        'depth': depth,
        'frames': frames,
        'warnings': warnings,
        'total_resolved': projection.resolved,
        'total_unresolved': projection.unresolved,
        'meta': meta,
    }


_MAX_EXTERNAL_NAME = 80


def _short_callee(call: str) -> str:
    """Display text for an unresolved callee: an anonymous class or lambda
    body is part of the call expression and must not become the name."""
    text = re.sub(r'\{.*\}', '{...}', ' '.join(call.split()), flags=re.S)
    return text if len(text) <= _MAX_EXTERNAL_NAME else text[:_MAX_EXTERNAL_NAME - 3] + '...'


def _frame(name: str, node: Optional[CalleeNode], depth: int) -> Dict[str, Any]:
    return {
        'name': name,
        'file': node.file if node else '',
        'line': node.line if node else 0,
        'params': node.params if node else [],
        'effects': node.effects if node else [],
        'calls': [],
        'depth': depth,
        'resolved': node is not None,
        'ambiguous': False,
    }


class _TraceFrames:
    """Projects the callee walk onto trace frames, in pre-order: a definition's frame sits
    under the call that placed it; external and ambiguous callees get one frame per name.
    Totals count each frame's distinct callee labels (ambiguous ones as resolved)."""

    def __init__(self) -> None:
        self.frames: List[Dict[str, Any]] = []
        self.resolved = 0
        self.unresolved = 0
        self.ambiguous_names: Set[str] = set()
        self._leaf_names: Set[str] = set()

    def visit(self, node: CalleeNode, relationship: Optional[str] = None) -> None:
        frame = _frame(node.name, node, node.level)
        if relationship:
            frame['relationship'] = relationship
        if node.references:
            frame['references'] = node.references
        self.frames.append(frame)
        if not node.expanded:
            return
        for edge, child in node.edges:
            label = edge['callee'] if edge['resolved'] else _short_callee(edge['call_expr'])
            first = label not in frame['calls']
            if first:
                frame['calls'].append(label)
                if edge['resolved']:
                    self.resolved += 1
                else:
                    self.unresolved += 1
            if child is not None:
                self.visit(child, edge.get('relationship'))
            elif first and not edge['resolved']:
                self._leaf(label, edge, node.level + 1)
            elif first and edge.get('ambiguous'):
                self.ambiguous_names.add(label)
                self._leaf(label, edge, node.level + 1)

    def _leaf(self, label: str, edge: Dict[str, Any], depth: int) -> None:
        """External and ambiguous callees: one frame per name, never expanded."""
        if label in self._leaf_names:
            return
        self._leaf_names.add(label)
        frame = _frame(label, None, depth)
        frame['resolved'] = edge['resolved']
        if edge.get('relationship'):
            frame['relationship'] = edge['relationship']
        if edge.get('ambiguous'):
            frame['ambiguous'] = True
            frame['candidates'] = edge['candidates']
        self.frames.append(frame)


def _relpath(file_str: str, base: str) -> str:
    try:
        return os.path.relpath(file_str, base)
    except ValueError:
        return file_str



def _render_trace_metadata(report: Dict[str, Any]) -> None:
    """Existing strings remain inline; render every other diagnostic once."""
    from ..utils.warning_render import render_meta_warnings
    mirrored = set(report.get('warnings', []))
    meta = dict(report.get('meta') or {})
    for field in ('warnings', 'errors'):
        meta[field] = [entry for entry in meta.get(field, [])
                       if entry.get('message') not in mirrored]
    render_meta_warnings({'meta': meta})

def _render_trace(report: Dict[str, Any]) -> None:
    root = report['root']
    path = report['path']
    depth = report['depth']
    frames = report['frames']
    total_r = report['total_resolved']
    total_u = report['total_unresolved']

    print(f"Trace: {root}  (depth {depth})")
    print(f"Project: {path}")
    print(f"Resolved: {total_r}  External/unresolved: {total_u}")
    for warning in report.get('warnings', []):
        print(f"⚠ {warning}")
    _render_trace_metadata(report)
    print()

    if not frames:
        print(f"  No functions found for '{root}'.")
        return

    for frame in frames:
        d = frame['depth']
        indent = '  ' * d
        name = frame['name']

        loc = ''
        if frame['file']:
            rel = _relpath(frame['file'], path)
            loc = f"  [{rel}:{frame['line']}]" if frame['line'] else f"  [{rel}]"

        if frame.get('ambiguous'):
            where = ', '.join(f"{_relpath(c['file'], path)}:{c['line']}" for c in frame['candidates'][:3])
            more = ', ...' if len(frame['candidates']) > 3 else ''
            marker = f"  [ambiguous: {len(frame['candidates'])} definitions -- {where}{more}]"
        else:
            marker = '' if frame['resolved'] else '  [external]'
        relation = ' [JSX reference]' if frame.get('relationship') in ('jsx_reference', 'call_and_jsx_reference') else ''
        print(f"{indent}{name}{loc}{marker}{relation}")

        inner = indent + '  '
        if frame['params']:
            print(f"{inner}params:  {', '.join(frame['params'])}")
        if frame['effects']:
            print(f"{inner}effects: {', '.join(frame['effects'])}")
        if frame['calls']:
            print(f"{inner}calls:   {', '.join(frame['calls'])}")
        print()


class TraceRenderer:
    """Renderer for trace:// results."""

    RENDERS_META_WARNINGS = True

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
            return
        _render_trace(result)


def _trace_depth(value: Any) -> int:
    return clamped_whole(value, 1, 5)


def _trace_frame_valid(frame: Any, depth: int) -> bool:
    if not isinstance(frame, dict):
        return False
    scalar = (isinstance(frame.get('name'), str) and bool(frame['name'])
              and isinstance(frame.get('file'), str) and _trace_count(frame.get('line'))
              and _trace_count(frame.get('depth')) and frame['depth'] <= depth
              and type(frame.get('resolved')) is bool and type(frame.get('ambiguous')) is bool)
    return scalar and all(_trace_strings(frame.get(field)) for field in ('params', 'effects', 'calls'))


def _trace_candidates_valid(frame: Dict[str, Any]) -> bool:
    if not frame['ambiguous']:
        return True
    candidates = frame.get('candidates')
    return isinstance(candidates, list) and bool(candidates) and all(
        isinstance(candidate, dict) and isinstance(candidate.get('file'), str) and bool(candidate['file'])
        and _trace_count(candidate.get('line')) for candidate in candidates)


def _trace_placeholder(result: Dict[str, Any]) -> bool:
    return (result.get('frames') == [_frame(result.get('root', ''), None, 0)]
            and result.get('total_resolved') == result.get('total_unresolved') == 0)


def _trace_absence_diagnostic_error(result: Dict[str, Any]) -> Optional[str]:
    meta = result.get('meta') or {}
    errors = meta.get('errors', []) if isinstance(meta, dict) else []
    for entry in errors if isinstance(errors, list) else []:
        if isinstance(entry, dict) and entry.get('code') == 'trace_root_not_found':
            if not _trace_placeholder(result) or entry.get('message') != _trace_root_message(result):
                return 'Trace absence diagnostic lacks canonical root-absence proof'
    return None


def _trace_identity_error(result: Dict[str, Any]) -> Optional[str]:
    if not all(isinstance(result.get(field), str) and result[field] for field in ('root', 'path')):
        return 'Trace required root/path identity is missing or malformed'
    depth = result.get('depth')
    if type(depth) is not int or not 1 <= depth <= 5:
        return 'Trace required depth is missing or malformed'
    if not all(_trace_count(result.get(field)) for field in ('total_resolved', 'total_unresolved')):
        return 'Trace required edge totals are missing or malformed'
    return None


def _trace_proof_error(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return 'Trace required answer must be an object'
    identity_error = _trace_identity_error(result)
    if identity_error:
        return identity_error
    depth = result['depth']
    frames = result.get('frames')
    if not isinstance(frames, list) or not frames:
        return 'Trace required frames are missing or malformed'
    if not all(_trace_frame_valid(frame, depth) and _trace_candidates_valid(frame) for frame in frames):
        return 'Trace required renderer frame evidence is malformed'
    if not isinstance(result.get('warnings'), list) or not all(isinstance(w, str) for w in result['warnings']):
        return 'Trace required warning strings are missing or malformed'
    return _trace_absence_diagnostic_error(result)


def _trace_root_message(result: Dict[str, Any]) -> str:
    return f"Entry point '{result['root']}' not found in {result['path']}"


def _trace_missing_evidence(result: Dict[str, Any]) -> bool:
    meta = result.get('meta') or {}
    if not isinstance(meta, dict):
        return True
    errors, warnings = meta.get('errors', []), meta.get('warnings', [])
    if not isinstance(errors, list) or not isinstance(warnings, list):
        return True
    if any(not isinstance(entry, dict) for entry in [*errors, *warnings]):
        return True
    required = {'analysis_failed', 'parse_recovered', 'partial_parse', 'parse_degraded',
                'worker_lost', 'check_rules_failed', 'analysis_incomplete'}
    return (any(entry.get('code') != 'trace_root_not_found' for entry in errors)
            or any(entry.get('type') in required for entry in warnings))


def _trace_absent(result: Dict[str, Any]) -> bool:
    if _trace_proof_error(result) or _trace_missing_evidence(result):
        return False
    if result.get('error') and result['error'] != _trace_root_message(result):
        return False
    return _trace_placeholder(result)


@register_adapter('trace')
@register_renderer(TraceRenderer)
class TraceAdapter(ResourceAdapter):
    """Adapter walking the call graph from a named entry point and building
    a depth-indented execution narrative (the calls:// callee walk: each definition
    expanded once, at the shallowest depth it is reached)."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a typo'd path exits 1, not 'entry point has no calls' (BACK-1524)
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}  # --no-gitignore (BACK-1386)

    RESULT_TYPE = 'trace'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = (
        ParamSpec('from', 'string', 'Entry-point function; FILE:FUNC selects a definition', None,
                  nonempty_scalar, required=True, uri_codec='percent', role='analysis',
                  examples=('from=main', 'from=src/app.py:run'),
                  cli=CliBinding(('--from',), dest='root', required=True, metavar='FUNC')),
        ParamSpec('depth', 'integer', 'Call levels to expand (signed whole integer, clamped 1-5)', 2,
                  _trace_depth, role='analysis', examples=('depth=4',),
                  cli=CliBinding(('--depth',), metavar='N')),
    )

    def __init__(self, resource: str, query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        self.path = to_posix(Path(resource).expanduser())
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(self.PARAM_SPECS, query or '', transport='uri')
        self._warn_unknown_query_params(self.query_params)

    def answer_requirement_error(self, result, expected_type, prior_facts=None):
        from ..utils.results import AnalysisCompleteness, FailureCause
        error = _trace_proof_error(result)
        if error:
            return error
        supplied = dict(peek_query_items(self.query_params))
        if (result['root'] != supplied.get('from') or result['path'] != self.path
                or result['depth'] != supplied.get('depth', 2)):
            return 'Trace answer identity differs from the validated request'
        if _trace_absent(result) and prior_facts is not None:
            prior_usage = (prior_facts.completeness is AnalysisCompleteness.COMPLETE
                           and prior_facts.failures == frozenset({FailureCause.INVALID_REQUEST}))
            if not prior_usage:
                return 'Trace postprocessing cannot establish absent root from prior analysis'
        return None

    def public_diagnostic(self, result):
        return _trace_root_message(result) if _trace_absent(result) else None

    @staticmethod
    def execution_facts(result):
        from ..utils.results import (AnalysisCompleteness, ExecutionFacts, FailureCause,
                                     result_execution_facts, failure_execution_facts)
        if _trace_proof_error(result):
            return failure_execution_facts(FailureCause.ANALYSIS)
        if _trace_absent(result):
            return ExecutionFacts(AnalysisCompleteness.COMPLETE,
                                  failures=frozenset({FailureCause.INVALID_REQUEST}))
        state = AnalysisCompleteness.COMPLETE
        if _trace_missing_evidence(result):
            state = (AnalysisCompleteness.INCOMPLETE if any(frame['resolved'] for frame in result['frames'])
                     else AnalysisCompleteness.FAILED)
        return result_execution_facts(result, completeness=state)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'trace',
            'description': ('Walks the call graph from a named entry point and prints '
                            'a depth-indented execution narrative.'),
            'syntax': 'trace://<path>?from=<FUNC>[&depth=2]',
            'examples': [
                {'uri': "trace://src?from=main", 'description': 'Trace from main(), depth 2'},
                {'uri': "trace://src?from=handle_request&depth=4", 'description': 'Trace 4 levels deep'},
            ],
            'features': [
                'One frame per definition: two unrelated functions named run() are never merged',
                'Each definition is expanded once, at the shallowest depth it is reached; a later call to it is listed in its caller\'s calls without a second frame',
                'from=<file>:<name> picks one definition; a bare name with several traces each and warns',
                'Callees with several same-named definitions resolve via the same file, then imports, else [ambiguous]',
                'Each frame: file/line, parameters, classified side-effects, and what it calls next',
                'Unresolved (external/stdlib) callees marked [external]',
            ],
            'notes': [
                'depth is clamped to 1-5.',
                'A same-named definition in an unrelated language is not conflated with the real target (BACK-405).',
            ],
            'see_also': [
                'calls://<path>?callees=<FUNC>&depth=N&detail - the replacement (reveal calls <path> --callees ...)',
                "reveal_trace MCP tool - same narrative, MCP-native",
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'trace',
            'description': 'Retired (use calls://<path>?callees=<FUNC>&depth=N&detail). Execution narrative: call-graph walk from a named entry point, each definition expanded at the shallowest depth it is reached',
            'uri_syntax': 'trace://<path>?from=<FUNC>&depth=2',
            'resource': TraceAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': 'none', 'fail_on': ['none']},
            'query_params': param_schema(TraceAdapter.PARAM_SPECS),
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'trace',
                    'description': 'Depth-indented call-graph frames from the entry point',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'root': {'type': 'string'},
                            'frames': {'type': 'array'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'trace://src?from=main', 'description': 'Trace from main()', 'output_type': 'trace', 'task': 'debugging'},
            ],
            'notes': [
                'Frames are per definition (file:line), in pre-order under the call that first reaches them; each definition is expanded once, at the shallowest depth it is reached, by the same walk as calls://?callees=&depth= (BACK-2096). A callee name with several definitions resolves through the same file, then the caller\'s imports; otherwise it is marked ambiguous and not expanded (BACK-1399).',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        root = self.PARAM_SPECS[0].read(self.query_params)
        depth = self.PARAM_SPECS[1].read(self.query_params)

        report = _build_trace(self.path, str(root), depth)
        meta = report.pop('meta', {})
        for problem in meta.pop('errors', []):
            self.record_composed_error('collect_structures', problem['file'], ValueError(problem['message']))
        self.fold_meta(meta)

        result = ResultBuilder.create(
            result_type='trace',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=report,
            meta=dict(self.composed_meta() or {}) or None,
        )

        return result
