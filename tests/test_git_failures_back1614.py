"""BACK-1614: git:// no longer returns a partial ref list or a missing element
when the real cause is a failure."""

import pytest

pygit2 = pytest.importorskip('pygit2')

from reveal.adapters.git import files, refs  # noqa: E402
from reveal.adapters.git.adapter import GitAdapter  # noqa: E402


class _Unlistable:
    def __iter__(self):
        raise pygit2.GitError('corrupt packed-refs')


class _Repo:
    class branches:
        local = _Unlistable()
    references = _Unlistable()


def test_branch_listing_failure_propagates():
    with pytest.raises(pygit2.GitError):
        refs.list_branches(_Repo())


def test_tag_listing_failure_propagates():
    with pytest.raises(pygit2.GitError):
        refs.list_tags(_Repo())


@pytest.fixture
def repo_dir(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    (tmp_path / 'a.py').write_text('x = 1\n', encoding='utf-8')
    repo.index.add('a.py')
    repo.index.write()
    sig = pygit2.Signature('t', 't@example.com')
    repo.create_commit('HEAD', sig, sig, 'init', repo.index.write_tree(), [])
    return tmp_path


def test_missing_file_element_is_none(repo_dir):
    assert GitAdapter(str(repo_dir)).get_element('nope.py') is None


def test_analysis_bug_in_file_element_propagates(repo_dir, monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError('analyzer bug')

    monkeypatch.setattr(files, 'get_file_at_ref', _boom)
    with pytest.raises(RuntimeError):
        GitAdapter(str(repo_dir)).get_element('a.py')
