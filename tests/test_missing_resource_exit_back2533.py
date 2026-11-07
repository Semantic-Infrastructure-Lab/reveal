"""A path that does not exist is an invalid resource, exit 2, on legacy URI operations too (BACK-2533).

D6 and rule 9: git:///no/such/path answered 'not applicable: Not a git repository', exit 0, and
markdown:///no/such/ printed 'Path not found' with exit 1, the findings code. git:// keeps its genuine
decline (exit 0) for a directory that exists outside every repository, and a path missing on disk
inside a repository is still read at a ref.
"""
import json
import subprocess

import pytest

from conftest import _run_reveal_direct


@pytest.fixture
def outside(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'plain').mkdir()
    return tmp_path


@pytest.mark.parametrize('scheme', ['git', 'markdown'])
def test_a_missing_path_exits_2(outside, scheme):
    missing = (outside / 'no_such_zz_2533').as_posix()
    result = _run_reveal_direct(f'{scheme}://{missing}')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert f'Error ({scheme}://): Path not found:' in result.stderr
    assert result.stdout == ''
    payload = json.loads(_run_reveal_direct(f'{scheme}://{missing}', '--format', 'json').stdout)
    assert payload['meta']['errors'][0]['code'] == 'invalid_request'


def test_an_existing_directory_outside_a_repository_still_declines(outside):
    """Control: the genuine not-applicable answer for a real directory with no repository stays exit 0."""
    result = _run_reveal_direct(f"git://{(outside / 'plain').as_posix()}")
    assert result.returncode == 0, result.stderr
    assert 'Not a git repository' in result.stdout + result.stderr


def test_a_deleted_file_inside_a_repository_still_reads_its_history(outside):
    """Control: a path gone from disk inside a repository is valid (history, a file at a ref)."""
    repo = outside / 'repo'
    repo.mkdir()
    env = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com', 'PATH': '/usr/bin:/bin'}
    git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True, env=env)  # noqa: E731
    git('init', '-q')
    (repo / 'gone.txt').write_text('x\n', encoding='utf-8')
    git('add', 'gone.txt')
    git('commit', '-q', '-m', 'add')
    git('rm', '-q', 'gone.txt')
    git('commit', '-q', '-m', 'remove')
    result = _run_reveal_direct(f"git://{(repo / 'gone.txt').as_posix()}?type=history")
    assert result.returncode == 0, result.stderr
    assert 'File History' in result.stdout
