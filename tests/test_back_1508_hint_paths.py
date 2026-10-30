"""BACK-1508: next-step hints must run from the cwd as printed."""

import os

from reveal.utils.formatting import cwd_path


def test_cwd_path_joins_the_scan_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cwd_path('pkg', 'mod.py') == os.path.join('pkg', 'mod.py')
    assert cwd_path('.', 'mod.py') == 'mod.py'
    assert cwd_path(str(tmp_path / 'pkg'), 'mod.py') == os.path.join('pkg', 'mod.py')


def test_cwd_path_outside_cwd_stays_absolute(tmp_path, monkeypatch):
    (tmp_path / 'here').mkdir()
    monkeypatch.chdir(tmp_path / 'here')
    other = str(tmp_path / 'there')
    assert cwd_path(other, 'mod.py') == os.path.join(other, 'mod.py')




def test_overview_navigation_keeps_the_target_path(tmp_path, monkeypatch):
    import shlex
    from reveal.adapters.overview import OverviewAdapter
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'mod.py').write_text('x = 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    body = OverviewAdapter('pkg').get_structure()
    target = shlex.split(body['next_steps'][0]['command'])[1].partition('?')[0]
    assert target == 'imports://pkg'
