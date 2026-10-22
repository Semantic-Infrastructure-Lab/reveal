"""testability:// adapter - correlate patch pressure with production boundaries.

Scan logic already lived in the dedicated reveal.testability.report module
(build_testability_report, already self-enveloped with contract_version/
type/source — BACK-906); this adapter just gives it the same URI/adapter
registration every other capability follows (BACK-901/BACK-959). Render
logic and test-path resolution live here; the `reveal testability` command is
generated from this adapter's declaration.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ResourceAdapter, register_adapter, register_renderer
from ..errors import NotApplicableError
from ..utils.path_utils import is_test_dir
from ..rendering.adapters.testability import TestabilityRenderer
from ..utils.query_binding import bind_declared_params, boolean_value
from ..utils.query_parser import (CliBinding, ParamSpec, QueryParams, ResourceSpec,
                                  param_schema, peek_query_items, whole_number)
from ..utils.results import AnalysisCompleteness, result_execution_facts


def _whole_control(value: Any) -> int:
    """Keep URI's non-exponent rule without rounding decimal strings through float."""
    if isinstance(value, bool):
        raise ValueError('boolean is not a whole number')
    if isinstance(value, str):
        spelling = value.strip()
        if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.0*)?|\.0+)', spelling):
            raise ValueError('expected a signed whole decimal')
        integer = spelling.split('.')[0]
        value = int(integer + '0' if integer in ('', '+', '-') else integer)
    try:
        return whole_number(value)
    except OverflowError:
        raise ValueError('expected a finite whole number') from None


def _top(value: Any) -> int:
    return max(0, _whole_control(value))


def _threshold(value: Any) -> int:
    return max(1, _whole_control(value))


def _test_roots(value: Any) -> tuple:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError('tests must contain at least one path')
    if any(not isinstance(path, str) or not path or '\x00' in path for path in value):
        raise ValueError('tests must contain nonempty paths')
    return tuple(value)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _required_loss(result: Dict[str, Any]) -> bool:
    meta = result.get('meta', {})
    kinds = {'analysis_failed', 'parse_recovered', 'analysis_incomplete', 'partial_parse', 'worker_lost'}
    return bool(meta.get('errors')) or any(
        isinstance(warning, dict) and warning.get('type') in kinds
        for warning in meta.get('warnings', []))


def _ranked_patch_valid(row: Any) -> bool:
    from ..testability.report import _count, _finite
    if not isinstance(row, dict):
        return False
    return (all(isinstance(row.get(key), str) for key in ('key', 'group_by', 'suggestion'))
            and all(_count(row.get(key)) for key in ('patch_count', 'test_count', 'private_patch_count', 'max_patches_in_test'))
            and _finite(row.get('score')) and _string_list(row.get('test_files'))
            and _string_list(row.get('boundary_categories'))
            and isinstance(row.get('related_profiles'), list)
            and all(_related_profile_valid(profile) for profile in row['related_profiles']))


def _related_profile_valid(row: Any) -> bool:
    from ..testability.report import _count
    if not isinstance(row, dict):
        return False
    return (all(isinstance(row.get(key), str) for key in ('file', 'function'))
            and all(_count(row.get(key)) for key in ('line', 'complexity', 'lines'))
            and row['line'] > 0 and _string_list(row.get('categories')))


def _ranked_profile_valid(row: Any) -> bool:
    from ..testability.report import _count, _finite
    return (isinstance(row, dict) and _related_profile_valid(row)
            and _count(row.get('patch_count')) and _finite(row.get('score'))
            and isinstance(row.get('suggestion'), str))


