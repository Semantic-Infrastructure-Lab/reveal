"""BACK-2229: a plain-call declarator Phase A does not list as a function is disclosed, not silently dropped.

BACK-2174 Phase A lists `const NAME = callee(fn)` as a function only when the file calls NAME (or the callee is
a declared wrapper). The drop loses real functions when the callee is imported and returns one (three.js
`Fn(...)`: 103 gate edges, found only by the offline gate, BACK-2191). Every `calls` mode now carries one
`function_values_dropped` warning that counts the dropped declarators and names their callees, imported ones
apart; it is not a loss (no exit code, confidence or parse_mode change).
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.registry import get_analyzer

SOURCE = '''\
import { Fn } from './tsl.js';
import * as ns from './ns.js';

function helper(x) { return x; }

export const imported = Fn((a) => helper(a));
export const viaMember = ns.make((a) => helper(a));
const timer = setTimeout(() => helper(1), 10);
const store = derived((a) => helper(a));
const called = derived((a) => helper(a));
called(1);
const cb = useCallback((q) => helper(q), []);
const mapped = [1].map((q) => helper(q));
'''
CLEAN = '''\
function helper(x) { return x; }
const called = derived((a) => helper(a));
called(1);
const cb = useCallback((q) => helper(q), []);
export const plain = (q) => helper(q);
'''
PYTHON = 'def helper():\n    return 1\n\ndef run():\n    return helper()\n'
DROPPED = {'imported', 'timer', 'store'}
MODES = ['callers=helper', 'callees=helper', 'rank=callers&top=3', 'uncalled=true', 'target=helper']


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'a.js').write_text(SOURCE, encoding='utf-8')
    return root


def run(uri):
    out = _run_reveal_direct(uri, '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def dropped_warnings(result):
    return [w for w in result['meta']['warnings'] if w.get('type') == 'function_values_dropped']


def test_the_analyzer_records_each_dropped_declarator(project):
    path = str(project / 'a.js')
    structure = get_analyzer(path)(path).get_structure()
    records = structure['_dropped_function_values']
    assert {r['name'] for r in records} == DROPPED
    by_name = {r['name']: r for r in records}
    assert by_name['imported']['callee'] == 'Fn' and by_name['imported']['imported'] is True
    assert by_name['timer']['callee'] == 'setTimeout' and by_name['timer']['imported'] is False
    assert by_name['store']['callee'] == 'derived' and by_name['store']['imported'] is False


def test_a_kept_declarator_is_not_recorded(tmp_path):
    (tmp_path / 'b.js').write_text(CLEAN, encoding='utf-8')
    path = str(tmp_path / 'b.js')
    assert '_dropped_function_values' not in get_analyzer(path)(path).get_structure()


@pytest.mark.parametrize('query', MODES)
def test_every_calls_mode_discloses_the_drops_once(project, query):
    result = run(f'calls://{project}?{query}')
    (warning,) = dropped_warnings(result)
    assert warning['count'] == 3
    assert warning['files'] == ['a.js'] or warning['files'] == [str(project / 'a.js')]
    assert warning['imported_callees'] == {'Fn': 1}
    assert warning['other_callees'] == {'derived': 1, 'setTimeout': 1}
    assert 'Fn' in warning['message'] and '3' in warning['message']


def test_the_disclosure_is_not_a_loss(project):
    result = run(f'calls://{project}?callers=helper')
    meta = result['meta']
    assert meta['parse_mode'] == 'tree_sitter_full'
    assert meta.get('confidence') is not None
    assert not [w for w in meta['warnings'] if w.get('type') in ('analysis_failed', 'analysis_incomplete')]


def test_no_drops_no_warning(tmp_path):
    (tmp_path / 'b.js').write_text(CLEAN, encoding='utf-8')
    (tmp_path / 'p.py').write_text(PYTHON, encoding='utf-8')
    for query in MODES:
        assert not dropped_warnings(run(f'calls://{tmp_path}?{query}')), query


def test_a_python_only_tree_has_no_warning(tmp_path):
    (tmp_path / 'p.py').write_text(PYTHON, encoding='utf-8')
    assert not dropped_warnings(run(f'calls://{tmp_path}?callers=helper'))


def test_the_text_view_prints_it_once(project):
    out = _run_reveal_direct(f'calls://{project}?callers=helper', '--no-gitignore')
    assert out.returncode == 0, out.stderr
    assert out.stdout.count('not treated as functions') == 1


@pytest.mark.disk_cache
def test_cold_warm_and_cache_off_agree(project, monkeypatch):
    uri = f'calls://{project}?callers=helper'
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    cold = dropped_warnings(run(uri))
    warm = dropped_warnings(run(uri))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    off = dropped_warnings(run(uri))
    assert cold == warm == off and len(cold) == 1


def test_a_dropped_name_is_not_declared_absent(project):
    """`imported` is a declaration the rule left out: "not found" (exit 2) would be a claim the tool cannot make."""
    out = _run_reveal_direct(f'calls://{project}?callees=imported', '--no-gitignore', '--format', 'json')
    result = json.loads(out.stdout)
    assert out.returncode == 0, out.stderr
    assert 'error' not in result
    assert len(dropped_warnings(result)) == 1


def test_a_name_that_is_not_dropped_is_still_absent(project):
    """Control: the same tree, a name nothing declares, keeps the canonical absence error."""
    out = _run_reveal_direct(f'calls://{project}?callees=nosuchname', '--no-gitignore', '--format', 'json')
    assert out.returncode == 2
    assert len(dropped_warnings(json.loads(out.stdout))) == 1


def test_a_computed_callee_is_named_as_such(tmp_path):
    (tmp_path / 'c.js').write_text('function helper(x) { return x; }\nconst curried = make(1)((a) => helper(a));\n',
                                   encoding='utf-8')
    path = str(tmp_path / 'c.js')
    (record,) = get_analyzer(path)(path).get_structure()['_dropped_function_values']
    assert record['callee'] == '<computed>' and record['imported'] is False
