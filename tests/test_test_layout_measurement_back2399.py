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


def test_external_policy_input_is_bounded_and_independent(tmp_path):
    policy = tmp_path / 'policy.yaml'
    policy.write_text('test_layout:\n  additional_paths: [t/./unit, "t\\\\unit", missing.py]\n', encoding='utf-8')
    selected = gate._read_test_policy(policy)
    assert selected['additional_paths'] == ['missing.py', 't/unit']
    assert selected['path'] == policy.resolve().as_posix()
    assert len(selected['file_sha256']) == len(selected['input_digest']) == 64
    assert 'raw' not in selected


@pytest.mark.parametrize('contents', [
    'test_layout: {additional_paths: []}\nignore: [pkg]\n',
    'test_layout: {additional_paths: [../escape]}\n',
    'test_layout: {additional_paths: [/absolute]}\n',
    'test_layout: {additional_paths: ["C:/drive"]}\n',
    'test_layout: {additional_paths: [true]}\n',
    'test_layout: {additional_paths: [], other: true}\n',
    'test_layout: {}\n',
])
def test_external_policy_rejects_unrecorded_or_unsafe_inputs(tmp_path, contents):
    policy = tmp_path / 'policy.yaml'
    policy.write_text(contents, encoding='utf-8')
    with pytest.raises(ValueError, match='policy'):
        gate._read_test_policy(policy)


@pytest.mark.parametrize('ambient', [None, 'prior.yaml'])
def test_explicit_policy_context_restores_environment_and_caches(tmp_path, monkeypatch, ambient):
    import os

    if ambient is None:
        monkeypatch.delenv('REVEAL_CONFIG', raising=False)
    else:
        monkeypatch.setenv('REVEAL_CONFIG', ambient)
    resets = []
    monkeypatch.setattr(gate, 'reset_request_caches', lambda: resets.append(True))
    policy = tmp_path / 'policy.yaml'
    with pytest.raises(RuntimeError, match='injected'):
        with gate._test_policy_config(policy):
            assert os.environ['REVEAL_CONFIG'] == policy.as_posix()
            raise RuntimeError('injected')
    assert os.environ.get('REVEAL_CONFIG') == ambient
    assert resets == [True, True]
