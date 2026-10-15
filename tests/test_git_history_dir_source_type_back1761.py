"""BACK-1761: ``?type=history&bucket=...`` on a directory names it a directory.

``files.get_file_timeline`` hard-coded ``source_type='file'``. The non-bucket directory
history (``files.get_file_history`` with ``is_dir``) says ``directory``; the timeline now
uses the same value, and keeps ``file`` for a file.
"""

import json
import subprocess

import pytest

pygit2 = pytest.importorskip('pygit2')

from reveal.adapters.git import GitAdapter  # noqa: E402

_CFG = ['-c', 'user.name=T', '-c', 'user.email=t@example.com']


def _git(repo, *args):
    subprocess.run(['git', '-C', str(repo), *_CFG, *args], check=True,
                   capture_output=True, timeout=60)


@pytest.fixture
def repo_path(tmp_path):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True, timeout=60)
    (tmp_path / 'sub' / 'deep').mkdir(parents=True)
    f = tmp_path / 'sub' / 'deep' / 'f.txt'
    f.write_text('a\n', encoding='utf-8')
    _git(tmp_path, 'add', '.')
    _git(tmp_path, 'commit', '-q', '-m', 'one')
    f.write_text('a\nb\n', encoding='utf-8')
    _git(tmp_path, 'commit', '-q', '-am', 'two')
    return tmp_path


def _structure(repo_path, subpath, query):
    return GitAdapter(path=str(repo_path), subpath=subpath,
                      query=dict(query)).get_structure()


def test_directory_timeline_source_type_is_directory(repo_path):
    result = _structure(repo_path, 'sub/deep', {'type': 'history', 'bucket': 'month'})
    assert result['type'] == 'git_timeline'
    assert result['source_type'] == 'directory'
    assert result['commit_count'] == 2


def test_directory_timeline_matches_directory_history_spelling(repo_path):
    history = _structure(repo_path, 'sub/deep', {'type': 'history'})
    timeline = _structure(repo_path, 'sub/deep', {'type': 'history', 'bucket': 'week'})
    assert timeline['source_type'] == history['source_type']


# Negative controls.

def test_file_timeline_source_type_stays_file(repo_path):
    result = _structure(repo_path, 'sub/deep/f.txt', {'type': 'history', 'bucket': 'month'})
    assert result['source_type'] == 'file'
    assert result['commit_count'] == 2


def test_directory_history_without_bucket_unchanged(repo_path):
    result = _structure(repo_path, 'sub/deep', {'type': 'history'})
    assert result['type'] == 'git_directory_history'
    assert result['source_type'] == 'directory'
    assert result['count'] == 2
    json.dumps(result, default=str)
