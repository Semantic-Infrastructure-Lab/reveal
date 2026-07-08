"""Tests for git/files.py:get_churn_counts (BACK-483)."""

import pytest


@pytest.fixture
def churn_repo(tmp_path):
    """Real git repo with a known per-file commit-touch pattern.

    Commits (chronological):
      1. add a.py, b.py                  -> a.py:1, b.py:1
      2. modify a.py                      -> a.py:2, b.py:1
      3. modify a.py, b.py (merge commit) -> a.py:3, b.py:2
      4. modify a.py                      -> a.py:4, b.py:2

    Commit 3 is a merge (two parents) so no_merges=1 should tally a.py:3,
    b.py:1 instead (commit 3's touches excluded).
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
    c2 = commit("modify a", [c1])

    (repo_dir / "a.py").write_text("def a(): return 2\n")
    (repo_dir / "b.py").write_text("def b(): return 1\n")
    c3 = commit("merge-shaped commit touching a, b", [c2, c1])  # 2 parents -> "merge"

    (repo_dir / "a.py").write_text("def a(): return 3\n")
    commit("modify a again", [c3])

    return repo_dir, repo


class TestGetChurnCounts:
    def test_tallies_touches_per_file(self, churn_repo):
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        counts = get_churn_counts(repo, 'HEAD', None)
        assert counts == {'a.py': 4, 'b.py': 2}

    def test_scope_limits_to_given_paths(self, churn_repo):
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        counts = get_churn_counts(repo, 'HEAD', {'a.py'})
        assert counts == {'a.py': 4}
        assert 'b.py' not in counts

    def test_no_merges_excludes_multi_parent_commits(self, churn_repo):
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        counts = get_churn_counts(repo, 'HEAD', None, no_merges=True)
        assert counts == {'a.py': 3, 'b.py': 1}

    def test_since_excludes_older_commits(self, churn_repo):
        from datetime import datetime, timedelta
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        # Bound to "the future" -> nothing should be tallied.
        future = (datetime.now() + timedelta(days=365)).date().isoformat()
        counts = get_churn_counts(repo, 'HEAD', None, since=future)
        assert counts == {}

        # Bound to "the past" -> everything should be tallied.
        past = (datetime.now() - timedelta(days=365)).date().isoformat()
        counts = get_churn_counts(repo, 'HEAD', None, since=past)
        assert counts == {'a.py': 4, 'b.py': 2}

    def test_matches_git_log_oneline_count(self, churn_repo):
        """Cross-check against `git log --oneline -- <file> | wc -l` semantics."""
        import subprocess
        from reveal.adapters.git.files import get_churn_counts

        repo_dir, repo = churn_repo
        counts = get_churn_counts(repo, 'HEAD', None)

        for fname in ('a.py', 'b.py'):
            result = subprocess.run(
                ['git', 'log', '--oneline', '--', fname],
                cwd=str(repo_dir), capture_output=True, text=True,
            )
            git_count = len([ln for ln in result.stdout.splitlines() if ln.strip()])
            assert counts[fname] == git_count, f"{fname}: reveal={counts[fname]} git={git_count}"
