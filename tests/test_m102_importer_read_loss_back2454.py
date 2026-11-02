"""Importer-file read loss uses M102's existing root artifact and answer route."""
import asyncio
import importlib
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from test_m102_discovery_loss_back2043 import _project, _write
from reveal.rules import scan_caches
from reveal.reveal_types import PathFailure

m102 = importlib.import_module('reveal.rules.maintainability.M102')
pytestmark = pytest.mark.component


@pytest.fixture
def reads(monkeypatch):
    state = {'active': False, 'denied': set(), 'filename': 'correct', 'transient': False,
             'events': [], 'builds': []}
    real_collect, real_read = m102.M102._collect_all_imports, Path.read_text

    def collect(self, root):
        missed = root not in m102._import_cache
        state['active'] = True
        try:
            value = real_collect(self, root)
            if missed:
                state['builds'].append(root)
            return value
        finally:
            state['active'] = False
            if state['transient']:
                state['denied'] = set()  # Failure ends before the ordinary healthy seal.

    def read(path, *args, **kwargs):
        if state['active'] and path in state['denied']:
            state['events'].append(path)
            filename = {'correct': str(path), 'missing': None,
                        'wrong': str(path.parent / 'not-the-source.py')}[state['filename']]
            raise PermissionError(13, 'importer read denied', filename)
        return real_read(path, *args, **kwargs)

    monkeypatch.setattr(m102.M102, '_collect_all_imports', collect)
    monkeypatch.setattr(Path, 'read_text', read)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    return state


def loss_note(notes, root, source):
    matching = [note for note in notes if 'importer file read' in note]
    assert len(matching) == 1, notes
    note = matching[0]
    assert root.as_posix() in note and source.relative_to(root).as_posix() in note
    assert 'PermissionError: importer read denied' in note
    assert 'false positives' in note and '1 importer file read' in note
    assert 'directory enumeration' not in note and 'lower bound' not in note
    return note


@pytest.mark.parametrize('directory', [False, True])
def test_native_source_only_read_loss_keeps_finding_but_exits_incomplete(tmp_path, reads, directory):
    root, worker, hidden = _project(tmp_path / 'project')
    healthy = run('check', str(worker), '--select', 'M102', '--format', 'json')
    assert healthy.returncode == 0
    m102._import_cache.pop(root)
    source = hidden / 'main.py'
    reads['denied'] = {source}
    response = run('check', str(root if directory else worker), '--select', 'M102', '--format', 'json')
    data = json.loads(response.stdout)
    assert reads['events'] == [source]
    if directory:
        summary = data['summary']
        assert summary['total_issues'] == 1 and summary['files_checked'] == 4
        assert summary['files_errored'] == summary['files_degraded'] == 0
        notes = summary['scan_disclosures']
    else:
        assert len(data['detections']) == 1 and data['detections'][0]['rule_code'] == 'M102'
        notes = data['scan_disclosures']
    loss_note(notes, root, source)
    assert response.returncode == 3


@pytest.mark.parametrize('filename,nonempty', [('missing', False), ('wrong', True)])
def test_known_read_operand_and_complete_facts_survive_same_invocation(tmp_path, reads, filename, nonempty):
    root, worker, hidden = _project(tmp_path / 'project', nonempty=nonempty)
    source = hidden / 'main.py'
    reads.update(denied={source}, filename=filename)
    value = m102.M102()._collect_all_imports(root)
    assert value == ({'os'} if nonempty else set())
    assert value.file_read_failures == (PathFailure(source.as_posix(), 'PermissionError: importer read denied'),)
    assert isinstance(value.file_read_failures, tuple) and value.traversal_failures == ()
    assert m102.M102()._collect_all_imports(root) is value and reads['events'] == [source]
    for _ in range(2):
        note = loss_note(scan_caches.get_scan_disclosures([worker], ['M102'], None), root, source)
        assert 'not-the-source' not in note and note.count(source.as_posix()) == 0
    assert value.copy() == value and value | {'extra'} == set(value) | {'extra'}
    assert len(value.file_read_failures) == len(reads['events']) == 1


def test_bounded_source_display_preserves_all_read_failures_without_replay_inflation(tmp_path, reads):
    root, worker, hidden = _project(tmp_path / 'project')
    sources = {hidden / 'main.py'} | {_write(root / f'extra{n}' / 'main.py', 'import worker\n') for n in range(6)}
    reads['denied'] = sources
    value = m102.M102()._collect_all_imports(root)
    assert len(value.file_read_failures) == len(reads['events']) == 7
    for _ in range(2):
        notes = scan_caches.get_scan_disclosures([worker], ['M102'], None)
        assert len(notes) == 1 and '7 importer file read' in notes[0] and 'and 2 more' in notes[0]
        assert sum(source.relative_to(root).as_posix() in notes[0] for source in sources) == 5
    assert len(value.file_read_failures) == len(reads['events']) == 7


