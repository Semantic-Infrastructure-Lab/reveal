"""New Stats disclosure-sink and fresh-process row-transfer acceptance."""
import importlib
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from reveal.adapters.stats.adapter import StatsAdapter
from reveal.adapters.stats.metrics import _count_check_issues
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
    assert state['events'] == ([hidden] if loss else [])
    assert row['quality']['check_issues'] == (0 if loss else 1)
    raw = row.get('check_scan_disclosures', [])
    assert bool(raw) == loss
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
                            input=pickle.dumps(row), capture_output=True, check=True)
    received = json.loads(packet.stdout)
    assert received['row'] == row
    warnings = received['result'].get('meta', {}).get('warnings', [])
    assert len(warnings) == (1 if loss else 0)
    if loss:
        assert raw[0] in warnings[0]['message']
        assert warnings[0]['type'] == 'analysis_incomplete'
        assert 'lower bound' not in warnings[0]['message']


def test_optional_sink_keeps_historical_three_argument_pair(measured):
    checked, hidden, state = measured
    state['loss'] = True
    counts, failed = _count_check_issues(checked, {}, LITERAL)
    assert state['events'] == [hidden]
    assert failed == [] and sum(counts.values()) == 0
    sink = []
    repeated = _count_check_issues(checked, {}, LITERAL, disclosures=sink)
    assert repeated == (counts, failed)
    assert len(sink) == 1 and 'D005:' in sink[0]
    assert 'directory enumeration' in sink[0]
    assert state['events'] == [hidden]  # Same invocation memo remains usable.
