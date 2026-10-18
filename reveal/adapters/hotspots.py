"""hotspots:// scan adapter; text rendering lives in rendering/adapters/hotspots.py."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, cast

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from ..conventions import LanguageConventions, conventions_for, family_for_path
from ..defaults import TEST_DIR_NAMES, VENDOR_DIR_NAMES
from ..rendering.adapters.hotspots import HotspotsRenderer
from ..utils.path_utils import EVIDENCE, resolve_project_root, walk_tree
from ..utils.query_parser import (CliBinding, ParamSpec, QueryParams, ResourceSpec,
                                  nonnegative_display_limit, param_schema, whole_number)
from ..utils.query_binding import bind_declared_params, boolean_value
from ..utils.results import AnalysisCompleteness, ResultBuilder, result_execution_facts


def _hotspots_top(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('top requires a whole number, not a boolean')
    return nonnegative_display_limit(value)


def _ranking_top(params: Dict[str, Any], verbose: bool) -> int:
    top = cast(int, _TOP.read(params))
    if verbose or top == 0:
        from reveal.adapters.overview import UNLIMITED_TOP
        return UNLIMITED_TOP
    return top


def _hotspots_min(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('min_complexity requires a whole number, not a boolean')
    try:
        return whole_number(float(value) if isinstance(value, str) else value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('min_complexity requires a whole number') from exc


_TOP = ParamSpec('top', 'integer', 'Retained items per ranking (0 = all)', 10,
                 _hotspots_top, ('top=20',), minimum=0, zero_policy='all',
                 role='presentation', cli=CliBinding(('--top',), metavar='N'))
_MIN_COMPLEXITY = ParamSpec('min_complexity', 'integer', 'Minimum complexity to analyze', 10,
                            _hotspots_min, ('min_complexity=15',), role='analysis',
                            cli=CliBinding(('--min-complexity',), metavar='N'))
_FUNCTIONS_ONLY = ParamSpec('functions_only', 'boolean', 'Skip file rankings', False,
                           boolean_value, ('functions_only=true',), role='analysis',
                           cli=CliBinding(('--functions-only',), action='store_true'))
_FILES_ONLY = ParamSpec('files_only', 'boolean', 'Skip function analysis', False,
                       boolean_value, ('files_only=true',), role='analysis',
                       cli=CliBinding(('--files-only',), action='store_true'))
_COMPOSE_FAILED = object()
_REQUIRED_WARNINGS = {'parse_degraded', 'check_rules_failed', 'analysis_failed', 'parse_recovered',
                      'analysis_incomplete'}


def _is_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def _is_metric(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _rank_entries(values: Any, field: str) -> List[Dict[str, Any]]:
    """Keep usable observations even when sibling proof is incomplete."""
    if not isinstance(values, list):
        return []
    return [entry for entry in values if isinstance(entry, dict) and _is_metric(entry.get(field))]


def _valid_rank(values: Any, field: str) -> bool:
    return isinstance(values, list) and len(_rank_entries(values, field)) == len(values)


def _stats_proof_valid(data: Any, ranking: bool) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get('summary'), dict):
        return False
    total = data['summary'].get('total_files')
    if not _is_count(total):
        return False
    if not ranking:
        return True
    files = data.get('files')
    if not isinstance(files, list) or len(files) != total:
        return False
    return (all(isinstance(entry, dict) and isinstance(entry.get('quality'), dict)
                and _is_metric(entry['quality'].get('score')) for entry in files)
            and _valid_rank(data.get('hotspots'), 'quality_score'))


def _ast_proof_valid(data: Any) -> bool:
    if not isinstance(data, dict) or not _valid_rank(data.get('results'), 'complexity'):
        return False
    counts = [data.get(key) for key in ('total_files', 'total_results', 'displayed_results')]
    return (all(_is_count(count) for count in counts)
            and counts[2] == len(data['results']) and counts[1] >= counts[2])


def _hotspots_proof_error(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return 'Required hotspots answer is malformed'
    if not _valid_rank(result.get('file_hotspots'), 'quality_score'):
        return 'Required file ranking is missing or malformed'
    if not _valid_rank(result.get('function_hotspots'), 'complexity'):
        return 'Required function ranking is missing or malformed'
    summary = result.get('summary')
    if not isinstance(summary, dict) or not _is_count(summary.get('total_files')):
        return 'Required analyzed file coverage is missing or malformed'
    if type(summary.get('has_findings')) is not bool:
        return 'Required serious-findings evidence is missing or malformed'
    return None


def _provenance_for_file(file_str: Optional[str], base_path: Path) -> Optional[str]:
    """Classify a hotspot entry's 'test'/'vendor'/'minified'/None provenance
    (BACK-1195). `file_str` may be relative (file_hotspots, from StatsAdapter)
    or absolute (function_hotspots, from AstAdapter) -- relativize first so
    classification only sees the path components under the scan root, not
    ancestor directories of the analyst's own filesystem.
    """
    from ..utils.path_utils import provenance_for_display_path
    return provenance_for_display_path(file_str, base_path)


def _relativize_hotspots_paths(file_hotspots: List[Dict[str, Any]], fn_hotspots: List[Dict[str, Any]], base_path: Path) -> None:
    """Relativize both hotspot lists' 'file' fields before JSON serialization
    (BACK-1213). `fn_hotspots` comes from AstAdapter's compose() output, which
    never relativizes -- same confidentiality gap as BACK-1212/BACK-1194.
    `file_hotspots` (from StatsAdapter) is already relative today, but is
    relativized here too defensively so this doesn't silently regress if that
    upstream guarantee ever changes. Mutates in place.
    """
    from ..utils.path_utils import to_relative_display

    def rel(value: Optional[str]) -> Optional[str]:
        return to_relative_display(value, base_path) if value else value

    for entry in file_hotspots:
        if entry.get('file'):
            entry['file'] = rel(entry['file'])
    for fn in fn_hotspots:
        if fn.get('file'):
            fn['file'] = rel(fn['file'])


def _has_findings(qualities: Iterable[Any], complexities: Iterable[Any]) -> bool:
    """The existing serious-hotspot predicate, independent of presentation."""
    return any(quality < 70 for quality in qualities) or any(cx > 20 for cx in complexities)


def _scan_has_findings(adapter: 'HotspotsAdapter', files: List[Dict[str, Any]],
                       functions: List[Dict[str, Any]]) -> bool:
    # Stats' files are whole even when its ranking is cut. AST ranks by
    # descending complexity with top >= 1, so a critical maximum survives.
    return adapter._file_findings or _has_findings(
        (entry.get('quality_score', 100) for entry in files),
        (fn.get('complexity', 0) for fn in functions))


def _compose_stats(adapter: 'HotspotsAdapter', path: Path, **params: Any) -> Dict[str, Any]:
    """Run StatsAdapter through compose() and keep its summary as the scan's coverage record."""
    from reveal.adapters.stats import StatsAdapter
    from reveal.utils.exclusions import active_exclusions
    # BACK-1257: stats:// filters via its own ?exclude= param, not the walk-scope
    # context, so the scope has to be forwarded explicitly here -- overview://'s
    # _run_stats already does this. Without it hotspots:// would honor --exclude
    # for its function list (via ast://) but not its file list.
    _root, _patterns = active_exclusions()
    extra: Dict[str, Any] = {'exclude': list(_patterns)} if _patterns else {}
    data = adapter.compose(StatsAdapter, str(path), default=_COMPOSE_FAILED, **params, **extra)
    if data is _COMPOSE_FAILED:
        return {}
    if not _stats_proof_valid(data, bool(params.get('hotspots'))) and not (isinstance(data, dict) and data.get('error')):
        adapter.record_composed_error('StatsAdapter', str(path), ValueError('Required Stats coverage/ranking evidence is missing or malformed'))
    if not isinstance(data, dict):
        return {}
    summary = data.get('summary')
    adapter.stats_summary = summary if isinstance(summary, dict) else {}
    if data.get('warnings'):
        # Stats still returns optional churn disclosures outside its meta frame.
        adapter.fold_meta({'warnings': data['warnings']})
    if params.get('hotspots'):
        files = data.get('files')
        files = files if isinstance(files, list) else []
        adapter._file_findings = _has_findings(
            (file['quality']['score'] for file in files
             if isinstance(file, dict) and isinstance(file.get('quality'), dict)
             and _is_metric(file['quality'].get('score'))), ())
    return cast(Dict[str, Any], data)


