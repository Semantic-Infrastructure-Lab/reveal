"""hotspots:// adapter - high-complexity, low-quality files and functions.

Scan/render logic lives here (BACK-901/BACK-955); `cli/commands/hotspots.py`
is a thin argparse shim over this adapter, matching the URI/adapter contract
every other capability follows.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, cast

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from ..conventions import LanguageConventions, conventions_for, family_for_path
from ..defaults import TEST_DIR_NAMES, VENDOR_DIR_NAMES
from ..utils import print_json_result
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder


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


def _run_file_hotspots(adapter: 'HotspotsAdapter', path: Path, top: int) -> List[Dict[str, Any]]:
    """Fetch file-level hotspots via StatsAdapter."""
    from reveal.adapters.stats import StatsAdapter
    from reveal.utils.exclusions import active_exclusions
    # BACK-1257: stats:// filters via its own ?exclude= param, not the walk-scope
    # context, so the scope has to be forwarded explicitly here -- overview://'s
    # _run_stats already does this. Without it hotspots:// would honor --exclude
    # for its function list (via ast://) but not its file list.
    _root, _patterns = active_exclusions()
    extra = {'exclude': list(_patterns)} if _patterns else {}
    data = adapter.compose(StatsAdapter, str(path), default={}, hotspots=True, top=top, **extra)
    hotspots = data.get('hotspots', [])
    return cast(List[Dict[str, Any]], hotspots[:top])


def _run_function_hotspots(adapter: 'HotspotsAdapter', path: Path, min_complexity: int, top: int) -> List[Dict[str, Any]]:
    """Fetch high-complexity functions via AstAdapter."""
    from reveal.adapters.ast import AstAdapter
    # BACK-984: '>=' directly, not the old '>{min_complexity - 1}' hack —
    # the filter parser supports it natively.
    query = f'complexity>={min_complexity}&sort=-complexity&limit={top}'
    data = adapter.compose(AstAdapter, str(path), default={}, query=query)
    results = data.get('results', data.get('elements', []))
    return cast(List[Dict[str, Any]], results[:top])


def _camel_to_snake(name: str) -> str:
    return re.sub(r'([A-Z])', lambda m: '_' + m.group(1).lower(), name).lstrip('_')


# Directories never worth walking for tests (vendored/build output).
_SKIP_WALK_DIRS = VENDOR_DIR_NAMES | {'target', 'build', 'dist', '__pycache__'}


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
    for root, dirs, files in os.walk(str(path)):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in _SKIP_WALK_DIRS]
        in_test_dir = any(part in TEST_DIR_NAMES for part in Path(root).relative_to(path).parts)
        for fname in files:
            conv = convs.get(family_for_path(fname))
            if conv is None:
                continue
            is_test_file = in_test_dir or any(p.match(fname) for p in conv.test_file_patterns)
            if is_test_file or conv.colocated_test_symbols:
                _scan_test_file(names, conv, fname, os.path.join(root, fname), is_test_file)
    return names


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


def _render_file_hotspots(hotspots: List[Dict[str, Any]], top: int) -> None:
    if not hotspots:
        return
    print(f"\nFile hotspots (top {min(len(hotspots), top)} by severity):")
    for h in hotspots:
        name = h.get('file', '?')
        quality = h.get('quality_score', '?')
        score = h.get('hotspot_score', 0)
        issues = h.get('issues', [])
        details = h.get('details', {})
        lines = details.get('lines', '')

        # Quality indicator
        if isinstance(quality, (int, float)):
            if quality < 70:
                icon = '❌'
            elif quality < 85:
                icon = '⚠️ '
            else:
                icon = '💡'
        else:
            icon = '  '

        lines_str = f"  {lines}L" if lines else ''
        print(f"  {icon} {name}")
        print(f"      quality: {quality}/100  score: {score}{lines_str}")
        if issues:
            print(f"      issues: {', '.join(issues)}")

        # Suggest next command
        print(f"      → reveal {name}")


def _render_function_hotspots(fns: List[Dict[str, Any]], test_index: Optional[Set[str]] = None) -> None:
    if not fns:
        return
    has_coverage_info = test_index is not None
    print("\nComplex functions:")
    if has_coverage_info:
        print("  (✅ = test found  ⚪ = no test found  ❔ = unknown for this language)")
    for fn in fns:
        name = fn.get('name', '?')
        cx = fn.get('complexity', '?')
        loc = fn.get('file', '')
        line = fn.get('line', '')
        line_count = fn.get('line_count', '')

        if isinstance(cx, int) and cx >= 20:
            icon = '❌'
        elif isinstance(cx, int) and cx >= 15:
            icon = '⚠️ '
        else:
            icon = '💡'

        if has_coverage_info:
            hint = fn.get('has_test_hint', ...)
            if hint is None:
                cov = '❔'  # language has no known test convention (BACK-1276)
            elif hint is ...:
                cov = '✅' if _is_covered(name, loc, test_index) else '⚪'  # type: ignore[arg-type]
            else:
                cov = '✅' if hint else '⚪'
            cov_str = f' {cov}'
        else:
            cov_str = ''

        loc_str = f"  {loc}" if loc else ''
        lc_str = f"  ({line_count}L)" if line_count else ''
        print(f"  {icon}{cov_str} {name}  complexity: {cx}{lc_str}{loc_str}:{line}")


def _render_summary(file_hotspots: List[Dict[str, Any]], fn_hotspots: List[Dict[str, Any]]) -> None:
    critical_files = sum(1 for h in file_hotspots if h.get('quality_score', 100) < 70)
    critical_fns = sum(1 for f in fn_hotspots if f.get('complexity', 0) > 20)
    total = len(file_hotspots) + len(fn_hotspots)

    print()
    if critical_files or critical_fns:
        parts = []
        if critical_files:
            parts.append(f"{critical_files} critical file(s)")
        if critical_fns:
            parts.append(f"{critical_fns} critical function(s)")
        print(f"Summary: {total} hotspot(s) — {', '.join(parts)} need immediate attention ❌")
    else:
        print(f"Summary: {total} hotspot(s) — no critical issues, review when convenient ⚠️")
    print()


def _render_report(report: Dict[str, Any], top: int, test_index: Optional[Set[str]] = None) -> None:
    """Render hotspots as human-readable text."""
    path = report['path']
    file_hotspots = report['file_hotspots']
    fn_hotspots = report['function_hotspots']

    print()
    print(f"Hotspots: {path}")
    print("━" * 50)

    if not file_hotspots and not fn_hotspots:
        print("\nNo hotspots found ✅  Code quality looks good.")
        print()
        return

    _render_file_hotspots(file_hotspots, top)
    _render_function_hotspots(fn_hotspots, test_index=test_index)
    _render_summary(file_hotspots, fn_hotspots)


class HotspotsRenderer:
    """Renderer for hotspots:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text',
                          top: int = 10, test_index: Optional[Set[str]] = None) -> None:
        if format == 'json':
            print_json_result(result)
            return
        _render_report(result, top, test_index=test_index)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error scanning hotspots: {error}")


