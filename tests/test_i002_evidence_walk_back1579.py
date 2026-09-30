"""BACK-1579: I002 builds its import graph from the evidence walk, not a bare rglob('*').

An in-tree .venv (thousands of .py files that ``check`` itself never checks) pushed a small
project over the cycle-detection limit, so a real a.py <-> b.py cycle went unreported.
"""
import pytest

from conftest import _run_reveal_direct
from reveal.rules.imports import I002 as i002_module


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / 'a.py').write_text('import b\n\n\ndef fa():\n    return b.fb\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('import a\n\n\ndef fb():\n    return a.fa\n', encoding='utf-8')
    site = tmp_path / '.venv' / 'lib' / 'site-packages' / 'junk'
    site.mkdir(parents=True)
    for i in range(12):
        (site / f'm{i}.py').write_text(f'x = {i}\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVEAL_I002_CYCLE_LIMIT', '10')  # 2 real files, 12 in .venv
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    monkeypatch.setattr(i002_module, '_graph_cache', {})
    return tmp_path


def _i002(*args):
    result = _run_reveal_direct('check', '.', '--select', 'I002', *args)
    return result.stdout + result.stderr


def test_a_venv_does_not_push_the_graph_over_the_cycle_limit(project):
    out = _i002()
    assert 'cycle-detection threshold' not in out
    assert 'a.py:1:1' in out and 'b.py:1:1' in out


def test_the_limit_still_trips_on_real_source(project):
    """Positive control: the same limit does trip when the files are real source."""
    for i in range(12):
        (project / f'real{i}.py').write_text(f'y = {i}\n', encoding='utf-8')
    assert 'cycle-detection threshold' in _i002()


def test_exclude_narrows_the_report_not_the_graph(project):
    """Evidence walk: --exclude b.py stops b.py being checked, but a.py's cycle through it
    is still a cycle."""
    out = _i002('--exclude', 'b.py')
    assert 'a.py:1:1' in out and 'b.py:1:1' not in out


def test_fingerprint_and_pass_a_select_the_same_files(project):
    supported = i002_module.get_all_extensions()
    files = sorted(p.name for p in i002_module._graph_source_files(project, supported))
    assert files == ['a.py', 'b.py']
