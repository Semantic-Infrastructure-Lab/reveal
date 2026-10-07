"""BACK-1690: an absolute git:// directory inside a work tree scopes to that directory.

``git:///abs/repo/sub?type=ownership`` answered for the whole repository ("Ownership
(Repository): .") because the parser read every absolute directory as a repo root,
while the relative spelling ``git://sub?type=ownership`` scoped to ``sub``. The two
spellings of one directory must give the same answer; the work-tree root itself,
the relative spelling and a path outside any repo keep today's output.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip('pygit2')

from conftest import _run_reveal_direct  # noqa: E402

pytestmark = [
    pytest.mark.component,
    pytest.mark.skipif(shutil.which('git') is None, reason='git not installed'),
]

# Every git:// view that takes a path (help://schemas/git: type=history|blame|diff|
# ownership, the log alias, the bucketed timeline and the default file-content view).
VIEWS = ['?type=ownership', '?type=history', '?type=log', '?type=history&bucket=month',
         '?type=blame', '?type=diff', '']


def _git(root: Path, *args: str, author: str = 'alice', date: str = '2026-01-01T12:00:00') -> None:
    env = dict(os.environ, GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    subprocess.run(
        ['git', '-C', str(root), '-c', f'user.name={author}', '-c', f'user.email={author}@example.com',
         '-c', 'commit.gpgsign=false', '-c', 'core.excludesFile=', *args],
        check=True, capture_output=True, text=True, encoding='utf-8', env=env, timeout=30,
    )


def _commit(root: Path, rel: str, text: str, message: str, author: str, date: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    _git(root, 'add', rel)
    _git(root, 'commit', '-q', '-m', message, author=author, date=date)


@pytest.fixture
def layout(tmp_path):
    """tmp/repo: 4 commits, 2 of them under sub/, 1 under sub/deep/; tmp itself is no repo."""
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-q')
    _commit(repo, 'top.py', 'a = 1\n', 'root one', 'alice', '2026-01-01T12:00:00')
    _commit(repo, 'sub/a.py', 'b = 1\n', 'sub one', 'bob', '2026-01-02T12:00:00')
    _commit(repo, 'sub/deep/b.py', 'c = 1\n', 'deep one', 'bob', '2026-01-03T12:00:00')
    _commit(repo, 'top.py', 'a = 2\n', 'root two', 'alice', '2026-01-04T12:00:00')
    (repo / 'untracked').mkdir()
    (repo / 'untracked' / 'u.py').write_text('u = 1\n', encoding='utf-8')
    (tmp_path / 'norepo').mkdir()
    return tmp_path, repo


def _reveal(cwd: Path, uri: str, *flags: str):
    old = os.getcwd()
    os.chdir(cwd)
    try:
        return _run_reveal_direct(uri, *flags)
    finally:
        os.chdir(old)


def _abs(path: Path) -> str:
    return path.as_posix()


def _answer(result, typed: str):
    """(exit, JSON, stderr); an error envelope's ``source`` echoes the typed resource, so it is checked and dropped."""
    data = json.loads(result.stdout)
    if 'error' in data:
        assert data.pop('source') == typed
    return result.returncode, data, result.stderr


@pytest.mark.parametrize('view', VIEWS)
@pytest.mark.parametrize('sub', ['sub', 'sub/deep', 'untracked'])
def test_absolute_subdir_answers_like_the_relative_spelling(layout, sub, view):
    parent, repo = layout
    typed = f'{_abs(repo)}/{sub}{view}'
    relative = _reveal(repo, f'git://{sub}{view}', '--format', 'json')
    absolute = _reveal(parent, f'git://{typed}', '--format', 'json')
    assert _answer(absolute, typed) == _answer(relative, f'{sub}{view}')


@pytest.mark.parametrize('sub, commits, messages', [
    ('sub', 2, ['deep one', 'sub one']),
    ('sub/deep', 1, ['deep one']),
])
def test_absolute_subdir_scope_names_the_subdir(layout, sub, commits, messages):
    parent, repo = layout
    uri = f'git://{_abs(repo)}/{sub}'
    owners = _reveal(parent, f'{uri}?type=ownership', '--format', 'json')
    data = json.loads(owners.stdout)
    assert owners.returncode == 0
    assert (data['path'], data['source_type'], data['total_commits']) == (sub, 'directory', commits)
    assert [a['name'] for a in data['authors']] == ['bob']

    history = json.loads(_reveal(parent, f'{uri}?type=history', '--format', 'json').stdout)
    assert (history['path'], history['source_type']) == (sub, 'directory')
    assert [c['message'] for c in history['commits']] == messages

    text = _reveal(parent, f'{uri}?type=ownership')
    assert f'Ownership (Directory): {sub} @ HEAD' in text.stdout
    assert f'Commits: {commits} ' in text.stdout


def test_overview_of_absolute_subdir_lists_its_own_commits(layout):
    """overview:// composes git:// with the absolute directory; its log was repo-wide too."""
    parent, repo = layout
    data = json.loads(_reveal(parent, f'overview://{_abs(repo)}/sub', '--format', 'json').stdout)
    assert [c['message'] for c in data['git_log']] == ['deep one', 'sub one']


@pytest.mark.parametrize('view', VIEWS)
@pytest.mark.parametrize('spelling', ['root', 'root/', 'root/.git'])
def test_work_tree_root_keeps_the_repository_view(layout, spelling, view):
    """Negative control: the work tree (or its .git dir) spelled absolutely is the repo, byte for byte."""
    parent, repo = layout
    target = _abs(repo) + spelling[len('root'):]
    expected = _reveal(repo, f'git://.{view}')
    actual = _reveal(parent, f'git://{target}{view}')
    assert (actual.returncode, actual.stdout, actual.stderr) == \
        (expected.returncode, expected.stdout, expected.stderr)


def test_repository_view_counts_every_commit(layout):
    """Negative control: the root's ownership is repo-wide (4 commits, both authors)."""
    parent, repo = layout
    data = json.loads(_reveal(parent, f'git://{_abs(repo)}?type=ownership', '--format', 'json').stdout)
    assert (data['source_type'], data['total_commits']) == ('repository', 4)
    assert sorted(a['name'] for a in data['authors']) == ['alice', 'bob']


def test_relative_spelling_is_unchanged(layout):
    """Negative control: the spelling that always scoped correctly still does."""
    _, repo = layout
    data = json.loads(_reveal(repo, 'git://sub?type=ownership', '--format', 'json').stdout)
    assert (data['path'], data['source_type'], data['total_commits']) == ('sub', 'directory', 2)


def test_absolute_dir_outside_any_repo_is_still_not_applicable(layout):
    """Negative control: no repository above the path says so instead of answering."""
    parent, _ = layout
    target = _abs(parent / 'norepo')
    result = _reveal(parent, f'git://{target}?type=ownership')
    output = result.stdout + result.stderr
    assert f'not applicable: Not a git repository: {target}' in output
    assert 'Ownership' not in output