def _run_file_hotspots(adapter: 'HotspotsAdapter', path: Path, top: int) -> List[Dict[str, Any]]:
    """Fetch file-level hotspots via StatsAdapter."""
    data = _compose_stats(adapter, path, hotspots=True, top=top,
                          cut_as=('file_hotspots', 'raise ?top=N'))
    return _rank_entries(data.get('hotspots'), 'quality_score')


def _record_function_scan_coverage(adapter: 'HotspotsAdapter', path: Path) -> None:
    """--functions-only runs no stats scan, so nothing says how many files the function
    scan covered or which did not parse (BACK-1839 F4). Take the same coverage record the
    default mode has, from stats' summary and its parse_degraded warning, without ranking files."""
    _compose_stats(adapter, path, summary_only=True)


def _run_function_hotspots(adapter: 'HotspotsAdapter', path: Path, min_complexity: int, top: int) -> List[Dict[str, Any]]:
    """Fetch high-complexity functions via AstAdapter."""
    from reveal.adapters.ast import AstAdapter
    # BACK-984: '>=' directly, not the old '>{min_complexity - 1}' hack —
    # the filter parser supports it natively.
    query = f'complexity>={min_complexity}&sort=-complexity&limit={top}'
    data = adapter.compose(AstAdapter, str(path), default=_COMPOSE_FAILED, query=query,
                           cut_as=('function_hotspots', 'raise ?top=N'))
    if data is _COMPOSE_FAILED:
        return []
    if not _ast_proof_valid(data) and not (isinstance(data, dict) and data.get('error')):
        adapter.record_composed_error('AstAdapter', str(path), ValueError('Required AST coverage/ranking evidence is missing or malformed'))
    return _rank_entries(data.get('results', data.get('elements')), 'complexity') if isinstance(data, dict) else []


