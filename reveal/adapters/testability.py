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
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import ResourceAdapter, register_adapter, register_renderer
from ..errors import NotApplicableError
from ..utils.path_utils import TestLayout, is_test_dir
from ..rendering.adapters.testability import TestabilityRenderer
from ..utils.query_binding import bound_constructor_params, boolean_value, verbose_legacy
from ..utils.query_parser import (CliBinding, LegacySpelling, ParamSpec, legacy_slices, ResourceSpec,
                                  param_schema, peek_query_items, whole_number)
from ..utils.results import AnalysisCompleteness, lost_evidence, result_execution_facts


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


def _threshold(value: Any) -> int:
    return max(1, _whole_control(value))


def _test_roots(value: Any) -> tuple:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError('test-paths must contain at least one path')
    if any(not isinstance(path, str) or not path or '\x00' in path for path in value):
        raise ValueError('test-paths must contain nonempty paths')
    return tuple(value)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _required_loss(result: Dict[str, Any]) -> bool:
    meta = result.get('meta', {})
    return bool(meta.get('errors')) or lost_evidence(meta.get('warnings'))


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


def _resolve_test_paths(src_path: Path, tests: Optional[List[str]],
                        test_layout: Optional[TestLayout] = None) -> List[Path]:
    """The roots the patch scan walks: the given ``--test-paths`` (trusted as the suite), else the target
    itself (its parent for a file), where the selected policy picks the test files, plus the test
    directories beside the target (``pkg/`` with a sibling ``tests/`` or ``t/``, the usual layout;
    BACK-1888). Declared project paths add literal file or directory roots without resolving aliases."""
    if tests:
        return [Path(t).expanduser().resolve() for t in tests if Path(t).expanduser().exists()]
    root = Path(os.path.abspath(src_path if src_path.is_dir() else src_path.parent))
    beside = [d for d in sorted(root.parent.iterdir()) if d != root and is_test_dir(d.name)] \
        if src_path.is_dir() and root.parent != root else []
    declared = [test_layout.anchor / selector for selector in test_layout.additional_paths] if test_layout else []
    return list(dict.fromkeys([root, *beside, *declared]))


# The pressure report's controls, declared once for testability:// and patches ?view=pressure (BACK-2160).
# test-paths names the roots trusted as the suite; --tests is the shared include|exclude test policy on every other noun
# (one value domain per shared control, D21), so the roots' old spelling --tests PATHS / ?tests= is its legacy word,
# noted until the cut (param:patches.tests, param:testability.tests; BACK-2774).
PRESSURE_SPECS = (
    ParamSpec('test-paths', 'array', 'Test paths, trusted as the suite (omitted: default project test/support policy and '
              'candidate suite roots)', None, _test_roots, ('--test-paths tests',), uri_codec='comma-percent',
              role='analysis',
              aliases=('test_paths',), legacy=(LegacySpelling('tests', flag='--tests'),),
              cli=CliBinding(('--test-paths',), dest='test_paths', nargs='+', metavar='PATH')),
    ParamSpec('top', 'integer', 'Maximum groups per hotspot list; 0 is all', 20,
              _whole_control, minimum=0, zero_policy='all', role='presentation', cli=CliBinding(('--top',))),
    ParamSpec('min_patches', 'integer', 'Minimum patches for a target group', 3,
              _threshold, role='analysis', cli=CliBinding(('--min-patches',))),
    ParamSpec('min_categories', 'integer', 'Minimum boundary categories', 3,
              _threshold, role='analysis', cli=CliBinding(('--min-categories',))),
    ParamSpec('include_unresolved', 'boolean', 'Include low-count unresolved targets', False,
              boolean_value, role='analysis', cli=CliBinding(('--include-unresolved',), action='store_true')),
)

_PRESSURE_TOP = PRESSURE_SPECS[1]
_LIMIT = replace(_PRESSURE_TOP, name='limit', cli=CliBinding(('--limit',)),
                 legacy=(LegacySpelling('top', flag='--top'), verbose_legacy(0, 'limit=0 (--limit 0)')))


