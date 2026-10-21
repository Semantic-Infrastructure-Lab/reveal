"""Architecture briefs and git comparisons through one declared adapter."""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from reveal.capabilities import scope_dict_for_path
from reveal.reveal_types import CONTRACT_VERSION, RevealMeta, WarningEntry

from .base import ResourceAdapter, register_adapter, register_renderer
from ..analyzers.imports import service as import_analysis
from ..conventions import conventions_for_path
from ..registry import language_for_extension
from ..rendering.adapters.architecture import ArchitectureRenderer
from ..utils.entry_points import active_entry_points, entry_point_filter
from ..utils.path_utils import to_posix, traversal_failed_warning
from ..utils.query_binding import bind_declared_params, boolean_value
from ..utils.query_parser import (CliBinding, ParamSpec, QueryParams, ResourceSpec,
                                  nonnegative_display_limit, param_schema, peek_query_items)
from ..utils.results import ResultBuilder

logger = logging.getLogger(__name__)

_COMPLEXITY_ENTRY_THRESHOLD = 20  # entry point complexity that warrants a warning
_FAN_IN_RISK_THRESHOLD = 8        # fan-in count that makes a file load-bearing

# Languages where bidirectional references between files are routine, idiomatic
# domain modeling (e.g. EF Core / JPA / Hibernate navigation properties on
# parent<->child entities), not the "accidental coupling, latent ImportError"
# pattern a Python/JS circular *module* import usually signals (BACK-1005).
# One severity heuristic applied uniformly across languages misled a DD
# reviewer unfamiliar with C#/EF conventions: 42-105-file EF-entity clusters
# in Jellyfin (C#) were flagged severity:high, same as a real Python/JS cycle.
_CIRCULAR_TOLERANT_LANGUAGES = frozenset({'csharp', 'java', 'kotlin', 'swift'})


def _ast_row_valid(row: Any) -> bool:
    return (isinstance(row, dict)
            and all(isinstance(row.get(key), str) and bool(row[key]) for key in ('file', 'name'))
            and type(row.get('complexity')) is int and row['complexity'] >= 0)


def _ast_counts_valid(data: Dict[str, Any], rows: list) -> bool:
    return (all(type(data.get(key)) is int and data[key] >= 0
                for key in ('total_files', 'total_results', 'displayed_results'))
            and data['displayed_results'] == len(rows)
            and data['total_results'] >= data['displayed_results'])


def _capture_ast_observations(data: Any, observations: Optional[Dict[str, bool]]) -> None:
    if observations is None:
        return
    rows = data.get('results', data.get('elements')) if isinstance(data, dict) else None
    valid = (isinstance(data, dict) and not data.get('error') and isinstance(rows, list)
             and all(_ast_row_valid(row) for row in rows) and _ast_counts_valid(data, rows))
    if not valid:
        observations['failed'] = True
    elif data['total_results'] > 0:
        # The existing domain-filtered count precedes the limit, including zero.
        # At limit=0 the producer is authoritative for the hidden identities.
        observations['usable'] = True


def _relationship_rows_valid(rows: Any, path_key: str, counts: tuple) -> bool:
    if not isinstance(rows, list):
        return False
    return all(isinstance(row, dict) and isinstance(row.get(path_key), str) and bool(row[path_key])
               and all(type(row.get(key)) is int and row[key] >= 0 for key in counts)
               for row in rows)


def _capture_import_observations(data: Dict[str, Any], observations: Optional[Dict[str, bool]]) -> None:
    if observations is None:
        return
    sections = [('entry_points', 'file', ('fan_out',)), ('core_abstractions', 'file', ('fan_in',)),
                ('components', 'component', ('internal', 'outgoing', 'incoming'))]
    valid = all(_relationship_rows_valid(data.get(key), path, counts) for key, path, counts in sections)
    cycles = data.get('circular_groups')
    if not valid or not _valid_cycles(cycles):
        observations['failed'] = True
        return
    positive = any(row[count] > 0 for key, _, counts in sections for row in data[key] for count in counts)
    if positive or any(len(set(cycle)) >= 2 for cycle in cast(List[List[str]], cycles)):
        observations['usable'] = True