@register_adapter('hotspots')
@register_renderer(HotspotsRenderer)
class HotspotsAdapter(ResourceAdapter):
    """Adapter for identifying high-complexity, low-quality files and functions."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    ALL_RESULTS_QUERY = 'top=1000000'  # default top=10 per ranking; --all lifts it (BACK-1229)

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507
        # Populated by get_structure(); text rendering needs the raw set for
        # its coverage overlay, but it must never appear in the JSON contract
        # (only the per-function `has_test_hint` boolean derived from it does).
        self.test_index: Optional[Set[str]] = None

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
                {'uri': 'reveal hotspots://. --all', 'description': 'Lift the default top-10 cap on both rankings'},
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
            'query_params': {
                'top': {'type': 'integer', 'description': 'Number of hotspots to show', 'examples': ['top=20']},
                'min_complexity': {'type': 'integer', 'description': 'Minimum cyclomatic complexity to report', 'examples': ['min_complexity=15']},
                'functions_only': {'type': 'boolean', 'description': 'Skip file-level hotspots', 'examples': ['functions_only=true']},
                'files_only': {'type': 'boolean', 'description': 'Skip function-level hotspots (and the test-index scan)', 'examples': ['files_only=true']},
            },
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

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        top = self.int_param('top', 10)
        min_cx = self.int_param('min_complexity', 10)
        functions_only = str(self.query_params.get('functions_only', False)).lower() == 'true'
        files_only = str(self.query_params.get('files_only', False)).lower() == 'true'

        file_hotspots: List[Dict[str, Any]] = [] if functions_only else _run_file_hotspots(self, path, top)
        fn_hotspots: List[Dict[str, Any]] = [] if files_only else _run_function_hotspots(self, path, min_cx, top)

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
        }

        meta = self.composed_meta()
        warnings = list(meta.get('warnings') or []) if meta else []
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
