"""T006 evidence losses survive consumer joins and never become healthy retained indexes."""
import importlib
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.rules import scan_caches
from reveal.utils import request_cache

rule = importlib.import_module('reveal.rules.types.T006')
pytestmark = pytest.mark.component
KEYS = ['alpha', 'beta', 'gamma', 'delta']


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _project(root):
    _write(root / 'pyproject.toml', '[project]\nname="independent-evidence"\n')
    _write(root / 'consumer.py', 'def consume(cfg: dict):\n    return '+','.join(f'cfg["{key}"]' for key in KEYS)+'\n')
    hidden = root / 'a_hidden'
    _write(hidden / 'types_.py', 'from typing import TypedDict\nclass Hidden(TypedDict):\n'+''.join(f'    {key}: str\n' for key in KEYS))
    return root / 'consumer.py', hidden.resolve()


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False, 'events': [], 'builds': [], 'stamps': []}
    real_build, real_scandir, real_stamp = rule._build_index, os.scandir, request_cache._tree_stamp

    def build(root):
        state['builds'].append(root)
        state['active'] = True
        try:
            return real_build(root)
        finally:
            state['active'] = False

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('independent unlocated T006 evidence loss')
            raise PermissionError(13, 'independent T006 evidence loss', str(path))
        return real_scandir(path)

    def stamp(root, *args, **kwargs):
        value = real_stamp(root, *args, **kwargs)
        state['stamps'].append((root, value, state['active']))
        return value

    monkeypatch.setattr(rule, '_build_index', build)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(request_cache, '_tree_stamp', stamp)
    return state


def _disclosures(file):
    return scan_caches.get_scan_disclosures([file], ['T006'], None)


@pytest.mark.parametrize('unknown', [False, True])
def test_actual_loss_before_ceiling_preserves_both_reasons_without_contaminating_cap_only_root(tmp_path, monkeypatch, fault, unknown):
    checked, hidden = _project(tmp_path / 'lost')
    _write(checked.parent / 'z_tail' / 'first.py', 'VALUE=1\n')
    _write(checked.parent / 'z_tail' / 'second.py', 'VALUE=2\n')
    other, _ = _project(tmp_path / 'cap_only')
    monkeypatch.setenv('REVEAL_T006_MAX_FILES', '1')
    fault.update(denied={hidden}, unknown=unknown)
    facts = rule._project_facts(str(checked))
    assert not facts['typeddicts'] and fault['events'] == [hidden]
    reasons = _disclosures(checked)
    assert len(reasons) == 2, reasons
    assert sum('exceeds 1 .py files' in message for message in reasons) == 1
    loss = next(message for message in reasons if 'PermissionError' in message)
    assert 'T006:' in loss and 'missing file population is unknown' in loss
    if unknown:
        assert '1 enumeration error event(s)' in loss
    assert rule._project_facts(str(checked)) is facts and fault['builds'].count(checked.parent) == 1
    other_facts = rule._project_facts(str(other))
    assert not other_facts['typeddicts']
    assert len(_disclosures(other)) == 1 and 'PermissionError' not in _disclosures(other)[0]


def test_ceiling_before_unvisited_subtree_does_not_invent_directory_loss(tmp_path, monkeypatch, fault):
    checked, hidden = _project(tmp_path)
    _write(tmp_path / 'extra.py', 'VALUE=1\n')
    monkeypatch.setenv('REVEAL_T006_MAX_FILES', '1')
    fault['denied'] = {hidden}
    facts = rule._project_facts(str(checked))
    assert not fault['events'] and not facts['typeddicts']
    reasons = _disclosures(checked)
    assert len(reasons) == 1 and 'exceeds 1 .py files' in reasons[0]