@register_adapter('testability')
@register_renderer(TestabilityRenderer)
class TestabilityAdapter(ResourceAdapter):
    """Adapter correlating test-suite patch/mock pressure with production
    boundary fan-out — where tests over-mock vs. where risky boundary code
    has no patch coverage at all."""
    HELP_CLUSTER = 'Code Analysis'
    CLI_QUERY_FLAGS = {'all': 'limit=1000000', 'limit': 'limit={value}', 'respect_gitignore': 'respect_gitignore=false'}  # limit= caps each hotspot group (default 20; BACK-1379, BACK-1496)

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)

    RESULT_TYPE = 'testability_report'
    FINDINGS_POLICIES = ('none',)
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    BUDGET_LIST_FIELD = ('patch_hotspots', 'boundary_hotspots')
    BUDGET_COUNT_FIELDS = {'patch_hotspots': ('summary.patch_groups_reported',),  # BACK-2653
                           'boundary_hotspots': ('summary.boundary_profiles_reported',)}
    # limit is the cap (COMMAND_MODEL "Caps", BACK-2673; each list capped separately): top is its legacy word, the same
    # value, and verbose lifts the group caps, the legacy word of limit=0 (rule 16 parity, BACK-2654 note #17). patches'
    # pressure view declares PRESSURE_SPECS as they are: its --limit question is BACK-2625's.
    # --head/--tail/--range slice both lists today: flag-only legacy modifiers until the cut (BACK-2673)
    PARAM_SPECS = (*(_LIMIT if spec is _PRESSURE_TOP else spec for spec in PRESSURE_SPECS),
                   *legacy_slices(head=(), tail=(), range=()))

    def __init__(self, resource: str, query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = bound_constructor_params(self.PARAM_SPECS, query, params)

    @staticmethod
    def validate_request(params, args):
        tests = dict(peek_query_items(params)).get('test-paths')
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
            'syntax': 'testability://<path>[?test-paths=tests,integration_tests&limit=20&min_patches=3&min_categories=3&include_unresolved=true]',
            'examples': [
                {'uri': 'testability://src', 'description': 'Pressure report for src/ using the selected project test/support policy'},
                {'uri': 'testability://src?test-paths=tests,integration_tests', 'description': 'Scan specific test directories'},
                {'uri': 'testability://src?limit=10', 'description': 'Top 10 patch/boundary groups'},
            ],
            'features': [
                'Production patch hotspots: functions/modules most mocked by tests',
                'Boundary fan-out hotspots: high-complexity boundary code with no patch coverage. '
                'Categories come from each function\'s own calls, classified exactly as --view effects does, '
                'in every language --view effects covers',
                'Patch pressure scans Python unittest.mock/monkeypatch and JS/TS jest/vitest tests',
            ],
            'notes': [
                'When `test-paths` is omitted, one selected project policy chooses test/support files under the source root or parent, conventional sibling candidates and declared additional paths; `test_scope` names the basis, anchor, candidate roots and file count.',
                'Default candidate roots can include absent optional declarations; outside-anchor sibling suites use conventional names without their configuration. Source boundary profiles retain their separate target scope.',
                'Explicit `test-paths` bypasses default policy selection: all Python files are trusted, while JS/TS retains recognized test filenames. Existing empty explicit suites remain valid.',
            ],
            'see_also': [
                'reveal patches <path> --view pressure - the current spelling (reveal testability is retired)',
                'reveal patches://<tests> - raw patch/mock scan',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'testability',
            'description': 'Test patch/mock pressure joined with production boundary fan-out',
            'uri_syntax': 'testability://<path>?test-paths=tests,integration_tests&limit=20&min_patches=3&min_categories=3',
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
                'A tree whose discovered test files are all in another language is declined as not applicable (the decision patches:// shares), naming the language.',
            ],
        }

    def get_structure(self) -> Dict[str, Any]:
        return testability_report(self.path, self.query_params, _LIMIT)


def testability_report(resource: str, query_params: Any, cap: ParamSpec = _PRESSURE_TOP,
                       thresholds: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
    """The report both ``testability://`` and ``patches://?view=pressure`` answer (BACK-2160): one owner, read from
    the declared parameters of whichever adapter was asked. *cap*: that adapter's group cap (testability's ``limit``,
    the pressure view's ``limit``); *thresholds*: the minimums when the caller reads them from where."""
    from reveal.testability.report import build_testability_report
    from reveal.utils.path_utils import as_spelled, detect_non_python_language

    path = Path(resource)
    tests = TestabilityAdapter.PARAM_SPECS[0].read(query_params)
    top = cap.read(query_params)
    # (min_patches, min_categories): testability's own parameters, or the pressure view's where terms (BACK-2625)
    min_patches, min_categories = thresholds or (TestabilityAdapter.PARAM_SPECS[2].read(query_params),
                                                 TestabilityAdapter.PARAM_SPECS[3].read(query_params))
    include_unresolved = TestabilityAdapter.PARAM_SPECS[4].read(query_params)

    by_test_path = not tests
    layout = None
    if by_test_path:
        from ..config import RevealConfig
        target = Path(os.path.abspath(path))
        layout = TestLayout.for_path(target, fallback_root=target)
        layout = RevealConfig.get(layout.anchor).apply_test_layout(layout)
    test_paths = _resolve_test_paths(path, tests, layout)
    if tests and not test_paths:
        raise NotApplicableError(f"none of the --test-paths roots exist for {path}: {', '.join(tests)}")
    report = build_testability_report(
        str(path),
        [str(p) for p in test_paths],
        top=max(0, top),
        min_patches=max(1, min_patches),
        min_categories=max(1, min_categories),
        include_unresolved=include_unresolved,
        by_test_path=by_test_path,
        test_layout=layout,
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
