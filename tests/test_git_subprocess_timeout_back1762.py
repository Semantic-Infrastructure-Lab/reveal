"""BACK-1762: the git subprocess calls in git/files.py carry a timeout.

``get_file_diff`` and ``_commit_diff_contains`` ran ``git diff`` with no ``timeout=``,
so a hung git (network filesystem, stuck lock) hung reveal. On timeout they behave like
their missing-binary siblings (BACK-1166): ``get_file_diff`` raises a ValueError that
names the cause, the content search records ``content_search_unavailable``.
"""

import subprocess

import pytest

pygit2 = pytest.importorskip('pygit2')

from reveal.adapters.git import GitAdapter  # noqa: E402
from reveal.adapters.git import files  # noqa: E402

_ENV_CFG = ['-c', 'user.name=T', '-c', 'user.email=t@example.com']


def _git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *_ENV_CFG, *args], check=True,
                   capture_output=True, timeout=60)


@pytest.fixture
def repo_path(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, timeout=60)
    (tmp_path / 'a.txt').write_text('one\n', encoding='utf-8')
    _git(tmp_path, 'add', 'a.txt')
    _git(tmp_path, 'commit', '-q', '-m', 'first')
    (tmp_path / 'a.txt').write_text('one\ntwo\n', encoding='utf-8')
    _git(tmp_path, 'commit', '-q', '-am', 'second')
    return tmp_path


def _open(repo_path):
    return pygit2.Repository(pygit2.discover_repository(str(repo_path)))


def _recording_run(calls):
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if cmd and cmd[0] == 'git':
            calls.append(kwargs)
        return real_run(cmd, *args, **kwargs)
    return run


def _timing_out(cmd, *args, **kwargs):
    raise subprocess.TimeoutExpired(cmd, kwargs.get('timeout') or 0)


def test_get_file_diff_passes_a_timeout(repo_path, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, 'run', _recording_run(calls))
    out = files.get_file_diff(_open(repo_path), 'HEAD', 'a.txt', {})
    assert '+two' in out['diff_text']
    assert calls and all(isinstance(c.get('timeout'), (int, float)) and c['timeout'] > 0 for c in calls)


def test_commit_diff_contains_passes_a_timeout(repo_path, monkeypatch):
    repo = _open(repo_path)
    calls = []
    monkeypatch.setattr(subprocess, 'run', _recording_run(calls))
    assert files._commit_diff_contains(repo, repo.revparse_single('HEAD'), '', 'two') is True
    assert calls and all(isinstance(c.get('timeout'), (int, float)) and c['timeout'] > 0 for c in calls)


def test_get_file_diff_timeout_is_a_clear_valueerror(repo_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', _timing_out)
    with pytest.raises(ValueError, match='timed out'):
        files.get_file_diff(_open(repo_path), 'HEAD', 'a.txt', {})


def test_content_search_timeout_is_disclosed(repo_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', _timing_out)
    result = GitAdapter(path=str(repo_path), subpath='a.txt',
                        query={'type': 'history', 'content~': 'two'}).get_structure()
    assert result['count'] == 0
    assert any(w.get('type') == 'content_search_unavailable' for w in result.get('warnings', []))


# Negative control: the successful path is unchanged.

def test_diff_and_content_search_results_unchanged(repo_path):
    repo = _open(repo_path)
    diff = files.get_file_diff(repo, 'HEAD', 'a.txt', {})['diff_text']
    assert '+two' in diff and '-one' not in diff
    result = GitAdapter(path=str(repo_path), subpath='a.txt',
                        query={'type': 'history', 'content~': 'two'}).get_structure()
    assert result['count'] == 1
    assert not any(w.get('type') == 'content_search_unavailable' for w in result.get('warnings', []))