def test_parent_preload_facts_survive_pickled_fresh_worker_and_reached_root_filters(tmp_path, fault):
    lost, hidden = _project(tmp_path / 'lost')
    healthy, _ = _project(tmp_path / 'healthy')
    untouched, _ = _project(tmp_path / 'unreached')
    fault['denied'] = {hidden}
    caches = scan_caches.preload_scan_caches([healthy, lost], tmp_path, ['T006'], None)
    assert set(fault['builds']) == {healthy.parent, lost.parent}
    assert untouched.parent not in caches['T006']
    assert not _disclosures(healthy) and not _disclosures(untouched)
    assert scan_caches.get_scan_disclosures([lost], ['C901'], None) == []
    assert scan_caches.get_scan_disclosures([lost], ['T006'], ['T006']) == []
    # A genuinely fresh interpreter receives the existing pool-initializer payload.
    payload = tmp_path / 'worker.pickle'
    payload.write_bytes(pickle.dumps(caches))
    script = '''import importlib,json,pickle,sys
from pathlib import Path
from reveal.rules.scan_caches import init_scan_caches,get_scan_disclosures
rule=importlib.import_module('reveal.rules.types.T006')
init_scan_caches(pickle.loads(Path(sys.argv[1]).read_bytes()))
def forbidden(root):raise AssertionError('preloaded index unexpectedly rebuilt')
rule._build_index=forbidden
file=Path(sys.argv[2])
found=rule.T006().check(str(file),None,file.read_text(encoding='utf-8'))
print(json.dumps({'findings':len(found),'disclosures':get_scan_disclosures([file],['T006'],None)}))
'''
    result = subprocess.run([sys.executable, '-c', script, str(payload), str(lost)],
                            capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    answer = json.loads(result.stdout)
    assert answer['findings'] == 0
    assert len(answer['disclosures']) == 1, answer
    assert 'PermissionError' in answer['disclosures'][0]
    assert len(_disclosures(lost)) == 1


@pytest.mark.parametrize('unknown', [False, True])
def test_normal_host_boundary_rebuilds_lost_evidence_despite_healthy_seal_and_retains_clean_root(tmp_path, fault, unknown):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    checked, hidden = _project(tmp_path / 'lost')
    sibling, _ = _project(tmp_path / 'sibling')
    fault.update(denied={hidden}, unknown=unknown)
    lost = reveal_check(str(checked), select='T006')
    assert type(lost) is str and fault['events'] == [hidden]
    first = rule._project_index[checked.parent]
    assert request_cache._STAMPS.get((rule.__name__, checked.parent))
    assert all(value and not active for _, value, active in fault['stamps'])
    # Keep the same actual source fault: the second ordinary request must rebuild.
    persistent = reveal_check(str(checked), select='T006')
    assert persistent == lost
    assert fault['builds'].count(checked.parent) == 2, fault
    assert rule._project_index[checked.parent] is not first
    assert len(fault['events']) == 2 and 'scan incomplete' in lost.lower()
    assert 'PermissionError' in lost and 'No issues found.' not in lost
    fault['denied'] = set()
    repaired = reveal_check(str(checked), select='T006')
    assert "TypedDict 'Hidden'" in repaired and 'scan incomplete' not in repaired.lower()
    assert fault['builds'].count(checked.parent) == 3
    healthy = rule._project_index[checked.parent]
    assert reveal_check(str(checked), select='T006') == repaired
    assert rule._project_index[checked.parent] is healthy and fault['builds'].count(checked.parent) == 3
    sibling_clean = reveal_check(str(sibling), select='T006')
    sibling_index = rule._project_index[sibling.parent]
    assert reveal_check(str(sibling), select='T006') == sibling_clean
    assert rule._project_index[sibling.parent] is sibling_index


@pytest.mark.parametrize('exit_zero', [False, True])
def test_single_file_cut_zero_json_and_artifact_keep_evidence_loss_status(tmp_path, fault, exit_zero):
    checked, hidden = _project(tmp_path)
    fault['denied'] = {hidden}
    args = ['check', str(checked), '--select', 'T006', '--max-items', '0']
    if exit_zero:
        args.append('--exit-zero')
    response = run(*args, '--format', 'json')
    assert fault['events'] == [hidden]
    assert response.returncode == (0 if exit_zero else 3), response.stdout
    result = json.loads(response.stdout)
    assert result['scan_disclosures'] and 'PermissionError' in result['scan_disclosures'][0]
    artifact = tmp_path / 'answer.json'
    text = run(*args, '--also-json', str(artifact))
    assert text.returncode == (0 if exit_zero else 3) and artifact.exists()
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert saved['scan_disclosures'] == result['scan_disclosures']
    assert 'No issues found' not in text.stdout and 'incomplete' in text.stdout.lower()


def test_preload_selection_controls_do_not_build_or_disclose_unrun_t006(tmp_path, fault):
    checked, hidden = _project(tmp_path)
    fault['denied'] = {hidden}
    for select, ignore in [(['C901'], None), (['T006'], ['T006'])]:
        caches = scan_caches.preload_scan_caches([checked], tmp_path, select, ignore)
        assert caches['T006'] == {}
        assert scan_caches.get_scan_disclosures([checked], select, ignore) == []
    assert not fault['builds'] and not fault['events']


@pytest.mark.parametrize('capped', [False, True])
def test_healthy_or_cap_only_indexes_retain_existing_cross_request_lifetime(tmp_path, monkeypatch, fault, capped):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    checked, _ = _project(tmp_path)
    if capped:
        monkeypatch.setenv('REVEAL_T006_MAX_FILES', '1')
    first = reveal_check(str(checked), select='T006')
    index = rule._project_index[tmp_path]
    assert request_cache._STAMPS.get((rule.__name__, tmp_path))
    assert reveal_check(str(checked), select='T006') == first
    assert rule._project_index[tmp_path] is index and fault['builds'] == [tmp_path]
    assert not fault['events']
    if capped:
        assert 'exceeds 1 .py files' in first
    else:
        assert "TypedDict 'Hidden'" in first