def _valid_cycles(cycles: Any) -> bool:
    return (isinstance(cycles, list) and all(isinstance(cycle, list)
            and all(isinstance(path, str) and bool(path) for path in cycle) for cycle in cycles))


def _directory_loss_error(meta, observations) -> Optional[WarningEntry]:
    if not any(w.get('type') == 'analysis_incomplete' for w in (meta or {}).get('warnings', [])):
        return None
    if observations.get('failed') or not observations.get('usable'):
        return {'code': 'E_ARCHITECTURE_ANALYSIS',
                'message': 'Required directory discovery failed; required analysis failed or no architectural observations survived'}
    return None


def _run_complex_functions(adapter: 'ArchitectureAdapter', path: Path, limit: int, *,
                           observations: Optional[Dict[str, bool]] = None) -> List[Dict[str, Any]]:
    if observations is None:
        observations = getattr(adapter, '_architecture_observations', None)
    from reveal.adapters.ast import AstAdapter
    data = adapter.compose(AstAdapter, str(path), default={},
                            query=f'complexity>9&sort=-complexity&limit={limit}',
                            cut_as=('complex_functions', 'raise ?top=N'))
    _capture_ast_observations(data, observations)
    return data.get('results', data.get('elements', []))


def _with_scope_warning(meta: Optional[RevealMeta], failures: List[OSError],
                        path: Path) -> Optional[RevealMeta]:
    """Append optional census disclosure only after required-source validation."""
    warning = traversal_failed_warning([
        (to_posix(exc.filename) if exc.filename else None, f'{type(exc).__name__}: {exc}')
        for exc in failures], path)
    if warning:
        warning['message'] = 'Independent scope/language census is incomplete; ' + warning['message']
        meta = meta or {}
        meta.setdefault('warnings', []).append(warning)
    return meta


def _run_scope(adapter: 'ArchitectureAdapter', path: Path, *,
               failures: Optional[List[OSError]] = None) -> Dict[str, Any]:
    """BACK-884: files discovered/analyzed/skipped by language, with
    per-language capability tier — additive 'scope' key in JSON output.
    Shared with overview.py via capabilities.scope_dict_for_path().

    BACK-1016: routes failures through record_composed_error() (in addition
    to the existing logger.warning) so a crashed census is reflected in
    meta.errors/confidence instead of silently rendering as an empty-but-
    trusted 'scope': {} — the same fix BACK-984 already gave every other
    sibling-adapter site in this file."""
    if failures is None:
        failures = []
    try:
        scope = scope_dict_for_path(path, on_error=failures.append)
        if failures:
            adapter.record_composed_error('scope_dict_for_path', path, failures[0])
            return {}
        return scope
    except Exception as exc:  # boundary-ok: broad-except -- the scope census is an optional report section whose callee chain (directory walk, gitignore, language sniffing in utils/path_utils) is not bounded; a failing census must not end the report, and it is recorded in meta.errors with confidence 0 by record_composed_error and logged
        logger.warning("scope census failed for %s: %s", path, exc)
        adapter.record_composed_error('scope_dict_for_path', path, exc)
        return {}


def _run_imports_analysis(adapter: 'ArchitectureAdapter', path: Path) -> Dict[str, Any]:
    # Uses ImportsAdapter's private walk/format methods directly (not
    # get_structure()) so cannot go through compose() — record the failure
    # the same way compose() would (BACK-984).
    try:
        from reveal.adapters.imports import ImportsAdapter
        importer = ImportsAdapter(str(path))
        importer._build_graph(path)
        warnings = importer.integrity_warnings(path)  # BACK-1598, BACK-1753
        if warnings:
            adapter.fold_meta({'warnings': warnings})
        return _format_imports_data(importer, path)
    except Exception as exc:  # boundary-ok: broad-except -- composition seam that bypasses compose() for the shared ImportsAdapter walk; the sibling adapter's failure set is not bounded (parse, resolution, pool), and a failure is recorded in meta.errors with confidence 0 by record_composed_error, exactly what compose() does
        adapter.record_composed_error('ImportsAdapter', path, exc)
        return {}


