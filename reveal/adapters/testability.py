"""testability:// adapter - correlate patch pressure with production boundaries.

Scan logic already lived in the dedicated reveal.testability.report module
(build_testability_report, already self-enveloped with contract_version/
type/source — BACK-906); this adapter just gives it the same URI/adapter
registration every other capability follows (BACK-901/BACK-959). Render
logic and test-path resolution move here from cli/commands/testability.py,
which becomes a thin argparse shim.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ResourceAdapter, register_adapter, register_renderer
from ..utils import print_json_result
from ..utils.query import parse_query_params


def _resolve_test_paths(src_path: Path, tests: Optional[List[str]]) -> List[Path]:
    if tests:
        return [Path(t).expanduser().resolve() for t in tests if Path(t).expanduser().exists()]

    roots = []
    candidates = []
    if src_path.is_dir():
        candidates.append(src_path)
        candidates.append(src_path.parent)
    else:
        candidates.append(src_path.parent)

    for root in candidates:
        for name in ('tests', 'test', 'spec'):
            candidate = root / name
            if candidate.exists():
                roots.append(candidate.resolve())
    return sorted(set(roots))


def _render_patch_hotspots(rows: List[Dict[str, Any]], note: str = '') -> None:
    print("Production Patch Hotspots")
    if not rows:
        if note:
            print(f"  {note}")
        else:
            print("  none above threshold")
        print()
        return
    for row in rows:
        print()
        print(f"  {row.get('key')}")
        print(
            f"    patched {row.get('patch_count', 0)} times across "
            f"{row.get('test_count', 0)} test(s)"
        )
        categories = row.get('boundary_categories') or []
        if categories:
            print(f"    boundary categories: {', '.join(categories)}")
        profiles = row.get('related_profiles') or []
        if profiles:
            print("    related production functions:")
            for profile in profiles[:3]:
                print(
                    f"      {profile.get('file')}::{profile.get('function')} "
                    f"(cx {profile.get('complexity')}, line {profile.get('line')})"
                )
        print(f"    suggestion: {row.get('suggestion')}")
    print()


def _render_boundary_hotspots(rows: List[Dict[str, Any]]) -> None:
    print("Boundary Fan-Out Hotspots")
    if not rows:
        print("  none above threshold")
        print()
        return
    for row in rows:
        print()
        print(f"  {row.get('file')}::{row.get('function')}")
        print(f"    complexity: {row.get('complexity')}  lines: {row.get('lines')}")
        print(f"    categories: {', '.join(row.get('categories', []))}")
        if row.get('patch_count'):
            print(f"    related patch pressure: {row.get('patch_count')} patches")
        print(f"    suggestion: {row.get('suggestion')}")
    print()


def _render_report(report: Dict[str, Any]) -> None:
    print(f"Testability: {report.get('source')}")
    tests = ', '.join(report.get('tests', []))
    print(f"Tests: {tests}")
    print("-" * 50)
    summary = report.get('summary', {})
    print(
        f"Patch uses: {summary.get('total_patch_uses', 0)}  "
        f"Patch targets: {summary.get('total_patch_targets', 0)}"
    )
    print()

    _render_patch_hotspots(report.get('patch_hotspots', []), note=report.get('_patch_note', ''))
    _render_boundary_hotspots(report.get('boundary_hotspots', []))

    print("Summary")
    print(f"  {summary.get('patch_groups_reported', 0)} patch hotspot(s) reported")
    print(f"  {summary.get('boundary_profiles_reported', 0)} boundary hotspot(s) reported")


class TestabilityRenderer:
    """Renderer for testability:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
            return
        _render_report(result)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error building testability report: {error}")


