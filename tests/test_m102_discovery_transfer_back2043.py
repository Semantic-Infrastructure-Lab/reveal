"""M102 immutable cached facts, existing payload transfer and owner lifetimes."""
import importlib
import json
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run, needs_forked_workers
from reveal.rules import scan_caches
from reveal.utils import request_cache

m102 = importlib.import_module('reveal.rules.maintainability.M102')
pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    aged = time.time_ns() - 60_000_000_000
    os.utime(path, ns=(aged, aged))
    return path


def project(root):
    worker = write(root / 'worker.py', 'VALUE=1\n')
    write(root / 'main.py', 'VALUE=1\n')
    write(root / 'included' / 'main.py', 'import worker\n')
    write(root / 'pyproject.toml', '[project]\nname="transfer"\n')
    return worker


@pytest.fixture
def losses(monkeypatch):
    state = {'denied': set(), 'unknown': False, 'walks': [], 'events': []}
    real_walk, real_scan = m102._walk_code_files, os.scandir
    active = False

    def walk(*args, **kwargs):
        nonlocal active
        active = True
        state['walks'].append(Path(args[0]))
        try:
            yield from real_walk(*args, **kwargs)
        finally:
            active = False

    def scandir(path):
        if active and Path(path) in state['denied']:
            state['events'].append(Path(path))
            if state['unknown']:
                raise PermissionError('actual unlocated M102 transfer discovery failure')
            raise PermissionError(13, 'actual M102 transfer discovery failure', str(path))
        return real_scan(path)

    monkeypatch.setattr(m102, '_walk_code_files', walk)
    monkeypatch.setattr(os, 'scandir', scandir)
    return state


@pytest.mark.parametrize('unknown', [False, True])
def test_full_seven_event_tuple_stays_on_actual_set_and_preload_aliases(tmp_path, losses, unknown):
    worker = project(tmp_path / 'project')
    root = worker.parent
    denied = {root / 'included', *[write(root / f'blocked{n}' / 'main.py', 'import worker\n').parent for n in range(6)]}
    losses.update(denied=denied, unknown=unknown)
    value = m102.M102()._collect_all_imports(root)
    assert isinstance(value, set) and value == set()
    assert len(value.traversal_failures) == 7 and isinstance(value.traversal_failures, tuple)
    assert all(isinstance(event, tuple) and event[1].startswith('PermissionError:') for event in value.traversal_failures)
    assert {path for path, _ in value.traversal_failures} == ({None} if unknown else {p.as_posix() for p in denied})
    assert losses['walks'] == [root] and len(losses['events']) == 7
    assert m102.M102()._collect_all_imports(root) is value
    payload = scan_caches._m102_preload(root, ['M102'], None, [worker])
    assert payload[root] is value and losses['walks'] == [root]
    assert value.copy() == set() and value | {'extra'} == {'extra'}
    for _ in range(3):
        notes = m102.get_scan_disclosures([worker], select=['M102'])
        assert len(notes) == 1
        assert ('7 enumeration error event(s)' if unknown else '7 identified directory') in notes[0]
        assert len(value.traversal_failures) == 7 and losses['walks'] == [root]
    restored = pickle.loads(pickle.dumps(payload))[root]
    assert restored == value and restored.traversal_failures == value.traversal_failures


@pytest.mark.parametrize('unknown', [False, True])
def test_fresh_process_existing_worker_initializer_preserves_empty_loss_and_healthy_plain_sets(tmp_path, losses, unknown):
    lost = project(tmp_path / 'lost')
    healthy = project(tmp_path / 'healthy')
    plain = project(tmp_path / 'legacy')
    losses.update(denied={lost.parent}, unknown=unknown)
    payload = scan_caches._m102_preload(tmp_path, ['M102'], None, [lost, healthy])
    payload[plain.parent] = {'worker'}
    assert payload[lost.parent] == set() and len(payload[lost.parent].traversal_failures) == 1
    assert not payload[healthy.parent].traversal_failures
    serialized = tmp_path / 'payload.pickle'
    serialized.write_bytes(pickle.dumps(payload))
    script = r'''
import importlib,json,pickle,sys
from pathlib import Path
from reveal.rules.scan_caches import _m102_init_worker
m=importlib.import_module('reveal.rules.maintainability.M102')
assert not m._import_cache
payload=pickle.loads(Path(sys.argv[1]).read_bytes());_m102_init_worker(payload)
def forbidden(*a,**kw):raise AssertionError('fresh worker must consume seeded evidence without rescanning')
m._walk_code_files=forbidden;m._extract_imports_regex=forbidden
rows={}
for target in sys.argv[2:]:
 path=Path(target);root=path.parent;value=m.M102()._collect_all_imports(root)
 assert value is payload[root] and isinstance(value,set)
 detections=m.M102().check(str(path),None,'VALUE=1\n')
 rows[root.name]={'events':list(getattr(value,'traversal_failures',())),'imports':sorted(value),'findings':len(detections),'notes':m.get_scan_disclosures([path],select=['M102'])}
assert rows['lost']['imports']==[] and rows['lost']['findings']==1 and len(rows['lost']['events'])==len(rows['lost']['notes'])==1
assert rows['healthy']['imports']==rows['legacy']['imports']==['worker']
assert rows['healthy']['findings']==rows['legacy']['findings']==0
assert rows['healthy']['notes']==rows['legacy']['notes']==[]
print(json.dumps(rows))
'''
    checkout = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, '-c', script, str(serialized), str(lost), str(healthy), str(plain)],
                            cwd=checkout, env=dict(os.environ, PYTHONPATH=str(checkout)),
                            text=True, encoding='utf-8', capture_output=True, check=True)
    rows = json.loads(result.stdout)
    assert rows['lost']['events'][0][0] == (None if unknown else lost.parent.as_posix())
    assert len(losses['walks']) == 2


