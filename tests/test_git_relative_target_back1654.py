"""BACK-1654: the git repo is discovered from the target path, not the cwd."""

import pytest

pygit2 = pytest.importorskip('pygit2')

from reveal.adapters.git.adapter import GitAdapter  # noqa: E402
from reveal.adapters.overview import OverviewAdapter  # noqa: E402
from reveal.errors import NotApplicableError  # noqa: E402


@pytest.fixture
def parent(tmp_path):
    """tmp/repo (a git repo with src/a.py) and tmp/norepo/x/b.py; tmp itself is not a repo."""
    repo_dir = tmp_path / 'repo'
    (repo_dir / 'src').mkdir(parents=True)
    (repo_dir / 'src' / 'a.py').write_text('def f():\n    pass\n', encoding='utf-8')
    repo = pygit2.init_repository(str(repo_dir))
    repo.index.add('src/a.py')
    repo.index.write()
    sig = pygit2.Signature('t', 't@example.com')
    repo.create_commit('HEAD', sig, sig, 'init', repo.index.write_tree(), [])
    (tmp_path / 'norepo' / 'x').mkdir(parents=True)
    (tmp_path / 'norepo' / 'x' / 'b.py').write_text('x = 1\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('spelling', ['relative', 'absolute'])
@pytest.mark.parametrize('target', ['repo/src', 'repo/src/a.py'])
def test_history_of_target_from_parent_cwd(parent, monkeypatch, spelling, target):
    monkeypatch.chdir(parent)
    resource = target if spelling == 'relative' else str(parent / target)
    result = GitAdapter(f'{resource}?type=history').get_structure()
    assert not result.get('error')
    # an absolute directory is a repo-root view ('history'); the rest are path views ('commits')
    commits = result.get('commits', result.get('history'))
    assert [c['message'] for c in commits] == ['init']


def test_overview_composes_git_from_parent_cwd(parent, monkeypatch):
    monkeypatch.chdir(parent)
    result = OverviewAdapter('repo/src').get_structure()
    errors = [e for e in (result.get('meta') or {}).get('errors', []) if e.get('code') == 'E_COMPOSE']
    assert errors == []
    assert [c['message'] for c in result['git_log']] == ['init']


def test_target_outside_any_repo_is_not_applicable(parent, monkeypatch):
    monkeypatch.chdir(parent)
    with pytest.raises(NotApplicableError) as exc:
        GitAdapter('norepo/x?type=history').get_structure()
    assert 'norepo/x' in str(exc.value)


def test_overview_outside_any_repo_discloses_git_failure(parent, monkeypatch):
    monkeypatch.chdir(parent)
    result = OverviewAdapter('norepo/x').get_structure()
    messages = [e['message'] for e in result['meta']['errors'] if e.get('code') == 'E_COMPOSE']
    assert messages and 'norepo/x' in messages[0]
    assert result['git_log'] == []


def test_cwd_inside_repo_still_works(parent, monkeypatch):
    """Negative control: the spelling that always worked is unchanged."""
    monkeypatch.chdir(parent / 'repo')
    result = GitAdapter('src?type=history').get_structure()
    assert [c['message'] for c in result['commits']] == ['init']
