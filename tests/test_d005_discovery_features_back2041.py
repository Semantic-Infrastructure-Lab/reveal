"""Post-source carrier and existing worker-transfer acceptance for D005."""
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from test_d005_discovery_loss_back2041 import fault, mod, project, write, LITERAL  # noqa: F401
from reveal.rules.scan_caches import get_scan_disclosures, preload_scan_caches
from reveal.utils.query_control import ScanBudget

pytestmark = pytest.mark.component


def test_optional_facts_preserve_three_positional_mapping_and_pickle_contract():
    original = mod.LiteralIndex(ScanBudget(2), 2, True)
    original['key'] = [('file.py', 1, 'NAMES')]
    assert original.traversal_failures == () and original['key'][0][1] == 1
    facts = [(None, 'PermissionError: unknown'), (None, 'PermissionError: unknown')]
    index = mod.LiteralIndex(ScanBudget(5), 0, traversal_failures=facts)
    facts.clear()
    assert isinstance(index.traversal_failures, tuple) and len(index.traversal_failures) == 2
    assert not index and not index.scan_budget['exact']
    restored = pickle.loads(pickle.dumps(index))
    assert restored == index and restored.traversal_failures == index.traversal_failures
    assert restored.scan_budget == index.scan_budget
    assert restored.disclosures == index.disclosures


@pytest.mark.parametrize('unknown', [False, True])
def test_full_actual_event_sequence_survives_pickle_without_display_dedup(tmp_path, fault, unknown):
    checked, _hidden = project(tmp_path, 'positive')
    for number in range(6):
        write(tmp_path / f'part{number}' / 'included_child' / 'hidden.py', LITERAL)
    fault.update(enabled=True, unknown=unknown)
    index = mod._build_index(tmp_path, mod.D005())
    mod._project_index[tmp_path] = index
    assert len(fault['events']) == len(index.traversal_failures) == 7
    assert index.scan_budget['total'] == index.scan_budget['returned'] == 3
    assert index.scan_budget['analyzed_files'] == 3 and index.scan_budget['failed_files'] == 0
    assert index.scan_budget['exact'] is False
    assert all(cause.startswith('PermissionError:') for _path, cause in index.traversal_failures)
    if unknown:
        assert index.traversal_failures == ((None, 'PermissionError: actual unnamed D005 source loss'),) * 7
    else:
        assert [path for path, _cause in index.traversal_failures] == [Path(event).as_posix() for event in fault['events']]
    note, = get_scan_disclosures([checked], ['D005'], None)
    assert ('7 enumeration error event(s)' if unknown else 'and 2 more') in note
    restored = pickle.loads(pickle.dumps(index))
    assert restored.traversal_failures == index.traversal_failures
    assert mod._index_disclosures(tmp_path, restored) == [note]


@pytest.mark.parametrize('unknown', [False, True])
def test_early_cap_keeps_actual_facts_and_unmodified_observed_lookahead(tmp_path, fault, monkeypatch, unknown):
    project(tmp_path, 'cap')
    monkeypatch.setenv('REVEAL_D005_MAX_FILES', '2')
    fault.update(enabled=True, unknown=unknown)
    index = mod._build_index(tmp_path, mod.D005())
    assert len(fault['events']) == len(index.traversal_failures) == 1
    assert index.traversal_failures[0][0] == (None if unknown else (tmp_path / 'a_hidden').as_posix())
    assert not index and index.scan_budget == {
        'scope': 'scan', 'total': 3, 'returned': 2, 'exact': False,
        'limit': 2, 'analyzed_files': 0, 'failed_files': 0, 'skipped': True,
    }
    notes = mod._index_disclosures(tmp_path, pickle.loads(pickle.dumps(index)))
    assert len(notes) == 2 and 'skipping cross-file scan' in notes[0]
    assert 'missing file population is unknown' in notes[1]


CHILD = r'''
import json,os,pickle,sys
from pathlib import Path
import reveal
assert Path(reveal.__file__).is_relative_to(Path.cwd()),reveal.__file__
import importlib
mod=importlib.import_module('reveal.rules.duplicates.D005')
from reveal.rules.scan_caches import init_scan_caches,get_scan_budgets,get_scan_disclosures
init_scan_caches(pickle.loads(Path(sys.argv[1]).read_bytes()))
builds=[]
def unexpected(*args,**kwargs):
    builds.append(1)
    raise AssertionError('worker must consume transferred native literal index')
mod._build_index=unexpected
files=[Path(path) for path in sys.argv[2:]]
found=[len(mod.D005().check(str(path),None,'')) for path in files]
print(json.dumps({'pid':os.getpid(),'found':found,'builds':builds,
 'budgets':get_scan_budgets(files,['D005'],None),
 'notes':get_scan_disclosures(files,['D005'],None),
 'facts':{str(root):index.traversal_failures for root,index in mod._project_index.items()}} ,default=str))
'''


@pytest.mark.parametrize('unknown', [False, True])
@pytest.mark.parametrize('empty', [False, True])
def test_selected_multi_root_preload_reaches_real_fresh_worker_without_rebuild(tmp_path, fault, unknown, empty):
    first = tmp_path / 'first'; checked, hidden = project(first, 'positive')
    second = tmp_path / 'second'
    write(second / 'pyproject.toml', '[project]\nname="second"\n')
    for number in range(3):
        write(second / f'file{number}.py', LITERAL)
    other = second / 'file0.py'
    unreached = tmp_path / 'unreached'; project(unreached)
    selected = [checked, other]
    # Existing selection still avoids all D005 work when only an unrelated rule runs.
    assert preload_scan_caches(selected, tmp_path, ['E501'], None)['D005'] == {}
    assert fault['builds'] == [] and fault['events'] == []
    fault.update(enabled=True, unknown=unknown, root=first if empty else None)
    payload = preload_scan_caches(selected, tmp_path, ['D005'], None)
    assert set(payload['D005']) == {first, second}
    assert len(fault['builds']) == 2 and fault['events'] == [str(first if empty else hidden)]
    assert payload['D005'][second].traversal_failures == ()
    expected_notes = get_scan_disclosures(selected, ['D005'], None)
    packet = tmp_path / 'preload.pickle'; packet.write_bytes(pickle.dumps(payload))
    result = subprocess.run([sys.executable, '-c', CHILD, str(packet), *map(str, selected)],
                            cwd=Path.cwd(), env=dict(os.environ, PYTHONPATH=str(Path.cwd())),
                            capture_output=True, text=True, encoding='utf-8', timeout=30, check=True)
    data = json.loads(result.stdout)
    assert data['pid'] != os.getpid() and data['builds'] == [] and data['found'] == [0 if empty else 1, 1]
    assert data['notes'] == expected_notes and len(data['notes']) == 1
    assert data['facts'][str(first)] == [list(item) for item in payload['D005'][first].traversal_failures]
    assert data['facts'][str(second)] == []
    budgets = {row['root']: row for row in data['budgets']}
    assert not budgets[str(first)]['exact'] and budgets[str(second)]['exact']
    assert budgets[str(first)]['total'] == budgets[str(first)]['returned'] == budgets[str(first)]['analyzed_files'] == (0 if empty else 3)
    assert budgets[str(second)]['total'] == budgets[str(second)]['returned'] == budgets[str(second)]['analyzed_files'] == 3
