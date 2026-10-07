"""BACK-1738: `reveal review` names the files its hotspot step could not analyze.

Since BACK-1718 a dead stats:// pool worker no longer fails the run: the lost file goes
through stats' failure channel (a ``meta.warnings`` entry of type ``analysis_failed``)
and is left out of the ranking. overview:// and hotspots:// surface that warning; the
review command read only the hotspot list, so the file dropped out of it silently
(before BACK-1718 the same death printed "hotspot analysis failed").
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.stats import adapter as stats_adapter

# The real dying-worker harness (a user rule that ends its pool worker on one file).
from test_pool_start_methods_back1704 import DYING, METHODS, N_FILES, _need, _run, work  # noqa: F401

LOST = 'm2.py'
_SIMPLE = 'def f(x):\n    if x:\n        return 1\n    return 2\n'


def _tree(tmp_path, n=4):
    root = tmp_path / 'tree'
    root.mkdir()
    for i in range(n):
        (root / f'm{i}.py').write_text(_SIMPLE, encoding='utf-8')
    return root


def _review(root, fmt):
    result = _run_reveal_direct('review', str(root), '--format', fmt)
    return result.returncode, result.stdout


@pytest.fixture
def stats_loses_one_file(monkeypatch):
    """stats:// analysis fails for LOST through its own failure channel (the record a
    raising analyzer or a dead worker yields), the rest analyze normally."""
    real = stats_adapter._analyze_file_worker

    def worker(args):
        if args[0].endswith(LOST):
            return {'analysis_failed': 'BrokenProcessPool: worker died', 'path': args[0]}
        return real(args)
    monkeypatch.setattr(stats_adapter, '_analyze_file_worker', worker)


def test_review_json_names_the_file_hotspots_lost(tmp_path, stats_loses_one_file):
    code, out = _review(_tree(tmp_path), 'json')
    report = json.loads(out)
    lost, = [w for w in report['meta']['warnings'] if w['type'] == 'analysis_failed']
    assert lost['count'] == 1 and lost['files'] == [LOST]
    assert lost['message'].startswith('hotspots: 1 file(s) failed analysis')
    assert LOST not in {h.get('file') for h in report['sections']['hotspots']}


def test_review_text_names_the_file_hotspots_lost(tmp_path, stats_loses_one_file):
    _, out = _review(_tree(tmp_path), 'text')
    assert 'Caveats:' in out
    assert f'hotspots: 1 file(s) failed analysis and are not counted: {LOST}' in out


def test_review_negative_control_no_failure_no_caveat(tmp_path):
    root = _tree(tmp_path)
    code, out = _review(root, 'json')
    report = json.loads(out)
    warnings = report.get('meta', {}).get('warnings', [])
    assert not [w for w in warnings if w['type'] == 'analysis_failed']
    _, text = _review(root, 'text')
    assert 'Caveats:' not in text and 'failed analysis' not in text


def test_review_is_incomplete_when_hotspots_lost_a_file(tmp_path, stats_loses_one_file):
    """A review that could not rank every file did not cover everything: incomplete/3,
    like a quality pass that could not check every file (Scott, 2026-10-07), so a CI
    gate reading only the exit code sees it."""
    root = _tree(tmp_path)
    code, out = _review(root, 'json')
    report = json.loads(out)
    assert (code, report['overall_status'], report['exit_code']) == (3, 'incomplete', 3)
    _, text = _review(root, 'text')
    assert 'Recommendation: Review incomplete' in text and 'hotspot' in text.split('Recommendation:')[1]


def test_review_negative_control_clean_tree_is_not_incomplete(tmp_path):
    code, out = _review(_tree(tmp_path), 'json')
    assert json.loads(out)['overall_status'] != 'incomplete' and code != 3


def test_review_blocking_issue_still_fails_when_hotspots_lost_a_file(
        tmp_path, stats_loses_one_file, monkeypatch):
    """fail/2 outranks incomplete/3, as it does for a quality pass that missed files."""
    from reveal.cli.commands import review
    monkeypatch.setattr(review, '_run_check', lambda *a, **k: [
        {'file': 'm0.py', 'line': 1, 'rule': 'S001', 'severity': 'critical', 'message': 'x'}])
    code, out = _review(_tree(tmp_path), 'json')
    assert (code, json.loads(out)['overall_status']) == (2, 'fail')


def test_single_file_review_names_a_file_hotspots_could_not_analyze(tmp_path, monkeypatch):
    """A file target (and each file of a diff-scoped review) is ranked on its own;
    stats:// answers a single file whose analysis failed with an error, which the
    hotspot step dropped silently."""
    root = _tree(tmp_path)
    real = stats_adapter.analyze_file
    monkeypatch.setattr(stats_adapter, 'analyze_file', lambda path, fn: (
        {'analysis_failed': 'ValueError: boom', 'path': str(path)} if path.name == LOST else real(path, fn)))
    _, out = _review(root / LOST, 'json')
    report = json.loads(out)
    lost, = [w for w in report['meta']['warnings'] if w['type'] == 'analysis_failed']
    assert LOST in lost['message'] and 'analysis failed: ValueError: boom' in lost['message']
    assert report['sections']['hotspots'] == []


@pytest.mark.parametrize('method', METHODS)
def test_review_names_the_file_a_dead_stats_worker_lost(work, method):  # noqa: F811
    """The real thing: a pool worker dies on one file. review still runs to the end, and
    its hotspot caveat names the dead file; collateral files may be named with it."""
    _need(method)
    proc, calls = _run(work, method, 2, 'review', 'tree', '--select', 'B001,Z901',
                       '--format', 'json', die=True)
    assert calls and set(calls) <= {f'{method} True'}, sorted(set(calls))
    report = json.loads(proc.stdout)
    lost, = [w for w in report['meta']['warnings'] if w['type'] == 'analysis_failed']
    assert DYING in lost['files'], lost
    assert 1 <= lost['count'] <= N_FILES
    assert 'hotspot analysis failed' not in proc.stderr
