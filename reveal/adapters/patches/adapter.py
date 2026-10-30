"""patches:// adapter - scan tests for patch pressure."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.adapters.base import ResourceAdapter, register_adapter, register_renderer
from reveal.reveal_types import CONTRACT_VERSION
from reveal.testability.patches import (group_patches, language_not_scanned_warning, no_scannable_tests_reason,
                                        scan_patches)
from reveal.utils.path_utils import to_posix
from reveal.utils.query_binding import bind_declared_params, boolean_value
from reveal.utils.query_parser import (CliBinding, ParamSpec, QueryParams, ResourceSpec, param_schema,
                                       peek_query_items, whole_number)
from reveal.utils.results import AnalysisCompleteness, ResultBuilder, note_truncation, result_execution_facts
from reveal.utils.validation import require_path_exists

from ...rendering.adapters.patches import PatchesRenderer
from ...errors import NotApplicableError
from ..testability import TestabilityAdapter, _report_error, testability_report


# The warning types a patch scan emits when it lost files it should have read.
_REQUIRED_WARNINGS = frozenset({'analysis_failed', 'analysis_incomplete', 'parse_recovered'})

# The declaration `reveal patches` and patches:// are both generated from (BACK-2160). The default view is the raw
# scan of a test root; ?view=pressure is testability's report (was testability://), whose path is the production
# root and whose test files are chosen by the shared is_test_path rule or the explicit tests= override.
VIEWS = ('pressure',)
GROUPS = ('target', 'test', 'file')


def _text(value: Any) -> str:
    return str(value)


def _whole(value: Any) -> int:
    """whole_number for a URI value: '2' and '2.0' are accepted, '1.5' is not (the legacy query parser
    turned numeric strings into numbers first)."""
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            pass
    return whole_number(value)


_VIEW = ParamSpec('view', 'string', 'pressure: testability\'s report (was testability://), patch hotspots joined with production '
                  'boundary fan-out; the path is then the production root. Omitted: the raw patch scan of a test root',
                  None, _text, ('view=pressure',), choices=VIEWS, role='analysis',
                  cli=CliBinding(('--view',), metavar='VIEW'))
_GROUP = ParamSpec('group', 'string', 'Grouping mode: target, test, or file', 'target', _text,
                   ('group=target',), choices=GROUPS, role='analysis', cli=CliBinding(('--group',), metavar='MODE'))
_LIMIT = ParamSpec('limit', 'integer', 'Maximum groups to return', 20, _whole,
                   ('limit=20',), minimum=0, zero_policy='all', role='presentation',
                   cli=CliBinding(('--limit',), metavar='N'))
_MIN = ParamSpec('min', 'integer', 'Minimum patch count for a group', 1, _whole,
                 ('min=3',), minimum=0, zero_policy='no minimum', role='analysis', cli=CliBinding(('--min',), metavar='N'))
_TARGET = ParamSpec('target', 'string', 'Filter by target substring or glob', '', _text, ('target=ssl',),
                    role='analysis', cli=CliBinding(('--target',), metavar='PATTERN'))
_PRIVATE = ParamSpec('private', 'boolean', 'Only include private/internal patch targets', False, boolean_value,
                     ('private=true',), role='analysis', cli=CliBinding(('--private',), action='store_true'))
_SUPPRESS = ParamSpec('suppress', 'boolean', 'Hide stdlib I/O noise (sys.stdout/stderr, builtins) from grouped output. '
                      'Default: true. Raw totals always include them.', True, boolean_value, ('suppress=false',),
                      role='analysis', cli=CliBinding(('--no-suppress',), action='store_false'))
# The pressure view's own parameters are testability's, declared once there.
_PRESSURE_SPECS = TestabilityAdapter.PARAM_SPECS
PARAM_SPECS = (_VIEW, _GROUP, _LIMIT, _MIN, _TARGET, _PRIVATE, _SUPPRESS, *_PRESSURE_SPECS)


@register_adapter('patches')
@register_renderer(PatchesRenderer)
class PatchesAdapter(ResourceAdapter):
    """Patch pressure in Python and TypeScript tests; ?view=pressure joins it with production boundary fan-out
    (was testability://)."""
    HELP_CLUSTER = 'Code Analysis'

    BUDGET_LIST_FIELD = 'groups'
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESULT_TYPE = 'patches_scan'
    FINDINGS_POLICIES = ('none',)  # patch pressure is advisory; there is no findings gate
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = PARAM_SPECS
    CLI_QUERY_FLAGS = {'all': 'limit=1000000', 'respect_gitignore': 'respect_gitignore=false'}  # lifts the limit=20 group default (BACK-1379)

    def __init__(self, resource: str, query: Optional[str] = None, *, params: Optional[Dict[str, Any]] = None):
        self.path = to_posix(Path(resource).expanduser())  # '/' on every OS (BACK-1586)
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(self.PARAM_SPECS, query or '', transport='uri')
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def result_type_for(params) -> str:
        """The answer type the selected view produces, from key presence before conversion."""
        return TestabilityAdapter.RESULT_TYPE if dict(peek_query_items(params)).get('view') == 'pressure' else 'patches_scan'

    @staticmethod
    def validate_request(params, args):
        if dict(peek_query_items(params)).get('view') == 'pressure':
            TestabilityAdapter.validate_request(params, args)

    def answer_requirement_error(self, result, expected_type, prior_facts=None):
        if expected_type == TestabilityAdapter.RESULT_TYPE:
            return _report_error(result, initial=prior_facts is None)
        return None

    @staticmethod
    def execution_facts(result):
        """The report view is testability's. A scan that lost test files (unparsable, unreadable, an unwalkable
        directory) is incomplete: its totals leave out uses it could not read."""
        if isinstance(result, dict) and result.get('type') == TestabilityAdapter.RESULT_TYPE:
            return TestabilityAdapter.execution_facts(result)
        meta = result.get('meta') or {} if isinstance(result, dict) else {}
        lost = any(w.get('type') in _REQUIRED_WARNINGS for w in meta.get('warnings', []) if isinstance(w, dict))
        return result_execution_facts(
            result, completeness=AnalysisCompleteness.INCOMPLETE if lost else AnalysisCompleteness.COMPLETE)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'patches',
            'description': 'Scan Python and TypeScript/JavaScript tests for mock/patch pressure grouped by target.',
            'syntax': 'patches://<tests-path>[?group=target|test|file&limit=N&min=N]',
            'examples': [
                {'uri': 'patches://tests', 'description': 'Summarize patch pressure in tests/'},
                {'uri': 'patches://tests?group=target', 'description': 'Group patches by production target'},
                {'uri': 'patches://tests?group=test&min=3', 'description': 'Find tests with at least 3 patches'},
                {'uri': 'patches://tests?target=ssl&limit=10', 'description': 'Show patch groups matching ssl'},
                {'uri': 'patches://tests?private=true', 'description': 'Show patches of private/internal targets'},
            ],
            'features': [
                'Detects unittest.mock.patch decorators and context managers (Python)',
                'Detects patch.object and pytest monkeypatch.setattr (Python)',
                'Detects jest.mock, vi.mock, jest.spyOn, vi.spyOn, jest.fn, vi.fn, jest.replaceProperty (TypeScript/JS)',
                'Groups by target, test function, or test file',
                'Preserves unresolved dynamic targets instead of dropping them',
                'JSON output for agents and dashboards',
            ],
            'notes': [
                'Supports Python (unittest.mock/pytest) and TypeScript/JavaScript (Jest/Vitest).',
                'A tree whose test files are all in another language (Go, Java, Rust, ...) is declined as not applicable (exit 0), naming the language: 0 uses there would mean not scanned, not none. A scanned JS/TS suite with no mock calls is a real 0.',
                'Patch pressure is advisory. Mocking external boundaries can be normal and correct.',
                'Use reveal patches <src> --view pressure --tests <tests> to join patch pressure with production boundary fan-out.',
            ],
            'see_also': [
                'reveal patches src --view pressure --tests tests - Combined patch-pressure and boundary fan-out report',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'patches',
            'description': 'Patch pressure scanner for Python and TypeScript/JavaScript tests',
            'uri_syntax': 'patches://<path>?group=target&limit=20',
            'resource': PatchesAdapter.RESOURCE_SPEC.schema(),
            'query_params': param_schema(PatchesAdapter.PARAM_SPECS),
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'patches_scan',
                    'description': 'Patch uses and grouped patch pressure summaries',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'total_uses': {'type': 'integer'},
                            'total_targets': {'type': 'integer'},
                            'groups': {'type': 'array'},
                            'uses': {'type': 'array'},
                        },
                    },
                },
                {
                    'type': 'testability_report',
                    'description': 'view=pressure: patch hotspots and boundary fan-out hotspots for a source tree (was testability://)',
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
                {'uri': 'patches://tests', 'description': 'Summarize patch pressure', 'output_type': 'patches_scan'},
                {'uri': 'patches://tests?group=test&min=3', 'description': 'Find patch-heavy tests', 'output_type': 'patches_scan'},
            ],
            'notes': [
                'Scans the test files under <path> by the shared is_test_path rule, judged from the path\'s own name down (patches://tests scans all of tests/); `test_scope` names the rule and the file count.',
                'Mixed trees: the Python and JS/TS tests are scanned; when the test files in other languages outnumber them, `test_scope.unscanned` (language -> files) and a `language_not_scanned` warning say so.',
                'Uses Python AST parsing for .py files, tree-sitter for .ts/.tsx/.js/.jsx files.',
                'TypeScript: recognises jest.mock, vi.mock, jest.spyOn, vi.spyOn, jest.fn, vi.fn, jest.replaceProperty.',
                'Dynamic patch targets are retained with lower confidence.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        if _VIEW.read(self.query_params) == 'pressure':
            return testability_report(self.path, self.query_params, bool(kwargs.get('verbose')))
        # BACK-1250: scan_patches() silently accepted a nonexistent path and
        # returned a clean, successful-looking empty result (total_uses: 0,
        # errors: [], source_type mislabeled 'file') -- indistinguishable
        # from "this suite genuinely does no patching." Same convention as
        # classify.py's own get_structure().
        require_path_exists(Path(self.path))
        from ...config import RevealConfig
        RevealConfig.require_conventional_test_layout(Path(self.path), 'patches default test selection')
        # The path is the root; the test files under it are chosen by the shared is_test_path rule, judged from
        # the root's own name down, so patches://tests scans all of tests/ and a repository root only its tests (BACK-1888).
        patches = scan_patches([self.path], by_test_path=True)
        # A tree with no test file the scan reads has no answer: 0 uses would mean 'not scanned', not 'none'
        # (BACK-2224). The same decision testability makes. A walk that lost directories is reported below instead.
        if not patches.files_scanned and not patches.traversal_failures:
            raise NotApplicableError(no_scannable_tests_reason(self.path, patches.unscanned_languages))
        # BACK-1211: query_parser.coerce_value() turns a literal '0'/'1'
        # value into bool regardless of field type -- str(True/False) would
        # silently corrupt group_by/target_filter if either were ever
        # literally '0' or '1'. Not a live bug (group is a fixed enum,
        # target is a mock-target name), but if that ever changes, follow
        # PackAdapter.get_structure()'s isinstance(value, bool) recovery
        # pattern for ?budget= (BACK-1180).
        group_by = _GROUP.read(self.query_params)
        limit = _LIMIT.read(self.query_params)
        min_count = _MIN.read(self.query_params)
        target_filter = _TARGET.read(self.query_params)
        private_only = _PRIVATE.read(self.query_params)
        suppress = _SUPPRESS.read(self.query_params)

        ranked = group_patches(
            patches,
            group_by=group_by,
            min_count=min_count,
            target_filter=target_filter,
            private_only=private_only,
            suppress=suppress,
        )
        groups = ranked[:limit] if limit > 0 else ranked
        targets = {p.target_qualname or p.target_raw for p in patches}

        warnings: List[Any] = [{
            'type': 'advisory',
            'code': 'W-PATCHES-1',
            'message': 'Patch pressure is advisory; mocking external boundaries can be correct.',
        }]
        from ..ast.analysis import analysis_skipped_warning, parse_recovered_warning, traversal_failed_warning

        unscanned = language_not_scanned_warning(patches.unscanned_to_report())
        if unscanned:
            warnings.append(unscanned)
        traversal = traversal_failed_warning(patches.traversal_failures)
        if traversal:
            warnings.append(traversal)
        failed = analysis_skipped_warning(
            patches.skipped, None, 'their patch uses are missing from the result')
        if failed:
            warnings.append(failed)
        recovered = parse_recovered_warning([
            {'file': f, 'parse_recovered': True} for f in patches.recovered_files])
        if recovered:
            recovered['message'] += ' Patch uses may be incomplete.'
            warnings.append(recovered)

        result = ResultBuilder.create(
            result_type='patches_scan',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            parse_mode='python_ast+tree_sitter',
            confidence=0.9,
            warnings=warnings,
            errors=[],
            data={
                'query': {
                    'group': group_by,
                    'limit': limit,
                    'min': min_count,
                    'target': target_filter,
                    'private': private_only,
                    'suppress': suppress,
                },
                'test_scope': patches.test_scope('is_test_path'),
                'total_uses': len(patches),
                'total_targets': len(targets),
                'displayed_groups': len(groups),
                'groups': [g.to_dict() for g in groups],
                'uses': [p.to_dict() for p in patches],
            },
        )
        # BACK-1543: '?limit=3&group=file' showed 3 of 124 groups as all of them.
        note_truncation(result, 'groups', len(groups), len(ranked), 'limit', hint='raise ?limit=N')
        return result
