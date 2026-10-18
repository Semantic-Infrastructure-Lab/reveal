"""Post-source feature acceptance; original old-API semantic reds remain separate."""
import dataclasses
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from test_i007_discovery_loss_back2039 import fault, project, write  # noqa: F401
from reveal.rules.imports import _dep_reconciliation as dep
from reveal.rules.scan_caches import get_scan_disclosures, preload_scan_caches

pytestmark = pytest.mark.component


@pytest.mark.parametrize('language', ['python', 'rust'])
@pytest.mark.parametrize('unknown', [False, True])
def test_full_actual_event_sequence_is_frozen_and_replayed_without_new_walk(tmp_path, fault, language, unknown):
    manifest, hidden, helper, used, missing, ext = project(tmp_path, language)
    for number in range(6):
        write(tmp_path / f'part{number}' / 'included_child' / ('usage' + ext), hidden.read_text(encoding='utf-8'))
    fault.update(mode='directory', unknown=unknown)
    events = []
    result = helper(tmp_path, on_traversal_failure=events.append)
    assert result.unused == {missing} and result.skipped == ()
    assert len(fault['events']) == len(events) == 7
    facts = next(iter(dep._scan_cache[tmp_path].values()))
    assert facts.traversal_failures == tuple(events)
    assert facts.imports.names == {used}
    with pytest.raises(dataclasses.FrozenInstanceError):
        facts.traversal_failures = ()
    replay = []; before = len(fault['builds'])
    assert helper(tmp_path, on_traversal_failure=replay.append) == result
    assert replay == events and len(fault['builds']) == before
    note, = get_scan_disclosures([manifest], ['I007'], None)
    if unknown:
        assert all(path is None for path, _cause in events)
        assert '7 enumeration error event(s)' in note and '0 identified directory' in note
    else:
        assert len({path for path, _cause in events}) == 7
        assert '7 identified directory' in note and 'and 2 more' in note


CHILD = r'''
import json,pickle,sys
from pathlib import Path
import reveal
assert Path(reveal.__file__).is_relative_to(Path.cwd()),reveal.__file__
from reveal.rules.imports import _dep_reconciliation as dep
from reveal.rules.imports.I007 import I007
from reveal.rules.scan_caches import init_scan_caches,get_scan_disclosures
payload=pickle.loads(Path(sys.argv[1]).read_bytes())
init_scan_caches(payload)
calls=[]
def unexpected(*args,**kwargs):
    calls.append(1);raise RuntimeError('worker must consume transferred native facts')
dep._scan_project_imports_uncached=unexpected
manifest=Path(sys.argv[2]);rule=I007();found=rule.check(str(manifest),None,'')
print(json.dumps({'contexts':[d.context for d in found],'outcomes':rule.outcomes,'notes':get_scan_disclosures([manifest],['I007'],None),'builds':len(calls),'cache_roots':[str(p) for p in dep._scan_cache]}))
'''


@pytest.mark.parametrize('language', ['python', 'rust'])
def test_existing_pool_payload_survives_a_real_fresh_interpreter(tmp_path, fault, language):
    root = tmp_path / 'project'
    manifest, hidden, _helper, _used, missing, _ext = project(root, language)
    fault.update(mode='directory', unknown=True)
    payload = preload_scan_caches([manifest], root, ['I007'], None)
    assert fault['events'] == [str(hidden.parent)]
    expected = get_scan_disclosures([manifest], ['I007'], None)
    packet = tmp_path / 'facts.pickle'; packet.write_bytes(pickle.dumps(payload))
    result = subprocess.run([sys.executable, '-c', CHILD, str(packet), str(manifest)],
                            cwd=Path.cwd(), env=dict(os.environ, PYTHONPATH=str(Path.cwd())),
                            capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    data = json.loads(result.stdout)
    assert data['builds'] == 0 and data['cache_roots'] == [str(root)]
    assert len(data['contexts']) == 1 and missing in data['contexts'][0]
    assert data['notes'] == expected and len(data['outcomes']) == 1
    assert '1 enumeration error event(s)' in data['notes'][0]


@pytest.mark.parametrize('view', ['text', 'json', 'grep', 'cap-zero', 'exit-zero'])
def test_existing_public_cuts_and_grep_boundaries_keep_incomplete_exit(tmp_path, fault, view):
    manifest, hidden, *_ = project(tmp_path, 'python')
    fault['mode'] = 'directory'
    flags = ['--format', view if view in {'text', 'json', 'grep'} else 'json']
    if view == 'cap-zero':
        flags += ['--max-items', '0']
    if view == 'exit-zero':
        flags += ['--exit-zero']
    result = run('check', str(manifest), '--select', 'I007', *flags)
    assert fault['events'] == [str(hidden.parent)]
    assert result.returncode == (0 if view == 'exit-zero' else 3)
    if view == 'grep':
        assert 'I007' in result.stdout and 'missing file population' not in result.stdout
        assert 'missing file population' not in result.stderr  # existing detection-only legacy renderer
    elif view == 'text':
        assert result.stdout.count('missing file population is unknown') == 1
    else:
        data = json.loads(result.stdout)
        assert len(data['scan_disclosures']) == 1
        assert 'Python' in data['scan_disclosures'][0] and str(tmp_path) in data['scan_disclosures'][0]
        assert len(data['detections']) == (0 if view == 'cap-zero' else 1)
