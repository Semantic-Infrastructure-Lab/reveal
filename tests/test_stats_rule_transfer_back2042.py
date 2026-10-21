"""Stats rows carry no cross-file scan facts through a pool, a pickle or the parent fold (BACK-1884).

BACK-2042 sent each row's ``check_scan_disclosures`` from a worker to the parent and folded them
into one ``analysis_incomplete`` warning. The count is file-local now, so a row has no such field,
the optional disclosure sink of ``_count_check_issues`` is gone (the function is
``_count_local_check_issues``), and the owner's directory denial never fires.
"""
import importlib
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from reveal.adapters.stats.adapter import StatsAdapter
from reveal.adapters.stats import metrics
from reveal.rules import RuleRegistry

pytestmark = pytest.mark.component
owner = importlib.import_module('reveal.rules.duplicates.D005')
LITERAL = 'ROUTE_KEYS=["alpha","beta","gamma","delta","epsilon"]\n'


@pytest.fixture
def measured(tmp_path, monkeypatch):
    codes = [r.code for r in RuleRegistry.get_rules() if r.code != 'D005']
    (tmp_path / '.reveal.yaml').write_text(
        'root: true\nrules:\n  disable: ' + json.dumps(codes) + '\n', encoding='utf-8')
    (tmp_path / 'pyproject.toml').write_text('[project]\nname="transfer"\n', encoding='utf-8')
    checked = tmp_path / 'checked.py'
    checked.write_text(LITERAL, encoding='utf-8')
    (tmp_path / 'visible.py').write_text(LITERAL, encoding='utf-8')
    hidden = tmp_path / 'included'
    hidden.mkdir()
    (hidden / 'other.py').write_text(LITERAL, encoding='utf-8')
    state = {'active': False, 'loss': False, 'events': []}
    real_build, real_scan = owner._build_index, os.scandir

    def build(*args, **kwargs):
        state['active'] = True
        try:
            return real_build(*args, **kwargs)
        finally:
            state['active'] = False

    def scan(path):
        if state['active'] and state['loss'] and Path(path) == hidden:
            state['events'].append(Path(path))
            raise PermissionError(13, 'actual transfer importer loss', str(path))
        return real_scan(path)

    monkeypatch.setattr(owner, '_build_index', build)
    monkeypatch.setattr(os, 'scandir', scan)
    return checked, hidden, state


@pytest.mark.parametrize('loss', [False, True])
def test_actual_native_row_survives_fresh_process_pickle_and_parent_fold(measured, loss):
    checked, hidden, state = measured
    state['loss'] = loss
    row = StatsAdapter(str(checked.parent)).get_element(checked.name)
    assert state['events'] == [], 'Stats must not scan for the cross-file rule, so nothing is denied'
    assert row['quality']['local_check_issues'] == 0
    assert 'check_scan_disclosures' not in row
    script = '''
import importlib, json, pickle, sys
from reveal.adapters.stats.adapter import StatsAdapter
owner = importlib.import_module('reveal.rules.duplicates.D005')
def forbidden(*args, **kwargs):
    raise AssertionError('a transferred row must not rebuild its rule index')
owner._build_index = forbidden
row = pickle.loads(sys.stdin.buffer.read())
adapter = StatsAdapter(sys.argv[1])
adapter._record_analysis_results([row, row])
result = {}
adapter._disclose_failures(result)
print(json.dumps({'row': row, 'result': result}))
'''
    packet = subprocess.run([sys.executable, '-c', script, str(checked.parent)],
                            input=pickle.dumps(row), capture_output=True, check=True, timeout=120)
    received = json.loads(packet.stdout)
    assert received['row'] == row
    assert received['result'].get('meta', {}).get('warnings', []) == []


def test_the_count_function_is_local_and_takes_no_disclosure_sink(measured):
    checked, hidden, state = measured
    state['loss'] = True
    counts, failed = metrics._count_local_check_issues(checked, {}, LITERAL)
    assert state['events'] == []
    assert failed == [] and sum(counts.values()) == 0
    with pytest.raises(TypeError):
        metrics._count_local_check_issues(checked, {}, LITERAL, disclosures=[])
