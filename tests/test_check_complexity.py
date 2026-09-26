"""Unit tests for scripts/check_complexity.py (the C901 complexity ratchet, BACK-1512)."""
import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    'check_complexity', Path(__file__).resolve().parent.parent / 'scripts' / 'check_complexity.py')
cc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cc)


def test_function_scores_qualifies_methods_and_numbers_repeats():
    structure = {
        'classes': [{'name': 'A', 'line': 1, 'line_end': 10},
                    {'name': 'B', 'line': 3, 'line_end': 6}],
        'functions': [{'name': 'f', 'line': 2, 'complexity': 5},
                      {'name': 'f', 'line': 4, 'complexity': 7},
                      {'name': 'g', 'line': 12, 'complexity': 1},
                      {'name': 'g', 'line': 14, 'complexity': 2}],
    }
    assert cc.function_scores(structure) == [('A.f', 5), ('B.f', 7), ('g', 1), ('g#2', 2)]


def test_threshold_comes_from_the_repo_reveal_yaml(tmp_path, monkeypatch):
    cfg = tmp_path / '.reveal.yaml'
    cfg.write_text('rules:\n  C901:\n    threshold: 17\n', encoding='utf-8')
    monkeypatch.setattr(cc, 'CONFIG', cfg)
    monkeypatch.setenv('REVEAL_C901_THRESHOLD', '99')  # user/env config must not leak in
    assert cc.threshold() == 17


def test_compare_reports_regressions_and_stale_entries():
    base = {'a': 25, 'b': 30, 'gone': 22}
    now = {'a': 27, 'b': 28, 'new': 23}
    regressions, stale = cc.compare(base, now)
    assert regressions == [('a', 25, 27), ('new', None, 23)]
    assert stale == [('b', 30, 28), ('gone', 22, None)]


@pytest.fixture
def ratchet(tmp_path, monkeypatch):
    """Point main() at a temp baseline, a fixed threshold and a fake scan result."""
    baseline = tmp_path / 'baseline.json'
    monkeypatch.setattr(cc, 'BASELINE', baseline)
    state = {'limit': 21, 'found': {}}
    monkeypatch.setattr(cc, 'threshold', lambda: state['limit'])
    monkeypatch.setattr(cc, 'scan', lambda limit: state['found'])

    def run(found, base=None, argv=(), limit=21, base_limit=21):
        state['found'], state['limit'] = found, limit
        if base is not None:
            baseline.write_text(json.dumps({'threshold': base_limit, 'functions': base}),
                                encoding='utf-8')
        return cc.main(list(argv))
    run.stored = lambda: json.loads(baseline.read_text(encoding='utf-8'))
    return run


def test_main_passes_at_baseline(ratchet, capsys):
    assert ratchet({'a': 25}, {'a': 25}) == 0
    assert 'complexity ratchet OK' in capsys.readouterr().out


def test_main_fails_when_a_frozen_function_grows(ratchet, capsys):
    assert ratchet({'a': 26}, {'a': 25}) == 1
    assert 'a: 25 -> 26' in capsys.readouterr().out


def test_main_fails_when_a_new_function_crosses_the_threshold(ratchet, capsys):
    assert ratchet({'a': 25, 'b': 22}, {'a': 25}) == 1
    assert 'b: new -> 22' in capsys.readouterr().out


def test_main_fails_on_stale_baseline_so_scores_only_fall(ratchet, capsys):
    assert ratchet({}, {'a': 25}) == 1
    out = capsys.readouterr().out
    assert 'under threshold' in out and '--update-baseline' in out


def test_main_fails_when_the_threshold_changed(ratchet, capsys):
    assert ratchet({'a': 25}, {'a': 25}, limit=22) == 1
    assert 'baseline was taken at 21' in capsys.readouterr().out


def test_update_baseline_lowers_scores(ratchet):
    assert ratchet({'a': 23}, {'a': 25}, ['--update-baseline']) == 0
    assert ratchet.stored() == {'threshold': 21, 'functions': {'a': 23}}


def test_update_baseline_accepts_a_move_that_does_not_add_complexity(ratchet):
    assert ratchet({'moved': 25}, {'a': 25}, ['--update-baseline']) == 0
    assert ratchet.stored()['functions'] == {'moved': 25}


@pytest.mark.parametrize('found', [
    {'a': 26},              # a frozen function grew
    {'a': 25, 'b': 22},     # a new offender with nothing removed
    {'moved': 30},          # a "move" that also added complexity
])
def test_update_baseline_refuses_to_raise(ratchet, found):
    assert ratchet(found, {'a': 25}, ['--update-baseline']) == 1
    assert ratchet.stored()['functions'] == {'a': 25}


def test_update_baseline_refuses_a_higher_threshold(ratchet):
    assert ratchet({}, {'a': 25}, ['--update-baseline'], limit=30) == 1
    assert ratchet.stored()['threshold'] == 21