def _report_error(result: Dict[str, Any], *, initial: bool = False) -> Optional[str]:
    from ..testability.report import _count
    if result.get('error') or result.get('applicable') is False:
        return None
    summary = result.get('summary')
    counts = ('total_patch_uses', 'total_boundary_profiles', 'total_patch_targets',
              'patch_groups_reported', 'boundary_profiles_reported')
    if not isinstance(summary, dict) or not all(_count(summary.get(key)) for key in counts):
        return 'Testability answer is missing required uncapped observation counts'
    if not _string_list(result.get('tests')):
        return 'Testability answer has malformed test paths'
    for field, validator, count in (
        ('patch_hotspots', _ranked_patch_valid, 'patch_groups_reported'),
        ('boundary_hotspots', _ranked_profile_valid, 'boundary_profiles_reported'),
    ):
        rows = result.get(field)
        if not isinstance(rows, list) or not all(validator(row) for row in rows):
            return f'Testability answer has malformed required {field}'
        if initial and len(rows) != summary[count]:
            return f'Testability answer has inconsistent {count}'
    return None


def _resolve_test_paths(src_path: Path, tests: Optional[List[str]]) -> List[Path]:
    """The roots the patch scan walks: the given ``tests=`` (trusted as the suite), else the target
    itself (its parent for a file), where ``is_test_path`` picks the test files, plus the test
    directories beside the target (``pkg/`` with a sibling ``tests/`` or ``t/``, the usual layout;
    BACK-1888)."""
    if tests:
        return [Path(t).expanduser().resolve() for t in tests if Path(t).expanduser().exists()]
    root = (src_path if src_path.is_dir() else src_path.parent).resolve()
    beside = [d for d in sorted(root.parent.iterdir()) if d.is_dir() and d != root and is_test_dir(d.name)] \
        if src_path.is_dir() and root.parent != root else []
    return [root, *beside]


@register_adapter('testability')
@register_renderer(TestabilityRenderer)
class TestabilityAdapter(ResourceAdapter):
    """Adapter correlating test-suite patch/mock pressure with production
    boundary fan-out — where tests over-mock vs. where risky boundary code
    has no patch coverage at all."""
    HELP_CLUSTER = 'Code Analysis'
    CLI_QUERY_FLAGS = {'all': 'top=1000000', 'limit': 'top={value}', 'respect_gitignore': 'respect_gitignore=false'}  # top= caps each hotspot group (default 20; BACK-1379, BACK-1496)

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)

    RESULT_TYPE = 'testability_report'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    BUDGET_LIST_FIELD = ('patch_hotspots', 'boundary_hotspots')
    PARAM_SPECS = (
        ParamSpec('tests', 'array', 'Test paths, trusted as the suite (omitted: the test files under the target, by the shared is_test_path rule)', None,
                  _test_roots, uri_codec='comma-percent', role='analysis',
                  cli=CliBinding(('--tests',), nargs='+')),
        ParamSpec('top', 'integer', 'Maximum groups per hotspot list; zero is unlimited', 20,
                  _top, zero_policy='unlimited', role='presentation', cli=CliBinding(('--top',))),
        ParamSpec('min_patches', 'integer', 'Minimum patches for a target group', 3,
                  _threshold, role='analysis', cli=CliBinding(('--min-patches',))),
        ParamSpec('min_categories', 'integer', 'Minimum boundary categories', 3,
                  _threshold, role='analysis', cli=CliBinding(('--min-categories',))),
        ParamSpec('include_unresolved', 'boolean', 'Include low-count unresolved targets', False,
                  boolean_value, role='analysis', cli=CliBinding(('--include-unresolved',), action='store_true')),
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
    def validate_request(params, args):
        tests = dict(peek_query_items(params)).get('tests')
        for root in tests or ():
            try:
                Path(root).expanduser().stat()
            except (FileNotFoundError, NotADirectoryError):
                raise ValueError(f'Test path not found: {root}') from None

    def answer_requirement_error(self, result, expected_type, prior_facts=None):
        return _report_error(result, initial=prior_facts is None)

    @staticmethod
    def execution_facts(result):
        from ..utils.results import FailureCause, failure_execution_facts
        if _report_error(result):
            return failure_execution_facts(FailureCause.ANALYSIS)
        state = AnalysisCompleteness.COMPLETE
        if _required_loss(result):
            summary = result.get('summary', {})
            usable = summary.get('total_patch_uses', 0) or summary.get('total_boundary_profiles', 0)
            state = AnalysisCompleteness.INCOMPLETE if usable else AnalysisCompleteness.FAILED
        return result_execution_facts(result, completeness=state)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'testability',
            'description': 'Find testability pressure by joining test patch usage with production boundary fan-out.',
            'syntax': 'testability://<path>[?tests=tests,integration_tests&top=20&min_patches=3&min_categories=3&include_unresolved=true]',
            'examples': [
                {'uri': 'testability://src', 'description': 'Testability report for src/ (finds its test files by the is_test_path rule)'},
                {'uri': 'testability://src?tests=tests,integration_tests', 'description': 'Scan specific test directories'},
                {'uri': 'testability://src?top=10', 'description': 'Top 10 patch/boundary groups'},
            ],
            'features': [
                'Production patch hotspots: functions/modules most mocked by tests',
                'Boundary fan-out hotspots: high-complexity boundary code with no patch coverage. '
                'Categories come from each function\'s own calls, classified exactly as --sideeffects does, '
                'in every language --sideeffects covers',
                'Patch pressure scans Python unittest.mock/monkeypatch and JS/TS jest/vitest tests',
            ],
            'notes': [
                'When `tests` is omitted the test files are the ones under the source root that the shared is_test_path rule calls tests (test directories, test_*, *_test, *.spec.*); the report names the rule and the file count in `test_scope`.',
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
            'resource': TestabilityAdapter.RESOURCE_SPEC.schema(),
            'query_params': param_schema(TestabilityAdapter.PARAM_SPECS),
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
                'Patch-pressure detection supports Python and recognized JavaScript/TypeScript test files.',
            ],
        }

    def get_structure(self, verbose: bool = False, **kwargs: Any) -> Dict[str, Any]:
        return testability_report(self.path, self.query_params, verbose)


