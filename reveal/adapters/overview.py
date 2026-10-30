"""overview://: a compact project map from the code census and import views."""
from __future__ import annotations

import logging
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, cast
from urllib.parse import quote

from reveal.capabilities import scope_dict_for_path
from reveal.config import RevealConfig
from reveal.defaults import UNLIMITED_TOP
from reveal.reveal_types import CONTRACT_VERSION, RevealMeta, RevealResult, WarningEntry

from .base import ResourceAdapter, register_adapter, register_renderer
from ..analyzers.imports import service as import_analysis, resolution
from ..analyzers.imports.diagnostics import integrity_warnings
from ..analyzers.imports.map_facts import MapFacts, project_map_facts, validate_scan_budget
from ..analyzers.imports.views import ImportView
from ..rendering.adapters.overview import OverviewRenderer
from ..utils.exclusions import active_exclusions, exclusion_scope
from ..utils.entry_points import ACTIVE_ENTRY_POINT_RULE, is_active_entry_point
from ..utils.gitignore import gitignore_scope, respect_gitignore_param
from ..utils.path_utils import (HiddenTally, as_spelled, failure_of, hidden_entries_warning,
                               traversal_failed_warning)
from ..utils.query_binding import bind_declared_params, boolean_value
from ..utils.query_parser import (CliBinding, ParamSpec, ParamValueError, QueryParams, ResourceSpec,
                                  nonempty_scalar, nonnegative_display_limit, param_schema, split_exclude_param)
from ..utils.query_parser import peek_query_items
from ..utils.results import ResultBuilder, note_truncation

logger = logging.getLogger(__name__)

DIAGNOSTIC_CUT_HINT = ('Overview diagnostic samples contain at most 50 details; use imports://FILE '
                       'or reveal FILE for a named source when available.')


def without_internal_filter_warnings(meta: Optional[RevealMeta]) -> List[WarningEntry]:
    """Hotspots' generated AST filter is not a caller typo on an empty tree."""
    return [w for w in ((meta or {}).get('warnings') or []) if w.get('type') != 'unknown_filter_key']


def _count(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f'{field} must be a nonnegative integer')
    return value


def _validate_scope(scope: Any) -> None:
    if not isinstance(scope, dict):
        raise ValueError('scope census must be an object')
    total = _count(scope.get('total_code_files'), 'scope.total_code_files')
    rows = scope.get('languages')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('scope languages must contain records')
    for row in rows:
        if not isinstance(row.get('language'), str) or not row['language']:
            raise ValueError('scope language requires its name')
        _count(row.get('files'), 'scope language files')
    if sum(row['files'] for row in rows) != total:
        raise ValueError('scope language counts must sum to total_code_files')


def _validate_scope_disclosure(scope: dict) -> None:
    if type(scope.get('complete')) is not bool:
        raise ValueError('scope must retain census completeness')
    _validate_path(scope.get('counting_rule'))
    if _count(scope.get('language_count'), 'scope.language_count') != len(scope['languages']):
        raise ValueError('scope must retain its language population')
    hidden = scope.get('hidden')
    if (not isinstance(hidden, dict) or hidden.get('unit') != 'entries'
            or not isinstance(hidden.get('by_cause'), dict)):
        raise ValueError('scope must retain hidden-entry units and causes')
    for cause, count in hidden['by_cause'].items():
        _validate_path(cause)
        _count(count, 'hidden entries')


def _run_scope(adapter: 'OverviewAdapter', path: Path) -> Dict[str, Any]:
    failures: List[OSError] = []
    hidden = HiddenTally()
    try:
        scope = scope_dict_for_path(path, exclude_patterns=adapter.exclude_patterns,
                                    respect_gitignore=adapter.respect_gitignore,
                                    on_error=failures.append, on_hidden=hidden)
        _validate_scope(scope)
        # These legacy counters have no measurement in this census.
        scope = {key: value for key, value in scope.items() if not key.startswith('skipped_')}
        scope.update(complete=not failures,
                     counting_rule='Recognized code files retained by the configured scope; data, markup and unknown extensions are not counted.',
                     hidden={'unit': 'entries', 'by_cause': dict(hidden)},
                     language_count=len(scope['languages']))
        warning = traversal_failed_warning([failure_of(error) for error in failures], path)
        if warning:
            adapter.fold_meta({'warnings': [warning]})
        hidden_warning = hidden_entries_warning(hidden, scope['total_code_files'])
        if hidden_warning:
            adapter.fold_meta({'warnings': [hidden_warning]})
        return scope
    except Exception as exc:  # boundary-ok: broad-except -- required census boundary; walker, configuration and language sniffing may fail, and record_composed_error discloses the failure rather than fabricating an empty census
        logger.warning('scope census failed for %s: %s', path, exc)
        adapter.record_composed_error('scope_dict_for_path', path, exc)
        return {}


