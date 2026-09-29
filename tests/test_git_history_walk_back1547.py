"""BACK-1547: one commit walk behind every git:// view, and what it says about the rest.

Five copies of the walk each stopped at ``offset + limit``. So a cut history had no total
and no marker, ``?sort=`` ordered only the commits already walked (``sort=date&limit=3``
listed the 3 newest, re-sorted), the repository view ignored ``?limit``/``--all`` (a fixed
10), and two copies returned whatever they held when the walk raised.
"""

import pytest

pygit2 = pytest.importorskip('pygit2')

from reveal.adapters.git import GitAdapter
from reveal.utils.results import outcome_of, truncations_of

DAY = 86400
BASE = 1_700_000_000


@pytest.fixture
def repo_path(tmp_path):
    """Five commits to app.py, a day apart, oldest first: 'c1' .. 'c5'."""
    path = tmp_path / 'repo'
    path.mkdir()
    repo = pygit2.init_repository(str(path))
    parents = []
    for i in range(1, 6):
        (path / 'app.py').write_text(f'x = {i}\n', encoding='utf-8')
        repo.index.add('app.py')
        repo.index.write()
        sig = pygit2.Signature('t', 't@example.com', BASE + i * DAY, 0)
        oid = repo.create_commit('refs/heads/master', sig, sig, f'c{i}',
                                 repo.index.write_tree(), parents)
        parents = [oid]
    repo.set_head('refs/heads/master')
    return path


def _history(repo_path, **query):
    return GitAdapter(path=str(repo_path), subpath='app.py',
                      query={'type': 'history', **query}).get_structure()


def _messages(commits):
    return [c['message'] for c in commits]


def _cut(result):
    [cut] = truncations_of(result)
    return cut['field'], cut['shown'], cut['total'], cut['exact']


class TestHistoryPage:
    def test_a_page_short_of_history_is_a_lower_bound_cut(self, repo_path):
        result = _history(repo_path, limit='2')
        assert _messages(result['commits']) == ['c5', 'c4']
        assert _cut(result) == ('commits', 2, 3, False)
        assert outcome_of(result) == 'truncated'
        assert result['total_matches'] is None  # unknown, not the page size

    @pytest.mark.parametrize('limit', ['5', '6', '100'])
    def test_a_page_that_holds_all_of_history_is_not_a_cut(self, repo_path, limit):
        result = _history(repo_path, limit=limit)
        assert len(result['commits']) == 5
        assert truncations_of(result) == []

    def test_offset_pages_past_the_skipped_commits(self, repo_path):
        """BACK-1506 kept: offset=1&limit=2 is the 2nd and 3rd newest, and the walk
        stops one past them."""
        result = _history(repo_path, limit='2', offset='1')
        assert _messages(result['commits']) == ['c4', 'c3']
        assert _cut(result) == ('commits', 2, 4, False)


class TestSortReadsAllOfHistory:
    def test_sort_with_a_limit_orders_every_match(self, repo_path):
        """The bug: the walk stopped at 2 and sorted those, so oldest-first listed the
        two newest. A limit cuts the answer; it doesn't bound what is read."""
        result = _history(repo_path, limit='2', sort='date')
        assert _messages(result['commits']) == ['c1', 'c2']
        assert _cut(result) == ('commits', 2, 5, True)
        assert result['total_matches'] == 5

    def test_descending_sort_is_the_newest(self, repo_path):
        result = _history(repo_path, limit='2', sort='-date')
        assert _messages(result['commits']) == ['c5', 'c4']


class TestEveryViewDisclosesItsCut:
    def test_repository_view_honors_limit(self, repo_path):
        """It was a fixed 10, so ?limit and --all (limit=1000000) were no-ops."""
        result = GitAdapter(path=str(repo_path), query={'limit': '2'}).get_structure()
        assert _messages(result['commits']['recent']) == ['c5', 'c4']
        assert _cut(result) == ('commits.recent', 2, 3, False)

    def test_repository_view_lists_all_under_its_default(self, repo_path):
        result = GitAdapter(path=str(repo_path)).get_structure()
        assert len(result['commits']['recent']) == 5
        assert truncations_of(result) == []

    def test_ref_history(self, repo_path):
        result = GitAdapter(path=str(repo_path), ref='master',
                            query={'limit': '3'}).get_structure()
        assert _messages(result['history']) == ['c5', 'c4', 'c3']
        assert _cut(result) == ('history', 3, 4, False)

    @pytest.mark.parametrize('subpath', [None, 'app.py'])
    def test_a_timeline_stopped_by_its_limit_says_so(self, repo_path, subpath):
        """A timeline's counts come from the commits its walk reached; stopped at ?limit,
        older history is missing from every bucket."""
        result = GitAdapter(path=str(repo_path), subpath=subpath,
                            query={'type': 'history', 'bucket': 'month',
                                   'limit': '2'}).get_structure()
        assert result['commit_count'] == 2
        field, shown, total, exact = _cut(result)
        assert (field, shown, total, exact) == ('commits', 2, 3, False)
        assert 'timeline counts only the newest N' in truncations_of(result)[0]['message']
        assert 'walk' not in result

    def test_a_whole_timeline_is_not_a_cut(self, repo_path):
        result = GitAdapter(path=str(repo_path), query={'type': 'history',
                                                        'bucket': 'month'}).get_structure()
        assert result['commit_count'] == 5
        assert truncations_of(result) == []


class TestAFailedWalkFails:
    def test_an_error_partway_fails_the_query(self, repo_path, monkeypatch):
        """Two copies ended in `except Exception: pass`, so a walk that broke after two
        commits listed those two as the whole history."""
        real_walk = pygit2.Repository.walk

        def breaking_walk(self, *args, **kwargs):
            for n, commit in enumerate(real_walk(self, *args, **kwargs)):
                if n == 2:
                    raise pygit2.GitError('object not found')
                yield commit

        monkeypatch.setattr(pygit2.Repository, 'walk', breaking_walk)
        with pytest.raises(ValueError, match='walk failed after 2 commits: object not found'):
            GitAdapter(path=str(repo_path), ref='master').get_structure()
        with pytest.raises(ValueError, match='walk failed after 2 commits'):
            GitAdapter(path=str(repo_path)).get_structure()


# Walks that aggregate over history rather than list it, and so don't page.
AGGREGATE_WALKS = {
    'get_churn_counts': 'per-file touch counts over all of history; no limit',
    '_aggregate_commit_authors': "ownership's ?limit is a window of commits to count",
}


def test_every_listing_walk_is_walk_history():
    """The five listing views call one walk. Another function calling ``repo.walk`` in the
    git package is a copy that can drift from its paging, sort and error rules again."""
    import ast
    from pathlib import Path

    import reveal.adapters.git as git_pkg
    walkers = set()
    for path in Path(git_pkg.__file__).parent.glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                    isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == 'walk' and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'repo'
                    for node in ast.walk(fn)):
                walkers.add(fn.name)
    assert walkers - set(AGGREGATE_WALKS) == {'walk_history'}
