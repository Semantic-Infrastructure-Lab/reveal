"""M102 importer-discovery losses through existing native and host answers."""
import importlib
import json
import os
import time
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run, needs_forked_workers
from reveal.rules import scan_caches
from reveal.utils import request_cache

m102 = importlib.import_module('reveal.rules.maintainability.M102')
pytestmark = pytest.mark.component


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(aged, aged))
    return path


def _project(root, nonempty=False):
    _write(root / 'pyproject.toml', '[project]\nname="m102-loss"\nversion="0.0.0"\n')
    checked = _write(root / 'worker.py', 'def execute():\n    return 1\n')
    _write(root / 'main.py', 'import os\n' if nonempty else 'VALUE=1\n')
    hidden = _write(root / 'included' / 'main.py', 'import worker\n').parent
    return root, checked, hidden


@pytest.fixture
def observed(monkeypatch, tmp_path):
    state = {'active': False, 'denied': set(), 'unknown': False, 'transient': False,
             'builds': [], 'extracts': [], 'events': [], 'stamps': []}
    check_log = tmp_path / 'actual-checks.jsonl'
    state['check_log'] = check_log
    real_collect, real_scan = m102.M102._collect_all_imports, os.scandir
    real_extract, real_stamp, real_check = m102._extract_imports_regex, request_cache._tree_stamp, m102.M102.check
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')

    def collect(self, root):
        missed = root not in m102._import_cache
        state['active'] = True
        try:
            result = real_collect(self, root)
            if missed:
                state['builds'].append((root, result))
            return result
        finally:
            state['active'] = False
            if state['transient']:
                state['denied'] = set()  # Loss ends before the ordinary healthy seal.

    def scandir(path):
        if state['active'] and Path(path).resolve() in state['denied']:
            state['events'].append(Path(path).resolve())
            if state['unknown']:
                raise PermissionError('actual unlocated M102 importer discovery failure')
            raise PermissionError(13, 'actual M102 importer discovery failure', str(path))
        return real_scan(path)

    def extract(*args, **kwargs):
        result = real_extract(*args, **kwargs)
        if state['active']:
            state['extracts'].append(Path(args[2]))
        return result

    def stamp(root, *args, **kwargs):
        assert not state['active']
        result = real_stamp(root, *args, **kwargs)
        state['stamps'].append(result)
        return result

    def checked(self, path, *args, **kwargs):
        with check_log.open('a', encoding='utf-8') as output:
            output.write(json.dumps({'pid': os.getpid(), 'path': str(path)}) + '\n')
        return real_check(self, path, *args, **kwargs)

    monkeypatch.setattr(m102.M102, '_collect_all_imports', collect)
    monkeypatch.setattr(os, 'scandir', scandir)
    monkeypatch.setattr(m102, '_extract_imports_regex', extract)
    monkeypatch.setattr(request_cache, '_tree_stamp', stamp)
    monkeypatch.setattr(m102.M102, 'check', checked)
    return state


def _check(root, *flags):
    return run('check', str(root), '--select', 'M102', *flags)


def _note(notes, root):
    matching = [note for note in notes if 'M102' in note and 'directory enumeration' in note]
    assert len(matching) == 1, notes
    note = matching[0]
    assert root.as_posix() in note and 'missing file population is unknown' in note
    assert 'false positive' in note.lower().replace('-', ' '), note
    return note