def _observed_relationships(fan_in, entrypoints, components, cycles) -> bool:
    rows = [*fan_in, *entrypoints, *components]
    return (any(type(row.get(key)) is int and row[key] > 0 for row in rows
                for key in ('fan_in', 'fan_out', 'internal', 'outgoing', 'incoming'))
            or any(len(set(group)) >= 2 for group in cycles))


def _import_warnings(built, target: Path, limit: Optional[int]) -> list[WarningEntry]:
    warnings = integrity_warnings(built.analysis, target)
    traversal_warning = traversal_failed_warning(built.files.traversal_failures, target)
    if traversal_warning and traversal_warning not in warnings:
        warnings.append(traversal_warning)
    hidden_warning = hidden_entries_warning(built.files.hidden, built.files.analyzed)
    if hidden_warning:
        warnings.append(hidden_warning)
    if built.files.capped:
        warnings.append(cast(WarningEntry, {'type': 'scan_capped', 'limit': limit,
                         'message': f'Import discovery stopped at its {limit} file limit; map totals describe the observed graph only.'}))
    return warnings


def _run_imports_analysis(adapter: 'OverviewAdapter', path: Path, top: int, *, scope_usable: bool) -> tuple[Optional[MapFacts], str]:
    """Validate full owner evidence before any map or diagnostic presentation cuts."""
    try:
        target = path.resolve()
        with exclusion_scope(target if target.is_dir() else target.parent, adapter.exclude_patterns), \
                gitignore_scope(adapter.respect_gitignore):
            scope = import_analysis.path_scope(target)
            built = import_analysis.analyze(scope)
        warnings = _import_warnings(built, target, scope.cap)
        adapter.fold_meta({'warnings': warnings})
        view = ImportView(built.analysis, target, resolution.ScanRoot(target, 'path'),
                          scope.cap)
        with import_analysis.composed_rules('overview://'):
            fan_in, entries = view.fan_in(), view.entrypoints()
            components, circular = view.components(), view.circular()
        metadata = view.get_metadata()
        facts = project_map_facts(fan_in, entries, components, circular, metadata,
                                  path=target, top=top, test_layout=view.test_layout)
        _validate_rules(facts['rules'])
        budget = metadata['scan_budget']
        directory_loss = any(w['type'] == 'analysis_incomplete' for w in warnings)
        usable = _observed_relationships(fan_in['entries'], entries['entries'],
                                        components['components'], circular['cycles'])
        if directory_loss and not usable and not scope_usable:
            adapter.fold_meta({'errors': [{'code': 'E_OVERVIEW_ANALYSIS',
                'message': 'Required import discovery failed and no relationship observations survived.'}]})
            return facts, 'failed'
        incomplete = (bool(metadata['files_failed_count']) or bool(metadata['files_lost_count'])
                      or budget['exact'] is not True or any(w['type'] in (
                          'analysis_incomplete', 'analysis_failed', 'partial_parse', 'worker_lost', 'scan_capped') for w in warnings))
        return facts, 'incomplete' if incomplete else 'complete'
    except Exception as exc:  # boundary-ok: broad-except -- required import-service composition boundary; extraction, resolution, view validation and pool failures must be attributed before a failed map is returned
        adapter.record_composed_error('ImportsAdapter', path, exc)
        return None, 'failed'