@register_adapter('testability')
@register_renderer(TestabilityRenderer)
class TestabilityAdapter(ResourceAdapter):
    """Adapter correlating test-suite patch/mock pressure with production
    boundary fan-out — where tests over-mock vs. where risky boundary code
    has no patch coverage at all."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'testability',
            'description': 'Find testability pressure by joining test patch usage with production boundary fan-out.',
            'syntax': 'testability://<path>[?tests=tests,integration_tests&top=20&min_patches=3&min_categories=3&include_unresolved=true]',
            'examples': [
                {'uri': 'testability://src', 'description': 'Testability report for src/ (auto-detects tests/, test/, or spec/)'},
                {'uri': 'testability://src?tests=tests,integration_tests', 'description': 'Scan specific test directories'},
                {'uri': 'testability://src?top=10', 'description': 'Top 10 patch/boundary groups'},
            ],
            'features': [
                'Production patch hotspots: functions/modules most mocked by tests',
                'Boundary fan-out hotspots: high-complexity boundary code with no patch coverage',
                'Python-only (patch-pressure pipeline); JS/TS test suites get a pointer to patches:// instead',
            ],
            'notes': [
                'Auto-detects tests/, test/, or spec/ under the source root (or its parent) when `tests` is omitted.',
            ],
            'see_also': [
                'reveal testability <path> - CLI subcommand form',
                'reveal patches://<tests> - raw patch/mock scan',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'testability',
            'description': 'Test patch/mock pressure joined with production boundary fan-out',
            'uri_syntax': 'testability://<path>?tests=tests,integration_tests&top=20&min_patches=3&min_categories=3',
            'query_params': {
                'tests': {'type': 'string', 'description': 'Comma-separated test paths to scan (default: auto-detect tests/, test/, spec/)', 'examples': ['tests=tests,integration_tests']},
                'top': {'type': 'integer', 'description': 'Maximum patch and boundary groups to show', 'examples': ['top=10']},
                'min_patches': {'type': 'integer', 'description': 'Minimum patches for a target group', 'examples': ['min_patches=5']},
                'min_categories': {'type': 'integer', 'description': 'Minimum boundary categories for unpatched functions', 'examples': ['min_categories=2']},
                'include_unresolved': {'type': 'boolean', 'description': 'Include low-count unresolved patch targets', 'examples': ['include_unresolved=true']},
            },
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'testability_report',
                    'description': 'Patch hotspots and boundary fan-out hotspots for a source tree',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'summary': {'type': 'object'},
                            'patch_hotspots': {'type': 'array'},
                            'boundary_hotspots': {'type': 'array'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'testability://src', 'description': 'Testability report for src/', 'output_type': 'testability_report', 'task': 'quality'},
            ],
            'notes': [
                'Patch-pressure detection is Python-only; JS/TS test suites see a note pointing at patches://.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        from reveal.testability.report import build_testability_report
        from reveal.utils.path_utils import detect_non_python_language

        path = Path(self.path)
        tests_param = self.query_params.get('tests')
        tests = [t.strip() for t in str(tests_param).split(',') if t.strip()] if tests_param else None
        top = self.int_param('top', 20)
        min_patches = self.int_param('min_patches', 3)
        min_categories = self.int_param('min_categories', 3)
        include_unresolved = str(self.query_params.get('include_unresolved', False)).lower() == 'true'

        test_paths = _resolve_test_paths(path, tests)
        if not test_paths:
            raise ValueError(f"no tests found for {path} — pass tests=<path> or add tests/, test/, or spec/")

        report = build_testability_report(
            str(path),
            [str(p) for p in test_paths],
            top=max(0, top),
            min_patches=max(1, min_patches),
            min_categories=max(1, min_categories),
            include_unresolved=include_unresolved,
        )

        # When no patches were found, check whether the test suite is
        # non-Python (patch pressure is Python-only) so the renderer can
        # explain the silence.
        if report.get('summary', {}).get('total_patch_uses', 0) == 0:
            lang = detect_non_python_language(test_paths[0])
            if lang:
                note = (
                    f'patch pressure not computed for {lang} test suites — '
                    "`reveal testability`'s boundary-profile pipeline is Python-only."
                )
                if lang in ('TypeScript', 'JavaScript'):
                    note += (
                        ' For JS/TS mock pressure use `reveal patches://<tests>` '
                        '(jest/vitest supported).'
                    )
                report['_patch_note'] = note

        return report
