"""The gitignore oracle follows edits between host requests (BACK-2117).

``gitignore._ROOT_CACHE`` (directory -> repository root) never expired, and ``_REPO_CACHE``
(root -> ignored paths) lived 10 s, so inside a long-lived host (MCP, ``reveal.api``) a
``git init``, a ``.gitignore`` edit, a ``.git/info/exclude`` edit, a nested ``.gitignore`` edit
or a ``core.excludesFile`` change made between two requests was invisible to the second one.
Each scenario asks the same question in two successive ``host_request()`` blocks around the
edit; the positive control is the cold answer (cache cleared) which must equal the warm one.
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from reveal.utils import gitignore
from reveal.utils.gitignore import GitIgnoreFilter
from reveal.utils.request_cache import host_request

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
        check=True, capture_output=True, text=True, encoding='utf-8', timeout=60,
    ).stdout


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _ask(root: Path, *rels: str) -> dict:
    """One host request: is each path ignored? (directories end in '/')"""
    with host_request():
        flt = GitIgnoreFilter(root)
        return {rel: flt.ignored(root / rel.rstrip('/'), is_dir=rel.endswith('/')) for rel in rels}


def _cold(root: Path, *rels: str) -> dict:
    """The same question with every cache emptied: what a fresh process answers."""
    gitignore.clear_cache()
    return _ask(root, *rels)


@pytest.fixture
def work(tmp_path, monkeypatch):
    # Keep the developer's global excludes file and config out of the verdicts.
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    root = tmp_path.resolve() / 'work'
    root.mkdir()
    return root


@pytest.fixture
def repo(work):
    _git(work, 'init', '-q')
    return work


def test_git_init_between_requests_is_seen(work):
    """(a) A tracked file matching a pattern is ignored by the pattern fallback and kept by git."""
    _write(work, '.gitignore', '*.log\n')
    _write(work, 'a.log', 'x\n')
    assert _ask(work, 'a.log') == {'a.log': True}  # no repository yet: pattern fallback
    _git(work, 'init', '-q')
    _git(work, 'add', '-f', 'a.log')
    warm = _ask(work, 'a.log')
    assert warm == _cold(work, 'a.log') == {'a.log': False}


def test_gitignore_edit_between_requests_is_seen(repo):
    """(b) The root .gitignore gains a pattern."""
    _write(repo, 'x.tmp', 'x\n')
    assert _ask(repo, 'x.tmp') == {'x.tmp': False}
    _write(repo, '.gitignore', '*.tmp\n')
    warm = _ask(repo, 'x.tmp')
    assert warm == _cold(repo, 'x.tmp') == {'x.tmp': True}


def test_info_exclude_edit_between_requests_is_seen(repo):
    """(c) .git/info/exclude gains a pattern."""
    _write(repo, 'y.tmp', 'x\n')
    assert _ask(repo, 'y.tmp') == {'y.tmp': False}
    _write(repo, '.git/info/exclude', '*.tmp\n')
    warm = _ask(repo, 'y.tmp')
    assert warm == _cold(repo, 'y.tmp') == {'y.tmp': True}


def test_nested_gitignore_edit_between_requests_is_seen(repo):
    """(d) A nested .gitignore that existed at the first request is edited."""
    _write(repo, 'sub/.gitignore', '*.bak\n')
    _write(repo, 'sub/a.bak', 'x\n')
    _write(repo, 'sub/b.tmp', 'x\n')
    assert _ask(repo, 'sub/a.bak', 'sub/b.tmp') == {'sub/a.bak': True, 'sub/b.tmp': False}
    _write(repo, 'sub/.gitignore', '*.bak\n*.tmp\n')
    warm = _ask(repo, 'sub/a.bak', 'sub/b.tmp')
    assert warm == _cold(repo, 'sub/a.bak', 'sub/b.tmp') == {'sub/a.bak': True, 'sub/b.tmp': True}


def test_core_excludes_file_change_between_requests_is_seen(repo, tmp_path):
    """(e) core.excludesFile is pointed at a file, and then that file is edited."""
    excludes = tmp_path.resolve() / 'global_excludes'
    excludes.write_text('*.tmp\n', encoding='utf-8')
    _write(repo, 'z.tmp', 'x\n')
    _write(repo, 'z.bak', 'x\n')
    assert _ask(repo, 'z.tmp', 'z.bak') == {'z.tmp': False, 'z.bak': False}
    _git(repo, 'config', 'core.excludesFile', excludes.as_posix())
    assert _ask(repo, 'z.tmp', 'z.bak') == {'z.tmp': True, 'z.bak': False}
    excludes.write_text('*.tmp\n*.bak\n', encoding='utf-8')
    warm = _ask(repo, 'z.tmp', 'z.bak')
    assert warm == _cold(repo, 'z.tmp', 'z.bak') == {'z.tmp': True, 'z.bak': True}


def test_tracking_an_ignored_file_between_requests_is_seen(repo):
    """The index decides tracked status, and git never ignores a tracked file."""
    _write(repo, '.gitignore', '*.tmp\n')
    _write(repo, 'k.tmp', 'x\n')
    assert _ask(repo, 'k.tmp') == {'k.tmp': True}
    _git(repo, 'add', '-f', 'k.tmp')
    warm = _ask(repo, 'k.tmp')
    assert warm == _cold(repo, 'k.tmp') == {'k.tmp': False}


# --- negative controls: what must not change -------------------------------------------------

def _count_loads(monkeypatch) -> list:
    loads: list = []
    real = gitignore._load_repo
    monkeypatch.setattr(gitignore, '_load_repo', lambda root: loads.append(root) or real(root))
    return loads


def test_unchanged_repo_is_not_reloaded_by_the_next_request(repo, monkeypatch):
    """An unchanged repository costs one ``ls-files`` for any number of requests."""
    _write(repo, '.gitignore', '*.tmp\n')
    _write(repo, 'a.tmp', 'x\n')
    loads = _count_loads(monkeypatch)
    answers = [_ask(repo, 'a.tmp', 'b.py') for _ in range(3)]
    assert answers == [{'a.tmp': True, 'b.py': False}] * 3
    assert len(loads) == 1


def test_one_shot_run_loads_once_per_repository(repo, monkeypatch):
    """Outside a host request (the CLI) the cache is the plain per-run one."""
    _write(repo, '.gitignore', '*.tmp\n')
    _write(repo, 'a.tmp', 'x\n')
    loads = _count_loads(monkeypatch)
    for _ in range(3):
        assert GitIgnoreFilter(repo).ignored(repo / 'a.tmp') is True
    assert len(loads) == 1


def test_entry_older_than_the_ttl_is_reloaded_by_the_next_request(repo, monkeypatch):
    """New ignored files are not in any stamped file: the 10 s TTL still bounds that staleness."""
    _write(repo, '.gitignore', '*.tmp\n')
    _write(repo, 'a.tmp', 'x\n')
    loads = _count_loads(monkeypatch)
    _ask(repo, 'a.tmp')
    real = gitignore.time.monotonic
    monkeypatch.setattr(gitignore.time, 'monotonic', lambda: real() + gitignore._CACHE_TTL_S + 1)
    _ask(repo, 'a.tmp')
    assert len(loads) == 2


def test_an_entry_does_not_expire_inside_one_request(repo, monkeypatch):
    """One request sees one answer: the TTL is checked on entry, not between two paths."""
    _write(repo, '.gitignore', '*.tmp\n')
    _write(repo, 'a.tmp', 'x\n')
    loads = _count_loads(monkeypatch)
    real = gitignore.time.monotonic
    with host_request():
        flt = GitIgnoreFilter(repo)
        assert flt.ignored(repo / 'a.tmp') is True
        monkeypatch.setattr(gitignore.time, 'monotonic', lambda: real() + gitignore._CACHE_TTL_S + 1)
        assert flt.ignored(repo / 'a.tmp') is True
    assert len(loads) == 1


def test_a_request_forgets_the_directory_to_root_map(repo):
    """The map is emptied at every request, so it is bounded by one request's directories."""
    _write(repo, 'sub/a.py', 'x\n')
    _ask(repo, 'sub/a.py')
    assert gitignore._ROOT_CACHE
    with host_request():
        assert not gitignore._ROOT_CACHE