def _camel_to_snake(name: str) -> str:
    return re.sub(r'([A-Z])', lambda m: '_' + m.group(1).lower(), name).lstrip('_')


# Vendored trees and Rust/Maven build output, never walked for tests. build/, dist/ and
# caches are the shared walker's noise (build/ with code at its top level is source, BACK-552).
_SKIP_WALK_DIRS = VENDOR_DIR_NAMES | {'target'}


def _add_names(names: Set[str], raw: str) -> None:
    """Index *raw* both as written and snake_cased (`MemberPromote` -> member_promote)."""
    names.add(raw)
    snake = _camel_to_snake(raw)
    if snake:
        names.add(snake)


def _scan_test_file(names: Set[str], conv: LanguageConventions, fname: str, full: str,
                    is_test_file: bool) -> None:
    """Add what one file's name and (test-file or colocated) symbols say is tested."""
    for pat in conv.test_file_patterns:
        m = pat.match(fname)
        if m:
            _add_names(names, m.group(1))  # test_liquidity_sweep.py -> liquidity_sweep
            break
    if not (conv.test_symbol_patterns and (is_test_file or conv.colocated_test_symbols)):
        return
    try:
        content = Path(full).read_text(errors='replace', encoding='utf-8')
    except OSError:
        return
    for pat in conv.test_symbol_patterns:
        for m in pat.finditer(content):
            _add_names(names, m.group(1))  # TestClassifyGuard -> classify_guard


def _build_test_name_index(path: Path, families: Optional[Iterable[str]] = None) -> Set[str]:
    """Heuristic: names covered by test files/symbols, per each family's conventions.

    *families* limits the scan to those language families (default: Python only,
    the historical behavior). A file counts as a test file when it sits under a
    test directory or its name matches the family's test-file pattern, so
    colocated layouts (Go `_test.go`, JS `*.test.ts`) are seen too (BACK-1276).
    """
    convs = {f: conventions_for(f) for f in (families if families is not None else ('python',))}
    convs = {f: c for f, c in convs.items() if c.has_test_index}
    names: Set[str] = set()
    if not convs:
        return names
    # BACK-1578: an evidence walk -- --exclude narrows which hotspots are reported, not which
    # tests count (check --exclude tests must not mark every hotspot untested). Vendored
    # trees are pruned before descent: their tests cover vendored code, not the project's.
    for base, is_test_tree in [(path, False)] + [(d, True) for d in _outside_test_dirs(path)]:
        for root, dirs, files in walk_tree(base, EVIDENCE):
            dirs[:] = [d for d in dirs if d not in _SKIP_WALK_DIRS]
            in_test_dir = is_test_tree or any(part in TEST_DIR_NAMES for part in root.relative_to(base).parts)
            for fname in files:
                conv = convs.get(family_for_path(fname))
                if conv is None:
                    continue
                is_test_file = in_test_dir or any(p.match(fname) for p in conv.test_file_patterns)
                if is_test_file or conv.colocated_test_symbols:
                    _scan_test_file(names, conv, fname, str(root / fname), is_test_file)
    return names


