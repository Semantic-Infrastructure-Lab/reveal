"""Independent recall-gate controls for reported test-layout evidence."""
import copy

import pytest

from test_recall_gate import gate, test_import_corpus  # noqa: F401


pytestmark = pytest.mark.component


def test_gate_preserves_lexical_scope_without_changing_scoring(test_import_corpus):
    root, entry = test_import_corpus
    result = gate.measure(entry, root)
    for row in (result, *result['lazy'].values(), result['tests']['exclude']):
        scope = row['edge_rule']['test_scope']
        assert scope['anchor'] == '.'
        assert scope['source'] == 'explicit_root'
        assert scope['rule'] == 'is_test_path'
        assert scope['include_anchor_name'] is False
    assert result['hit_edges'] == result['oracle_edges'] == 4
    assert result['tests']['exclude']['hit_edges'] == 2


@pytest.mark.parametrize('damage', ['missing', 'empty', 'anchor', 'rule', 'flag'])
def test_gate_rejects_lost_or_malformed_lexical_scope(test_import_corpus, monkeypatch, damage):
    root, _ = test_import_corpus
    healthy = gate._importers_request(root, root, None)
    assert healthy['count'] if 'count' in healthy else healthy['total']
    broken = copy.deepcopy(healthy)
    scope = broken['edge_rule']['test_scope']
    if damage == 'missing':
        del broken['edge_rule']['test_scope']
    elif damage == 'empty':
        broken['edge_rule']['test_scope'] = {}
    elif damage == 'anchor':
        scope['anchor'] = None
    elif damage == 'rule':
        scope['rule'] = 'unknown-rule'
    else:
        scope['include_anchor_name'] = 'false'
    monkeypatch.setattr(gate, '_cli_json', lambda *args, **kwargs: broken)
    with pytest.raises(RuntimeError, match='test_scope'):
        gate._importers_request(root, root, None)


def test_gate_retained_scope_is_not_an_alias():
    scope = {'anchor': '.', 'source': 'project', 'rule': 'is_test_path',
             'include_anchor_name': False, 'basis': 'paths relative to the selected project'}
    original = {'edge_rule': {**gate.SCORED_RULE, 'test_scope': scope}}
    recorded = gate._edge_rule(original)
    assert recorded['test_scope'] == scope
    original['edge_rule']['test_scope']['anchor'] = 'changed'
    assert recorded['test_scope']['anchor'] == '.'
