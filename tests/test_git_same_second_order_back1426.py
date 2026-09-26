"""BACK-1426: commits made in the same second must list newest-first, like `git log`.

GIT_SORT_TIME alone left equal timestamps in arbitrary order: three commits made in one
second came back c3, c1, c2 from git://, git://FILE and git://DIR history.
"""
import json
import os
import subprocess
import sys

import pytest

pytest.importorskip('pygit2')

FROZEN = {'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@t', 'GIT_COMMITTER_NAME': 't',
          'GIT_COMMITTER_EMAIL': 't@t', 'GIT_AUTHOR_DATE': '2026-01-01T00:00:00',
          'GIT_COMMITTER_DATE': '2026-01-01T00:00:00'}
N = 8  # enough same-second commits that an arbitrary tie order is very unlikely to match


@pytest.fixture(scope='module')
def repo(tmp_path_factory):
    path = tmp_path_factory.mktemp('sameSecond')
    env = {**os.environ, **FROZEN}

    def git(*args):
        subprocess.run(['git', *args], cwd=path, check=True, capture_output=True, env=env)

    git('init', '-q')
    (path / 'sub').mkdir()
    for i in range(1, N + 1):
        (path / 'sub' / 'f.txt').write_text(f"{i}\n", encoding='utf-8')
        git('add', '-A')
        git('commit', '-qm', f"c{i}")
    return path


EXPECTED = [f"c{i}" for i in range(N, 0, -1)]


def messages(repo, uri):
    proc = subprocess.run([sys.executable, '-m', 'reveal.main', uri, '--format', 'json'],
                          cwd=repo, capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    commits = data.get('commits') or data.get('recent_commits') or data.get('history') or []
    return [c['message'].strip() for c in commits]


@pytest.mark.parametrize('uri', ['git://.?type=history', 'git://sub/f.txt?type=history',
                                 'git://sub?type=history'])
def test_history_lists_same_second_commits_newest_first(repo, uri):
    assert messages(repo, uri)[:N] == EXPECTED


def test_matches_git_log(repo):
    log = subprocess.run(['git', 'log', '--format=%s'], cwd=repo, capture_output=True,
                         text=True, encoding='utf-8', check=True).stdout.split()
    assert log == EXPECTED