def _outside_test_dirs(path: Path) -> List[Path]:
    """The project root's own test directories that sit outside *path*.

    `reveal hotspots src/pkg` (a src layout) indexed only src/pkg, so the tests in
    <root>/tests were never seen and every function read "no test found" (BACK-1370).
    """
    target = (path if path.is_dir() else path.parent).resolve()
    root = resolve_project_root(target)
    if root is None or root == target:
        return []
    return [d for d in (root / name for name in sorted(TEST_DIR_NAMES))
            if d.is_dir() and not d.resolve().is_relative_to(target)]


def _is_covered(name: str, loc: str, test_index: Set[str]) -> bool:
    snake = _camel_to_snake(name)
    if snake != name and _is_covered(snake, loc, test_index):  # Go/Java CamelCase names
        return True
    module_name = _camel_to_snake(Path(loc).stem) if loc else ''
    bare = name.lstrip('_')
    return (
        name in test_index
        or bare in test_index
        or module_name in test_index
        or any(s.startswith(bare) for s in test_index)
        or any(  # reverse: bare contains an index word, e.g. get_file_blame ← file_blame
            bare.endswith('_' + s) or bare.startswith(s + '_') or ('_' + s + '_') in bare
            for s in test_index if len(s) >= 5
        )
    )


@register_adapter('hotspots')
@register_renderer(HotspotsRenderer)
class HotspotsAdapter(ResourceAdapter):
    """Adapter for identifying high-complexity, low-quality files and functions."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    BUDGET_LIST_FIELD = ('file_hotspots', 'function_hotspots')  # --head/--tail slice both (BACK-1497)
    # default top=10 per ranking; --all lifts it (BACK-1229)
    CLI_QUERY_FLAGS = {'all': 'top=1000000', 'limit': 'top={value}', 'respect_gitignore': 'respect_gitignore=false'}  # top= caps each list (BACK-1496)

    RESULT_TYPE = 'hotspots_scan'
    FINDINGS_POLICIES = ('none', 'findings')
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = (_TOP, _MIN_COMPLEXITY, _FUNCTIONS_ONLY, _FILES_ONLY)

    def __init__(self, resource: str, query: Optional[str] = None, *, params: Optional[Dict[str, Any]] = None):
        self.path = str(Path(resource).expanduser())
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(self.PARAM_SPECS, query or '', transport='uri')
        self._warn_unknown_query_params(self.query_params)  # BACK-507
        # Populated by get_structure(); text rendering needs the raw set for
        # its coverage overlay, but it must never appear in the JSON contract
        # (only the per-function `has_test_hint` boolean derived from it does).
        self.test_index: Optional[Set[str]] = None
        self.stats_summary: Dict[str, Any] = {}
        self._file_findings = False

    @staticmethod
    def answer_requirement_error(result, expected_type, prior_facts=None):
        return _hotspots_proof_error(result)

    @staticmethod
    def execution_facts(result):
        if _hotspots_proof_error(result):
            return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
        meta = result.get('meta') or {}
        missing = bool(meta.get('errors')) or any(
            warning.get('type') in _REQUIRED_WARNINGS for warning in meta.get('warnings', []))
        usable = result['summary']['total_files'] > 0 or bool(result['function_hotspots'])
        state = AnalysisCompleteness.COMPLETE
        if missing:
            state = AnalysisCompleteness.INCOMPLETE if usable else AnalysisCompleteness.FAILED
        return result_execution_facts(result,
            completeness=state,
            findings=result['summary']['has_findings'])

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'hotspots',
            'description': 'Identify high-complexity files and functions that need attention.',
            'syntax': 'hotspots://<path>[?top=10&min_complexity=10&functions_only=true&files_only=true]',
            'examples': [
                {'uri': 'hotspots://src', 'description': 'Hotspots in a directory'},
                {'uri': 'hotspots://.?top=20', 'description': 'Top 20 hotspot files'},
                {'uri': 'hotspots://.?functions_only=true', 'description': 'Only complex functions'},
                {'uri': 'hotspots://. --all', 'description': 'Lift the default top-10 cap on both rankings'},
            ],
            'features': [
                'File-level hotspots via StatsAdapter (quality score, complexity, issues)',
                'Function-level hotspots via AstAdapter (cyclomatic complexity ranking)',
                'Heuristic test-coverage hint per function (has a matching test_* found?)',
                "Each hotspot entry carries a 'provenance' field: 'test'/'vendor'/'minified'/null "
                '(first-party) — BACK-1195, cheap path-only classification, no ranking-order '
                'change (yet).',
            ],
            'notes': [
                'Test-coverage hint is a name-matching heuristic, not real coverage data.',
                'Default --fail-on none reports findings without failing; --fail-on findings exits 1 '
                'for file quality below 70 or function complexity above 20. Required analysis/output '
                'failure exits 3; invalid requests exit 2.',
                'top caps both JSON and text rankings (0 = all; negative values reject). '
                'Whole decimal/scientific values are accepted; min_complexity remains signed. '
                '--verbose lifts both caps. URI --all lifts caps only without explicit top; '
                'the subcommand does not accept --all.',
            ],
            'see_also': [
                'reveal hotspots <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'hotspots',
            'description': 'High-complexity, low-quality file and function scanner',
            'uri_syntax': 'hotspots://<path>?top=10&min_complexity=10',
            'resource': HotspotsAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': 'none', 'fail_on': ['none', 'findings']},
            'query_params': param_schema(HotspotsAdapter.PARAM_SPECS),
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'hotspots_scan',
                    'description': 'File-level and function-level complexity/quality hotspots',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'file_hotspots': {'type': 'array'},
                            'function_hotspots': {'type': 'array'},
                            'summary': {'type': 'object', 'description': 'Analyzed file and complexity totals'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'hotspots://src', 'description': 'Hotspots in src/', 'output_type': 'hotspots_scan', 'task': 'quality'},
            ],
            'notes': [
                'Composes StatsAdapter (file quality) and AstAdapter (function complexity) — not an independent scan.',
            ],
        }

    def get_structure(self, verbose: bool = False, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        top = _ranking_top(self.query_params, verbose)
        min_cx = _MIN_COMPLEXITY.read(self.query_params)
        functions_only = _FUNCTIONS_ONLY.read(self.query_params)
        files_only = _FILES_ONLY.read(self.query_params)

        self.stats_summary = {}
        self._file_findings = False
        self._composed_errors = []
        self._composed_warnings = []
        self._composed_confidences = []
        file_hotspots: List[Dict[str, Any]] = [] if functions_only else _run_file_hotspots(self, path, top)
        fn_hotspots: List[Dict[str, Any]] = [] if files_only else _run_function_hotspots(self, path, min_cx, top)
        if functions_only:
            _record_function_scan_coverage(self, path)

        has_findings = _scan_has_findings(self, file_hotspots, fn_hotspots)
        _relativize_hotspots_paths(file_hotspots, fn_hotspots, path)

        # BACK-1195: mark each ranked entry with its provenance so a reader
        # can discount vendored/generated/test noise in place.
        for entry in file_hotspots:
            entry['provenance'] = _provenance_for_file(entry.get('file'), path)
        for fn in fn_hotspots:
            fn['provenance'] = _provenance_for_file(fn.get('file'), path)

        test_index: Optional[Set[str]] = None
        unknown_families: Set[str] = set()
        if not files_only:
            families = {family_for_path(fn.get('file', '')) for fn in fn_hotspots}
            test_index = _build_test_name_index(path, families or None)
            for fn in fn_hotspots:
                family = family_for_path(fn.get('file', ''))
                if conventions_for(family).has_test_index:
                    fn['has_test_hint'] = _is_covered(fn.get('name', ''), fn.get('file', ''), test_index)
                else:
                    # No test convention known for this language: unknown, not "untested".
                    fn['has_test_hint'] = None
                    unknown_families.add(Path(fn.get('file', '')).suffix or family or '?')
        self.test_index = test_index

        report = {
            'path': str(path),
            'file_hotspots': file_hotspots,
            'function_hotspots': fn_hotspots,
            'summary': {**self.stats_summary, 'has_findings': has_findings},
        }

        meta = self.composed_meta()
        from reveal.adapters.overview import without_internal_filter_warnings
        warnings = without_internal_filter_warnings(meta)
        if unknown_families:
            warnings.append({
                'type': 'test_convention_unknown',
                'message': 'has_test_hint is null for functions in languages with no known '
                           'test convention (' + ', '.join(sorted(unknown_families)) + '); '
                           'null means unknown, not untested',
            })
        return ResultBuilder.create(
            result_type='hotspots_scan',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=report,
            warnings=warnings or None,
            errors=meta.get('errors') if meta else None,
            confidence=meta.get('confidence') if meta else None,
        )