def _format_imports_data(adapter, path: Path, *,
                         observations: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    with import_analysis.composed_rules('architecture://'):  # BACK-2087
        fan_in_data = adapter._format_fan_in()
        entrypoints_data = adapter._format_entrypoints()
        components_data = adapter._format_components()
        circular_data = adapter._format_circular()
    _capture_import_observations({
        'entry_points': entrypoints_data.get('entries'),
        'core_abstractions': fan_in_data.get('entries'),
        'components': components_data.get('components'),
        'circular_groups': circular_data.get('cycles'),
    }, observations)

    all_entries = fan_in_data.get('entries', [])
    raw_eps = entrypoints_data.get('entries', [])
    components = components_data.get('components', [])
    cycle_groups = circular_data.get('cycles', [])

    live_eps = active_entry_points(raw_eps)
    core_abstractions = [e for e in all_entries if e.get('fan_in', 0) > 0]

    return {
        # BACK-2087: the rule these counts were made by (edge_rule, edge_rule_sections).
        'edge_rules': import_analysis.architecture_edge_rules(
            fan_in_data, entrypoints_data, components_data, circular_data),
        'entry_points': live_eps,
        # BACK-1891: the fan-in-0 count, the active count and the rule between them.
        'entry_point_filter': entry_point_filter(raw_eps),
        'core_abstractions': core_abstractions,
        'components': components,
        'circular_groups': cycle_groups,
        # BACK-518 part 2: same coverage disclosure imports:// itself already
        # gives — without it, an unsupported-language repo (e.g. all-Lua) with
        # zero entry points/abstractions renders a blank "Architecture Brief"
        # that reads as "nothing here" rather than "not analyzed".
        'unsupported_extensions': adapter.get_metadata().get('unsupported_extensions', {}),
    }


def _run_combined_analysis(adapter: 'ArchitectureAdapter', path: Path, limit: int, *,
                           observations: Optional[Dict[str, bool]] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Run imports + complexity analysis sharing one walk, one parse per file.

    Running these as two independent full-repo walk+parse passes (the original
    shape) double-parses every file on any repo bigger than the tree-sitter
    parse cache (128 entries) — see BACK-489,
    internal-docs/design/BACK489_ARCHITECTURE_PERF_FINDINGS_2026-07-06.md.
    Piggybacking the AST/complexity collection onto the imports walk's
    per-file callback keeps each file's parse-cache entry warm between the
    two uses instead of it getting evicted by the rest of a large repo.
    """
    if observations is None:
        observations = getattr(adapter, '_architecture_observations', None)
    structures: List[Dict[str, Any]] = []

    imports_data: Dict[str, Any] = {}
    graph_built = False
    try:
        from reveal.adapters.imports import ImportsAdapter
        importer = ImportsAdapter(str(path))
        # collect_structures=True runs per-file AST analysis in the same
        # (parallelized) walk as import extraction — no second full-repo pass.
        importer._build_graph(path, collect_structures=True)
        structures = importer._structures
        graph_built = True
        warnings = importer.integrity_warnings(path)  # BACK-1598, BACK-1753
        if warnings:
            adapter.fold_meta({'warnings': warnings})
        imports_data = _format_imports_data(importer, path, observations=observations)
    except Exception as exc:  # boundary-ok: broad-except -- composition seam that bypasses compose() for the shared ImportsAdapter walk; the sibling adapter's failure set is not bounded (parse, resolution, pool), and a failure is recorded in meta.errors with confidence 0 by record_composed_error, exactly what compose() does
        if observations is not None:
            observations['failed'] = True
        adapter.record_composed_error('ImportsAdapter', path, exc)

    if not graph_built:
        # The shared walk never ran, so no structures were collected either —
        # fall back to complexity analysis's own independent walk.
        if observations is None:
            return _run_complex_functions(adapter, path, limit), imports_data
        return _run_complex_functions(adapter, path, limit, observations=observations), imports_data

    try:
        from reveal.adapters.ast import AstAdapter
        # Reuses `structures` from the shared walk above (get_structure()'s
        # extra kwarg), so this can't go through compose() either — same
        # attributed-failure treatment as the ImportsAdapter branch (BACK-984).
        data = AstAdapter(str(path), f'complexity>9&sort=-complexity&limit={limit}').get_structure(structures=structures)
        _capture_ast_observations(data, observations)
        from ..utils.results import echo_source, relabel_truncations
        # Match compose(cut_as=...) while retaining the shared-walk structures.
        echo_source(data, str(path))
        relabel_truncations(data, 'complex_functions', 'raise ?top=N')
        adapter.fold_meta(data.get('meta'))
        if data.get('error'):
            adapter.record_composed_error('AstAdapter', path, ValueError(str(data['error'])))
        complex_fns = data.get('results', data.get('elements', []))
    except Exception as exc:  # boundary-ok: broad-except -- composition seam that bypasses compose() to reuse the shared walk's structures; the sibling adapter's failure set is not bounded, and a failure is recorded in meta.errors with confidence 0 by record_composed_error, exactly what compose() does
        if observations is not None:
            observations['failed'] = True
        adapter.record_composed_error('AstAdapter', path, exc)
        complex_fns = []

    return complex_fns, imports_data


def _group_language(group: List[str]) -> Optional[str]:
    """Return the dominant reveal language slug among *group*'s file paths.

    A mixed-language cycle group is rare and not the case this heuristic is
    for; majority vote over the group's extensions is enough to decide
    whether BACK-1005's OO-entity-modeling tolerance applies.
    """
    langs = Counter(
        lang for f in group
        if (lang := language_for_extension(Path(f).suffix))
    )
    return langs.most_common(1)[0][0] if langs else None


def _compute_risks(
    imports_data: Dict[str, Any],
    complex_fns: List[Dict[str, Any]],
    base_path: Path,
) -> List[Dict[str, Any]]:
    risks: List[Dict[str, Any]] = []

    file_max_cx: Dict[str, int] = {}
    for fn in complex_fns:
        f = fn.get('file', '')
        cx = fn.get('complexity', 0)
        if f:
            file_max_cx[f] = max(file_max_cx.get(f, 0), cx)

    for group in imports_data.get('circular_groups', []):
        count = len(group)
        rep = _relpath(group[0], base_path) if group else ''
        tolerant = _group_language(group) in _CIRCULAR_TOLERANT_LANGUAGES
        if tolerant:
            severity = 'medium' if count > 10 else 'low'
            description = (
                f"{count}-file circular group — likely idiomatic bidirectional "
                "domain-model refs (common in this language's entity/navigation-"
                "property conventions); verify before treating as a design smell"
            )
        else:
            severity = 'high' if count > 10 else 'medium'
            description = f"{count}-file circular group"
        risks.append({
            'type': 'circular',
            'severity': severity,
            'description': description,
            'detail': f"{rep} + {count - 1} more" if count > 1 else rep,
            'file_count': count,
            'representative': group[0] if group else '',
        })

    for ep in imports_data.get('entry_points', []):
        cx = file_max_cx.get(ep['file'], 0)
        if cx >= _COMPLEXITY_ENTRY_THRESHOLD:
            risks.append({
                'type': 'high_complexity_entry',
                'severity': 'medium',
                'description': f"{_relpath(ep['file'], base_path)} — high-complexity entry point",
                'detail': f"fan-out {ep['fan_out']}, cx {cx}",
                'file': ep['file'],
                'complexity': cx,
                'fan_out': ep['fan_out'],
            })

    for abstraction in imports_data.get('core_abstractions', [])[:5]:
        fan_in = abstraction.get('fan_in', 0)
        if fan_in >= _FAN_IN_RISK_THRESHOLD:
            risks.append({
                'type': 'load_bearing',
                'severity': 'low',
                'description': f"{_relpath(abstraction['file'], base_path)} — load-bearing file",
                'detail': f"fan-in {fan_in}",
                'file': abstraction['file'],
                'fan_in': fan_in,
            })

    return risks


def _build_next_commands(
    path: Path,
    risks: List[Dict[str, Any]],
    imports_data: Dict[str, Any],
) -> List[str]:
    """Commands to run next, from the user's cwd: paths as they named the target (BACK-1366).

    ``risks[].file`` is relative to the target by now (``_relativize_risks``), so a file
    command is spelled under ``path``; the bare file name didn't run from the cwd.
    """
    from ..utils.path_utils import as_spelled

    cmds: List[str] = []
    target = as_spelled(path, path)

    def file_arg(rel: str) -> str:
        return as_spelled(path / rel, path)

    if any(r['type'] == 'circular' for r in risks):
        cmds.append(f"reveal 'imports://{target}?circular'")

    cx_entries = [r for r in risks if r['type'] == 'high_complexity_entry']
    if cx_entries:
        worst = max(cx_entries, key=lambda r: r.get('complexity', 0))
        cmds.append(f"reveal {file_arg(worst['file'])} --boundary")

    if imports_data.get('core_abstractions'):
        cmds.append(f"reveal 'ast://{target}?complexity>20'")

    lb = [r for r in risks if r['type'] == 'load_bearing']
    if lb:
        top_lb = max(lb, key=lambda r: r.get('fan_in', 0))
        cmds.append(f"reveal {file_arg(top_lb['file'])}")

    if not cmds:
        cmds.append(f"reveal overview {target}")
        cmds.append(f"reveal {target}")

    return cmds


def _is_reexport_file(file_str: str) -> bool:
    """Barrel/re-export files (`__init__.py`, `index.ts`, `mod.rs`, `doc.go`) hold
    no logic of their own, so they must not dominate 'Core Abstractions' (BACK-1287)."""
    name = Path(file_str).name
    return name in conventions_for_path(name).reexport_files


def _relpath(file_str: str, base_path: Optional[Path]) -> str:
    """Return path relative to base_path if possible, else the original string.

    BACK-1194: delegates to the shared, resolve()-aware helper — see
    to_relative_display()'s docstring for why the old lexical-only
    relative_to() let absolute paths leak through on relative CLI targets.
    """
    from ..utils.path_utils import to_relative_display
    return to_relative_display(file_str, base_path)


def _relativize_architecture_paths(report: Dict[str, Any], base_path: Path) -> None:
    """Relativize the file-path fields the text renderer already relativizes
    via `_relpath` (_render_entry_points/_render_core_abstractions/etc), but
    in the raw `report` dict get_structure() serializes directly to JSON --
    that never routed through the text renderer, so `--format json` leaked
    absolute host paths (analyst's filesystem layout/username), same gap as
    overview.py's `_relativize_paths` (BACK-1194 follow-up). BACK-1212.

    `facts.*` comes straight from ImportsAdapter's raw (unrelativized)
    `_format_fan_in`/`_format_entrypoints`/`_format_components`/
    `_format_circular` via `_format_imports_data()` -- imports.py's own
    get_structure() relativizes those (BACK-1212), but architecture.py calls
    the adapter methods directly, bypassing that. See `_relativize_risks()`
    for the separate `risks[]` fix (must run earlier, before
    `_build_next_commands()`). Mutates in place.
    """
    from ..utils.path_utils import to_relative_display

    def rel(value: Optional[str]) -> Optional[str]:
        return to_relative_display(value, base_path) if value else value

    facts = report.get('facts', {})
    for key in ('entry_points', 'core_abstractions'):
        for entry in facts.get(key, []):
            if entry.get('file'):
                entry['file'] = rel(entry['file'])
    for component in facts.get('components', []):
        if component.get('component'):
            component['component'] = rel(component['component'])
        if component.get('top_bridge'):
            component['top_bridge'] = rel(component['top_bridge'])
    circular_groups = facts.get('circular_groups')
    if circular_groups:
        facts['circular_groups'] = [[rel(fp) for fp in group] for group in circular_groups]


def _relativize_risks(risks: List[Dict[str, Any]], base_path: Path) -> None:
    """Relativize `risks[].file`/`.representative` -- the structured fields
    `_compute_risks()` leaves raw even though it already relativizes the
    human-readable `description`/`.detail` strings computed from the same
    values (BACK-1212). Called before `_build_next_commands()`, which spells
    these target-relative files under the target as the user named it
    (BACK-1366). Mutates in place.
    """
    from ..utils.path_utils import to_relative_display

    def rel(value: Optional[str]) -> Optional[str]:
        return to_relative_display(value, base_path) if value else value

    for risk in risks:
        if risk.get('file'):
            risk['file'] = rel(risk['file'])
        if risk.get('representative'):
            risk['representative'] = rel(risk['representative'])


def _architecture_top(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('top requires an integer value')
    return nonnegative_display_limit(value)


def _architecture_ref(value: Any) -> str:
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('against requires a nonempty git ref string')
    return value


def _architecture_completeness(result, meta, invalid_only):
    from ..utils.results import AnalysisCompleteness
    if any(error.get('code') == 'E_ARCHITECTURE_ANALYSIS' for error in meta.get('errors', [])):
        return AnalysisCompleteness.FAILED
    missing = {'analysis_failed', 'parse_recovered', 'partial_parse', 'worker_lost', 'analysis_incomplete'}
    missing_inputs = any(w.get('type') in missing for w in meta.get('warnings', []))
    if invalid_only and 'analysis' not in result and not missing_inputs:
        return AnalysisCompleteness.NOT_STARTED
    incomplete = (bool(meta.get('errors')) and not invalid_only) or missing_inputs
    if isinstance(result, dict) and result.get('type') == 'architecture_diff':
        analysis = result.get('analysis')
        complete = isinstance(analysis, dict) and analysis.get('complete') is True
        incomplete = incomplete or not complete
    return AnalysisCompleteness.INCOMPLETE if incomplete else AnalysisCompleteness.COMPLETE


@register_adapter('architecture')
@register_renderer(ArchitectureRenderer)
class ArchitectureAdapter(ResourceAdapter):
    """Adapter for a targeted architectural brief: entry points, core
    abstractions, risks, and suggested next commands for a directory."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}  # --no-gitignore (BACK-1386)
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)

    RESULT_TYPE = 'architecture'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = (
        ParamSpec('top', 'integer', 'Items per text section and complexity analysis population (top*4)',
                  5, _architecture_top, minimum=0, role='analysis', examples=('top=10',),
                  zero_policy='ordinary: no ranked complexity; diff: population 4',
                  cli=CliBinding(('--top',), metavar='N')),
        ParamSpec('no_imports', 'boolean', 'Skip ordinary import graph analysis', False,
                  boolean_value, role='analysis', examples=('no_imports=true',),
                  cli=CliBinding(('--no-imports',), action='store_true')),
        ParamSpec('against', 'string', 'Compare the live working tree against a git ref', None,
                  _architecture_ref, role='operation', uri_codec='percent',
                  cli=CliBinding(('--against',), metavar='REF')),
        ParamSpec('verbose', 'boolean', 'Expand ordinary complexity analysis and text sections',
                  False, boolean_value, role='analysis'),
    )

    def __init__(self, resource: str, query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        self.path = str(Path(resource).expanduser())
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(self.PARAM_SPECS, query or '', transport='uri')
        self._warn_unknown_query_params(self.query_params)

    @staticmethod
    def result_type_for(params):
        return 'architecture_diff' if 'against' in dict(peek_query_items(params)) else 'architecture'

    @staticmethod
    def answer_requirement_error(result, expected_type, prior_facts=None):
        from ..utils.results import AnalysisCompleteness, FailureCause
        if expected_type != 'architecture_diff':
            return None
        analysis = result.get('analysis')
        if isinstance(analysis, dict) and isinstance(analysis.get('complete'), bool):
            return None
        errors = result.get('meta', {}).get('errors', [])
        invalid_only = bool(errors) and all(error.get('code') == 'invalid_request' for error in errors)
        before_analysis = prior_facts is None or (
            prior_facts.completeness is AnalysisCompleteness.NOT_STARTED
            and prior_facts.failures == frozenset({FailureCause.INVALID_REQUEST}))
        if invalid_only and 'analysis' not in result and before_analysis:
            return None
        return 'Architecture comparison missing required completeness evidence'

    @staticmethod
    def validate_request(params, args):
        from ..cli.routing.ledger import peek
        supplied = dict(peek_query_items(params))
        if 'against' in supplied and ('no_imports' in supplied or 'verbose' in supplied or peek(args, 'verbose', False)):
            raise ValueError('architecture diff does not support no_imports or verbose')

    @staticmethod
    def execution_facts(result):
        from ..utils.results import (ExecutionFacts, FailureCause, failure_execution_facts,
                                     result_execution_facts)
        meta = result.get('meta', {}) if isinstance(result, dict) else {}
        errors = meta.get('errors', [])
        invalid_only = bool(errors) and all(error.get('code') == 'invalid_request' for error in errors)
        state = _architecture_completeness(result, meta, invalid_only)
        cause = FailureCause.INVALID_REQUEST if invalid_only else FailureCause.ANALYSIS
        facts = result_execution_facts(result, completeness=state, failure_cause=cause)
        if invalid_only and not facts.failures:
            # Explicit owner usage diagnostics remain a cause even without a
            # redundant top-level error; retain independent completeness facts.
            return ExecutionFacts(state, failures=failure_execution_facts(cause).failures)
        return facts

    def _comparison(self, path: Path, against: str, top: int) -> Dict[str, Any]:
        from ..diff.architecture_diff import _open_repo, _resolve_commit, run_architecture_diff
        from ..utils.results import FailureCause
        try:
            repo = _open_repo(path.resolve())
            _resolve_commit(repo, against)
        except ValueError as exc:
            return cast(Dict[str, Any], ResultBuilder.create(
                'architecture_diff', self.path, contract_version=CONTRACT_VERSION,
                errors=[{'code': FailureCause.INVALID_REQUEST.value, 'message': str(exc)}],
                error=str(exc)))
        return run_architecture_diff(path, against, top_n=max(top, 1) * 4)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'architecture',
            'description': 'Architectural brief for a directory: entry points, core abstractions, risks, and suggested next commands.',
            'syntax': 'architecture://<path>[?top=5&no_imports=true|against=REF]',
            'examples': [
                {'uri': 'architecture://src', 'description': 'Brief for a subdirectory'},
                {'uri': 'architecture://.?top=10', 'description': 'Top 10 items per section'},
                {'uri': 'architecture://.?no_imports=true', 'description': 'Skip import graph analysis'},
            ],
            'features': [
                'Entry points and core abstractions (via imports:// fan-in/fan-out)',
                'Circular dependency groups',
                'High-complexity entry points and load-bearing files as risks',
                'Suggested next reveal commands',
            ],
            'notes': [
                'Static imports only — dynamically loaded files (plugins, registries) may appear as entry points.',
                'Counts state their rule (Rule: lines in text, edge_rule and edge_rule_sections in JSON): '
                'function-level imports count, entry points ignore test importers, cycles use the load-time view.',
                'Use --against REF or ?against=REF for git comparisons; diff rejects no_imports and verbose.',
            ],
            'see_also': [
                'reveal architecture <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'architecture',
            'description': 'Targeted architectural brief (entry points, core abstractions, risks, next commands)',
            'uri_syntax': 'architecture://<path>?top=5&no_imports=true',
            'resource': ArchitectureAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': 'none', 'fail_on': ['none']},
            'query_params': param_schema(ArchitectureAdapter.PARAM_SPECS),
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {'type': 'architecture_diff', 'description': 'Git comparison with explicit snapshot completeness'},
                {
                    'type': 'architecture',
                    'description': 'Facts (entry points/core abstractions/components/cycles), risks, and next commands',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'facts': {'type': 'object'},
                            'risks': {'type': 'array'},
                            'next_commands': {'type': 'array'},
                            'edge_rule': {'type': 'object'},
                            'edge_rule_sections': {'type': 'object'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'architecture://src', 'description': 'Brief for src/', 'output_type': 'architecture', 'task': 'due-diligence'},
            ],
            'notes': [
                'Composed from imports:// (fan-in/fan-out/circular) and ast:// (complexity) — not an independent scan.',
                'against selects architecture_diff; ordinary no_imports/verbose controls do not apply.',
            ],
        }

    def get_structure(self, verbose: bool = False, **kwargs: Any) -> Dict[str, Any]:
        from argparse import Namespace
        self.validate_request(self.query_params, Namespace(verbose=verbose))
        path = Path(self.path)
        top_spec, no_imports_spec, against_spec, verbose_spec = self.PARAM_SPECS
        if self.result_type_for(self.query_params) == 'architecture_diff':
            return self._comparison(path, against_spec.read(self.query_params), top_spec.read(self.query_params))
        verbose = verbose or verbose_spec.read(self.query_params)
        from .overview import UNLIMITED_TOP
        top = UNLIMITED_TOP if verbose else top_spec.read(self.query_params)
        no_imports = no_imports_spec.read(self.query_params)
        observations: Dict[str, bool] = {}

        self._architecture_observations = observations
        try:
            if no_imports:
                complex_fns = _run_complex_functions(self, path, top * 4)
                imports_data: Dict[str, Any] = {}
            else:
                complex_fns, imports_data = _run_combined_analysis(self, path, top * 4)
        finally:
            del self._architecture_observations

        risks = _compute_risks(imports_data, complex_fns, path)
        if not no_imports:
            from reveal.adapters.imports import detect_autoload_regime, autoload_regime_warning
            regime = detect_autoload_regime(path)
            if regime:
                # BACK-1245: surface in `risks` (the established disclosure
                # channel other adapters/callers already consume) rather
                # than only in the text renderer's footer -- a JSON caller
                # reading entry_points/core_abstractions never saw this.
                risks.insert(0, {
                    'type': 'autoload_regime',
                    'severity': 'medium',
                    'description': f"{regime['framework']} detected ({regime['evidence']}) — import graph is structurally thin here",
                    'detail': autoload_regime_warning(regime),
                })
        _relativize_risks(risks, path)
        next_commands = _build_next_commands(path, risks, imports_data)

        scope_failures: List[OSError] = []
        report = {
            'path': str(path),
            'facts': {
                'entry_points': imports_data.get('entry_points', []),
                'core_abstractions': imports_data.get('core_abstractions', []),
                'components': imports_data.get('components', []),
                'circular_groups': imports_data.get('circular_groups', []),
            },
            'risks': risks,
            'next_commands': next_commands,
            **imports_data.get('edge_rules', {}),
            **({'entry_point_filter': imports_data['entry_point_filter']}
               if 'entry_point_filter' in imports_data else {}),
            'unsupported_extensions': imports_data.get('unsupported_extensions', {}),
            'scope': _run_scope(self, path, failures=scope_failures),
        }
        if verbose:
            report['verbose'] = True
        if no_imports:
            report['no_imports'] = True
        _relativize_architecture_paths(report, path)

        meta = self.composed_meta()
        error = _directory_loss_error(meta, observations)
        if error:
            meta = meta or {}
            meta.setdefault('errors', []).append(error)
        meta = _with_scope_warning(meta, scope_failures, path)
        return ResultBuilder.create(
            result_type='architecture',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            scope=report.pop('scope'),
            data=report,
            warnings=meta.get('warnings') if meta else None,
            errors=meta.get('errors') if meta else None,
            confidence=meta.get('confidence') if meta else None,
        )
