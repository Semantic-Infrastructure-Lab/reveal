"""BACK-1760: a relative git:// spelling of a repository root is that repository.

From the repo's parent, ``git://repo?type=history`` printed "Directory History: ."
with 0 commits (exit 0), ``?type=ownership`` said "Path not found at HEAD: ." and
bare ``git://repo`` said "File not found at HEAD: .": the parser read ``repo`` as a
cwd-relative subpath, which resolves to the repo root ``.``, a path that no commit
touches. The absolute spelling (``git:///abs/repo``, BACK-1690) and the guide's
``git://path/to/repo`` already mean the repository; the relative spelling must answer
exactly like the absolute one. Subdirectories, ``git://.`` and non-repos keep today's output.
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
    pytest.mark.cli,  # the git:// entry point via _run_reveal_direct (BACK-1149)
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
    """tmp/repo (3 commits, 1 under sub/), tmp/other (a second repo), tmp/norepo; tmp is no repo."""
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-q')
    _commit(repo, 'top.py', 'a = 1\n', 'root one', 'alice', '2026-01-01T12:00:00')
    _commit(repo, 'sub/a.py', 'b = 1\n', 'sub one', 'bob', '2026-01-02T12:00:00')
    _commit(repo, 'top.py', 'a = 2\n', 'root two', 'alice', '2026-01-04T12:00:00')
    other = tmp_path / 'other'
    other.mkdir()
    _git(other, 'init', '-q')
    _commit(other, 'o.py', 'o = 1\n', 'other one', 'carol', '2026-02-01T12:00:00')
    (tmp_path / 'norepo').mkdir()
    return tmp_path, repo, other


def _reveal(cwd: Path, uri: str, *flags: str):
    old = os.getcwd()
    os.chdir(cwd)
    try:
        return _run_reveal_direct(uri, *flags)
    finally:
        os.chdir(old)


def _answer(result):
    """(exit, JSON, stderr) without ``source``, which echoes the typed resource for some views."""
    data = json.loads(result.stdout)
    data.pop('source', None)
    return result.returncode, data, result.stderr


@pytest.mark.parametrize('view', VIEWS)
@pytest.mark.parametrize('spelling', ['repo', 'repo/', './repo'])
def test_relative_repo_root_answers_like_the_absolute_spelling(layout, spelling, view):
    parent, repo, _ = layout
    absolute = f'{repo.as_posix()}{view}'
    expected = _reveal(parent, f'git://{absolute}', '--format', 'json')
    actual = _reveal(parent, f'git://{spelling}{view}', '--format', 'json')
    assert _answer(actual) == _answer(expected)


@pytest.mark.parametrize('view', VIEWS)
def test_dotdot_repo_root_answers_like_the_absolute_spelling(layout, view):
    """``../other-repo`` from a sibling directory (the adapter's own parser comment)."""
    _, repo, other = layout
    absolute = f'{repo.as_posix()}{view}'
    expected = _reveal(other, f'git://{absolute}', '--format', 'json')
    actual = _reveal(other, f'git://../repo{view}', '--format', 'json')
    assert _answer(actual) == _answer(expected)


def test_relative_repo_root_counts_every_commit(layout):
    """The symptom itself: history said 0 commits, ownership 'Path not found', the bare view 'File not found'."""
    parent, _, _ = layout
    history = _reveal(parent, 'git://repo?type=history', '--format', 'json')
    data = json.loads(history.stdout)
    assert history.returncode == 0
    assert [c['message'] for c in data['history']] == ['root two', 'sub one', 'root one']

    owners = json.loads(_reveal(parent, 'git://repo?type=ownership', '--format', 'json').stdout)
    assert (owners['source_type'], owners['total_commits']) == ('repository', 3)
    assert sorted(a['name'] for a in owners['authors']) == ['alice', 'bob']

    bare = _reveal(parent, 'git://repo')
    assert bare.returncode == 0
    assert 'not found' not in (bare.stdout + bare.stderr).lower()

    text = _reveal(parent, 'git://repo?type=history')
    assert 'root one' in text.stdout
    assert 'Directory History: .' not in text.stdout


def test_overview_of_relative_repo_root_lists_every_commit(layout):
    """overview:// composes git:// with the same relative spelling."""
    parent, _, _ = layout
    data = json.loads(_reveal(parent, 'overview://repo', '--format', 'json').stdout)
    assert [c['message'] for c in data['git_log']] == ['root two', 'sub one', 'root one']


def test_relative_subdir_of_another_repo_is_unchanged(layout):
    """Negative control: ``repo/sub`` from the parent already scoped to ``sub`` and still does."""
    parent, _, _ = layout
    data = json.loads(_reveal(parent, 'git://repo/sub?type=ownership', '--format', 'json').stdout)
    assert (data['path'], data['source_type'], data['total_commits']) == ('sub', 'directory', 1)
    history = json.loads(_reveal(parent, 'git://repo/sub?type=history', '--format', 'json').stdout)
    assert [c['message'] for c in history['commits']] == ['sub one']


def test_relative_subdir_inside_the_cwd_repo_is_unchanged(layout):
    """Negative control: ``sub`` from inside the repo is that directory, not the repository."""
    _, repo, _ = layout
    data = json.loads(_reveal(repo, 'git://sub?type=ownership', '--format', 'json').stdout)
    assert (data['path'], data['source_type'], data['total_commits']) == ('sub', 'directory', 1)


def test_dot_from_inside_the_repo_is_unchanged(layout):
    """Negative control: ``git://.`` is the repository."""
    _, repo, _ = layout
    data = json.loads(_reveal(repo, 'git://.?type=ownership', '--format', 'json').stdout)
    assert (data['source_type'], data['total_commits']) == ('repository', 3)


def test_absolute_spelling_is_unchanged(layout):
    """Negative control: the spelling that always meant the repository still does."""
    parent, repo, _ = layout
    data = json.loads(_reveal(parent, f'git://{repo.as_posix()}?type=ownership', '--format', 'json').stdout)
    assert (data['source_type'], data['total_commits']) == ('repository', 3)


@pytest.mark.parametrize('spelling', ['norepo', './norepo'])
def test_relative_dir_outside_any_repo_is_still_not_applicable(layout, spelling):
    """Negative control: no repository above the directory says so (naming it as typed) instead of answering."""
    parent, _, _ = layout
    result = _reveal(parent, f'git://{spelling}?type=ownership')
    output = result.stdout + result.stderr
    assert f'not applicable: Not a git repository: {spelling.removeprefix("./")}' in output
    assert 'Ownership' not in output
