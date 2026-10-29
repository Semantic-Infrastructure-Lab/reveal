"""surface:// adapter - external boundary map for a codebase.

Scan/render logic lives here (BACK-904). The `reveal surface` command is generated from
this adapter's declaration (BACK-901).
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, List, Optional, Tuple

from reveal.reveal_types import CONTRACT_VERSION, WarningEntry

from .base import ResourceAdapter, register_adapter, register_renderer
from ..rendering.adapters.surface import (  # noqa: F401 -- _SURFACE_LABELS and the notes are re-exported
    SurfaceRenderer,
    _SURFACE_LABELS,
    _count_error_region,
    _recovered_note,
    _unparsed_note,
)
from ..capabilities import capability_tiers_for
from ..registry import (
    JS_TS_LANGUAGES, _is_cpp_header_content, extensions_for_languages, language_for_extension,
)
from ..utils.path_utils import (
    ANALYSIS,
    HiddenTally,
    census_and_coverage_for_path,
    detect_non_python_language,
    hidden_entries_warning,
    is_test_dir,
    is_test_file_name,
    traversal_failed_warning,
    walk_tree,
    failure_of,
)
from ..utils.query_parser import (
    CliBinding, ParamSpec, QueryParams, ResourceSpec, nonnegative_display_limit, param_schema,
)
from ..utils.query_binding import bind_declared_params, boolean_value
from .ast.surface_matrix import CATEGORIES, RECOVERED_KEY, UNPARSED_KEY, coverage_matrix
from .surface_file_cache import scan_file_cached
from .ast.nav_surface_common import ROUTE_CLASSES_KEY, resolve_inherited_route_prefixes
from .ast.nav_surface_rails import resolve_engine_mounts
from ..utils.results import ResultBuilder
from ..defaults import TEST_DIR_PREFIX as _TEST_DIR_PREFIX
from ..reveal_types import PathFailure

# Test file patterns pruned by --source-only

def _is_test_dir(name: str) -> bool:
    # Broader than the canonical is_test_dir() by design — also matches
    # `testing/`, `test-fixtures/`, etc. (prefix-match covers tests/,
    # testing/, etc.); see defaults.TEST_DIR_PREFIX docstring.
    return name.startswith(_TEST_DIR_PREFIX) or is_test_dir(name)


def _is_test_file(fpath: Path) -> bool:
    """File-name test detection: generic naming (BACK-1252) plus the file's own
    language convention from the conventions profile (BACK-1277)."""
    return is_test_file_name(fpath)


@dataclass(frozen=True)
class _SurfaceScanner:
    """One language's surface-scan registration: which extensions it claims
    and where its `scan_file_surface_*(path) -> Dict[category, entries]`
    function lives. Single source of truth for "what languages does surface
    scan" — file-collection, dispatch, and assess_language_coverage()'s
    supported set all derive from this one list so they can't silently
    diverge by position (BACK-888/BACK-903; design doc
    BACK884_COVERAGE_CENSUS_UNIFICATION finding #3)."""
    extensions: frozenset
    module: str
    func: str
    language: str  # coverage-matrix column (ast/surface_matrix.py)


def _scanner(languages: tuple, module: str, func: str, column: str) -> '_SurfaceScanner':
    # Extensions come from the registry, never a local list (BACK-1255): a newly
    # registered extension (.mts/.cts, .h++) is scanned without touching this table.
    return _SurfaceScanner(extensions_for_languages(*languages), f'reveal.adapters.ast.{module}', func, column)


# Registration order does not matter — lookup is by extension, not position.
_SURFACE_SCANNERS: tuple = (
    _scanner(('python',), 'nav_surface', 'scan_file_surface', 'python'),
    _scanner(JS_TS_LANGUAGES, 'nav_surface_ts', 'scan_file_surface_ts', 'typescript'),
    _scanner(('java',), 'nav_surface_java', 'scan_file_surface_java', 'java'),
    _scanner(('csharp',), 'nav_surface_csharp', 'scan_file_surface_csharp', 'csharp'),
    _scanner(('php',), 'nav_surface_php', 'scan_file_surface_php', 'php'),
    _scanner(('swift',), 'nav_surface_swift', 'scan_file_surface_swift', 'swift'),
    _scanner(('kotlin',), 'nav_surface_kotlin', 'scan_file_surface_kotlin', 'kotlin'),
    _scanner(('ruby',), 'nav_surface_ruby', 'scan_file_surface_ruby', 'ruby'),
    _scanner(('go',), 'nav_surface_go', 'scan_file_surface_go', 'go'),
    _scanner(('rust',), 'nav_surface_rust', 'scan_file_surface_rust', 'rust'),
    _scanner(('cpp',), 'nav_surface_cpp', 'scan_file_surface_cpp', 'cpp'),
)

# `.h` defaults to C in the registry (BACK-630) — content-sniffed C++ headers
# route here explicitly rather than through extension lookup.
_CPP_SCANNER = next(s for s in _SURFACE_SCANNERS if '.cpp' in s.extensions)


def _load_scanner(spec: '_SurfaceScanner') -> Callable[[str], Dict[str, List[Any]]]:
    return getattr(importlib.import_module(spec.module), spec.func)


def _supported_coverage_languages() -> frozenset:
    """Registry language keys surface can scan, derived from _SURFACE_SCANNERS."""
    langs = set()
    for spec in _SURFACE_SCANNERS:
        for ext in spec.extensions:
            lang = language_for_extension(ext)
            if lang:
                langs.add(lang)
    return frozenset(langs)


def _collect_source_files(
    path: Path, source_only: bool = False, *,
    on_error: Optional[Callable[[OSError], None]] = None,
) -> Dict['_SurfaceScanner', List[Path]]:
    """Map each registered scanner to the files under `path` it should scan."""

    def _scanner_for(fpath: Path):
        suffix = fpath.suffix
        for spec in _SURFACE_SCANNERS:
            if suffix in spec.extensions:
                return spec
        # BACK-630: `.h` defaults to C in the registry — only route it into the
        # cpp scanner when content-sniffed as C++ (header-only classes/templates),
        # same marker set the registry uses for single-file analyzer selection.
        if suffix == '.h' and _is_cpp_header_content(str(fpath)):
            return _CPP_SCANNER
        return None

    buckets: Dict[_SurfaceScanner, List[Path]] = {spec: [] for spec in _SURFACE_SCANNERS}

    if path.is_file():
        spec = _scanner_for(path)
        if spec is not None:
            buckets[spec].append(path)
        return buckets

    # The shared walker (BACK-1577): the same files the coverage census below counts,
    # dot-dir source included (BACK-1038). source_only prunes test dirs before descent.
    for root, dirs, filenames in walk_tree(path, ANALYSIS, on_error=on_error):
        if source_only:
            dirs[:] = [d for d in dirs if not _is_test_dir(d)]
        for fname in filenames:
            fpath = root / fname
            if source_only and _is_test_file(fpath):
                continue
            spec = _scanner_for(fpath)
            if spec is not None:
                buckets[spec].append(fpath)
    return buckets


def _relativize_surface_paths(surfaces: Dict[str, List[Dict[str, Any]]], base_path: Path) -> None:
    """Relativize each surface entry's 'file' field before JSON serialization
    (BACK-1215). Entries come from per-language scanners that record the
    absolute file path they were invoked with -- never routed through
    relativization, same confidentiality gap as BACK-1212/BACK-1213/BACK-1194.
    Mutates in place.
    """
    from ..utils.path_utils import to_relative_display

    for entries in surfaces.values():
        for entry in entries:
            if entry.get('file'):
                entry['file'] = to_relative_display(entry['file'], base_path)


def _rollup_by_dir(surfaces: Dict[str, List[Dict[str, Any]]], depth: int = 0) -> List[Dict[str, Any]]:
    """Count entries per (directory, category) so the output answers "which layer
    owns DB access / shells out / reads env" without inferring layering from
    paths (BACK-1337). `depth` keeps only the first N path segments of each
    directory (0 = the full directory). Busiest directories first; ties by name."""
    rollup: Dict[str, Dict[str, int]] = {}
    for category, entries in surfaces.items():
        for entry in entries:
            parts = PurePosixPath(str(entry.get('file') or '.').replace(os.sep, '/')).parent.parts
            if depth > 0:
                parts = parts[:depth]
            counts = rollup.setdefault('/'.join(parts) or '.', {})
            counts[category] = counts.get(category, 0) + 1
    rows = [{'dir': d, 'total': sum(c.values()), 'counts': c} for d, c in rollup.items()]
    return sorted(rows, key=lambda r: (-r['total'], r['dir']))


def _record_traversal_error(failures: List[PathFailure], error: OSError) -> None:
    failures.append(failure_of(error))


def _surface_row_valid(row: Any) -> bool:
    return (isinstance(row, dict) and isinstance(row.get('name'), str)
            and all(isinstance(row.get(key), str) and bool(row[key].strip()) for key in ('file', 'type'))
            and type(row.get('line')) is int and row['line'] > 0)


def _validate_requested_surface(result: Any, type_filter: str) -> None:
    """Check the actual requested scanner observations before merging or formatting."""
    if not isinstance(result, dict):
        raise ValueError('required surface scanner output must be an object')
    for category, rows in result.items():
        if category in (UNPARSED_KEY, RECOVERED_KEY, ROUTE_CLASSES_KEY):
            continue
        if type_filter and category != type_filter:
            continue
        if category not in CATEGORIES or not isinstance(rows, list):
            raise ValueError(f'invalid required surface group: {category}')
        if any(not _surface_row_valid(row) for row in rows):
            raise ValueError(f'invalid required surface row: {category}')


def _scan_collected_surface(
    collected: Dict[_SurfaceScanner, List[Path]], type_filter: str, directory_loss: bool,
) -> Tuple[Dict[str, List[Dict[str, Any]]], set[str], List[str], List[str], List[Dict[str, Any]], Optional[str]]:
    """Merge native scanner results, retaining malformed required input as failure."""
    surfaces: Dict[str, List[Dict[str, Any]]] = {k: [] for k in CATEGORIES}
    scanned_languages = set()
    unparsed: List[str] = []
    recovered: List[str] = []
    route_classes: List[Dict[str, Any]] = []
    error: Optional[str] = None
    for spec, file_list in collected.items():
        if not file_list:
            continue
        scanned_languages.add(spec.language)
        scan_fn = _load_scanner(spec)
        scanner_id = f'{spec.module}.{spec.func}'
        for file_path in file_list:
            # The scanner's full raw result, from the persisted per-file entry when the file is
            # unchanged (BACK-2151). Validation and the type filter below run on it either way.
            result = scan_file_cached(scan_fn, scanner_id, spec.language, str(file_path), _validate_requested_surface)
            if directory_loss:
                try:
                    _validate_requested_surface(result, type_filter)
                except ValueError as exc:
                    error = str(exc)
                    continue
            unparsed.extend(result.pop(UNPARSED_KEY, []))
            recovered.extend(result.pop(RECOVERED_KEY, []))
            classes = result.pop(ROUTE_CLASSES_KEY, [])
            if not directory_loss or type_filter in ('', 'http'):
                route_classes.extend(classes)
            for category, entries in result.items():
                if directory_loss and type_filter and category != type_filter:
                    continue
                surfaces[category].extend(entries)
    return surfaces, scanned_languages, unparsed, recovered, route_classes, error


def _surface_discovery_error(
    surfaces: Dict[str, List[Dict[str, Any]]], source_failures: List[PathFailure],
    census_failures: List[PathFailure], malformed: Optional[str],
) -> Optional[str]:
    if not source_failures and not census_failures:
        return None
    population = 'Surface source discovery' if source_failures else 'Required scope/coverage census'
    if malformed:
        return f'{population} failed and requested surface observations are invalid: {malformed}'
    if not any(surfaces.values()):
        return f'{population} failed and no requested surface observations survived'
    return None


def _surface_traversal_warnings(
    source_failures: List[PathFailure], census_failures: List[PathFailure], path: Path,
) -> List[WarningEntry]:
    warnings: List[WarningEntry] = []
    for failures, attribution in (
        (source_failures, 'Surface source discovery is incomplete'),
        (census_failures, 'Required scope/coverage census is incomplete; counts reflect only observed files'),
    ):
        warning = traversal_failed_warning(failures, path)
        if warning:
            warning['message'] = f"{attribution}: {warning['message']}"
            warnings.append(warning)
    return warnings


def _scan_surface(
    path: Path, type_filter: str = '', source_only: bool = False, by: str = '', depth: int = 0,
) -> Dict[str, Any]:
    source_failures: List[PathFailure] = []
    census_failures: List[PathFailure] = []
    collected = _collect_source_files(path, source_only=source_only,
                                     on_error=partial(_record_traversal_error, source_failures))

    unsupported_language = ''
    if not any(collected.values()):
        unsupported_language = detect_non_python_language(path)

    # BACK-518: a handful of stray supported-language files (e.g. 15 .py tooling
    # scripts in a 1,300-file Lua repo) used to be silently presented as the
    # whole project's surface. Assess how much of the tree is actually in a
    # language `surface` analyzes so _render_report can warn on the substitution.
    # BACK-884: one walk produces both `coverage` (gated to surface's
    # supported-language set, BACK-518) and the broader per-language `scope`
    # census below.
    hidden = HiddenTally()
    census, coverage = census_and_coverage_for_path(
        path, _supported_coverage_languages(), on_error=partial(_record_traversal_error, census_failures),
        on_hidden=hidden)
    # The census walks what the scan walked: nothing left to scan and something hidden
    # means "no surfaces" is gitignore's answer, not the code's (BACK-2065).
    scope_hidden = hidden_entries_warning(hidden, census.total_code_files)
    scope = census.to_scope_dict(capability_tiers=capability_tiers_for(census.language_extensions))

    directory_loss = bool(source_failures or census_failures)
    surfaces, scanned_languages, unparsed, recovered, route_classes, malformed = _scan_collected_surface(
        collected, type_filter, directory_loss)
    # BACK-1418: a controller's route prefix is often declared on a base class
    # in another file; resolved here, where every scanned class is known.
    resolve_inherited_route_prefixes(surfaces['http'], route_classes)
    # BACK-1417: a Rails engine's routes are drawn relative to its mount point,
    # which the app's routes (another file) declare.
    resolve_engine_mounts(surfaces['http'])

    if type_filter:
        surfaces = {k: v for k, v in surfaces.items() if k == type_filter}

    discovery_error = _surface_discovery_error(surfaces, source_failures, census_failures, malformed)

    # BACK-1332: which of the 0s above are "not implemented" rather than "found none".
    matrix = coverage_matrix(scanned_languages, tuple(surfaces))

    _relativize_surface_paths(surfaces, path)
    from ..utils.path_utils import to_relative_display
    unparsed_files = sorted(to_relative_display(f, path) for f in unparsed)
    recovered_files = sorted(to_relative_display(f, path) for f in recovered)
    error_region_entries = _count_error_region(surfaces)

    # BACK-1244: 'http' entries come from AST call-shape matching alone
    # (verb('/path', ...)) -- a real route declaration and an RSpec/pytest
    # request-spec call exercising that same route are indistinguishable at
    # that level, so test-spec calls can pad (or, before the BACK-1417 Rails
    # interpreter, make up) the reported "http surface" -- inverted evidence
    # for a DD review, where untested routes are exactly what's absent. Tag
    # each entry and, when any are test-sourced, disclose it in known_limits
    # rather than presenting the mix as an undifferentiated route table.
    http_entries = surfaces.get('http', [])
    test_origin_count = 0
    if http_entries and not source_only:
        for entry in http_entries:
            entry_path = Path(entry['file'])
            is_test_origin = _is_test_file(entry_path) or any(
                is_test_dir(part) for part in entry_path.parts[:-1]
            )
            entry['test_origin'] = is_test_origin
            test_origin_count += is_test_origin

    total = sum(len(v) for v in surfaces.values())
    by_dir = {'by_dir': _rollup_by_dir(surfaces, depth)} if by == 'dir' else {}
    return {
        **({'_source_traversal_failures': source_failures, '_census_traversal_failures': census_failures,
            '_discovery_error': discovery_error} if directory_loss else {}),
        '_scope_hidden': scope_hidden,
        'path': str(path),
        'total': total,
        'surfaces': surfaces,
        'matrix': matrix,
        **by_dir,
        'unsupported_language': unsupported_language,
        'unparsed_files': unparsed_files,
        'recovered_files': recovered_files,
        'coverage': coverage.to_scope_dict('surface'),
        'scope': scope,
        '_meta': {
            'analysis_kind': 'surface-scan',
            'confidence': 'medium',
            'known_limits': [
                'taxonomy covers common libraries only — project-specific clients not detected',
                'dynamic surface registrations (e.g. plugin-loaded routes) not tracked',
                *(['test files excluded (--source-only)'] if source_only else []),
                *([
                    f"{test_origin_count} of {len(http_entries)} 'http' surface entries come from "
                    "test files (test-spec calls exercising a route, not the route declaration "
                    "itself) -- see each entry's 'test_origin' field, or pass source_only=true to "
                    "exclude them"
                ] if test_origin_count else []),
                *([_unparsed_note(unparsed_files)] if unparsed_files else []),
                *([_recovered_note(recovered_files, error_region_entries)] if recovered_files else []),
            ],
        },
    }


def _surface_limit(value: Any, name: str) -> int:
    """Numeric surface controls need a value; bare presence is not integer one."""
    if isinstance(value, bool):
        raise ValueError(f'{name} must be a non-negative integer, not a boolean')
    return nonnegative_display_limit(value, name)


@register_adapter('surface')
@register_renderer(SurfaceRenderer)
class SurfaceAdapter(ResourceAdapter):
    """Adapter for mapping known boundary indicators in source: CLI,
    HTTP routes, env vars, network, filesystem writes, subprocess calls."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}  # --no-gitignore (BACK-1386)
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    RESULT_TYPE = 'surface_scan'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    BOUND_QUERY_CALL = True

    PARAM_SPECS = (
        ParamSpec('type', 'string', 'Filter to one surface type', '', str,
                  examples=('type=env',),
                  choices=('', *CATEGORIES), role='analysis', cli=CliBinding(('--type',), metavar='TYPE')),
        ParamSpec('source_only', 'boolean', 'Exclude test files and directories', False, boolean_value,
                  examples=('source_only=true',),
                  role='analysis', cli=CliBinding(('--source-only',), action='store_true')),
        ParamSpec('by', 'string', 'Group entries by directory', '', str,
                  examples=('by=dir',),
                  choices=('', 'dir'), role='analysis', cli=CliBinding(('--by',))),
        ParamSpec('depth', 'integer', 'Directory rollup depth (0 = full directory)', 0,
                  lambda value: _surface_limit(value, 'depth'), minimum=0,
                  examples=('depth=2',),
                  zero_policy='full directory', role='analysis', cli=CliBinding(('--depth',), metavar='N')),
        ParamSpec('top', 'integer', 'Text entries per category (omitted = all; JSON stays complete)', None,
                  lambda value: _surface_limit(value, 'top'), minimum=0,
                  examples=('top=20', 'top=0'),
                  zero_policy='no text entries', role='presentation', cli=CliBinding(('--top',), metavar='N')),
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

    @staticmethod
    def execution_facts(result):
        """The scan owner supplies completeness; scope limitations are not failures."""
        from ..utils.results import AnalysisCompleteness, result_execution_facts
        incomplete = isinstance(result, dict) and bool(
            result.get('unparsed_files') or result.get('recovered_files') or
            any(w.get('type') == 'analysis_incomplete' and w.get('unit') == 'directories'
                for w in (result.get('meta') or {}).get('warnings', [])))
        state = AnalysisCompleteness.INCOMPLETE if incomplete else AnalysisCompleteness.COMPLETE
        return result_execution_facts(result, completeness=state)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'surface',
            'description': 'Map known boundary indicators: CLI, HTTP routes, env vars, client imports and filesystem writes.',
            'syntax': 'surface://<path>[?type=cli|http|mcp|env|network|db|sdk|fs|subprocess&source_only=true&by=dir&depth=N]',
            'examples': [
                {'uri': 'surface://src', 'description': 'All surfaces in src/'},
                {'uri': 'surface://.?type=env', 'description': 'Only env vars'},
                {'uri': 'surface://.?source_only=true', 'description': 'Production code only (exclude tests)'},
                {'uri': 'surface://.?by=dir&depth=2', 'description': 'Which directories touch which boundary kinds (two levels deep)'},
            ],
            'features': [
                'Detects CLI arguments/subcommands, HTTP routes, MCP tool registrations',
                'Detects environment variable reads, network/db/sdk imports',
                'Detects filesystem writes and subprocess/shell execution',
                'by=dir rolls entries up per directory (counts per category) to show which layers own which boundaries',
                'Covers Python, TypeScript/JavaScript, Java, C#, PHP, Swift, Kotlin, Ruby, Go, Rust, C++',
            ],
            'notes': [
                'Taxonomy-based — project-specific clients outside known libraries not detected.',
                'Dynamic surface registrations (e.g. plugin-loaded routes) not tracked.',
                'Python network/db/sdk entries are known client import sites, not executed I/O or resolved external-provider identities.',
            ],
            'see_also': [
                'reveal surface <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'surface',
            'description': 'External-boundary surface scanner (CLI, HTTP, env, network, fs, subprocess)',
            'uri_syntax': 'surface://<path>?type=env&source_only=true',
            'resource': SurfaceAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': SurfaceAdapter.DEFAULT_FAIL_ON,
                                 'fail_on': list(SurfaceAdapter.FINDINGS_POLICIES)},
            'query_params': param_schema(SurfaceAdapter.PARAM_SPECS),
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'surface_scan',
                    'description': 'Per-category external surface entries',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'total': {'type': 'integer'},
                            'surfaces': {'type': 'object'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'surface://src', 'description': 'All surfaces in src/', 'output_type': 'surface_scan', 'task': 'security'},
            ],
            'notes': [
                'Taxonomy-based — project-specific clients outside known libraries not detected.',
            ],
        }

    def get_structure(self) -> Dict[str, Any]:
        applied = {spec.name: spec.read(self.query_params)
                   for spec in self.PARAM_SPECS if spec.role == 'analysis'}
        type_filter = applied['type']
        source_only = applied['source_only']
        by = applied['by']
        depth = applied['depth']

        report = _scan_surface(Path(self.path), type_filter=type_filter, source_only=source_only,
                               by=by, depth=depth)

        source_failures = report.pop('_source_traversal_failures', [])
        census_failures = report.pop('_census_traversal_failures', [])
        directory_loss = bool(source_failures or census_failures)
        warnings = _surface_traversal_warnings(source_failures, census_failures, Path(self.path))
        scope_hidden = report.pop('_scope_hidden', None)
        if scope_hidden:
            warnings.append(scope_hidden)
        errors = []
        discovery_error = report.pop('_discovery_error', None)
        if discovery_error:
            report['error'] = discovery_error
            errors.append({'code': 'E_SURFACE_DISCOVERY', 'message': discovery_error})
        if directory_loss:
            report['_meta'].pop('confidence', None)
        coverage_warning = report.get('coverage', {}).get('warning', '')
        if coverage_warning:
            warnings.append({'type': 'coverage_gap', 'code': 'W-SURFACE-1', 'message': coverage_warning})
        if report['unparsed_files']:
            warnings.append({'type': 'unparsed_files', 'code': 'W-SURFACE-2', 'message': _unparsed_note(report['unparsed_files'])})
        if report['recovered_files']:
            warnings.append({'type': 'parse_recovered', 'code': 'W-SURFACE-3', 'message': _recovered_note(
                report['recovered_files'], _count_error_region(report['surfaces']))})

        return ResultBuilder.create(
            result_type=self.RESULT_TYPE,
            source=self.path,
            contract_version=CONTRACT_VERSION,
            parse_mode='ast+tree_sitter',
            confidence=None if directory_loss else 0.6,
            warnings=warnings,
            errors=errors,
            scope=report.pop('scope'),
            data=report,
        )