def test_existing_preload_and_fresh_worker_transfer_read_facts_without_rescan(tmp_path, reads):
    root, worker, hidden = _project(tmp_path / 'lost')
    healthy_root, healthy, _ = _project(tmp_path / 'healthy')
    source = hidden / 'main.py'
    reads['denied'] = {source}
    payload = scan_caches._m102_preload(tmp_path, ['M102'], None, [worker, healthy])
    assert payload[root] is m102._import_cache[root]
    assert payload[root].file_read_failures == (PathFailure(source.as_posix(), 'PermissionError: importer read denied'),)
    payload[healthy_root] = {'worker'}  # Legacy plain-set worker seed remains supported.
    serialized = tmp_path / 'payload.pickle'
    serialized.write_bytes(pickle.dumps(payload))
    script = '''
import importlib,json,pickle,sys
from pathlib import Path
from reveal.rules.scan_caches import _m102_init_worker
m=importlib.import_module('reveal.rules.maintainability.M102')
payload=pickle.loads(Path(sys.argv[1]).read_bytes());_m102_init_worker(payload)
def forbidden(*a,**k):raise AssertionError('seeded worker must not rebuild import evidence')
m._walk_code_files=forbidden;m._extract_imports_regex=forbidden
rows=[]
for arg in sys.argv[2:]:
 p=Path(arg);value=m.M102()._collect_all_imports(p.parent)
 assert value is payload[p.parent]
 rows.append({'findings':len(m.M102().check(str(p),None,'VALUE=1\\n')),
              'notes':m.get_scan_disclosures([p],select=['M102']),
              'failures':list(getattr(value,'file_read_failures',()))})
print(json.dumps(rows))
'''
    checkout = Path(__file__).resolve().parents[1]
    response = subprocess.run([sys.executable, '-c', script, str(serialized), str(worker), str(healthy)],
                              cwd=checkout, env=dict(os.environ, PYTHONPATH=str(checkout)),
                              capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    lost, clean = json.loads(response.stdout)
    assert lost['findings'] == 1 and lost['failures'] == [[source.as_posix(), 'PermissionError: importer read denied']]
    loss_note(lost['notes'], root, source)
    assert clean == {'findings': 0, 'notes': [], 'failures': []}


def test_transient_read_loss_retries_next_request_with_healthy_warm_sibling_reuse(tmp_path, reads):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_check
    root, worker, hidden = _project(tmp_path / 'primary')
    sibling, sibling_file, _ = _project(tmp_path / 'sibling')
    baseline = reveal_check(str(worker), select='M102')
    other = reveal_check(str(sibling_file), select='M102')
    sibling_value = m102._import_cache[sibling]
    _write(root / 'added.py', 'VALUE=1\n')
    reads.update(denied={hidden / 'main.py'}, transient=True)
    before = len(reads['builds'])
    lost = reveal_check(str(worker), select='M102')
    partial = m102._import_cache[root]
    assert len(reads['builds']) == before + 1 and reads['denied'] == set()
    loss_note(lost.splitlines(), root, hidden / 'main.py')
    assert reveal_check(str(worker), select='M102') == baseline
    assert len(reads['builds']) == before + 2 and m102._import_cache[root] is not partial
    warm = m102._import_cache[root]
    assert reveal_check(str(worker), select='M102') == baseline
    assert reveal_check(str(sibling_file), select='M102') == other
    assert m102._import_cache[root] is warm and m102._import_cache[sibling] is sibling_value
    assert len(reads['builds']) == before + 2


def test_registered_sdk_discloses_usable_read_incomplete_evidence(tmp_path, reads):
    pytest.importorskip('mcp')
    from reveal import mcp_server
    root, worker, hidden = _project(tmp_path / 'project')
    source = hidden / 'main.py'
    reads['denied'] = {source}

    async def scenario():
        result = await mcp_server.mcp.call_tool('reveal_check', {'path': str(worker), 'select': 'M102'})
        assert not result.is_error
        body = '\n'.join(item.text for item in result.content if item.type == 'text')
        loss_note(body.splitlines(), root, source)
        assert "Module 'worker' is not imported" in body
    asyncio.run(asyncio.wait_for(scenario(), timeout=30))


def test_read_loss_uses_existing_config_target_scope_and_plain_set_controls(tmp_path, reads):
    root, worker, hidden = _project(tmp_path / 'project')
    disabled = _write(root / 'disabled.py', 'VALUE=1\n')
    _write(root / '.reveal.yaml', 'root: true\noverrides:\n  - files: disabled.py\n    rules:\n      disable: [M102]\n')
    reads['denied'] = {hidden / 'main.py'}
    value = m102.M102()._collect_all_imports(root)
    notes = scan_caches.get_scan_disclosures
    assert notes([disabled], None, None) == []
    loss_note(notes([disabled], ['M102'], None), root, hidden / 'main.py')
    for files, select, ignore in [([worker], ['E501'], None), ([worker], None, ['M102']),
                                 ([hidden / 'main.py'], ['M102'], None),
                                 ([_write(root / 'tests' / 'test_worker.py', 'import worker\n')], ['M102'], None),
                                 ([], ['M102'], None)]:
        assert notes(files, select, ignore) == []
    other_root, other, _ = _project(tmp_path / 'other')
    assert notes([other], ['M102'], None) == [] and other_root not in m102._import_cache
    assert m102._import_cache[root] is value and reads['events'] == [hidden / 'main.py']
    m102._import_cache[root] = {'worker'}
    assert m102.M102().check(str(worker), None, 'VALUE=1\n') == []
    assert notes([worker], ['M102'], None) == []


def test_initializer_only_read_failure_remains_separate_held_scope(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    _write(root / 'pyproject.toml', '[project]\nname="probe"\n')
    worker = _write(root / 'pkg' / 'worker.py', 'VALUE=1\n')
    initializer = _write(worker.parent / '__init__.py', '__all__=["worker"]\n')
    rule = m102.M102()
    assert rule.check(str(worker), None, 'VALUE=1\n') == []
    value = m102._import_cache[root]  # Complete collector; deny only the later fallback read.
    real_read = Path.read_text
    def read(path, *args, **kwargs):
        if path == initializer:
            raise PermissionError(13, 'initializer fallback denied', str(path))
        return real_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', read)
    assert len(rule.check(str(worker), None, 'VALUE=1\n')) == 1
    assert getattr(value, 'file_read_failures', ()) == ()
    assert scan_caches.get_scan_disclosures([worker], ['M102'], None) == []