@needs_forked_workers
def test_real_parent_preload_and_parallel_multiroot_workers_keep_one_attributed_loss(tmp_path, losses, monkeypatch):
    outer = tmp_path / 'projects'
    lost = project(outer / 'lost')
    healthy = project(outer / 'healthy')
    losses['denied'] = {lost.parent / 'included'}
    parent = os.getpid()
    builds, checks = tmp_path / 'builds.jsonl', tmp_path / 'checks.jsonl'
    real_collect, real_check = m102.M102._collect_all_imports, m102.M102.check

    def collect(self, root):
        if root not in m102._import_cache:
            with builds.open('a', encoding='utf-8') as output:
                output.write(json.dumps({'root': str(root), 'pid': os.getpid()}) + '\n')
        return real_collect(self, root)

    def checked(self, path, *args, **kwargs):
        with checks.open('a', encoding='utf-8') as output:
            output.write(json.dumps({'file': str(path), 'pid': os.getpid()}) + '\n')
        return real_check(self, path, *args, **kwargs)

    monkeypatch.setattr(m102.M102, '_collect_all_imports', collect)
    monkeypatch.setattr(m102.M102, 'check', checked)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '2')
    response = run('check', str(outer), '--select', 'M102', '--format', 'json')
    data = json.loads(response.stdout)
    built = [json.loads(line) for line in builds.read_text(encoding='utf-8').splitlines()]
    checked_rows = [json.loads(line) for line in checks.read_text(encoding='utf-8').splitlines()]
    assert len(built) == 2 and {row['root'] for row in built} == {str(lost.parent), str(healthy.parent)}
    assert all(row['pid'] == parent for row in built)
    assert len(checked_rows) == 6 and all(row['pid'] != parent for row in checked_rows)
    assert losses['events'] == [lost.parent / 'included'] and len(losses['walks']) == 2
    assert response.returncode == 3 and data['summary']['total_issues'] == 1
    assert data['summary']['files_checked'] == 8 and data['summary']['files_errored'] == data['summary']['files_degraded'] == 0
    notes = data['summary']['scan_disclosures']
    assert len(notes) == 1 and lost.parent.as_posix() in notes[0] and healthy.parent.as_posix() not in notes[0]


@pytest.mark.parametrize('unknown', [False, True])
def test_normal_request_reset_prunes_only_actual_directory_loss_after_healthy_seal(tmp_path, losses, unknown):
    lost = project(tmp_path / 'lost')
    healthy = project(tmp_path / 'healthy')
    legacy = project(tmp_path / 'legacy')
    losses.update(denied={lost.parent}, unknown=unknown)
    partial = m102.M102()._collect_all_imports(lost.parent)
    complete = m102.M102()._collect_all_imports(healthy.parent)
    plain = {'worker'}
    m102._import_cache[legacy.parent] = plain
    assert partial == set() and len(partial.traversal_failures) == 1
    request_cache.seal_request_caches(time.time_ns())
    assert all((m102.__name__, root) in request_cache._STAMPS for root in (lost.parent, healthy.parent, legacy.parent))
    request_cache.reset_request_caches()
    assert lost.parent not in m102._import_cache
    assert m102._import_cache[healthy.parent] is complete and m102._import_cache[legacy.parent] is plain
    assert (m102.__name__, lost.parent) not in request_cache._STAMPS
    assert len(losses['walks']) == 2