@pytest.mark.parametrize('loss', ['child-empty', 'child-nonempty', 'named-root', 'unknown-root'])
def test_actual_source_only_loss_discloses_false_orphan_risk_with_healthy_outer_files(tmp_path, observed, loss):
    root, checked, hidden = _project(tmp_path / 'project', nonempty=loss == 'child-nonempty')
    denied = root if loss.endswith('root') else hidden
    observed.update(denied={denied}, unknown=loss == 'unknown-root')
    response = _check(root, '--format', 'json')
    data = json.loads(response.stdout)
    assert observed['events'] == [denied] and len(observed['builds']) == 1
    assert len(observed['extracts']) == (0 if denied == root else 2)
    assert m102._import_cache[root] == ({'os'} if loss == 'child-nonempty' else set())
    assert data['summary']['files_checked'] == 4 and data['summary']['files_errored'] == data['summary']['files_degraded'] == 0
    assert data['summary']['total_issues'] == 1  # Preserve the existing heuristic with uncertainty.
    assert data['files'][0]['detections'][0]['rule_code'] == 'M102'
    assert response.returncode == 3, (response.stdout, response.stderr)
    note = _note(data['summary']['scan_disclosures'], root)
    assert ('0 identified directory' if loss == 'unknown-root' else '1 identified directory') in note
    assert not any('lower bound' in note.lower() for note in data['summary']['scan_disclosures'])


@pytest.mark.parametrize('unknown', [False, True])
def test_seven_actual_directory_events_survive_one_shared_inventory_without_replay_inflation(tmp_path, observed, unknown):
    root, _, hidden = _project(tmp_path / 'project')
    denied = {hidden, *[_write(root / f'blocked{n}' / 'main.py', 'import worker\n').parent for n in range(6)]}
    observed.update(denied=denied, unknown=unknown)
    response = _check(root, '--format', 'json')
    data = json.loads(response.stdout)
    assert len(observed['events']) == 7 and set(observed['events']) == denied
    assert len(observed['builds']) == 1 and data['summary']['files_checked'] == 10
    assert data['summary']['files_errored'] == data['summary']['files_degraded'] == 0
    note = _note(data['summary']['scan_disclosures'], root)
    assert ('0 identified directory' if unknown else '7 identified directory') in note
    assert ('7 enumeration error event(s)' if unknown else 'and 2 more') in note
    assert response.returncode == 3


@pytest.mark.parametrize('view', ['text-artifact', 'grep-artifact', 'cap0', 'severity', 'exit-zero'])
def test_uncertain_importer_inventory_is_not_hidden_by_existing_output_views(tmp_path, observed, view):
    root, _, hidden = _project(tmp_path / 'project')
    observed['denied'] = {hidden}
    artifact = tmp_path / 'answer.json'
    flags = {'text-artifact': ['--also-json', str(artifact)],
             'grep-artifact': ['--format', 'grep', '--also-json', str(artifact)],
             'cap0': ['--format', 'json', '--max-items', '0'],
             'severity': ['--format', 'json', '--severity', 'critical'],
             'exit-zero': ['--format', 'json', '--exit-zero']}[view]
    response = _check(root, *flags)
    data = json.loads(artifact.read_text(encoding='utf-8') if 'artifact' in view else response.stdout)
    assert observed['events'] == [hidden] and len(observed['builds']) == 1
    assert data['summary']['total_issues'] == (0 if view == 'severity' else 1)
    _note(data['summary']['scan_disclosures'], root)
    assert response.returncode == (0 if view == 'exit-zero' else 3)
    if view == 'cap0':
        assert all(not row['detections'] for row in data['files'])
    if view == 'grep-artifact':
        assert response.stdout.count(':M102:') == 1
        assert 'directory enumeration' in response.stderr and 'directory enumeration' not in response.stdout


