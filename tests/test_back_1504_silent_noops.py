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


def test_calls_depth_on_rank_is_refused(pkg):
    # ?callees takes depth since BACK-2066 (a level-by-level walk); rank does not read it, so the request is refused
    # before the adapter is built (BACK-2656), no longer warned on stderr.
    from reveal import api
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError, match="control 'depth' is not read by this answer"):
        api.query(f'calls://{pkg}?rank=callers&depth=3')


@pytest.mark.parametrize('query', ['target=leaf&depth=2', 'root=top&depth=2', 'callees=top',
                                   'callees=top&depth=3'])
def test_calls_depth_where_it_applies_is_silent(pkg, capsys, query):
    CallsAdapter(str(pkg), query).get_structure()
    assert "'depth'" not in capsys.readouterr().err


def test_surface_unknown_type_is_an_error(pkg):
    with pytest.raises(ValueError, match=r"kind must be one of .*got 'routes'"):  # type is kind's legacy word (BACK-2623)
        SurfaceAdapter(str(pkg), 'type=routes').get_structure()


def test_surface_subcommand_rejects_unknown_type(pkg):
    proc = subprocess.run([sys.executable, '-m', 'reveal', 'surface', str(pkg), '--type', 'routes'],
                          capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 2
    assert "kind must be one of" in proc.stderr and "routes" in proc.stderr


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


def test_git_file_filter_without_history_is_refused(repo, monkeypatch):
    # A file's content reads no commit filter: the request is refused before the adapter is built (BACK-2656), no
    # longer warned on stderr; the filter is named as typed beside the control it reached.
    from reveal import api
    from reveal.errors import RequestValidationError
    monkeypatch.chdir(repo)
    with pytest.raises(RequestValidationError,
                       match=r"control 'where' \(message~=fix\) is not read by this answer \(git_file_structure"):
        api.query('git://a.py?message~=fix')


def test_git_file_filter_with_history_answers(repo, monkeypatch):
    from reveal import api
    monkeypatch.chdir(repo)
    result = api.query('git://a.py?view=history&message~=fix')
    assert result['type'] == 'git_file_history' and [row['message'] for row in result['commits']] == ['fix: first']