def _overview_top(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('top requires a non-negative whole number')
    return nonnegative_display_limit(value)


def _obsolete_git(value: Any) -> bool:
    raise ParamValueError('overview no longer collects Git history; omit no_git and use git:// for history')


def _obsolete_tests(value: Any) -> str:
    raise ParamValueError('overview no longer ranks complexity or hotspots; omit tests and use metrics:// or ast:// with type=function')


_AGAINST = ParamSpec('against', 'string', 'Compare the live working tree against a Git ref',
                     None, nonempty_scalar, role='operation', uri_codec='percent',
                     cli=CliBinding(('--against',), metavar='REF'))


def _validate_comparison_controls(params, *, all_requested=False, verbose_requested=False) -> None:
    supplied = dict(peek_query_items(params))
    if supplied.get('against') is None:
        return
    if 'no_git' in supplied:
        _obsolete_git(supplied['no_git'])
    if 'tests' in supplied:
        _obsolete_tests(supplied['tests'])
    if supplied.keys() & {'no_imports', 'all', 'verbose'} or all_requested or verbose_requested:
        raise ValueError('overview comparison does not support no_imports, all or verbose')


def _next_steps(path: str, exclude_patterns: List[str], respect_gitignore: bool) -> List[dict]:
    target = quote(path, safe='/.:')
    questions = (
        ('Full observed fan-in ranking (subject to scan coverage)', f'imports://{target}?rank=fan-in&scope=path'),
        ('All observed component relationships', f'imports://{target}?components&scope=path'),
        ('All observed entrypoint candidates; apply the stated active predicate', f'imports://{target}?entrypoints&scope=path'),
        ('Full observed cycle groups and witness paths (subject to scan coverage)', f'imports://{target}?circular&scope=path'),
        ('Detailed file measurements', f'metrics://{target}'),
    )
    flags = [] if respect_gitignore else ['--no-gitignore']
    for pattern in exclude_patterns:
        flags += ['--exclude', pattern]
    steps = [(question, ['reveal', uri]) for question, uri in questions]
    steps.append(('Function complexity ranking', ['reveal', f'ast://{target}?type=function&sort=-complexity']))
    steps.append(('Concrete rule findings', ['reveal', 'check', path]))
    return [{'question': question, 'command': shlex.join(tokens + flags)} for question, tokens in steps]


def _navigation_exclusions(path: Path, requested: List[str]) -> List[str]:
    # Config/REVEAL_IGNORE applies again in every deeper command. Repeat only
    # request-specific patterns, not the automatic defaults on every hint.
    root = path if path.is_dir() else path.parent
    configured = RevealConfig.get(start_path=root).ignore_patterns()
    active = [pattern for pattern in active_exclusions()[1] if pattern not in configured]
    return list(dict.fromkeys([*active, *requested]))


def _cut_sequence(result: dict, holder: dict, key: str, field: str, limit: int,
                  *, total: Optional[int] = None) -> None:
    values = holder.get(key)
    if isinstance(values, list):
        known = len(values) if total is None else total
        holder[key] = values[:limit]
        note_truncation(result, field, len(holder[key]), known, 'auto_cap', hint=DIAGNOSTIC_CUT_HINT)


def _bound_nested_details(result: dict, value: Any, field: str, limit: int) -> None:
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if isinstance(child, list):
                _cut_sequence(result, value, key, f'{field}.{key}', limit)
                child = value[key]
            _bound_nested_details(result, child, f'{field}.{key}', limit)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _bound_nested_details(result, child, f'{field}.{index}', limit)


def _bound_details(result: dict, top: int) -> None:
    limit = min(max(top, 5), 50)
    result['diagnostic_budget'] = {'limit': limit, 'minimum': 5, 'maximum': 50,
                                   'rule': 'Diagnostic details use max(top, 5), capped at 50; graph expansion has a separate budget.'}
    facts = result.get('map')
    if facts is not None:
        metadata = facts['metadata']
        for key in ('files_failed', 'files_lost'):
            _cut_sequence(result, metadata, key, f'map.metadata.{key}', limit,
                          total=metadata[key + '_count'])
        diagnostics = metadata['extraction_diagnostics']
        metadata['extraction_diagnostics_count'] = len(diagnostics)
        metadata['extraction_diagnostics'] = dict(sorted(diagnostics.items())[:limit])
        note_truncation(result, 'map.metadata.extraction_diagnostics',
                        len(metadata['extraction_diagnostics']), len(diagnostics), 'auto_cap',
                        hint=DIAGNOSTIC_CUT_HINT)
        _bound_nested_details(result, metadata['extraction_diagnostics'],
                              'map.metadata.extraction_diagnostics', limit)
    # Existing owners supply a fixed set of category records. Retain every category,
    # its count and its cause; bound nested lists rather than cutting failure proof.
    meta = result.get('meta') or {}
    for kind in ('warnings', 'errors'):
        for index, record in enumerate(list(meta.get(kind, []))):
            if record.get('type') == 'truncated':
                continue
            for key in ('files', 'directories', 'causes'):
                total = record.get('count') if key in ('files', 'directories') else None
                _cut_sequence(result, record, key, f'meta.{kind}.{index}.{key}', limit,
                              total=total if type(total) is int else None)


def _validate_page(value: Any, name: str) -> None:
    if not isinstance(value, dict) or not isinstance(value.get('rows'), list):
        raise ValueError(f'{name} must retain its bounded rows')
    total = _count(value.get('total'), name + '.total')
    returned = _count(value.get('returned'), name + '.returned')
    omitted = _count(value.get('omitted'), name + '.omitted')
    if returned != len(value['rows']) or total != returned + omitted:
        raise ValueError(f'{name} must retain exact observed row bounds')


def _validate_map_coverage(metadata: Any, status: str) -> None:
    if not isinstance(metadata, dict):
        raise ValueError('map must retain import coverage')
    for key in ('scanned_files', 'files_failed_count', 'files_lost_count', 'extraction_diagnostics_count'):
        _count(metadata.get(key), key)
    validate_scan_budget(metadata.get('scan_budget'))
    budget = metadata['scan_budget']
    if status == 'complete' and (budget['exact'] is not True or budget['capped'] is not False
                                 or metadata['files_failed_count'] or metadata['files_lost_count']):
        raise ValueError('a complete map requires complete source accounting and no file loss')
    if not isinstance(metadata.get('unsupported_extensions'), dict):
        raise ValueError('map must retain unsupported-extension coverage')
    for extension, count in metadata['unsupported_extensions'].items():
        _validate_path(extension)
        _count(count, 'unsupported extension count')


def _validate_path(value: Any) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError('map path must be nonempty text')


def _validate_relationship(row: Any, kind: str) -> None:
    if not isinstance(row, dict):
        raise ValueError('map relationships must contain records')
    _validate_path(row.get('component' if kind == 'components' else 'file'))
    if kind != 'components':
        _count(row.get('fan_out'), kind + '.fan_out')
        if kind == 'fan_in':
            if not _count(row.get('fan_in'), 'fan_in'):
                raise ValueError('fan-in rows must retain positive relationships')
        else:
            _count(row.get('test_only_importers'), 'test_only_importers')
            if row.get('is_test') is not False or not is_active_entry_point(row):
                raise ValueError('entrypoint rows must retain the active predicate')
        return
    for field in ('files', 'internal', 'outgoing', 'incoming'):
        _count(row.get(field), 'component.' + field)
    cohesion = row.get('cohesion')
    if cohesion is None:
        _validate_path(row.get('cohesion_reason'))
        if not row['cohesion_reason'].strip():
            raise ValueError('declined component cohesion requires its reason')
    elif type(cohesion) not in (int, float) or not 0 <= cohesion <= 1:
        raise ValueError('component cohesion must be a fraction or declined')
    if row.get('top_bridge') is not None:
        _validate_path(row['top_bridge'])
    if 'top_bridge' not in row:
        raise ValueError('component bridge evidence is required')


def _validate_counting_rule(rule: Any, lazy: str, tests: str) -> None:
    if (not isinstance(rule, dict) or not isinstance(rule.get('text'), str) or not rule['text']
            or rule.get('lazy') != lazy or rule.get('tests') != tests
            or rule.get('scope') != 'scanned_path' or rule.get('type_checking') != 'excluded'):
        raise ValueError('map counting rules must retain their distinct view semantics')


def _validate_rules(rules: Any) -> None:
    if not isinstance(rules, dict) or not isinstance(rules.get('edge_rule_sections'), dict):
        raise ValueError('map must retain its distinct counting rules')
    sections = rules['edge_rule_sections']
    _validate_counting_rule(rules.get('edge_rule'), 'include', 'included')
    _validate_counting_rule(sections.get('entry_points'), 'include', 'importers_not_counted')
    _validate_counting_rule(sections.get('cycles'), 'exclude', 'included')
    _validate_path(rules.get('component_order'))


def _validate_samples(metadata: dict, limit: int) -> None:
    for name in ('files_failed', 'files_lost'):
        paths = metadata.get(name)
        if not isinstance(paths, list) or len(paths) != min(metadata[name + '_count'], limit):
            raise ValueError('map failure paths must retain the diagnostic sample')
        for path in paths:
            _validate_path(path)
    if metadata['files_lost_count'] > metadata['files_failed_count']:
        raise ValueError('map lost count exceeds failed count')
    diagnostics = metadata.get('extraction_diagnostics')
    if not isinstance(diagnostics, dict) or len(diagnostics) != min(metadata['extraction_diagnostics_count'], limit):
        raise ValueError('map must retain diagnostic sample counts')
    for path, cause in diagnostics.items():
        _validate_path(path)
        if not isinstance(cause, dict):
            raise ValueError('map must retain extraction cause records')


def _validate_map(facts: Any, status: str, limit: int) -> None:
    if not isinstance(facts, dict):
        raise ValueError('requested map must retain its facts')
    for name in ('fan_in', 'entrypoints', 'components', 'cycles'):
        _validate_page(facts.get(name), name)
        if name != 'cycles':
            for row in facts[name]['rows']:
                _validate_relationship(row, name)
    for cycle in facts['cycles']['rows']:
        if not isinstance(cycle, dict):
            raise ValueError('cycle evidence must contain records')
        for key, minimum in (('members', 2), ('path', 1)):
            _validate_page(cycle.get(key), 'cycle.' + key)
            if cycle[key]['total'] < minimum:
                raise ValueError('cycle evidence must retain real groups and witnesses')
            for path in cycle[key]['rows']:
                _validate_path(path)
    predicate = facts.get('entry_point_filter')
    if not isinstance(predicate, dict) or predicate.get('rule') != ACTIVE_ENTRY_POINT_RULE:
        raise ValueError('map must retain its entrypoint predicate')
    if predicate.get('path_basis') != 'producer paths before target-relative display':
        raise ValueError('map must retain its entrypoint predicate path basis')
    raw = _count(predicate.get('fan_in_zero'), 'raw entrypoints')
    active = _count(predicate.get('active'), 'active entrypoints')
    if active > raw or active != facts['entrypoints']['total']:
        raise ValueError('entrypoint totals must retain the raw-to-active selection')
    _validate_rules(facts.get('rules'))
    _validate_map_coverage(facts.get('metadata'), status)
    _validate_samples(facts['metadata'], limit)


def _distinct_owner_warnings(meta: Optional[RevealMeta]) -> Optional[RevealMeta]:
    if meta and 'warnings' in meta:
        distinct: List[WarningEntry] = []
        for warning in meta['warnings']:
            if warning not in distinct:
                distinct.append(warning)
        meta['warnings'] = distinct
    return meta


@register_adapter('overview')
@register_renderer(OverviewRenderer)
class OverviewAdapter(ResourceAdapter):
    """Compact project scope and static import map."""
    HELP_CLUSTER = 'Code Analysis'
    LEGACY_INIT = False
    BOUND_QUERY_CALL = True
    RESOURCE_IS_PATH = True
    CLI_QUERY_FLAGS = {'all': 'all=true', 'verbose': 'verbose=true',
                       'respect_gitignore': 'respect_gitignore=false'}
    RESULT_TYPE = 'overview'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = (
        ParamSpec('top', 'integer', 'Rows per map section; comparison centroid population is max(top,1)*4',
                  5, _overview_top, minimum=0, role='analysis', examples=('top=10',),
                  zero_policy='Ordinary: no graph rows, retain totals and diagnostics; comparison: population 4',
                  cli=CliBinding(('--top',), metavar='N')),
        ParamSpec('no_git', 'boolean', 'Removed: use Git queries for history',
                  False, _obsolete_git, role='analysis', cli=CliBinding(('--no-git',), action='store_true')),
        ParamSpec('no_imports', 'boolean', 'Request only the recognized-code census; omit import analysis explicitly',
                  False, boolean_value, role='analysis', examples=('no_imports=true',),
                  cli=CliBinding(('--no-imports',), action='store_true')),
        ParamSpec('tests', 'string', 'Removed: use metrics or AST for test-filtered rankings',
                  'exclude', _obsolete_tests, role='analysis',
                  cli=CliBinding(('--tests',), metavar='{include,exclude}')),
        ParamSpec('all', 'boolean', 'Expand map evidence; diagnostic details remain capped at 50',
                  False, boolean_value, role='presentation'),
        ParamSpec('verbose', 'boolean', 'Expand map evidence; diagnostic details remain capped at 50',
                  False, boolean_value, role='presentation'),
        _AGAINST,
    )

    def __init__(self, resource: str, query: Optional[str] = None, *, params: Optional[Dict[str, Any]] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = (params if isinstance(params, QueryParams) else bind_declared_params(
            self.PARAM_SPECS, params if params is not None else query or '',
            transport='typed' if params is not None else 'uri'))
        self._warn_unknown_query_params(self.query_params)
        self.exclude_patterns = split_exclude_param(self.query_params.get('exclude'))
        self.respect_gitignore = respect_gitignore_param(self.query_params)

    @staticmethod
    def result_type_for(params):
        return 'overview_diff' if dict(peek_query_items(params)).get('against') is not None else 'overview'

    @staticmethod
    def validate_request(params, args):
        flags = vars(args)  # Validation must not count inspected controls as applied.
        _validate_comparison_controls(params, all_requested=flags.get('all', False),
                                       verbose_requested=flags.get('verbose', False))

    def answer_requirement_error(self, result, expected_type, prior_facts=None):
        if expected_type == 'overview_diff':
            from ..diff.architecture_diff import comparison_answer_requirement_error
            return comparison_answer_requirement_error(result, prior_facts)
        if result.get('error'):
            return None
        if (prior_facts is None and result.get('map_status') == 'failed'
                and result.get('meta', {}).get('errors')):
            return None
        try:
            _validate_scope(result.get('scope'))
            _validate_scope_disclosure(result['scope'])
            _validate_path(result.get('reading_note'))
            status = result.get('map_status')
            no_imports = dict(peek_query_items(self.query_params)).get('no_imports', False)
            diagnostic_budget = result.get('diagnostic_budget')
            if not isinstance(diagnostic_budget, dict):
                raise ValueError('overview must retain its diagnostic budget')
            limit = _count(diagnostic_budget.get('limit'), 'diagnostic limit')
            if not 5 <= limit <= 50:
                raise ValueError('diagnostic limit must stay between five and fifty')
            if status == 'not_requested':
                if not no_imports or result.get('map') is not None:
                    raise ValueError('scope-only overview must omit graph evidence')
            elif status in ('complete', 'incomplete', 'failed'):
                if no_imports:
                    raise ValueError('scope-only overview cannot manufacture a requested map')
                _validate_map(result.get('map'), status, limit)
            else:
                raise ValueError('overview must retain its requested-map status')
        except ValueError as exc:
            return f'Overview missing required answer evidence: {exc}'
        return None

    @staticmethod
    def execution_facts(result):
        if result.get('type') == 'overview_diff':
            from ..diff.architecture_diff import comparison_execution_facts
            return comparison_execution_facts(result)
        from ..utils.results import AnalysisCompleteness, result_execution_facts
        status = result.get('map_status')
        scope = result.get('scope') or {}
        errors = (result.get('meta') or {}).get('errors', [])
        no_scope_observation = (status == 'not_requested' and not scope.get('complete')
                                and not scope.get('total_code_files'))
        if status == 'failed' or not scope or no_scope_observation or any(e.get('code') == 'E_OVERVIEW_ANALYSIS' for e in errors):
            state = AnalysisCompleteness.FAILED
        elif status == 'incomplete' or not scope.get('complete') or errors:
            state = AnalysisCompleteness.INCOMPLETE
        else:
            state = AnalysisCompleteness.COMPLETE
        return result_execution_facts(result, completeness=state)

    def _comparison(self, path: Path, against: str, top: int) -> RevealResult:
        from ..diff.architecture_diff import _open_repo, _resolve_commit, run_architecture_diff
        from ..utils.results import FailureCause
        try:
            repo = _open_repo(path.resolve())
            _resolve_commit(repo, against)
        except ValueError as exc:
            return ResultBuilder.create(
                'overview_diff', as_spelled(path, path), contract_version=CONTRACT_VERSION,
                errors=[{'code': FailureCause.INVALID_REQUEST.value, 'message': str(exc)}],
                error=str(exc))
        report = run_architecture_diff(path, against, head_ref='working tree', top_n=max(top, 1) * 4)
        return cast(RevealResult, {**report, 'type': 'overview_diff'})

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {'name': 'overview', 'description': 'Compact project map: recognized-code scope, components and static import relationships.',
                'syntax': 'overview://<path>[?top=5&no_imports=true|against=REF]',
                'examples': [{'uri': 'overview://src', 'description': 'Compact project map'},
                             {'uri': 'overview://.?top=10', 'description': 'Expand map evidence'},
                             {'uri': 'overview://.?no_imports=true', 'description': 'Scope census only'},
                             {'uri': 'overview://.?against=HEAD', 'description': 'Compare HEAD with the live working tree'}],
                'features': ['Recognized-code language counts', 'Bounded fan-in, active entrypoint candidates, components and cycles',
                             'Coverage, losses, counting rules and drill-down commands'],
                'notes': ['Static imports are not runtime execution evidence or risk judgments.',
                          'top=0 shows no graph rows; diagnostic details retain a minimum of five and maximum of fifty.',
                          'Graph totals describe the observed graph; scan accounting and losses qualify its coverage.',
                          'Data, markup and unknown extensions are not counted by the code census.',
                          'no_git and tests are obsolete; use Git, metrics and AST queries for those questions.',
                          'against selects overview_diff before map collection; comparison rejects no_imports, all and verbose.',
                          'Comparison centroid population is max(top, 1)*4; identical trees have unmeasured null centroids and proved zero change.'],
                'output_formats': ['text', 'json']}

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {'adapter': 'overview', 'description': 'Compact project map',
                'uri_syntax': 'overview://<path>?top=5&no_imports=true|against=REF',
                'resource': OverviewAdapter.RESOURCE_SPEC.schema(),
                'execution_policy': {'default_fail_on': 'none', 'fail_on': ['none']},
                'query_params': {**param_schema(OverviewAdapter.PARAM_SPECS),
                    'exclude': {'type': 'string', 'description': 'Comma-separated scope exclusion globs'},
                    'respect_gitignore': {'type': 'boolean', 'description': 'Respect .gitignore (default: true)'}},
                'elements': {}, 'supports_batch': False, 'supports_advanced': False,
                'output_types': [{'type': 'overview', 'description': 'Bounded project scope and import map',
                    'schema': {'type': 'object', 'properties': {'map': {'type': ['object', 'null']},
                               'map_status': {'type': 'string'}, 'scope': {'type': 'object'}}}},
                    {'type': 'overview_diff', 'description': 'Architecture comparison with basis and per-side snapshot proof'}],
                'example_queries': [{'uri': 'overview://src', 'description': 'Compact project map', 'output_type': 'overview'},
                    {'uri': 'overview://.?against=HEAD', 'description': 'Compare the live working tree with HEAD',
                     'output_type': 'overview_diff'}],
                'notes': ['Ordinary overview is a bounded static import map, not a quality assessment.',
                          'Comparison uses the live working tree and retains required snapshot losses.']}

    def get_structure(self, all: bool = False, verbose: bool = False, **kwargs: Any) -> RevealResult:
        with self.composition_run():
            _validate_comparison_controls(self.query_params, all_requested=all, verbose_requested=verbose)
            path = Path(self.path)
            # Direct API calls do not pass through the CLI's existing resource stat.
            # A missing/inaccessible target must not become a successful empty walk.
            path.stat()
            top = self.PARAM_SPECS[0].read(self.query_params)
            if self.result_type_for(self.query_params) == 'overview_diff':
                return self._comparison(path, _AGAINST.read(self.query_params), top)
            no_imports = self.PARAM_SPECS[2].read(self.query_params)
            all_requested = self.PARAM_SPECS[4].read(self.query_params)
            verbose_requested = self.PARAM_SPECS[5].read(self.query_params)
            expanded = all_requested or verbose_requested
            top = UNLIMITED_TOP if all or verbose or expanded else top
            scope = _run_scope(self, path)
            facts, status = ((None, 'not_requested') if no_imports else _run_imports_analysis(
                self, path, top, scope_usable=bool(scope.get('total_code_files'))))
            meta = _distinct_owner_warnings(self.composed_meta())
            if not scope:
                status = 'failed'
            note = 'Static import relationships and entrypoint candidates describe the observed graph, not runtime execution or a risk assessment.'
            if no_imports:
                note += ' Import analysis was not requested (no_imports=true).'
            result = ResultBuilder.create('overview', source=as_spelled(path, path),
                contract_version=CONTRACT_VERSION, scope=scope, meta=cast(Optional[Dict[str, Any]], meta),
                data={'path': as_spelled(path, path), 'map': facts, 'map_status': status,
                      'reading_note': note,
                      'next_steps': _next_steps(as_spelled(path, path), _navigation_exclusions(path, self.exclude_patterns),
                                                self.respect_gitignore)})
            _bound_details(cast(Dict[str, Any], result), top)
            return result
