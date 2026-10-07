"""BACK-1731: git stdout is split where git splits it, not wherever ``str.splitlines()`` does.

``splitlines()`` also breaks at form feed, NEL (U+0085) and U+2028/U+2029. Two readers
of git stdout used it:

- ``pack --since`` read ``git diff --name-only`` paths, so a changed file whose name holds
  one of those characters was never marked changed (git also C-quotes such a name unless
  ``-z`` is given, which hid it the same way);
- the ``content~=`` commit search read ``git diff`` text, so a pattern after one of those
  characters on a changed line was reported absent.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip('pygit2')

from conftest import _run_reveal_direct  # noqa: E402
from reveal.adapters.pack import _get_changed_files  # noqa: E402

pytestmark = [
    pytest.mark.component,
    pytest.mark.skipif(shutil.which('git') is None, reason='git not installed'),
]

# splitlines() boundaries that are legal inside a POSIX file name and inside a line of text.
SEPARATORS = {'u2028': ' ', 'u2029': ' ', 'nel': '\x85', 'formfeed': '\x0c'}


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@example.com',
         '-c', 'commit.gpgsign=false', '-c', 'core.excludesFile=', *args],
        check=True, capture_output=True, text=True, encoding='utf-8', timeout=30,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-q')
    (repo / 'base.py').write_text('base = 1\n', encoding='utf-8')
    _git(repo, 'add', 'base.py')
    _git(repo, 'commit', '-q', '-m', 'base')
    return repo


def _odd_file(repo: Path, sep: str) -> Path:
    """repo/odd<sep>name.py, or a skip where the filesystem refuses the name (Windows: form feed)."""
    target = repo / f'odd{sep}name.py'
    try:
        target.write_text('odd = 1\n', encoding='utf-8')
    except (OSError, UnicodeEncodeError) as exc:
        pytest.skip(f'filesystem refuses a file name with {sep!r}: {exc}')
    if target.name not in os.listdir(repo):
        pytest.skip(f'filesystem rewrote a file name with {sep!r}')
    return target


@pytest.mark.parametrize('sep', SEPARATORS.values(), ids=SEPARATORS.keys())
def test_changed_file_with_a_splitlines_boundary_in_its_name(tmp_path, sep):
    repo = _repo(tmp_path)
    odd = _odd_file(repo, sep)
    (repo / 'plain.py').write_text('plain = 1\n', encoding='utf-8')
    _git(repo, 'add', '--all')
    _git(repo, 'commit', '-q', '-m', 'odd and plain')

    changed, err = _get_changed_files(repo, 'HEAD~1')
    assert err is None
    assert changed == {str(odd.resolve()), str((repo / 'plain.py').resolve())}


@pytest.mark.parametrize('sep', SEPARATORS.values(), ids=SEPARATORS.keys())
def test_pack_since_marks_the_odd_file_changed(tmp_path, sep):
    repo = _repo(tmp_path)
    odd = _odd_file(repo, sep)
    _git(repo, 'add', '--all')
    _git(repo, 'commit', '-q', '-m', 'odd')

    result = _run_reveal_direct('pack', str(repo), '--since', 'HEAD~1', '--format', 'json')
    data = json.loads(result.stdout)
    flags = {Path(f['path']).name: f['changed'] for f in data['files']}
    assert flags == {odd.name: True, 'base.py': False}
    assert data['meta']['changed_files_count'] == 1


def test_pack_since_negative_control(tmp_path):
    """Negative control: ordinary names (one with a space) were always marked changed."""
    repo = _repo(tmp_path)
    for name in ('plain.py', 'with space.py'):
        (repo / name).write_text('x = 1\n', encoding='utf-8')
    _git(repo, 'add', '--all')
    _git(repo, 'commit', '-q', '-m', 'plain')

    changed, err = _get_changed_files(repo, 'HEAD~1')
    assert err is None
    assert changed == {str((repo / name).resolve()) for name in ('plain.py', 'with space.py')}


@pytest.mark.parametrize('sep', SEPARATORS.values(), ids=SEPARATORS.keys())
def test_content_search_finds_a_pattern_after_a_splitlines_boundary(tmp_path, sep):
    repo = _repo(tmp_path)
    (repo / 'code.py').write_text(f'text = "lead{sep}needle"\n', encoding='utf-8')
    _git(repo, 'add', 'code.py')
    _git(repo, 'commit', '-q', '-m', 'adds needle')

    result = _run_reveal_direct(f'git://{repo.as_posix()}?type=history&content~=needle', '--format', 'json')
    data = json.loads(result.stdout)
    assert [c['message'] for c in data['history']] == ['adds needle']


def test_content_search_negative_control(tmp_path):
    """Negative control: a pattern on an ordinary changed line was always found."""
    repo = _repo(tmp_path)
    (repo / 'code.py').write_text('text = "needle"\n', encoding='utf-8')
    _git(repo, 'add', 'code.py')
    _git(repo, 'commit', '-q', '-m', 'adds needle')

    result = _run_reveal_direct(f'git://{repo.as_posix()}?type=history&content~=needle', '--format', 'json')
    assert [c['message'] for c in json.loads(result.stdout)['history']] == ['adds needle']
