"""overview:// adapter - one-glance codebase dashboard.

Scan/render logic lives here (BACK-901/BACK-958); `cli/commands/overview.py`
is a thin argparse shim over this adapter, matching the URI/adapter contract
every other capability follows.
"""

from __future__ import annotations

import logging
import math
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast

from reveal.capabilities import scope_dict_for_path
from reveal.errors import NotApplicableError
from reveal.reveal_types import CONTRACT_VERSION, RevealMeta, WarningEntry

from .ast import AstAdapter
from .base import ResourceAdapter, register_adapter, register_renderer
from .git import GitAdapter
from .imports import ImportsAdapter
from .stats import StatsAdapter
from ..utils.exclusions import exclusion_scope
from ..utils.gitignore import respect_gitignore_param
from ..utils.path_utils import as_spelled, display_name_for_path
from ..utils.query_binding import bind_declared_params, boolean_value
from ..rendering.adapters.overview import (  # noqa: F401 -- the render helpers are re-exported
    OverviewRenderer,
    _NON_CODE_EXT_LABELS,
    _age_label,
    _is_test_file,
    _language_breakdown,
    _relpath,
    _render_architecture,
    _render_codebase_stats,
    _render_complex_functions,
    _render_git_log,
    _render_hotspots,
    _render_language_breakdown,
    _render_next_steps,
    _render_overview,
    _render_quality_pulse,
)
from ..utils.query_parser import (CliBinding, ParamSpec, QueryParams, ResourceSpec,
                                  join_exclude_patterns, nonnegative_display_limit,
                                  param_schema, peek_query_items, split_exclude_param)
from ..utils.results import ResultBuilder, note_truncation

logger = logging.getLogger(__name__)


# Large-but-finite stand-in for "no cap" on overview's --top-bounded sections
# (Languages, Hotspots, Entry points, Components; also the Complex-functions and
# git-log data fetch limits). Keeps every `[:top]`/`min(len(x), top)` call site
# plain int arithmetic instead of needing None-handling threaded through each
# renderer/collector — and a real "-n <huge>" git-log/AST query behaves exactly
# like an uncapped one, bounded by the actual repo/result size either way
# (BACK-1226).
UNLIMITED_TOP = 10**9


def _object(value: Any, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f'{field} requires an object')
    return value


def _count(data: Dict[str, Any], field: str) -> int:
    value = data.get(field)
    if type(value) is not int or value < 0:
        raise ValueError(f'{field} requires a non-negative integer count')
    return value


def _number(value: Any, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{field} requires a finite number')
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f'{field} requires a finite number')


def _text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{field} requires a nonempty string')


def _rows(data: Dict[str, Any], field: str) -> List[Dict[str, Any]]:
    value = data.get(field)
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f'{field} requires an array of objects')
    return cast(List[Dict[str, Any]], value)


def _validate_stats(data: Any) -> None:
    data = _object(data, 'StatsAdapter answer')
    summary = _object(data.get('summary'), 'stats.summary')
    for field in ('total_files', 'total_lines', 'total_code_lines', 'total_functions', 'total_classes'):
        _count(summary, field)
    for field in ('avg_complexity', 'avg_quality_score'):
        _number(summary.get(field), field)
    files = _rows(data, 'files')
    if len(files) != summary['total_files']:
        raise ValueError('stats.files must retain the summary total_files inventory')
    for entry in files:
        _text(entry.get('file'), 'stats.files.file')
    for hotspot in _rows(data, 'hotspots'):
        _text(hotspot.get('file'), 'stats.hotspots.file')
        _number(hotspot.get('quality_score'), 'stats.hotspots.quality_score')
        issues = hotspot.get('issues')
        if not isinstance(issues, list) or any(not isinstance(issue, str) for issue in issues):
            raise ValueError('stats.hotspots.issues requires an array of strings')


def _validate_functions(data: Dict[str, Any], field: str) -> None:
    for function in _rows(data, field):
        _text(function.get('file'), f'{field}.file')
        _text(function.get('name'), f'{field}.name')
        _count(function, 'complexity')


