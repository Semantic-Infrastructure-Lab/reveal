"""BACK-1504: three query forms answered as if a parameter had been applied.

- calls://?callees=X&depth=N ignored depth (only ?target/?root walk levels).
- git://FILE?message~=X without type=history showed the file and filtered nothing.
- surface type=<unknown> filtered every entry out and reported "0 entries".
"""

import subprocess
import sys

import pytest

from reveal.adapters.calls.adapter import CallsAdapter
from reveal.adapters.surface import SurfaceAdapter

pytestmark = pytest.mark.component


@pytest.fixture
def pkg(tmp_path):
    (tmp_path / 'mod.py').write_text(
        'def leaf():\n    pass\n\n\ndef mid():\n    leaf()\n\n\ndef top():\n    mid()\n',
        encoding='utf-8')
    return tmp_path


def test_calls_depth_on_callees_warns(pkg, capsys):
    CallsAdapter(str(pkg), 'callees=top&depth=3').get_structure()
    err = capsys.readouterr().err
    assert "'depth'" in err and '?root=<name>&depth=N' in err


@pytest.mark.parametrize('query', ['target=leaf&depth=2', 'root=top&depth=2', 'callees=top'])
def test_calls_depth_where_it_applies_is_silent(pkg, capsys, query):
    CallsAdapter(str(pkg), query).get_structure()
    assert "'depth'" not in capsys.readouterr().err


def test_surface_unknown_type_is_an_error(pkg):
    with pytest.raises(ValueError, match=r"unknown type='routes'"):
        SurfaceAdapter(str(pkg), 'type=routes').get_structure()


def test_surface_subcommand_rejects_unknown_type(pkg):
    proc = subprocess.run([sys.executable, '-m', 'reveal', 'surface', str(pkg), '--type', 'routes'],
                          capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 2
    assert "invalid choice: 'routes'" in proc.stderr


@pytest.fixture
def repo(tmp_path):
    pygit2 = pytest.importorskip('pygit2')
    repo = pygit2.init_repository(str(tmp_path))
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    repo.index.add('a.py')
    repo.index.write()
    sig = pygit2.Signature('T', 't@example.com')
    repo.create_commit('HEAD', sig, sig, 'fix: first', repo.index.write_tree(), [])
    return tmp_path


def test_git_file_filter_without_history_warns(repo, capsys, monkeypatch):
    from reveal.adapters.git.adapter import GitAdapter
    monkeypatch.chdir(repo)
    GitAdapter('a.py', query={'message~': 'fix'})
    err = capsys.readouterr().err
    assert '[message]' in err and 'add ?type=history' in err


def test_git_file_filter_with_history_is_silent(repo, capsys, monkeypatch):
    from reveal.adapters.git.adapter import GitAdapter
    monkeypatch.chdir(repo)
    GitAdapter('a.py', query={'type': 'history', 'message~': 'fix'})
    assert 'add ?type=history' not in capsys.readouterr().err
