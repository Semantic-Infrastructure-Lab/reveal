"""T006 must disclose actual lost EVIDENCE input and recover across host requests."""
import importlib
import json
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.rules import scan_caches
from reveal.utils import request_cache
from reveal.utils.path_utils import EVIDENCE

rule = importlib.import_module('reveal.rules.types.T006')
pytestmark = pytest.mark.component
KEYS = ('alpha', 'beta', 'gamma', 'delta')
OTHER = ('echo', 'foxtrot', 'golf', 'hotel')


def _definition(name, keys):
    return f'class {name}(TypedDict):\n' + ''.join(f'    {key}: str\n' for key in keys)


def _consumer(name, keys):
    return f'def {name}(cfg: dict):\n    return ' + ', '.join(f'cfg["{key}"]' for key in keys) + '\n'


def _project(root, survivor=True, local=False, children=1):
    root.mkdir(parents=True)
    (root / 'pyproject.toml').write_text('[project]\nname="evidence-test"\n', encoding='utf-8')
    hidden = []
    for number in range(children):
        directory = root / f'a_hidden_{number}'
        directory.mkdir()
        (directory / 'types_.py').write_text(
            'from typing import TypedDict\n' + _definition(f'Hidden{number}', KEYS), encoding='utf-8')
        hidden.append(directory.resolve())
    content = _consumer('hidden_use', KEYS)
    if survivor:
        (root / 'types_.py').write_text(
            'from typing import TypedDict\n' + _definition('Visible', OTHER), encoding='utf-8')
        content += _consumer('visible_use', OTHER)
    if local:
        content = 'from typing import TypedDict\n' + _definition('Local', KEYS) + content
    checked = root / 'consumer.py'
    checked.write_text(content, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000  # request-cache stamps skip files newer than the request; Windows' clock is coarse
    for source in root.rglob('*.py'):
        os.utime(source, ns=(aged, aged))
    return checked, hidden


def _why_untrusted(root, started_ns):
    """Why request_cache._tree_stamp refused *root*: walk errors, or files newer than the request."""
    from reveal.utils.path_utils import _walk_code_files
    errors = []
    newer = []
    try:
        for path in _walk_code_files(Path(root), purpose=EVIDENCE, on_error=errors.append):
            if started_ns is not None and os.stat(path).st_mtime_ns >= started_ns:
                newer.append(str(path))
    except OSError as exc:
        errors.append(exc)
    return {'root': str(root), 'started_ns': started_ns, 'walk_errors': [repr(e) for e in errors], 'newer': newer}


@pytest.fixture
def fault(monkeypatch):
    state = {'active': False, 'denied': set(), 'unknown': False, 'events': [],
             'builds': [], 'reached': [], 'parsed': [], 'stamps': [], 'untrusted': []}
    real_build, real_iter = rule._build_index, rule.iter_python_files
    real_parse, real_scandir = rule.parse_python, os.scandir
    real_stamp = request_cache._tree_stamp

    def build(root):
        state['builds'].append(Path(root))
        state['active'] = True
        try:
            return real_build(root)
        finally:
            state['active'] = False

    def files(*args, **kwargs):
        assert kwargs.get('purpose') == EVIDENCE
        for file in real_iter(*args, **kwargs):
            state['reached'].append(Path(file))
            yield file

    def parse(*args, **kwargs):
        result = real_parse(*args, **kwargs)
        if state['active']:
            state['parsed'].append(str(args[1]))
        return result

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('actual unlocated T006 EVIDENCE directory loss')
            raise PermissionError(13, 'actual T006 EVIDENCE directory loss', str(path))
        return real_scandir(path)

    def stamp(root, *args, **kwargs):
        result = real_stamp(root, *args, **kwargs)
        state['stamps'].append((Path(root), bool(args or kwargs), result, state['active']))
        if result is None:  # BACK-2057: say why a census was refused, so a CI flake names its cause
            state['untrusted'].append(_why_untrusted(root, args[0] if args else kwargs.get('started_ns')))
        return result

    monkeypatch.setattr(rule, '_build_index', build)
    monkeypatch.setattr(rule, 'iter_python_files', files)
    monkeypatch.setattr(rule, 'parse_python', parse)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(request_cache, '_tree_stamp', stamp)
    return state


def _notes(checked):
    return rule.get_scan_disclosures([checked])


def _directory_note(notes):
    selected = [note for note in notes if 'identified directory enumeration(s) failed' in note]
    assert len(selected) == 1, notes
    assert selected[0].startswith('T006:')
    assert 'missing file population is unknown' in selected[0]
    assert 'incomplete' in selected[0].lower()
    return selected[0]


@pytest.mark.parametrize('population', ['partial', 'all_lost', 'root', 'unknown'])
def test_native_matches_lost_only_in_evidence_walk_are_not_clean(tmp_path, fault, population):
    survivor = population in ('partial', 'root')
    checked, hidden = _project(tmp_path / 'project', survivor)
    healthy, _ = _project(tmp_path / 'sibling', survivor)
    baseline = run('check', healthy, '--select', 'T006', '--format', 'json')
    assert json.loads(baseline.stdout)['total'] == (2 if survivor else 1)
    fault.update(denied={checked.parent.resolve()} if population == 'root' else set(hidden),
                 unknown=population == 'unknown', events=[], reached=[], parsed=[])
    response = run('check', checked, '--select', 'T006', '--format', 'json')
    data = json.loads(response.stdout)
    assert fault['events'] and data['total'] == (1 if population == 'partial' else 0)
    assert checked.resolve() in fault['reached'] or population == 'root'
    assert len(data['detections']) == data['total']
    assert response.returncode == 3, data
    note = _directory_note(data['scan_disclosures'])
    if population == 'unknown':
        assert '0 identified' in note and '1 enumeration error event(s)' in note
    if population == 'partial':
        assert any('Visible' in detection['message'] for detection in data['detections'])
        assert fault['parsed'] == [str(checked.parent / 'types_.py')]


@pytest.mark.parametrize('recursive', [False, True])
def test_text_and_recursive_check_qualify_zero_evidence_result(tmp_path, fault, recursive):
    checked, hidden = _project(tmp_path / 'project', False)
    fault['denied'] = set(hidden)
    response = run('check', checked.parent if recursive else checked, '--select', 'T006')
    assert fault['events'] == hidden
    assert response.returncode == 3
    output = response.stdout + response.stderr
    assert 'scan incomplete' in output.lower() and '✅ No issues found' not in output
    assert output.count('identified directory enumeration(s) failed') == 1


@pytest.mark.parametrize('unknown', [False, True])
def test_multiple_events_keep_unknown_population_and_formatter_display_cap(tmp_path, fault, unknown):
    checked, hidden = _project(tmp_path / 'project', children=7)
    fault.update(denied=set(hidden), unknown=unknown)
    detections = rule.T006().check(str(checked), None, checked.read_text(encoding='utf-8'))
    assert len(detections) == 1 and len(fault['events']) == 7
    note = _directory_note(_notes(checked))
    if unknown:
        assert '0 identified' in note and '7 enumeration error event(s)' in note
    else:
        assert '7 identified' in note and 'and 2 more' in note
        assert 'a_hidden_6' not in note


def test_actual_loss_before_later_ceiling_retains_both_diagnostics(tmp_path, fault, monkeypatch):
    checked, hidden = _project(tmp_path / 'project', False)
    tail = checked.parent / 'z_tail'
    tail.mkdir()
    (tail / 'extra.py').write_text('VALUE = 1\n', encoding='utf-8')
    monkeypatch.setenv('REVEAL_T006_MAX_FILES', '1')
    empty_before = pickle.dumps(rule._EMPTY_FACTS)
    fault['denied'] = set(hidden)
    response = run('check', checked, '--select', 'T006', '--format', 'json')
    data = json.loads(response.stdout)
    assert fault['events'] == hidden and response.returncode == 3 and data['total'] == 0
    assert any('REVEAL_T006_MAX_FILES' in note for note in data['scan_disclosures'])
    assert pickle.dumps(rule._EMPTY_FACTS) == empty_before
    _directory_note(data['scan_disclosures'])


def test_local_match_and_invocation_partial_memo_survive_loss(tmp_path, fault):
    checked, _ = _project(tmp_path / 'project', local=True)
    fault['denied'] = {checked.parent.resolve()}
    content = checked.read_text(encoding='utf-8')
    first = rule.T006().check(str(checked), None, content)
    cached = rule._project_index[checked.parent]
    second = rule.T006().check(str(checked), None, content)
    assert len(first) == len(second) == 1 and 'Local' in first[0].message
    assert rule._project_index[checked.parent] is cached
    assert fault['builds'] == [checked.parent] and len(fault['events']) == 1
    _directory_note(_notes(checked))


def test_evidence_ignores_report_exclusion_and_disclosures_scope_to_reached_root(tmp_path, fault):
    checked, hidden = _project(tmp_path / 'project', False)
    sibling, _ = _project(tmp_path / 'sibling', False)
    clean = run('check', sibling, '--select', 'T006', '--exclude', 'a_hidden_0', '--format', 'json')
    assert json.loads(clean.stdout)['total'] == 1
    fault['denied'] = set(hidden)
    response = run('check', checked, '--select', 'T006', '--exclude', 'a_hidden_0', '--format', 'json')
    assert fault['events'] == hidden and json.loads(response.stdout)['total'] == 0
    _directory_note(scan_caches.get_scan_disclosures([checked], ['T006'], None))
    assert not scan_caches.get_scan_disclosures([sibling], ['T006'], None)
    assert not scan_caches.get_scan_disclosures([checked], ['T005'], None)
    assert not scan_caches.get_scan_disclosures([checked], None, ['T006'])


def test_parent_preload_disclosure_and_real_child_initializer_transfer(tmp_path, fault):
    checked, hidden = _project(tmp_path / 'project')
    fault['denied'] = set(hidden)
    cached = scan_caches._t006_preload(checked.parent, ['T006'], None, [checked])
    assert fault['events'] == hidden and checked.parent in cached
    notes = scan_caches.get_scan_disclosures([checked], ['T006'], None)
    _directory_note(notes)
    script = '''import json,pickle,sys
from pathlib import Path
import reveal
assert Path(reveal.__file__).resolve().is_relative_to(Path(sys.argv[2]))
from reveal.rules.scan_caches import _t006_init_worker, get_scan_disclosures
_t006_init_worker(pickle.loads(sys.stdin.buffer.read()))
print(json.dumps(get_scan_disclosures([Path(sys.argv[1])],['T006'],None)))
'''
    checkout = Path(__file__).resolve().parents[1]
    child = subprocess.run([sys.executable, '-c', script, str(checked), str(checkout)],
                           input=pickle.dumps(cached), capture_output=True, timeout=30,
                           env=dict(os.environ, PYTHONPATH=str(checkout), REVEAL_DISK_CACHE='0'))
    assert child.returncode == 0, child.stderr.decode()
    assert json.loads(child.stdout) == notes


@pytest.mark.parametrize('survivor,unknown', [(False, False), (True, False), (False, True)])
def test_normal_request_rebuilds_partial_evidence_and_recovers_without_clears(tmp_path, fault, survivor, unknown):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    checked, hidden = _project(tmp_path / 'project', survivor)
    fault.update(denied=set(hidden), unknown=unknown)
    first = reveal_check(str(checked), select='T006')
    assert type(first) is str and len(fault['events']) == 1
    cached = rule._project_index[checked.parent]
    # The real sealing census is healthy even though the earlier index build was denied.
    assert any(root == checked.parent and sealing and stamp and not active
               for root, sealing, stamp, active in fault['stamps']), fault['untrusted']
    second = reveal_check(str(checked), select='T006')
    assert len(fault['events']) == 2, 'A recovered sealing walk must not bless incomplete evidence'
    assert rule._project_index[checked.parent] is not cached
    assert 'incomplete' in first.lower() and first == second
    fault['denied'] = set()
    repaired = reveal_check(str(checked), select='T006')
    assert len(fault['builds']) == 3 and 'incomplete' not in repaired.lower()
    assert f'{2 if survivor else 1} issue' in repaired
    healthy_cache = rule._project_index[checked.parent]
    assert reveal_check(str(checked), select='T006') == repaired
    assert rule._project_index[checked.parent] is healthy_cache and len(fault['builds']) == 3
    sibling, _ = _project(tmp_path / 'sibling', survivor)
    sibling_result = reveal_check(str(sibling), select='T006')
    assert f'{2 if survivor else 1} issue' in sibling_result and 'incomplete' not in sibling_result.lower()


def test_clean_unchanged_request_reuses_healthy_index_and_exact_output(tmp_path, fault):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    checked, _ = _project(tmp_path / 'project')
    first = reveal_check(str(checked), select='T006')
    cached = rule._project_index[checked.parent]
    assert '2 issues found.' in first and not _notes(checked)
    assert reveal_check(str(checked), select='T006') == first
    assert rule._project_index[checked.parent] is cached and len(fault['builds']) == 1


def test_hard_noise_not_attempted_and_clean_default_facts_unchanged(tmp_path, fault):
    checked, hidden = _project(tmp_path / 'project', False)
    noise = checked.parent / '.venv'
    hidden[0].rename(noise)
    fault['denied'] = {noise.resolve()}
    response = run('check', checked, '--select', 'T006', '--format', 'json')
    data = json.loads(response.stdout)
    assert response.returncode == 0 and data['total'] == 0 and not data['scan_disclosures']
    assert not fault['events'] and not _notes(checked)


def test_cap_only_existing_incomplete_contract_and_empty_singleton_not_contaminated(tmp_path, fault, monkeypatch):
    checked, _ = _project(tmp_path / 'project')
    before = pickle.dumps(rule._EMPTY_FACTS)
    monkeypatch.setenv('REVEAL_T006_MAX_FILES', '1')
    response = run('check', checked, '--select', 'T006', '--format', 'json')
    data = json.loads(response.stdout)
    assert response.returncode == 3 and len(data['scan_disclosures']) == 1
    assert 'REVEAL_T006_MAX_FILES' in data['scan_disclosures'][0]
    assert not fault['events'] and pickle.dumps(rule._EMPTY_FACTS) == before


def test_cap_only_request_retains_existing_validated_cache_policy(tmp_path, fault, monkeypatch):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    checked, _ = _project(tmp_path / 'project')
    monkeypatch.setenv('REVEAL_T006_MAX_FILES', '1')
    first = reveal_check(str(checked), select='T006')
    cached = rule._project_index[checked.parent]
    assert 'REVEAL_T006_MAX_FILES' in first and 'incomplete' in first.lower()
    assert reveal_check(str(checked), select='T006') == first
    assert rule._project_index[checked.parent] is cached and len(fault['builds']) == 1, fault['untrusted']
    assert not fault['events']