def _validate_ast(data: Any) -> None:
    data = _object(data, 'AstAdapter answer')
    field = 'results' if 'results' in data else 'elements'
    _validate_functions(data, field)
    for count_field in ('total_files', 'total_results', 'displayed_results'):
        _count(data, count_field)
    if data['displayed_results'] != len(data[field]) or data['total_results'] < data['displayed_results']:
        raise ValueError('AST result counts must cover the retained results')


def _validate_scope(data: Any) -> None:
    data = _object(data, 'scope census')
    for field in ('total_code_files', 'skipped_gitignore', 'skipped_no_analyzer', 'skipped_dirs'):
        _count(data, field)
    languages = _rows(data, 'languages')
    for language in languages:
        _text(language.get('language'), 'scope.languages.language')
        _count(language, 'files')
    if sum(language['files'] for language in languages) != data['total_code_files']:
        raise ValueError('scope language counts must sum to total_code_files')


def _validate_import_rows(data: Any, field: str, kind: str) -> None:
    for entry in _rows(_object(data, 'ImportsAdapter answer'), field):
        _text(entry.get('component' if kind == 'components' else 'file'), f'{kind}.path')
        if kind == 'components':
            _count(entry, 'files')
            _number(entry.get('cohesion'), 'components.cohesion')
        else:
            _count(entry, 'fan_out')
            if kind == 'fan_in':
                _count(entry, 'fan_in')


def _validate_unsupported(unsupported: Any) -> None:
    for extension, count in _object(unsupported, 'unsupported_extensions').items():
        _text(extension, 'unsupported extension')
        _count({'count': count}, 'count')


def _validate_import_metadata(metadata: Any, unsupported: Any) -> None:
    metadata = _object(metadata, 'architecture.metadata')
    for field in ('files_failed', 'files_lost'):
        count = _count(metadata, field+'_count')
        paths = metadata.get(field)
        if not isinstance(paths, list) or len(paths) != min(count, 50):
            raise ValueError(f'{field} must retain the first 50 paths or the full smaller population')
        for path in paths:
            _text(path, field)
    if metadata['files_lost_count'] > metadata['files_failed_count']:
        raise ValueError('files_lost_count cannot exceed files_failed_count')
    for path, causes in _object(metadata.get('extraction_diagnostics'), 'extraction_diagnostics').items():
        _text(path, 'extraction_diagnostics path')
        _object(causes, 'extraction_diagnostics causes')
    _validate_unsupported(unsupported)


def _validate_architecture(data: Any) -> None:
    data = _object(data, 'architecture')
    for field in ('fan_in', 'entrypoints', 'components'):
        _validate_import_rows(data, field, field)
    _count(data, 'circular_count')
    _validate_import_metadata(data.get('metadata'), data.get('unsupported_extensions'))


def _validate_git_log(data: Any) -> None:
    data = _object(data, 'GitAdapter answer')
    field = 'history' if 'history' in data else 'commits'
    for commit in _rows(data, field):
        _text(commit.get('hash'), 'git commit hash')
        if not isinstance(commit.get('message'), str):
            raise ValueError('git commit message requires a string')
        if commit.get('timestamp') is not None:
            _number(commit['timestamp'], 'git commit timestamp')


def _required_child(adapter: 'OverviewAdapter', owner: type, path: Path,
                    validate: Callable[[Any], None], **kwargs: Any) -> Dict[str, Any]:
    # A unique fallback distinguishes an already-attributed compose failure from
    # a child returning {}, which is missing evidence rather than empty success.
    missing = object()
    data = adapter.compose(owner, str(path), default=missing, **kwargs)
    if data is missing or (isinstance(data, dict) and data.get('error')):
        return {}
    try:
        validate(data)
    except ValueError as exc:
        adapter.record_composed_error(getattr(owner, '__name__', str(owner)), path, exc)
        return {}
    return cast(Dict[str, Any], data)