@pytest.mark.parametrize('unknown_root', [False, True])
def test_transient_loss_before_healthy_seal_rebuilds_and_repairs_without_clears(tmp_path, observed, unknown_root):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    root, checked, hidden = _project(tmp_path / 'primary')
    sibling, sibling_file, _ = _project(tmp_path / 'sibling')
    baseline = reveal_check(str(checked), select='M102')
    other = reveal_check(str(sibling_file), select='M102')
    sibling_value = m102._import_cache[sibling]
    _write(root / 'added.py', 'VALUE=1\n')
    count = len(observed['builds'])
    observed.update(denied={root} if unknown_root else {hidden}, unknown=unknown_root, transient=True)
    lost = reveal_check(str(checked), select='M102')
    partial = m102._import_cache[root]
    assert len(observed['builds']) == count + 1 and observed['denied'] == set()
    assert observed['stamps'] and all(stamp is not None for stamp in observed['stamps'])
    repaired = reveal_check(str(checked), select='M102')
    assert len(observed['builds']) == count + 2, 'Healthy sealing must not validate lost importer evidence'
    assert m102._import_cache[root] is not partial and repaired == baseline
    _note(lost.splitlines(), root)
    assert type(lost) is str and 'No findings in the checked population; scan incomplete.' not in lost
    warm = m102._import_cache[root]
    assert reveal_check(str(checked), select='M102') == baseline
    assert len(observed['builds']) == count + 2 and m102._import_cache[root] is warm
    assert reveal_check(str(sibling_file), select='M102') == other and m102._import_cache[sibling] is sibling_value


@needs_forked_workers
def test_disabled_config_pool_may_preload_but_must_not_disclose_unused_m102_evidence(tmp_path, observed, monkeypatch):
    root, _, hidden = _project(tmp_path / 'disabled')
    _write(root / '.reveal.yaml', 'root: true\nrules:\n  disable: [M102]\n')
    for index in range(4):
        _write(root / f'other{index}.py', 'VALUE=1\n')
    observed['denied'] = {hidden}
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '2')
    response = run('check', str(root), '--format', 'json')
    data = json.loads(response.stdout)
    assert len(observed['builds']) == 1 and observed['events'] == [hidden]
    assert not observed['check_log'].exists(), 'No actual M102.check runs when disabled without select override'
    assert not any('M102' in note for note in data['summary']['scan_disclosures'])


def test_explicit_selection_overrides_disabled_config_and_keeps_importer_risk(tmp_path, observed):
    root, _, hidden = _project(tmp_path / 'selected')
    _write(root / '.reveal.yaml', 'root: true\nrules:\n  disable: [M102]\n')
    observed['denied'] = {hidden}
    response = _check(root, '--format', 'json')
    data = json.loads(response.stdout)
    assert observed['check_log'].exists() and observed['events'] == [hidden]
    assert data['summary']['total_issues'] == 1
    _note(data['summary']['scan_disclosures'], root)
    assert response.returncode == 3


@pytest.mark.parametrize('scope', ['unselected', 'ignored', 'entry-test-only'])
def test_preload_scope_controls_do_not_mistake_existing_cache_snapshot_for_a_build(tmp_path, observed, scope):
    root, checked, _ = _project(tmp_path / 'cached')
    inventory = m102.M102()._collect_all_imports(root)
    assert isinstance(inventory, set) and 'worker' in inventory and inventory | {'extra'} >= {'worker', 'extra'}
    assert inventory.copy() == inventory
    before = len(observed['builds'])
    target, _, _ = _project(tmp_path / 'target')
    files = [checked]
    select, ignore = ['E501'], None
    if scope == 'ignored':
        select, ignore = None, ['M102']
    if scope == 'entry-test-only':
        files = [_write(target / 'tests' / 'test_worker.py', 'import worker\n'), target / 'main.py']
        select = None
    snapshot = scan_caches._m102_preload(target, select, ignore, files)
    assert len(observed['builds']) == before
    assert snapshot == ({root: inventory} if scope == 'entry-test-only' else {})
    assert m102._import_cache[root] is inventory


def test_legacy_plain_set_seed_and_same_invocation_identity_remain_supported(tmp_path, observed):
    root, checked, _ = _project(tmp_path / 'legacy')
    value = {'worker'}
    scan_caches._m102_init_worker({root: value})
    assert m102.M102()._collect_all_imports(root) is value
    assert m102.M102().check(str(checked), None, checked.read_text(encoding='utf-8')) == []
    assert observed['builds'] == observed['extracts'] == observed['events'] == []
