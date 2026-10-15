"""BACK-1845: GitAdapter.get_metadata must not swallow a repository-open failure.

``get_metadata`` caught OSError/ValueError/GitError and returned metadata with no
``path`` and no error, so a libgit2 ownership refusal read as "not a repository" to
its callers (overview's git-root lookup). The refusal text is libgit2's own
(src/libgit2/repository.c: "repository path '%s' is not owned by current user"),
which pygit2 surfaces as ``pygit2.GitError``. A genuine "not a repository" is still
what it was (``NotApplicableError``, nothing disclosed).
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

pygit2 = pytest.importorskip('pygit2')

from reveal.adapters.git import GitAdapter  # noqa: E402
from reveal.adapters.overview import OverviewAdapter, _resolve_git_root  # noqa: E402
from reveal.errors import NotApplicableError  # noqa: E402

LIBGIT2_REFUSAL = "repository path '/srv/repo/.git/' is not owned by current user"
COMMITS = [{'hash': 'abc1234', 'message': 'x', 'author': 'a', 'date': '2026-01-01'}]


def _refuse(*_args, **_kwargs):
    raise pygit2.GitError(LIBGIT2_REFUSAL)


def _init_repo(path: Path) -> None:
    subprocess.run(['git', 'init', '-q', str(path)], check=True, timeout=60)


@pytest.fixture
def repo(tmp_path):
    _init_repo(tmp_path)
    return tmp_path


def _errors(result: dict) -> list:
    return (result.get('meta') or {}).get('errors') or []


def test_metadata_discloses_ownership_refusal(repo):
    with patch.object(pygit2, 'Repository', _refuse):
        with pytest.raises(ValueError) as exc:
            GitAdapter(path=str(repo)).get_metadata()
    assert 'not owned by current user' in str(exc.value)
    assert 'safe.directory' in str(exc.value)


def test_overview_resolver_discloses_ownership_refusal(repo):
    with patch.object(pygit2, 'Repository', _refuse):
        with pytest.raises(ValueError) as exc:
            _resolve_git_root(repo)
    assert 'not owned by current user' in str(exc.value)


def test_overview_warns_on_ownership_refusal(repo):
    with patch('reveal.adapters.overview._run_git_log', return_value=list(COMMITS)), \
            patch.object(pygit2, 'Repository', _refuse):
        result = OverviewAdapter(str(repo), 'no_imports=true').get_structure()
    messages = ' '.join(e['message'] for e in _errors(result))
    assert 'not owned by current user' in messages
    assert result['meta']['confidence'] < 1.0


# Negative controls: unchanged behavior.

def test_non_repository_is_still_not_applicable():
    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(pygit2, 'discover_repository', return_value=None):
            with pytest.raises(NotApplicableError):
                GitAdapter(path=tmp).get_metadata()
            assert _resolve_git_root(Path(tmp)) is None


def test_non_repository_overview_has_no_warning():
    with tempfile.TemporaryDirectory() as tmp, \
            patch('reveal.adapters.overview._run_git_log', return_value=list(COMMITS)), \
            patch.object(pygit2, 'discover_repository', return_value=None):
        result = OverviewAdapter(tmp, 'no_imports=true').get_structure()
    assert _errors(result) == []
    assert result['git_foreign_root'] is None


def test_real_repository_metadata_unchanged(repo):
    meta = GitAdapter(path=str(repo)).get_metadata()
    assert set(meta) == {'type', 'path', 'adapter'}
    assert meta['type'] == 'git_repository' and meta['adapter'] == 'git'
    assert Path(meta['path']).resolve() == repo.resolve()