def _overview_top(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('top requires a non-negative whole number')
    return nonnegative_display_limit(value)


def without_internal_filter_warnings(meta: Optional[RevealMeta]) -> List[WarningEntry]:
    """The composed warnings minus the typo hint for a filter key this adapter wrote itself.

    overview:// and hotspots:// both compose an AST query they generate (``complexity>9``,
    ``complexity>=N``); on a tree with no function AST cannot observe that key and warns
    "this may be a typo", which no caller could act on. A filter the CALLER wrote still
    warns, because ast:// emits it for a user query that never passes through here.
    """
    return [w for w in ((meta or {}).get('warnings') or []) if w.get('type') != 'unknown_filter_key']


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_stats(adapter: 'OverviewAdapter', path: Path, top: int) -> Dict[str, Any]:
    """Fetch stats and the top ``top`` hotspots via StatsAdapter.

    BACK-1042: forwards --exclude/--respect-gitignore as a raw query string
    (not compose()'s **params/urlencode path — nothing downstream in
    parse_query_params URL-decodes, so an urlencoded '*' would reach
    find_analyzable_files still percent-escaped and never match). ',', '&', '='
    and '%' inside a pattern are escaped by join_exclude_patterns (BACK-1380).

    BACK-1543: ``?top=N`` is forwarded, and stats' cut is restated as this report's
    ``hotspots``. Before, stats kept its own top 10 and dropped the total, so
    ``?top=2`` still listed 5 and "... and 5 more" counted against that hidden 10.
    """
    query = f'hotspots=true&top={top}'
    exclude_patterns = adapter.exclude_patterns
    if exclude_patterns:
        query += f'&exclude={join_exclude_patterns(exclude_patterns)}'
    query += f'&respect_gitignore={"true" if adapter.respect_gitignore else "false"}'
    stats = _required_child(adapter, StatsAdapter, path, _validate_stats, query=query,
                            cut_as=('hotspots', 'raise ?top=N'))
    if stats.get('warnings'):
        adapter.fold_meta({'warnings': stats['warnings']})
    # Each file's language as the scope census names it, while the file can be
    # read (`.h` is sniffed for C++); the text census counted by extension alone
    # and contradicted the JSON scope (BACK-1428).
    for entry in stats.get('files') or []:
        entry['language'] = display_name_for_path(path / entry['file'] if path.is_dir() else path)
    return stats


def _run_scope(adapter: 'OverviewAdapter', path: Path) -> Dict[str, Any]:
    """BACK-884: files discovered/analyzed/skipped by language, with
    per-language capability tier — additive 'scope' key in JSON output.
    Shared with architecture.py via capabilities.scope_dict_for_path().

    BACK-1016: routes failures through record_composed_error() (in addition
    to the existing logger.warning) so a crashed census is reflected in
    meta.errors/confidence instead of silently rendering as an empty-but-
    trusted 'scope': {} — the same fix BACK-984 already gave every other
    sibling-adapter site in this file.

    BACK-1042: honors --exclude/--respect-gitignore so the scope census
    agrees with what stats/check actually skipped.
    """
    try:
        scope = scope_dict_for_path(
            path,
            exclude_patterns=adapter.exclude_patterns,
            respect_gitignore=adapter.respect_gitignore,
        )
        _validate_scope(scope)
        return scope
    except Exception as exc:  # boundary-ok: broad-except -- the scope census is an optional report section whose callee chain (directory walk, gitignore, language sniffing in utils/path_utils) is not bounded; a failing census must not end the report, and it is recorded in meta.errors with confidence 0 by record_composed_error and logged
        logger.warning("scope census failed for %s: %s", path, exc)
        adapter.record_composed_error('scope_dict_for_path', path, exc)
        return {}


def _resolve_git_root(path: Path) -> Optional[Path]:
    """Discover the git repo root enclosing *path* (BACK-516).

    ``GitAdapter``/pygit2 walk up to the nearest ancestor ``.git`` unconditionally
    (correct git behavior), so a directory with no ``.git`` of its own — a vendored
    tree, a sample corpus, a submodule checked out without its own ``.git`` — silently
    inherits its enclosing repo's history. Returns the discovered root so callers can
    detect and disclose that mismatch; returns ``None`` if *path* isn't inside a repo
    at all. A ValueError (GitAdapter's "Failed to open repository", e.g. a libgit2
    ``safe.directory`` refusal) is not "no repo" and propagates (BACK-1691); see
    ``_git_root_or_disclose``.
    """
    try:
        metadata = _object(GitAdapter(path=str(path)).get_metadata(), 'Git metadata')
        root = metadata.get('path')
        return Path(root).resolve() if root else None
    except NotApplicableError:
        return None


def _git_root_or_disclose(adapter: 'OverviewAdapter', path: Path) -> Optional[Path]:
    """Resolve optional Git, retaining operational failures as composed errors.

    Without it the git-root mismatch warning was skipped and nothing said why.
    """
    try:
        return _resolve_git_root(path)
    except (ImportError, OSError, ValueError) as exc:
        adapter.record_composed_error('git_root', path, exc)
        return None


def _run_git_log(adapter: 'OverviewAdapter', path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch the newest ``limit`` commits via GitAdapter, and restate its cut as ``git_log``.

    BACK-1547: through ``compose`` like the other sections. It had constructed GitAdapter
    directly with a dict query (BACK-1016), so git's cut never reached this report and
    ``?top=1`` showed one commit as the whole log. GitAdapter takes ``compose``'s
    ``(resource, query-string)`` call, since it moves a query string passed as its ``ref``
    into its query. A crashed git log is still an attributed composed error, not ``[]``.

    BACK-1225: the query type is 'history', which GitAdapter's subpath dispatch recognizes
    ('log' fell through to its file-content branch on every subdirectory target). The two
    result shapes differ by key: repo-root's ``refs.get_ref_structure()`` returns
    'history', a subpath's ``files.get_file_history()`` returns 'commits', so both are read.
    """
    data = _required_child(adapter, GitAdapter, path, _validate_git_log,
                           query=f'type=history&limit={limit}',
                           cut_as=('git_log', 'raise ?top=N'))
    return data.get('history', data.get('commits', []))


def _run_complex_functions(adapter: 'OverviewAdapter', path: Path, limit: int) -> List[Dict[str, Any]]:
    """Fetch top complex functions via AstAdapter."""
    data = _required_child(adapter, AstAdapter, path, _validate_ast,
                            query=f'complexity>9&sort=-complexity&limit={limit}',
                            cut_as=('complex_functions', 'raise ?top=N'))
    return data.get('results', data.get('elements', []))


def _imports_metadata(adapter: 'OverviewAdapter', metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Retain the import owner's diagnostic fields and its existing path caps."""
    retained = {key: deepcopy(metadata[key]) for key in (
        'files_failed_count', 'files_failed', 'files_lost_count', 'files_lost',
        'extraction_diagnostics') if key in metadata}
    disclosures: Dict[str, Any] = {}
    for field in ('files_failed', 'files_lost'):
        count = field + '_count'
        if field in retained and count in retained:
            note_truncation(disclosures, f'architecture.metadata.{field}',
                            len(retained[field]), retained[count], 'auto_cap',
                            hint=f'the first 50 by path; {count} is exact')
    adapter.fold_meta(disclosures.get('meta'))
    return retained


def _run_imports_analysis(adapter: 'OverviewAdapter', path: Path) -> Dict[str, Any]:
    """Build import graph once and return architectural data for overview.

    Uses ImportsAdapter's private walk/format methods directly (not
    get_structure()) so cannot go through compose() — record the failure
    the same way compose() would (BACK-984).
    """
    try:
        importer = ImportsAdapter(str(path))
        # BACK-1495: this call bypasses compose(), so --exclude has to be scoped here.
        with exclusion_scope(path if path.is_dir() else path.parent, adapter.exclude_patterns):
            # Match ImportsAdapter.get_structure's resolved analysis target;
            # its metadata keys must not reinterpret a cwd-relative prefix.
            importer._build_graph(path.resolve())
        warnings = importer.integrity_warnings(path)  # BACK-1598, BACK-1753
        if warnings:
            adapter.fold_meta({'warnings': warnings})
        fan_in = importer._format_fan_in()
        entrypoints = importer._format_entrypoints()
        components = importer._format_components()
        circular = importer._format_circular()
        metadata = importer.get_metadata()
        _validate_import_rows(fan_in, 'entries', 'fan_in')
        _validate_import_rows(entrypoints, 'entries', 'entrypoints')
        _validate_import_rows(components, 'components', 'components')
        _count(_object(circular, 'circular imports'), 'count')
        metadata = _object(metadata, 'ImportsAdapter metadata')
        unsupported = metadata.get('unsupported_extensions')
        _validate_unsupported(unsupported)
        try:
            _validate_import_metadata(metadata, unsupported)
        except ValueError as exc:
            # Retain independently valid rankings and coverage disclosure, but
            # never fill unknown failure counts with fabricated zero evidence.
            adapter.record_composed_error('ImportsAdapter', path, exc)
            retained = {}
        else:
            retained = _imports_metadata(adapter, metadata)
        return {
            'fan_in': fan_in.get('entries', []),
            'entrypoints': entrypoints.get('entries', []),
            'components': components.get('components', []),
            'circular_count': circular.get('count', 0),
            # BACK-518 part 2: disclose files the import graph couldn't cover,
            # same signal imports:// itself already gives — otherwise an
            # unsupported-language repo (all fan_in/entrypoints/components
            # empty) renders as a blank Architecture section, which reads as
            # "nothing here" rather than "not analyzed".
            'unsupported_extensions': unsupported,
            'metadata': retained,
        }
    except Exception as exc:  # boundary-ok: broad-except -- composition seam that bypasses compose() for the shared ImportsAdapter walk; the sibling adapter's failure set is not bounded (parse, resolution, pool), and a failure is recorded in meta.errors with confidence 0 by record_composed_error, exactly what compose() does
        adapter.record_composed_error('ImportsAdapter', path, exc)
        return {'fan_in': [], 'entrypoints': [], 'components': [], 'circular_count': 0, 'unsupported_extensions': {}}


def _relativize_import_diagnostics(metadata: Dict[str, Any], base_path: Path) -> None:
    for field in ('files_failed', 'files_lost'):
        if field in metadata:
            # Imports' path lists retain the caller's cwd spelling; diagnostic
            # keys are already relative to its target. Normalize only the lists.
            metadata[field] = [_relpath(Path(file).absolute().as_posix(), base_path)
                               for file in metadata[field]]
    if 'extraction_diagnostics' in metadata:
        metadata['extraction_diagnostics'] = {
            _relpath(file, base_path): cause
            for file, cause in metadata['extraction_diagnostics'].items()}


def _relativize_paths(
    complex_fns: List[Dict[str, Any]],
    architecture: Dict[str, Any],
    base_path: Path,
) -> None:
    """Relativize the same file-path fields the text renderer already
    relativizes (via `_relpath`), but in the raw structures the JSON
    output serializes directly — get_structure() never routed through
    the text renderer, so `--format json` leaked absolute host paths
    (analyst's filesystem layout/username) even after BACK-1194 fixed
    the text path. Mutates in place.
    """
    _relativize_import_diagnostics(architecture.get('metadata', {}), base_path)
    for fn in complex_fns:
        if fn.get('file'):
            fn['file'] = _relpath(fn['file'], base_path)
    for section in ('fan_in', 'entrypoints'):
        for entry in architecture.get(section, []):
            if entry.get('file'):
                entry['file'] = _relpath(entry['file'], base_path)
    for component in architecture.get('components', []):
        if component.get('component'):
            component['component'] = _relpath(component['component'], base_path)
        if component.get('top_bridge'):
            component['top_bridge'] = _relpath(component['top_bridge'], base_path)


def _annotate_provenance(complex_fns: List[Dict[str, Any]], architecture: Dict[str, Any]) -> None:
    """Tag each ranked entry with its provenance classification (BACK-1195):
    'test' / 'vendor' / 'minified' / None (first-party). Live evidence on a
    real corpus: overview://'s top-5 components-by-cohesion and top
    complexity findings were 100% vendored/generated/test code, with the one
    genuine first-party finding ranked below the noise — a reader had no way
    to discount the noise in place without this. Must run AFTER
    `_relativize_paths()` so path fields are already relative to the scan
    root (classification only needs the relative path components, not the
    absolute one). Mutates in place.
    """
    from ..utils.path_utils import classify_path_provenance

    def provenance_for(file_str: Optional[str]) -> Optional[str]:
        if not file_str:
            return None
        rel = Path(file_str)
        return classify_path_provenance(rel.parts[:-1], rel.name)

    for fn in complex_fns:
        fn['provenance'] = provenance_for(fn.get('file'))
    for section in ('fan_in', 'entrypoints'):
        for entry in architecture.get(section, []):
            entry['provenance'] = provenance_for(entry.get('file'))
    for component in architecture.get('components', []):
        component['provenance'] = provenance_for(component.get('component'))


@register_adapter('overview')
@register_renderer(OverviewRenderer)
class OverviewAdapter(ResourceAdapter):
    """Adapter for the one-glance codebase dashboard: languages, quality,
    hotspots, architecture, recent activity."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    # --no-gitignore (BACK-1202). --all lifts ?top=N for the data, not only the render
    # (BACK-1543): overview://X --all printed "showing 5 of 387" complex functions.
    CLI_QUERY_FLAGS = {'all': 'top=1000000', 'respect_gitignore': 'respect_gitignore=false'}

    RESULT_TYPE = 'overview'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = (
        ParamSpec('top', 'integer', 'Items per section; also limits Stats, AST and Git populations',
                  5, _overview_top, minimum=0, role='analysis', examples=('top=10',),
                  zero_policy='Stats hotspots: all; AST and Git: none; text rankings: none',
                  cli=CliBinding(('--top',), metavar='N')),
        ParamSpec('no_git', 'boolean', 'Skip repository discovery and recent Git activity',
                  False, boolean_value, role='analysis', examples=('no_git=true',),
                  cli=CliBinding(('--no-git',), action='store_true')),
        ParamSpec('no_imports', 'boolean', 'Skip import graph analysis (architecture section)',
                  False, boolean_value, role='analysis', examples=('no_imports=true',),
                  cli=CliBinding(('--no-imports',), action='store_true')),
    )

    def __init__(self, resource: str, query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        self.path = str(Path(resource).expanduser())
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(self.PARAM_SPECS, query or '', transport='uri')
        self._warn_unknown_query_params(self.query_params)  # BACK-507
        # BACK-1042
        exclude_param = self.query_params.get('exclude')
        self.exclude_patterns: List[str] = (
            split_exclude_param(exclude_param)
        )
        self.respect_gitignore: bool = respect_gitignore_param(self.query_params)

    def answer_requirement_error(self, result, expected_type, prior_facts=None):
        # A canonical failed answer may lack section payloads. Enabled child
        # collectors have already recorded those failures before projection.
        if result.get('error') or result.get('meta', {}).get('errors'):
            return None
        try:
            _validate_stats(result.get('stats'))
            _validate_scope(result.get('scope'))
            _validate_functions(result, 'complex_functions')
            _rows(result, 'git_log')
            architecture = _object(result.get('architecture'), 'architecture')
            no_imports = dict(peek_query_items(self.query_params)).get('no_imports', False)
            if not no_imports or architecture:
                _validate_architecture(architecture)
        except ValueError as exc:
            return f'Overview missing required answer evidence: {exc}'
        return None

    @staticmethod
    def execution_facts(result):
        from ..utils.results import AnalysisCompleteness, result_execution_facts
        meta = result.get('meta', {})
        errors = meta.get('errors', [])
        required_warnings = {'analysis_failed', 'parse_recovered', 'parse_degraded',
                             'partial_parse', 'worker_lost', 'check_rules_failed'}
        missing = any(warning.get('type') in required_warnings for warning in meta.get('warnings', []))
        architecture = result.get('architecture')
        metadata = architecture.get('metadata') if isinstance(architecture, dict) else None
        metadata = metadata if isinstance(metadata, dict) else {}
        missing = missing or any(type(metadata.get(field)) is int and metadata[field] > 0
                                 for field in ('files_failed_count', 'files_lost_count'))
        incomplete = missing or bool(errors)
        state = AnalysisCompleteness.INCOMPLETE if incomplete else AnalysisCompleteness.COMPLETE
        return result_execution_facts(result, completeness=state)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'overview',
            'description': 'One-glance codebase dashboard: languages, quality, hotspots, recent activity.',
            'syntax': 'overview://<path>[?top=5&no_git=true&no_imports=true]',
            'examples': [
                {'uri': 'overview://src', 'description': 'Dashboard for src/'},
                {'uri': 'overview://.?no_git=true', 'description': 'Skip the recent-activity section'},
                {'uri': 'overview://.?top=10', 'description': 'Top 10 items per section'},
            ],
            'features': [
                'Language breakdown, codebase size, quality pulse',
                'Hotspots (via stats://) and complex functions (via ast://)',
                'Architecture summary: entry points, core abstractions, components (via imports://)',
                'Recent git activity (via git://)',
                "complex_functions[]/architecture.{fan_in,entrypoints,components}[] each carry a "
                "'provenance' field: 'test'/'vendor'/'minified'/null (first-party) — BACK-1195, "
                'so a reader can discount vendored/generated/test noise in the ranking in place.',
            ],
            'notes': [
                'Static imports only for the architecture section — dynamically loaded files may appear as entry points.',
                '?exclude= applies to stats/hotspots, scope and the Imports architecture section. '
                'Complex functions retain their existing scope; global --exclude also filters AST.',
                'Every section skips what git ignores (tracked files are never skipped); '
                'respect_gitignore=false / --no-gitignore includes it everywhere (BACK-1386).',
                'Both spellings use the overview v1.1 answer and none-only execution policy. '
                'Completed work exits 0; invalid requests exit 2; required analysis/output failures exit 3.',
            ],
            'see_also': [
                'reveal overview <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'overview',
            'description': 'One-glance codebase dashboard (languages, quality, hotspots, architecture, recent activity)',
            'uri_syntax': 'overview://<path>?top=5&no_git=true&no_imports=true&exclude=pat&respect_gitignore=true',
            'resource': OverviewAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': OverviewAdapter.DEFAULT_FAIL_ON,
                                 'fail_on': list(OverviewAdapter.FINDINGS_POLICIES)},
            'query_params': {
                **param_schema(OverviewAdapter.PARAM_SPECS),
                'exclude': {'type': 'string', 'description': 'Comma-separated globs for stats/hotspots, scope and Imports; does not filter AST complex functions', 'examples': ['exclude=dist/*,*.min.js']},
                'respect_gitignore': {'type': 'boolean', 'description': 'Respect .gitignore for the stats/hotspots and scope sections (default: true)', 'examples': ['respect_gitignore=false']},
            },
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'overview',
                    'description': 'Stats/hotspots, complex functions, architecture summary, recent git log',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'stats': {'type': 'object'},
                            'git_log': {'type': 'array'},
                            'architecture': {'type': 'object'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'overview://src', 'description': 'Dashboard for src/', 'output_type': 'overview'},
            ],
            'notes': [
                'Composed from stats://, git://, ast://, and imports:// — not an independent scan.',
            ],
        }

    def get_structure(self, all: bool = False, verbose: bool = False, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        top_spec, no_git_spec, no_imports_spec = self.PARAM_SPECS
        requested_top = top_spec.read(self.query_params)
        top = UNLIMITED_TOP if all or verbose else requested_top
        no_git = no_git_spec.read(self.query_params)
        no_imports = no_imports_spec.read(self.query_params)

        stats = _run_stats(self, path, top)
        git_root = None if no_git else _git_root_or_disclose(self, path)
        git_log = [] if git_root is None else _run_git_log(self, path, top)
        git_foreign_root: Optional[Path] = None
        # Compare resolved: 'overview://.' at a repo root is not foreign to itself.
        if git_log and git_root is not None and git_root.resolve() != path.resolve():
            git_foreign_root = git_root
        complex_fns = _run_complex_functions(self, path, top)
        architecture = {} if no_imports else _run_imports_analysis(self, path)
        _relativize_paths(complex_fns, architecture, path)
        _annotate_provenance(complex_fns, architecture)

        report: Dict[str, Any] = {
            'path': str(path),
            'stats': stats,
            'git_log': git_log,
            'git_foreign_root': as_spelled(git_foreign_root, path) if git_foreign_root else None,
            'complex_functions': complex_fns,
            'architecture': architecture,
            'scope': _run_scope(self, path),
        }

        meta = self.composed_meta()
        return ResultBuilder.create(
            result_type='overview',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            scope=report.pop('scope'),
            data=report,
            warnings=without_internal_filter_warnings(meta) or None,
            errors=meta.get('errors') if meta else None,
            confidence=meta.get('confidence') if meta else None,
        )
