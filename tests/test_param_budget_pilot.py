"""The pilot keeps schema/parser/CLI policy aligned and stage counts distinct."""
from dataclasses import FrozenInstanceError
import pytest
from reveal.adapters.patches.adapter import PatchesAdapter
from reveal.rendering.base import capped_section
from reveal.utils.query_control import BudgetAccounting, apply_budget_limits
from reveal.utils.query_parser import ParamSpec, collect_query_keys, parse_query_params

pytestmark = pytest.mark.component


@pytest.fixture
def patches(tmp_path):
    path = tmp_path / 'test_probe.py'
    path.write_text('from unittest.mock import patch\n'
                    'def test_probe():\n'
                    '    with patch("app.a"), patch("app.b"), patch("app.c"):\n        pass\n',
                    encoding='utf-8')
    return path


def test_patches_numeric_declaration_matches_runtime_and_cli(patches):
    schema = PatchesAdapter.get_schema()['query_params']
    default = PatchesAdapter(str(patches)).get_structure()
    assert default['query']['limit'] == schema['limit']['default'] == 20
    assert default['query']['min'] == schema['min']['default'] == 1
    assert schema['limit']['zero_policy'] == 'all'
    all_groups = PatchesAdapter(str(patches), 'limit=0').get_structure()
    assert len(all_groups['groups']) == 3
    assert len(PatchesAdapter(str(patches), 'limit=1').get_structure()['groups']) == 1
    assert PatchesAdapter(str(patches), 'min=0').get_structure()['query']['min'] == 0
    fragment = PatchesAdapter.CLI_QUERY_FLAGS['all']
    assert len(PatchesAdapter(str(patches), fragment).get_structure()['groups']) == 3
    with pytest.raises(ValueError):
        PatchesAdapter(str(patches), 'limit=oops').get_structure()


def test_declaration_validation_does_not_claim_an_unread_key():
    spec = ParamSpec('limit', 'integer', 'Rows', 20, int, minimum=0, zero_policy='empty')
    with collect_query_keys() as log:
        params = parse_query_params('limit=0')
        assert not log.used
        assert spec.schema()['minimum'] == 0 and not log.used
        assert spec.read(params) == 0 and log.used == {'limit'}
    with pytest.raises(ValueError):
        spec.read({'limit': -1})
    with pytest.raises(FrozenInstanceError):
        spec.default = 5


def test_budget_stages_preserve_existing_page_and_text_results():
    page = apply_budget_limits([{'n': n} for n in range(3)], max_items=1)
    assert page['meta'] == {'truncated': True, 'reason': 'max_items_exceeded',
                            'total_available': 3, 'returned': 1, 'next_cursor': 'offset=1'}
    assert capped_section([1, 2, 3], 1, str) == ['1', '    ... and 2 more']
    assert capped_section([1, 2], 0, str) == ['    ... and 2 more']
    assert capped_section([1, 2], None, str) == ['1', '2']
    assert BudgetAccounting('scan', 8, 3).remaining == 5
    assert BudgetAccounting('match', 3, 3).remaining == 0
    assert BudgetAccounting('page', 3, 1) != BudgetAccounting('text', 3, 1)
    with pytest.raises(ValueError):
        BudgetAccounting('page', 1, 2)
