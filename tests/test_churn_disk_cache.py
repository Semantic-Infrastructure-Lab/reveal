"""Correctness tests for the persistent churn-walk disk cache (BACK-624).

get_churn_counts() (BACK-483) walks the *entire* commit history once per
call, unconditionally, regardless of scope_paths -- on a real repo this walk
dominates `reveal hotspots` wall time (85-94%, see BACK-624). These tests pin
the cache invariant: a cached result must be identical to a fresh walk, must
invalidate on HEAD move, must NOT fragment across different scope_paths (the
walk is unscoped internally, scope is a post-filter), and must fail open.
"""

import pytest

from reveal.core import disk_cache


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the disk cache at a throwaway dir and start every test cold."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)


@pytest.fixture
def churn_repo(tmp_path):
    """Real git repo: 2 commits touching a.py, b.py.

    Kept in a subdir separate from the cache dir's tmp_path so
    _isolate_cache's REVEAL_CACHE_DIR doesn't collide with the repo itself.
    """
    import pygit2

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = pygit2.init_repository(str(repo_dir))
    author = pygit2.Signature("Test", "test@example.com")

    def commit(msg, parents):
        index = repo.index
        index.add_all()
        index.write()
        tree_oid = index.write_tree()
        return repo.create_commit("HEAD", author, author, msg, tree_oid, parents)

    (repo_dir / "a.py").write_text("def a(): pass\n")
    (repo_dir / "b.py").write_text("def b(): pass\n")
    c1 = commit("add a, b", [])

    (repo_dir / "a.py").write_text("def a(): return 1\n")
    commit("modify a", [c1])

    return repo_dir, repo


class TestChurnDiskCache:
    def test_cache_hit_matches_fresh_walk(self, churn_repo):
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        fresh = get_churn_counts(repo, 'HEAD', None)

        # Second call must be a cache hit: patch repo.walk (instance-level,
        # pygit2 allows it) to explode if the walk actually re-runs.
        def _boom(*a, **kw):
            raise AssertionError("walk re-ran on what should have been a cache hit")

        repo.walk = _boom
        cached = get_churn_counts(repo, 'HEAD', None)
        assert cached == fresh == {'a.py': 2, 'b.py': 1}

    def test_scope_paths_is_a_post_filter_not_a_cache_key(self, churn_repo):
        """Two different scope_paths on the same HEAD must share one cache entry."""
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        full = get_churn_counts(repo, 'HEAD', None)
        assert full == {'a.py': 2, 'b.py': 1}

        # Force any further walk to explode -- both scoped calls below must
        # be served from the one cache entry the unscoped call above wrote.
        def _boom(*a, **kw):
            raise AssertionError("walk re-ran instead of reusing the cached entry")

        repo.walk = _boom

        assert get_churn_counts(repo, 'HEAD', {'a.py'}) == {'a.py': 2}
        assert get_churn_counts(repo, 'HEAD', {'b.py'}) == {'b.py': 1}
        assert get_churn_counts(repo, 'HEAD', {'nonexistent.py'}) == {}

    def test_new_commit_invalidates_cache(self, churn_repo):
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        before = get_churn_counts(repo, 'HEAD', None)
        assert before == {'a.py': 2, 'b.py': 1}

        author = repo.default_signature if repo.default_signature else None
        import pygit2
        author = pygit2.Signature("Test", "test@example.com")
        (repo_dir / "b.py").write_text("def b(): return 1\n")
        index = repo.index
        index.add_all()
        index.write()
        tree_oid = index.write_tree()
        parent = repo.revparse_single('HEAD').id
        repo.create_commit("HEAD", author, author, "modify b", tree_oid, [parent])

        after = get_churn_counts(repo, 'HEAD', None)
        assert after == {'a.py': 2, 'b.py': 2}

    def test_since_and_no_merges_are_part_of_the_cache_key(self, churn_repo):
        """Different since/no_merges on the same HEAD must not share an entry."""
        from datetime import datetime, timedelta
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        unbounded = get_churn_counts(repo, 'HEAD', None)
        future = (datetime.now() + timedelta(days=365)).date().isoformat()
        bounded = get_churn_counts(repo, 'HEAD', None, since=future)
        no_merges = get_churn_counts(repo, 'HEAD', None, no_merges=True)

        assert unbounded == {'a.py': 2, 'b.py': 1}
        assert bounded == {}
        assert no_merges == {'a.py': 2, 'b.py': 1}

    def test_kill_switch_falls_back_to_uncached_walk(self, churn_repo, monkeypatch):
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
        result = get_churn_counts(repo, 'HEAD', None)
        assert result == {'a.py': 2, 'b.py': 1}
        # Nothing should have been persisted while disabled.
        monkeypatch.delenv("REVEAL_DISK_CACHE")
        assert disk_cache.get("churn", "anything") is None

    def test_corrupt_cache_entry_is_a_miss_not_a_crash(self, churn_repo):
        from reveal.adapters.git.files import get_churn_counts, _churn_fingerprint

        repo_dir, repo = churn_repo
        obj = repo.revparse_single('HEAD')
        while hasattr(obj, 'peel'):
            import pygit2
            if isinstance(obj, pygit2.Commit):
                break
            obj = obj.peel(pygit2.Commit)
        fingerprint = _churn_fingerprint(repo, obj.id, None, False)
        assert fingerprint is not None

        from reveal.core import disk_cache as dc
        dc.put("churn", fingerprint, "not a valid counts dict shape but still unpickles fine")

        # A malformed-but-picklable cached value should still round-trip as
        # returned (the cache doesn't validate shape) -- this test instead
        # exercises the true corruption path: an unreadable pickle file.
        path = dc._entry_path("churn", fingerprint)
        path.write_bytes(b"\x00not a pickle")
        result = get_churn_counts(repo, 'HEAD', None)
        assert result == {'a.py': 2, 'b.py': 1}