def testability_report(resource: str, query_params: Any, verbose: bool = False) -> Dict[str, Any]:
    """The report both ``testability://`` and ``patches://?view=pressure`` answer (BACK-2160): one owner, read from
    the declared parameters of whichever adapter was asked."""
    from reveal.testability.patches import iter_test_files
    from reveal.testability.report import build_testability_report
    from reveal.utils.path_utils import as_spelled, detect_non_python_language

    path = Path(resource)
    tests = TestabilityAdapter.PARAM_SPECS[0].read(query_params)
    from .overview import UNLIMITED_TOP
    top = UNLIMITED_TOP if verbose else TestabilityAdapter.PARAM_SPECS[1].read(query_params)
    min_patches = TestabilityAdapter.PARAM_SPECS[2].read(query_params)
    min_categories = TestabilityAdapter.PARAM_SPECS[3].read(query_params)
    include_unresolved = TestabilityAdapter.PARAM_SPECS[4].read(query_params)

    by_test_path = not tests
    test_paths = _resolve_test_paths(path, tests)
    if tests and not test_paths:
        raise NotApplicableError(f"none of the tests= paths exist for {path}: {', '.join(tests)}")
    if by_test_path and not iter_test_files(test_paths, by_test_path=True):
        raise NotApplicableError(
            f"no test files found under {path} (the shared is_test_path rule: test directories such as tests/, test/, "
            "spec/, t/, and test_*, *_test, *.spec.* names) — pass --tests <path> (URI: tests=<path>)"
        )

    report = build_testability_report(
        str(path),
        [str(p) for p in test_paths],
        top=max(0, top),
        min_patches=max(1, min_patches),
        min_categories=max(1, min_categories),
        include_unresolved=include_unresolved,
        by_test_path=by_test_path,
    )
    # The tests dirs found were resolved; name them as the user named the target (BACK-1366).
    report['tests'] = [as_spelled(p, resource) for p in test_paths]

    # A supported JS/TS suite can genuinely contain no recognized mock calls.
    if report.get('summary', {}).get('total_patch_uses', 0) == 0:
        lang = detect_non_python_language(test_paths[0])
        if lang and lang not in ('TypeScript', 'JavaScript'):
            report['_patch_note'] = (
                f'patch pressure not computed for {lang} test suites — '
                'the patch scan supports Python and JavaScript/TypeScript tests '
                '(boundary hotspots below still apply).'
            )

    return report
