"""BACK-1552: ?type=ownership&limit=N counts the newest N commits and says so."""
import json
import os
import subprocess
import sys

import pytest

pytest.importorskip('pygit2')

N = 5  # commits in the fixture history, all by one author touching a.txt


@pytest.fixture(scope='module')
def repo(tmp_path_factory):
    path = tmp_path_factory.mktemp('ownWindow')
    env = {**os.environ, 'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t',
           'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@t'}

    def git(*args):
        subprocess.run(['git', *args], cwd=path, check=True, capture_output=True,
                       env=env, timeout=60)

    git('init', '-q')
    for i in range(1, N + 1):
        (path / 'a.txt').write_text(f"{i}\n", encoding='utf-8')
        git('add', 'a.txt')
        git('commit', '-qm', f"c{i}")
    return path


def run(repo, uri, fmt):
    proc = subprocess.run([sys.executable, '-m', 'reveal.main', uri, '--format', fmt],
                          cwd=repo, capture_output=True, text=True, encoding='utf-8',
                          timeout=120)
    assert proc.returncode == 0, proc.stderr
    return proc


def cuts(data):
    return [w for w in data.get('meta', {}).get('warnings', []) if w.get('type') == 'truncated']


def test_limit_below_history_discloses_window_in_json(repo):
    data = json.loads(run(repo, 'git://.?type=ownership&limit=2', 'json').stdout)
    assert data['total_commits'] == 2
    [cut] = cuts(data)
    assert (cut['field'], cut['shown'], cut['total'], cut['exact']) == ('commits', 2, 3, False)
    assert 'newest 2' in cut['message']
    assert data['scope']['history_window'] == {'limit': 2, 'commits_counted': 2, 'complete': False}


def test_limit_below_history_discloses_window_in_text(repo):
    out = run(repo, 'git://.?type=ownership&limit=2', 'text').stdout
    assert 'newest 2 commits' in out
    assert 'Truncated commits: showing 2 of 3+' in out


@pytest.mark.parametrize('limit', [N, N + 10])
def test_limit_covering_history_claims_no_cut(repo, limit):
    """Negative control: a window that reaches the root commit is the whole history."""
    data = json.loads(run(repo, f'git://.?type=ownership&limit={limit}', 'json').stdout)
    assert data['total_commits'] == N
    assert cuts(data) == []
    assert data['scope']['history_window']['complete'] is True
    out = run(repo, f'git://.?type=ownership&limit={limit}', 'text').stdout
    assert 'newest' not in out and 'Truncated' not in out


def test_no_limit_has_no_window(repo):
    data = json.loads(run(repo, 'git://.?type=ownership', 'json').stdout)
    assert cuts(data) == []
    assert 'scope' not in data
