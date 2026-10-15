"""Precision pilot controls: deterministic coverage and rejected fabricated evidence."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
import pytest

pytestmark = pytest.mark.component
SCRIPTS = Path(__file__).resolve().parent.parent / 'scripts'


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load('recall_oracles'); load('recall_gate'); load('fetch_corpus')
pilot = load('rule_precision')


def test_stratified_selection_is_order_independent_and_rejects_zero_coverage():
    claims = [{'id': str(i), 'rule_code': 'X', 'stratum': str(i % 2)} for i in range(10)]
    selected = pilot.stratified_sample(claims, ['X'], 4)
    assert selected == pilot.stratified_sample(list(reversed(claims)), ['X'], 4)
    assert {c['stratum'] for c in selected} == {'0', '1'}
    assert all(c['stratum_population'] == 5 and c['stratum_sample'] == 2 for c in selected)
    with pytest.raises(ValueError, match='no claims'):
        pilot.stratified_sample(claims, ['MISSING'], 4)
    with pytest.raises(ValueError, match='omits a stratum'):
        pilot.stratified_sample(claims, ['X'], 1)


def test_population_rejects_truncation_and_missing_claim_sources(tmp_path):
    with pytest.raises(ValueError, match='truncated'):
        pilot.claims_from_report({'summary': {'items_truncated': True}}, tmp_path, 'pin', ['X'])
    with pytest.raises(ValueError, match='missing'):
        pilot.claims_from_report({'files': [{'file': 'missing.py'}]}, tmp_path, 'pin', ['X'])


def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, 'source_identity', lambda *args: None)
    path = tmp_path / 'demo.py'; path.write_text('value = 1\n', encoding='utf-8')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    claims = [{'id': name, 'file': 'demo.py', 'rule_code': 'X', 'source_sha256': digest,
               'stratum_population': population, 'stratum_sample': 1}
              for name, population in [('a', 2), ('b', 8)]]
    sample = {'source': {'sha': 'pin'}, 'implementation': {}, 'rules': ['X'], 'claims': claims}
    labels = {'labels': [{'id': 'a', 'verdict': 'tp', 'reason': 'source supports the claim'},
                         {'id': 'b', 'verdict': 'uncertain', 'reason': 'binding cannot be established'}]}
    return sample, labels


def test_uncertainty_is_preserved_in_weighted_bounds(tmp_path, monkeypatch):
    sample, labels = evidence(tmp_path, monkeypatch)
    result = pilot.score(sample, labels, tmp_path)['rules']['X']
    assert result['weighted_precision_bounds'] == [0.2, 1.0]
    assert result['sample_counts'] == {'tp': 1, 'uncertain': 1}
    assert result['estimated_population'] == 10


def test_missing_labels_and_deliberately_dropped_claim_fail(tmp_path, monkeypatch):
    sample, labels = evidence(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='exactly once'):
        pilot.score(sample, {'labels': labels['labels'][:1]}, tmp_path)
    sample['claims'].pop()
    with pytest.raises(ValueError, match='exactly once'):
        pilot.score(sample, labels, tmp_path)


def test_changed_source_and_unsupported_verdict_fail(tmp_path, monkeypatch):
    sample, labels = evidence(tmp_path, monkeypatch)
    bad = copy.deepcopy(labels); bad['labels'][0]['verdict'] = 'automatic-pass'
    with pytest.raises(ValueError, match='verdict'):
        pilot.score(sample, bad, tmp_path)
    (tmp_path / 'demo.py').write_text('different = 2\n', encoding='utf-8')
    with pytest.raises(ValueError, match='source changed'):
        pilot.score(sample, labels, tmp_path)


def test_real_manifest_pin_is_required(tmp_path):
    import subprocess
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, timeout=30)
    with pytest.raises(subprocess.CalledProcessError):
        pilot.source_identity(tmp_path, 'missing')
