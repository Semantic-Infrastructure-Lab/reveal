"""patches:// adapter - scan tests for patch pressure."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from reveal.adapters.base import ResourceAdapter, register_adapter, register_renderer
from reveal.reveal_types import CONTRACT_VERSION
from reveal.testability.patches import group_patches, scan_patches
from reveal.utils.query import parse_query_params
from reveal.utils.results import ResultBuilder
from reveal.utils.validation import require_path_exists

from .renderer import PatchesRenderer


@register_adapter('patches')
@register_renderer(PatchesRenderer)
class PatchesAdapter(ResourceAdapter):
    """Adapter for exploring patch pressure in Python and TypeScript tests."""
    HELP_CLUSTER = 'Code Analysis'

    BUDGET_LIST_FIELD = 'groups'
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

    def __init__(self, resource: str, query: Optional[str] = None):
        path, query_string = resource, query
        self.path = str(Path(path).expanduser())
        self.query_params = parse_query_params(query_string or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507

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
                'Patch pressure is advisory. Mocking external boundaries can be normal and correct.',
                'Use reveal testability <src> --tests <tests> to join patch pressure with production boundary fan-out.',
            ],
            'see_also': [
                'reveal help://testability - Testability workflow guide',
                'reveal testability src --tests tests - Combined report',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'patches',
            'description': 'Patch pressure scanner for Python and TypeScript/JavaScript tests',
            'uri_syntax': 'patches://<tests-path>?group=target&limit=20',
            'query_params': {
                'group': {'type': 'string', 'description': 'Grouping mode: target, test, or file', 'examples': ['group=target']},
                'limit': {'type': 'integer', 'description': 'Maximum groups to return', 'examples': ['limit=20']},
                'min': {'type': 'integer', 'description': 'Minimum patch count for a group', 'examples': ['min=3']},
                'target': {'type': 'string', 'description': 'Filter by target substring or glob', 'examples': ['target=ssl']},
                'private': {'type': 'boolean', 'description': 'Only include private/internal patch targets', 'examples': ['private=true']},
                'suppress': {'type': 'boolean', 'description': 'Hide stdlib I/O noise (sys.stdout/stderr, builtins) from grouped output. Default: true. Raw totals always include them.', 'examples': ['suppress=false']},
            },
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
            ],
            'example_queries': [
                {'uri': 'patches://tests', 'description': 'Summarize patch pressure', 'output_type': 'patches_scan'},
                {'uri': 'patches://tests?group=test&min=3', 'description': 'Find patch-heavy tests', 'output_type': 'patches_scan'},
            ],
            'notes': [
                'Uses Python AST parsing for .py files, tree-sitter for .ts/.tsx/.js/.jsx files.',
                'TypeScript: recognises jest.mock, vi.mock, jest.spyOn, vi.spyOn, jest.fn, vi.fn, jest.replaceProperty.',
                'Dynamic patch targets are retained with lower confidence.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        # BACK-1250: scan_patches() silently accepted a nonexistent path and
        # returned a clean, successful-looking empty result (total_uses: 0,
        # errors: [], source_type mislabeled 'file') -- indistinguishable
        # from "this suite genuinely does no patching." Same convention as
        # classify.py's own get_structure().
        require_path_exists(Path(self.path))
        patches = scan_patches([self.path])
        # BACK-1211: query_parser.coerce_value() turns a literal '0'/'1'
        # value into bool regardless of field type -- str(True/False) would
        # silently corrupt group_by/target_filter if either were ever
        # literally '0' or '1'. Not a live bug (group is a fixed enum,
        # target is a mock-target name), but if that ever changes, follow
        # PackAdapter.get_structure()'s isinstance(value, bool) recovery
        # pattern for ?budget= (BACK-1180).
        group_by = str(self.query_params.get('group') or 'target')
        if group_by not in {'target', 'test', 'file'}:
            group_by = 'target'
        limit = self.int_param('limit', 20)
        min_count = self.int_param('min', 1)
        target_filter = str(self.query_params.get('target') or '')
        private_only = bool(self.query_params.get('private') or False)
        _suppress_raw = self.query_params.get('suppress')
        suppress = str(_suppress_raw).lower() != 'false' if _suppress_raw is not None else True

        groups = group_patches(
            patches,
            group_by=group_by,
            limit=limit,
            min_count=min_count,
            target_filter=target_filter,
            private_only=private_only,
            suppress=suppress,
        )
        targets = {p.target_qualname or p.target_raw for p in patches}

        warnings = [{
            'code': 'W-PATCHES-1',
            'message': 'Patch pressure is advisory; mocking external boundaries can be correct.',
        }]

        return ResultBuilder.create(
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
                'total_uses': len(patches),
                'total_targets': len(targets),
                'displayed_groups': len(groups),
                'groups': [g.to_dict() for g in groups],
                'uses': [p.to_dict() for p in patches],
            },
        )
