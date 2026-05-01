"""Tests for Git adapter (git:// URI scheme).

Tests cover:
- Repository overview
- Branch/commit exploration
- File inspection at refs
- File history
- File blame
- Error handling
"""

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch
import pytest

# Check if pygit2 is available
try:
    import pygit2
    PYGIT2_AVAILABLE = True
except ImportError:
    PYGIT2_AVAILABLE = False

from reveal.adapters.git import GitAdapter


@pytest.fixture
def git_repo(tmp_path):
    """Create a test git repository with history."""
    if not PYGIT2_AVAILABLE:
        pytest.skip("pygit2 not available")

    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize repository
    repo = pygit2.init_repository(str(repo_path))

    # Configure signature for commits
    signature = pygit2.Signature("Test User", "test@example.com")

    # Create initial commit
    file1 = repo_path / "README.md"
    file1.write_text("# Test Repository\n\nInitial content\n")

    index = repo.index
    index.add("README.md")
    index.write()
    tree = index.write_tree()

    # Create initial commit on refs/heads/master (HEAD doesn't exist yet)
    repo.create_commit(
        "refs/heads/master",
        signature,
        signature,
        "Initial commit",
        tree,
        []
    )

    # Set HEAD to point to master
    repo.set_head("refs/heads/master")

    # Create second commit
    file2 = repo_path / "src" / "main.py"
    file2.parent.mkdir()
    file2.write_text("def main():\n    print('Hello, World!')\n")

    index.add("src/main.py")
    index.write()
    tree = index.write_tree()

    repo.create_commit(
        "HEAD",
        signature,
        signature,
        "Add main.py",
        tree,
        [repo.head.target]
    )

    # Create third commit (modify README)
    file1.write_text("# Test Repository\n\nUpdated content\n")

    index.add("README.md")
    index.write()
    tree = index.write_tree()

    repo.create_commit(
        "HEAD",
        signature,
        signature,
        "Update README",
        tree,
        [repo.head.target]
    )

    # Create a branch
    branch_ref = repo.branches.create("feature", repo.head.peel())

    # Create a tag
    tag_target = repo.head.peel()
    repo.create_tag("v1.0.0", tag_target.id, pygit2.GIT_OBJECT_COMMIT,
                    signature, "Version 1.0.0")

    yield repo_path

    # Cleanup
    shutil.rmtree(repo_path, ignore_errors=True)


@pytest.fixture
def git_repo_py_history(tmp_path):
    """Git repo with a Python file whose elements have distinct commit histories.

    Commit 1 – "Add calc.py with add()": creates add() only.
    Commit 2 – "Add subtract() to calc.py": appends subtract(); add() body unchanged.
    Commit 3 – "Improve add() with comment": inserts a comment inside add();
                subtract() body unchanged.

    This lets integration tests verify that ?element=add returns 2 commits (1, 3)
    and ?element=subtract returns 1 commit (2).
    """
    if not PYGIT2_AVAILABLE:
        pytest.skip("pygit2 not available")

    repo_path = tmp_path / "py_hist_repo"
    repo_path.mkdir()
    repo = pygit2.init_repository(str(repo_path))
    sig = pygit2.Signature("Test User", "test@example.com")
    calc = repo_path / "calc.py"
    idx = repo.index

    # Commit 1: add() only (2 lines)
    calc.write_text("def add(a, b):\n    return a + b\n")
    idx.add("calc.py")
    idx.write()
    tree = idx.write_tree()
    repo.create_commit("refs/heads/master", sig, sig, "Add calc.py with add()", tree, [])
    repo.set_head("refs/heads/master")

    # Commit 2: append subtract() — add() body is identical
    calc.write_text(
        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n"
    )
    idx.add("calc.py")
    idx.write()
    tree = idx.write_tree()
    repo.create_commit("HEAD", sig, sig, "Add subtract() to calc.py", tree, [repo.head.target])

    # Commit 3: insert a comment inside add() — subtract() body unchanged
    calc.write_text(
        "def add(a, b):\n    # improved\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n"
    )
    idx.add("calc.py")
    idx.write()
    tree = idx.write_tree()
    repo.create_commit("HEAD", sig, sig, "Improve add() with comment", tree, [repo.head.target])

    yield repo_path
    shutil.rmtree(repo_path, ignore_errors=True)


class TestGitAdapterBasics:
    """Test basic git adapter functionality."""

    def test_adapter_without_pygit2(self):
        """Test error message when pygit2 is not available."""
        # Mock PYGIT2_AVAILABLE to False to test the error case
        with patch('reveal.adapters.git.adapter.PYGIT2_AVAILABLE', False):
            adapter = GitAdapter(path='.')
            with pytest.raises(ImportError) as exc_info:
                adapter.get_structure()

            assert "pip install reveal-cli[git]" in str(exc_info.value)

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_adapter_with_invalid_path(self):
        """Test error handling for invalid repository path."""
        adapter = GitAdapter(path='/nonexistent/path')
        with pytest.raises(ValueError) as exc_info:
            adapter.get_structure()

        assert "Not a git repository" in str(exc_info.value) or "Failed to open" in str(exc_info.value)

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_adapter_registration(self):
        """Test that git adapter is properly registered."""
        from reveal.adapters.base import get_adapter_class

        adapter_class = get_adapter_class('git')
        assert adapter_class is not None
        assert adapter_class == GitAdapter

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_help(self):
        """Test help documentation."""
        help_info = GitAdapter.get_help()

        assert help_info is not None
        assert help_info['name'] == 'git'
        assert 'description' in help_info
        assert 'examples' in help_info
        assert len(help_info['examples']) > 0
        assert 'query_parameters' in help_info


class TestRepositoryOverview:
    """Test repository overview functionality."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_repository_overview(self, git_repo):
        """Test basic repository overview."""
        adapter = GitAdapter(path=str(git_repo))
        structure = adapter.get_structure()

        assert structure['type'] == 'git_repository'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'directory'
        assert 'source' in structure
        assert 'head' in structure
        assert 'branches' in structure
        assert 'tags' in structure
        assert 'commits' in structure

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_head_info(self, git_repo):
        """Test HEAD information."""
        adapter = GitAdapter(path=str(git_repo))
        structure = adapter.get_structure()

        head = structure['head']
        assert head['branch'] == 'master' or head['branch'] == 'main'
        assert head['commit'] is not None
        assert not head['detached']

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_branches_list(self, git_repo):
        """Test branches listing."""
        adapter = GitAdapter(path=str(git_repo))
        structure = adapter.get_structure()

        branches = structure['branches']
        assert branches['count'] >= 1  # At least master/main
        assert len(branches['recent']) >= 1

        # Check branch structure
        branch = branches['recent'][0]
        assert 'name' in branch
        assert 'commit' in branch
        assert 'author' in branch
        assert 'date' in branch

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_tags_list(self, git_repo):
        """Test tags listing."""
        adapter = GitAdapter(path=str(git_repo))
        structure = adapter.get_structure()

        tags = structure['tags']
        assert tags['count'] >= 1  # We created v1.0.0
        assert len(tags['recent']) >= 1

        # Check if v1.0.0 is present
        tag_names = [t['name'] for t in tags['recent']]
        assert 'v1.0.0' in tag_names

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_recent_commits(self, git_repo):
        """Test recent commits listing."""
        adapter = GitAdapter(path=str(git_repo))
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        assert len(commits) >= 3  # We made 3 commits

        # Check commit structure
        commit = commits[0]
        assert 'hash' in commit
        assert 'author' in commit
        assert 'date' in commit
        assert 'message' in commit


class TestRefExploration:
    """Test ref (branch/commit/tag) exploration."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_explore_commit(self, git_repo):
        """Test exploring a specific commit."""
        # First get the HEAD commit hash
        adapter = GitAdapter(path=str(git_repo))
        overview = adapter.get_structure()
        commit_hash = overview['head']['commit']

        # Now explore that commit
        adapter = GitAdapter(path=str(git_repo), ref=commit_hash)
        structure = adapter.get_structure()

        assert structure['type'] == 'git_ref'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'directory'
        assert structure['ref'] == commit_hash
        assert 'commit' in structure
        assert 'history' in structure

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_explore_branch(self, git_repo):
        """Test exploring a branch."""
        adapter = GitAdapter(path=str(git_repo), ref='feature')
        structure = adapter.get_structure()

        assert structure['type'] == 'git_ref'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'directory'
        assert structure['ref'] == 'feature'
        assert 'commit' in structure
        assert 'history' in structure

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_explore_tag(self, git_repo):
        """Test exploring a tag."""
        adapter = GitAdapter(path=str(git_repo), ref='v1.0.0')
        structure = adapter.get_structure()

        assert structure['type'] == 'git_ref'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'directory'
        assert structure['ref'] == 'v1.0.0'
        assert 'commit' in structure

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_invalid_ref(self, git_repo):
        """Test error handling for invalid ref."""
        adapter = GitAdapter(path=str(git_repo), ref='nonexistent')
        with pytest.raises(ValueError) as exc_info:
            adapter.get_structure()

        assert "Invalid ref" in str(exc_info.value)


class TestFileInspection:
    """Test file inspection at specific refs."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_file_at_ref(self, git_repo):
        """Test getting file structure at a ref (default behaviour)."""
        adapter = GitAdapter(path=str(git_repo), ref='HEAD', subpath='README.md')
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file_structure'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'file'
        assert structure['path'] == 'README.md'
        assert 'structure' in structure
        assert 'commit_info' in structure
        assert 'content' not in structure

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_file_at_ref_raw(self, git_repo):
        """Test ?raw=1 returns file contents instead of structure."""
        adapter = GitAdapter(path=str(git_repo), ref='HEAD', subpath='README.md',
                             query={'raw': '1'})
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file'
        assert structure['contract_version'] == '1.0'
        assert 'content' in structure
        assert 'Updated content' in structure['content']

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_file_at_tag(self, git_repo):
        """Test getting file structure at a tag."""
        adapter = GitAdapter(path=str(git_repo), ref='v1.0.0', subpath='README.md')
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file_structure'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'file'
        assert structure['path'] == 'README.md'
        assert 'structure' in structure

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_file_at_ref_has_commit_info(self, git_repo):
        """File structure result includes commit metadata."""
        adapter = GitAdapter(path=str(git_repo), ref='HEAD', subpath='README.md')
        structure = adapter.get_structure()

        ci = structure['commit_info']
        assert 'hash' in ci
        assert 'author' in ci
        assert 'date' in ci
        assert 'message' in ci

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_file_diff(self, git_repo):
        """?type=diff returns a commit diff for the file."""
        # Get a non-HEAD commit that touched README.md
        import pygit2
        repo = pygit2.Repository(str(git_repo))
        head = repo.head.peel(pygit2.Commit)
        ref = str(head.id)

        adapter = GitAdapter(path=str(git_repo), ref=ref, subpath='README.md',
                             query={'type': 'diff'})
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file_diff'
        assert structure['contract_version'] == '1.0'
        assert structure['path'] == 'README.md'
        assert 'diff_text' in structure
        assert 'commit_info' in structure
        ci = structure['commit_info']
        assert 'hash' in ci and 'author' in ci and 'message' in ci

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_file_not_found(self, git_repo):
        """Test error handling for nonexistent file."""
        adapter = GitAdapter(path=str(git_repo), ref='HEAD', subpath='nonexistent.txt')
        with pytest.raises(ValueError) as exc_info:
            adapter.get_structure()

        assert "File not found" in str(exc_info.value) or "not found" in str(exc_info.value).lower()


class TestFileHistory:
    """Test file history functionality."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_file_history(self, git_repo):
        """Test getting file commit history."""
        adapter = GitAdapter(
            path=str(git_repo),
            subpath='README.md',
            query={'type': 'history'}
        )
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file_history'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'file'
        assert structure['path'] == 'README.md'
        assert 'commits' in structure
        assert len(structure['commits']) >= 2  # README was in 2 commits

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_file_history_with_limit(self, git_repo):
        """Test file history with limit."""
        adapter = GitAdapter(
            path=str(git_repo),
            subpath='README.md',
            query={'type': 'history', 'limit': '1'}
        )
        structure = adapter.get_structure()

        assert len(structure['commits']) == 1


class TestFileBlame:
    """Test file blame functionality."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_file_blame(self, git_repo):
        """Test getting file blame."""
        adapter = GitAdapter(
            path=str(git_repo),
            subpath='README.md',
            query={'type': 'blame'}
        )
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file_blame'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'file'
        assert structure['path'] == 'README.md'
        assert 'hunks' in structure
        assert len(structure['hunks']) > 0

        # Check hunk structure
        hunk = structure['hunks'][0]
        assert 'lines' in hunk
        assert 'commit' in hunk
        assert 'author' in hunk['commit']
        assert 'date' in hunk['commit']


class TestGetElement:
    """Test get_element functionality."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_element_commit(self, git_repo):
        """Test getting a commit element."""
        # Get commit hash from overview
        adapter = GitAdapter(path=str(git_repo))
        overview = adapter.get_structure()
        commit_hash = overview['commits']['recent'][0]['hash']

        # Get element
        element = adapter.get_element(commit_hash)

        assert element is not None
        assert element['hash'] == commit_hash
        assert 'author' in element
        assert 'message' in element

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_element_file(self, git_repo):
        """Test getting a file element returns structural view."""
        adapter = GitAdapter(path=str(git_repo), ref='HEAD')
        element = adapter.get_element('README.md')

        assert element is not None
        assert element['type'] == 'git_file_structure'
        assert element['path'] == 'README.md'


class TestMetadata:
    """Test metadata functionality."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_metadata(self, git_repo):
        """Test getting adapter metadata."""
        adapter = GitAdapter(path=str(git_repo))
        metadata = adapter.get_metadata()

        assert metadata['type'] == 'git_repository'
        assert metadata['adapter'] == 'git'
        assert 'path' in metadata


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_empty_repository(self, tmp_path):
        """Test handling of empty repository."""
        repo_path = tmp_path / "empty_repo"
        repo_path.mkdir()
        pygit2.init_repository(str(repo_path))

        adapter = GitAdapter(path=str(repo_path))
        structure = adapter.get_structure()

        assert structure['type'] == 'git_repository'
        assert structure['contract_version'] == '1.0'
        assert structure['stats']['is_empty']

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_bare_repository(self, tmp_path):
        """Test handling of bare repository."""
        repo_path = tmp_path / "bare_repo"
        repo_path.mkdir()
        pygit2.init_repository(str(repo_path), bare=True)

        adapter = GitAdapter(path=str(repo_path))
        structure = adapter.get_structure()

        assert structure['type'] == 'git_repository'
        assert structure['contract_version'] == '1.0'
        assert structure['stats']['is_bare']


class TestCommitFiltering:
    """Test commit filtering functionality."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_by_author(self, git_repo):
        """Test filtering commits by author name."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'author': 'Test User'}
        )
        structure = adapter.get_structure()

        # All commits should be by "Test User"
        assert structure['type'] == 'git_repository'
        commits = structure['commits']['recent']
        assert len(commits) >= 3  # We made 3 commits with Test User
        for commit in commits:
            assert commit['author'] == 'Test User'

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_by_author_case_insensitive(self, git_repo):
        """Test filtering commits by author name (case-insensitive)."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'author': 'test user'}  # lowercase
        )
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        assert len(commits) >= 3  # Should still match "Test User"
        for commit in commits:
            assert commit['author'] == 'Test User'

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_by_author_partial_match(self, git_repo):
        """Test filtering commits by partial author name (regex)."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'author~': 'Test'}  # Regex match
        )
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        assert len(commits) >= 3
        for commit in commits:
            assert 'Test' in commit['author'] or 'test' in commit['author'].lower()

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_by_email(self, git_repo):
        """Test filtering commits by email."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'email': 'test@example.com'}
        )
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        assert len(commits) >= 3
        for commit in commits:
            assert commit['email'] == 'test@example.com'

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_by_message(self, git_repo):
        """Test filtering commits by message."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'message~': 'README'}  # Regex match for commits with README
        )
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        # Should find "Update README" (only commit with README in message)
        assert len(commits) == 1
        assert 'README' in commits[0]['message']

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_by_message_exact(self, git_repo):
        """Test filtering commits by exact message."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'message': 'Add main.py'}
        )
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        assert len(commits) == 1
        assert commits[0]['message'] == 'Add main.py'

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_no_matches(self, git_repo):
        """Test filtering with no matching commits."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'author': 'Nonexistent User'}
        )
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        assert len(commits) == 0

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_multiple_criteria(self, git_repo):
        """Test filtering with multiple criteria (AND logic)."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={
                'author': 'Test User',
                'message~': 'README'
            }
        )
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        # Should match commits by "Test User" with "README" in message
        assert len(commits) == 1
        for commit in commits:
            assert commit['author'] == 'Test User'
            assert 'README' in commit['message']

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_file_history(self, git_repo):
        """Test filtering in file history."""
        adapter = GitAdapter(
            path=str(git_repo),
            subpath='README.md',
            query={
                'type': 'history',
                'message~': 'Update'
            }
        )
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file_history'
        commits = structure['commits']
        # Should only include commits with "Update" in message
        assert len(commits) == 1
        assert 'Update' in commits[0]['message']

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_ref_query_param_overrides_starting_ref(self, git_repo):
        """?ref= query param should set the starting ref (alias for @ref in URI)."""
        # Get the second commit (one step before HEAD)
        repo = pygit2.Repository(str(git_repo))
        all_commits = list(repo.walk(repo.head.target, pygit2.GIT_SORT_TIME))
        second_commit_hash = str(all_commits[1].id)  # one step before HEAD

        adapter = GitAdapter(
            path=str(git_repo),
            query={'type': 'history', 'ref': second_commit_hash}
        )
        structure = adapter.get_structure()

        # Should start from the second commit, not HEAD
        assert structure['type'] == 'git_ref'
        assert structure['commit']['full_hash'] == second_commit_hash
        # History from second commit should be shorter than from HEAD
        full_adapter = GitAdapter(path=str(git_repo), query={'type': 'history'})
        full_structure = full_adapter.get_structure()
        assert len(structure['history']) < len(full_structure['history'])

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_ref_query_param_tag(self, git_repo):
        """?ref= query param should accept tag names."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'type': 'history', 'ref': 'v1.0.0'}
        )
        structure = adapter.get_structure()

        assert structure['type'] == 'git_ref'
        assert structure['ref'] == 'v1.0.0'

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_applied_flag_set_when_filters_present(self, git_repo):
        """filter_applied should be True when query filters are used."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'type': 'history', 'author': 'Nonexistent'}
        )
        structure = adapter.get_structure()

        assert structure['type'] == 'git_ref'
        assert structure['filter_applied'] is True
        assert structure['history'] == []

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_applied_flag_not_set_without_filters(self, git_repo):
        """filter_applied should be False when no query filters are used."""
        adapter = GitAdapter(
            path=str(git_repo),
            query={'type': 'history'}
        )
        structure = adapter.get_structure()

        assert structure['type'] == 'git_ref'
        assert structure['filter_applied'] is False

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_filter_preserves_default_limit(self, git_repo):
        """Test that filtering works with default limit."""
        # Create more commits (more than the default limit of 10)
        repo = pygit2.Repository(str(git_repo))
        signature = pygit2.Signature("Test User", "test@example.com")

        # Add 12 more commits (we already have 3, so total will be 15)
        for i in range(12):
            file1 = Path(git_repo) / "README.md"
            file1.write_text(f"# Test Repository\n\nUpdate {i}\n")
            index = repo.index
            index.add("README.md")
            index.write()
            tree = index.write_tree()
            repo.create_commit(
                "HEAD",
                signature,
                signature,
                f"Update {i}",
                tree,
                [repo.head.target]
            )

        # Filter - should get default limit of 10
        adapter = GitAdapter(
            path=str(git_repo),
            query={'author': 'Test User'}
        )
        structure = adapter.get_structure()

        commits = structure['commits']['recent']
        # Should respect default limit of 10
        assert len(commits) == 10
        for commit in commits:
            assert commit['author'] == 'Test User'


class TestGitAdapterBugFixes:
    """Regression tests for git adapter bugs fixed in session digital-vault-0321."""

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_blame_cwd_nested_inside_repo(self, git_repo, tmp_path, monkeypatch):
        """Blame should work when CWD is a subdirectory of the git repo root.

        Bug: pygit2 requires repo-root-relative paths but subpath was CWD-relative.
        When CWD == src/ (inside the repo), 'main.py' was passed to pygit2 instead
        of 'src/main.py', causing a KeyError in the tree lookup.
        """
        # The fixture already created src/main.py inside git_repo.
        # Change CWD to the src/ subdirectory — this simulates the bug scenario.
        src_dir = git_repo / "src"
        monkeypatch.chdir(src_dir)

        # Adapter sees path='.' (CWD = src/) and subpath='main.py'.
        # Without the fix: git_subpath = 'main.py' → pygit2 can't find it in repo tree.
        # With the fix: git_subpath = 'src/main.py' (repo-root-relative).
        adapter = GitAdapter(
            path='.',
            subpath='main.py',
            query={'type': 'blame'}
        )
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file_blame'
        assert structure['path'] == 'src/main.py'
        assert len(structure['hunks']) > 0

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_blame_element_percentage_uses_element_span(self, git_repo):
        """Element blame % should use element line span, not total file lines.

        Bug: _render_file_blame_summary used result['lines'] (total file lines) as
        denominator for element blame. A sole author of a 3-line function in a 10-line
        file showed 30% instead of 100%.
        """
        from io import StringIO
        from reveal.adapters.git.renderer import GitRenderer

        # Craft a blame result that would expose the bug:
        # - file has 10 total lines
        # - element spans lines 1-3 (3 lines)
        # - one author owns all 3 lines in the element
        # Bug: 3/10 = 30.0%; correct: 3/3 = 100.0%
        result = {
            'type': 'git_file_blame',
            'path': 'src/main.py',
            'lines': 10,
            'hunks': [
                {
                    'lines': {'start': 1, 'count': 3},
                    'commit': {
                        'hash': 'abc1234',
                        'author': 'Test User',
                        'email': 'test@example.com',
                        'date': '2026-01-01 00:00:00',
                        'message': 'Add main function',
                    },
                }
            ],
            'element': {
                'name': 'main',
                'line_start': 1,
                'line_end': 3,
            },
            'file_content': ['def main():', "    print('Hello')", '', '', '', '', '', '', '', ''],
            'detail': False,
            'ref': 'HEAD',
            'commit': 'abc1234',
            'contract_version': '1.0',
            'source_type': 'file',
            'source': 'src/main.py@HEAD',
        }

        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        GitRenderer.render_structure(result, format='text')
        sys.stdout = old_stdout
        output = captured.getvalue()

        # With the fix, sole author of all 3 element lines = 100.0%
        assert '100.0%' in output
        # Bug value (3/10) would show 30.0% — must not appear
        assert '30.0%' not in output

    def test_blame_element_percentage_clips_oversized_hunk(self, git_repo):
        """Element blame % should clip oversized hunks to the element span.

        Bug: when a blame hunk spans more lines than the element (e.g. a mass
        line-ending normalization commit owns 344 lines but the element is 27),
        the numerator was the full hunk size → 344/27 = 1274.1%. The fix clips
        the hunk count to its intersection with the element range.
        """
        from io import StringIO
        from reveal.adapters.git.renderer import GitRenderer

        # Element spans lines 10-12 (3 lines).
        # Hunk spans lines 1-100 (100 lines) — a mass-formatting commit.
        # _apply_element_blame_filter clips the intersection to 3 lines.
        # Correct: 3/3 = 100.0%. Bug (no clipping): 100/3 = 3333.3%.
        result = {
            'type': 'git_file_blame',
            'path': 'src/utils.py',
            'lines': 100,
            'hunks': [
                {
                    'lines': {'start': 1, 'count': 100},
                    'clipped_lines': 3,  # set by _apply_element_blame_filter
                    'commit': {
                        'hash': 'def5678',
                        'author': 'Format Bot',
                        'email': 'bot@example.com',
                        'date': '2025-05-01 00:00:00',
                        'message': 'Normalize line endings',
                    },
                }
            ],
            'element': {
                'name': 'helper',
                'line_start': 10,
                'line_end': 12,
            },
            'file_content': ['line'] * 100,
            'detail': False,
            'ref': 'HEAD',
            'commit': 'def5678',
            'contract_version': '1.0',
            'source_type': 'file',
            'source': 'src/utils.py@HEAD',
        }

        old_stdout = sys.stdout
        sys.stdout = captured = StringIO()
        GitRenderer.render_structure(result, format='text')
        sys.stdout = old_stdout
        output = captured.getvalue()

        assert '100.0%' in output
        assert '3333' not in output

    def test_dotslash_uri_form_parses_to_subpath(self):
        """'./path/file.py' URI form should set subpath, not be treated as repo root.

        Bug: './src/main.py' was not handled, falling through to the bare-path branch
        which set path='./src/main.py' and subpath=None — routing to repo overview
        instead of file blame.
        """
        from reveal.adapters.git.adapter import GitAdapter
        parsed = GitAdapter._parse_resource_string('./src/main.py?type=blame')

        assert parsed['path'] == '.'
        assert parsed['subpath'] == 'src/main.py'
        assert parsed['query'] == {'type': 'blame'}

    def test_dotslash_root_still_means_repo_overview(self):
        """'.' and './' should still route to repo overview (path='.', subpath=None)."""
        from reveal.adapters.git.adapter import GitAdapter

        for resource in ('.', './'):
            parsed = GitAdapter._parse_resource_string(resource)
            assert parsed['path'] == resource
            assert parsed['subpath'] is None


class TestApplyElementBlameFilter(unittest.TestCase):
    """Unit tests for _apply_element_blame_filter clipped_lines computation."""

    def _get_range_func(self, el_start, el_end):
        return lambda name, path, subpath: {'line': el_start, 'line_end': el_end}

    def _make_hunk(self, start, count):
        return {
            'lines': {'start': start, 'count': count},
            'commit': {'hash': 'abc', 'author': 'A', 'date': '2026-01-01', 'message': 'msg'},
        }

    def test_hunk_exactly_matches_element(self):
        from reveal.adapters.git.files import _apply_element_blame_filter
        hunk = self._make_hunk(5, 3)  # lines 5-7
        _, filtered = _apply_element_blame_filter(
            'func', [hunk], 'repo', 'f.py', self._get_range_func(5, 7)
        )
        assert filtered[0]['clipped_lines'] == 3

    def test_hunk_larger_than_element(self):
        from reveal.adapters.git.files import _apply_element_blame_filter
        hunk = self._make_hunk(1, 100)  # lines 1-100
        _, filtered = _apply_element_blame_filter(
            'func', [hunk], 'repo', 'f.py', self._get_range_func(10, 12)
        )
        assert filtered[0]['clipped_lines'] == 3  # only lines 10-12 are in the element

    def test_hunk_partially_overlaps_start(self):
        from reveal.adapters.git.files import _apply_element_blame_filter
        hunk = self._make_hunk(8, 5)  # lines 8-12; element is 10-15
        _, filtered = _apply_element_blame_filter(
            'func', [hunk], 'repo', 'f.py', self._get_range_func(10, 15)
        )
        assert filtered[0]['clipped_lines'] == 3  # overlap: lines 10-12

    def test_hunk_partially_overlaps_end(self):
        from reveal.adapters.git.files import _apply_element_blame_filter
        hunk = self._make_hunk(13, 5)  # lines 13-17; element is 10-15
        _, filtered = _apply_element_blame_filter(
            'func', [hunk], 'repo', 'f.py', self._get_range_func(10, 15)
        )
        assert filtered[0]['clipped_lines'] == 3  # overlap: lines 13-15

    def test_hunk_outside_element_excluded(self):
        from reveal.adapters.git.files import _apply_element_blame_filter
        hunk = self._make_hunk(20, 5)  # lines 20-24; element is 10-12
        _, filtered = _apply_element_blame_filter(
            'func', [hunk], 'repo', 'f.py', self._get_range_func(10, 12)
        )
        assert filtered == []


class TestFilterIgnoredHunks(unittest.TestCase):
    """Tests for GIT-6: ?ignore= noise-commit blame suppression."""

    def _make_hunk(self, h_hash, lines_count, message='msg'):
        return {
            'lines': {'start': 1, 'count': lines_count},
            'commit': {'hash': h_hash, 'author': 'A', 'email': 'a@b', 'date': '2026-01-01', 'message': message},
        }

    def test_no_ignore_returns_all_hunks(self):
        from reveal.adapters.git.files import _filter_ignored_hunks
        hunks = [self._make_hunk('abc1234', 10), self._make_hunk('def5678', 5)]
        kept, ignored = _filter_ignored_hunks(hunks, [])
        assert kept == hunks
        assert ignored == []

    def test_exact_hash_match_removes_hunk(self):
        from reveal.adapters.git.files import _filter_ignored_hunks
        hunks = [self._make_hunk('abc1234', 10), self._make_hunk('def5678', 5)]
        kept, ignored = _filter_ignored_hunks(hunks, ['abc1234'])
        assert len(kept) == 1
        assert kept[0]['commit']['hash'] == 'def5678'
        assert len(ignored) == 1
        assert ignored[0]['hash'] == 'abc1234'
        assert ignored[0]['lines'] == 10

    def test_prefix_match_removes_hunk(self):
        from reveal.adapters.git.files import _filter_ignored_hunks
        hunks = [self._make_hunk('abc1234', 7)]
        kept, ignored = _filter_ignored_hunks(hunks, ['abc'])
        assert kept == []
        assert ignored[0]['hash'] == 'abc1234'

    def test_multiple_hunks_same_commit_collapsed_in_summary(self):
        from reveal.adapters.git.files import _filter_ignored_hunks
        hunks = [self._make_hunk('abc1234', 10), self._make_hunk('abc1234', 15)]
        kept, ignored = _filter_ignored_hunks(hunks, ['abc1234'])
        assert kept == []
        assert len(ignored) == 1
        assert ignored[0]['lines'] == 25

    def test_clipped_lines_used_when_present(self):
        from reveal.adapters.git.files import _filter_ignored_hunks
        hunk = {**self._make_hunk('abc1234', 100), 'clipped_lines': 12}
        _, ignored = _filter_ignored_hunks([hunk], ['abc1234'])
        assert ignored[0]['lines'] == 12

    def test_unmatched_sha_not_removed(self):
        from reveal.adapters.git.files import _filter_ignored_hunks
        hunks = [self._make_hunk('abc1234', 10), self._make_hunk('xyz9999', 5)]
        kept, ignored = _filter_ignored_hunks(hunks, ['zzz0000'])
        assert len(kept) == 2
        assert ignored == []

    def test_ignore_summary_includes_message(self):
        from reveal.adapters.git.files import _filter_ignored_hunks
        hunks = [self._make_hunk('abc1234', 10, 'Normalize line endings')]
        _, ignored = _filter_ignored_hunks(hunks, ['abc1234'])
        assert ignored[0]['message'] == 'Normalize line endings'


class TestCommitTouchesElement(unittest.TestCase):
    """Unit tests for GIT-5: commit_touches_element using a real git_repo fixture."""

    def test_touches_element_returns_false_when_file_unchanged(self, git_repo=None):
        """If commit_touches_file is False, commit_touches_element must also be False."""
        from unittest.mock import MagicMock, patch
        from reveal.adapters.git.files import commit_touches_element

        repo = MagicMock()
        commit = MagicMock()
        commit.parents = [MagicMock()]

        with patch('reveal.adapters.git.files.commit_touches_file', return_value=False):
            result = commit_touches_element(repo, commit, 'foo.py', 'my_func')

        assert result is False

    def test_touches_element_true_when_content_differs(self):
        from unittest.mock import MagicMock, patch
        from reveal.adapters.git.files import commit_touches_element

        repo = MagicMock()
        commit = MagicMock()
        parent = MagicMock()
        commit.parents = [parent]

        with patch('reveal.adapters.git.files.commit_touches_file', return_value=True), \
             patch('reveal.adapters.git.files._get_element_content_at_commit',
                   side_effect=lambda repo, c, path, name: 'v1' if c is commit else 'v0'):
            result = commit_touches_element(repo, commit, 'foo.py', 'my_func')

        assert result is True

    def test_touches_element_false_when_content_same(self):
        from unittest.mock import MagicMock, patch
        from reveal.adapters.git.files import commit_touches_element

        repo = MagicMock()
        commit = MagicMock()
        parent = MagicMock()
        commit.parents = [parent]

        with patch('reveal.adapters.git.files.commit_touches_file', return_value=True), \
             patch('reveal.adapters.git.files._get_element_content_at_commit',
                   return_value='same content'):
            result = commit_touches_element(repo, commit, 'foo.py', 'my_func')

        assert result is False

    def test_touches_element_true_for_initial_commit(self):
        from unittest.mock import MagicMock, patch
        from reveal.adapters.git.files import commit_touches_element

        repo = MagicMock()
        commit = MagicMock()
        commit.parents = []

        with patch('reveal.adapters.git.files.commit_touches_file', return_value=True), \
             patch('reveal.adapters.git.files._get_element_content_at_commit',
                   return_value='def my_func(): pass'):
            result = commit_touches_element(repo, commit, 'foo.py', 'my_func')

        assert result is True

    def test_touches_element_false_when_element_missing_at_commit(self):
        from unittest.mock import MagicMock, patch
        from reveal.adapters.git.files import commit_touches_element

        repo = MagicMock()
        commit = MagicMock()
        commit.parents = [MagicMock()]

        with patch('reveal.adapters.git.files.commit_touches_file', return_value=True), \
             patch('reveal.adapters.git.files._get_element_content_at_commit',
                   return_value=None):
            result = commit_touches_element(repo, commit, 'foo.py', 'my_func')

        assert result is False


class TestGitAdapterSchema(unittest.TestCase):
    """Test schema generation for AI agent integration."""

    def test_get_schema(self):
        """Should return machine-readable schema."""
        schema = GitAdapter.get_schema()

        self.assertIsNotNone(schema)
        self.assertEqual(schema['adapter'], 'git')
        self.assertIn('description', schema)
        self.assertIn('uri_syntax', schema)
        self.assertIn('git://', schema['uri_syntax'])

    def test_schema_query_params(self):
        """Schema should document query parameters."""
        schema = GitAdapter.get_schema()

        self.assertIn('query_params', schema)
        query_params = schema['query_params']

        # Should have filtering params
        self.assertIn('author', query_params)
        self.assertIn('email', query_params)
        self.assertIn('message', query_params)
        self.assertIn('hash', query_params)

        # Should have type param for history/blame
        self.assertIn('type', query_params)
        type_param = query_params['type']
        self.assertIn('history', type_param['values'])
        self.assertIn('blame', type_param['values'])

    def test_schema_cli_flags(self):
        """Schema should document CLI flags."""
        schema = GitAdapter.get_schema()

        self.assertIn('cli_flags', schema)
        self.assertIsInstance(schema['cli_flags'], list)

    def test_schema_output_types(self):
        """Schema should define output types."""
        schema = GitAdapter.get_schema()

        self.assertIn('output_types', schema)
        self.assertTrue(len(schema['output_types']) >= 1)

        # Should have repository output type
        output_types = [ot['type'] for ot in schema['output_types']]
        self.assertIn('git_repository', output_types)

    def test_schema_examples(self):
        """Schema should include usage examples."""
        schema = GitAdapter.get_schema()

        self.assertIn('example_queries', schema)
        self.assertTrue(len(schema['example_queries']) >= 5)

        # Examples should have required fields
        for example in schema['example_queries']:
            self.assertIn('uri', example)
            self.assertIn('description', example)

    def test_schema_batch_support(self):
        """Schema should indicate batch support status."""
        schema = GitAdapter.get_schema()

        self.assertIn('supports_batch', schema)
        self.assertIn('supports_advanced', schema)


class TestGitRenderer(unittest.TestCase):
    """Test renderer output formatting."""

    @pytest.fixture(autouse=True)
    def setup(self, git_repo):
        """Set up test fixtures."""
        self.git_repo = git_repo

    def test_renderer_repository_overview(self):
        """Renderer should format repository overview correctly."""
        from reveal.adapters.git.adapter import GitRenderer
        from io import StringIO

        adapter = GitAdapter(path=str(self.git_repo))
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        GitRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain key sections
        self.assertIn('Repository:', output)
        self.assertIn('HEAD:', output)
        self.assertIn('Branches:', output)
        self.assertIn('Recent Commits:', output)

    def test_renderer_json_format(self):
        """Renderer should support JSON output."""
        import json
        from reveal.adapters.git.adapter import GitRenderer
        from io import StringIO

        adapter = GitAdapter(path=str(self.git_repo))
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        GitRenderer.render_structure(result, format='json')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should be valid JSON
        parsed = json.loads(output)
        self.assertIn('type', parsed)
        self.assertEqual(parsed['type'], 'git_repository')

    def test_renderer_error_handling(self):
        """Renderer should handle errors gracefully."""
        from reveal.adapters.git.adapter import GitRenderer
        from io import StringIO

        # Capture stderr (render_error outputs to stderr)
        old_stderr = sys.stderr
        sys.stderr = captured_output = StringIO()

        error = FileNotFoundError("Repository not found")
        GitRenderer.render_error(error)

        sys.stderr = old_stderr
        output = captured_output.getvalue()

        self.assertIn('Error', output)
        self.assertIn('Repository not found', output)

    def test_renderer_file_history(self):
        """Renderer should format file history correctly."""
        from reveal.adapters.git.adapter import GitRenderer
        from io import StringIO

        adapter = GitAdapter(
            path=str(self.git_repo),
            subpath='test.txt',
            query={'type': 'history'}
        )
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        GitRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain file history info
        self.assertIn('File History:', output)
        self.assertIn('test.txt', output)

    def test_renderer_empty_history_with_filter_shows_hint(self):
        """When history is empty and a filter was applied, renderer shows a helpful hint."""
        from reveal.adapters.git.renderer import GitRenderer
        from io import StringIO

        result = {
            'type': 'git_ref',
            'ref': 'HEAD',
            'commit': {
                'full_hash': 'abc1234',
                'author': 'Test User',
                'email': 'test@example.com',
                'date': '2026-01-01 00:00:00',
                'full_message': 'test commit\n',
            },
            'history': [],
            'filter_applied': True,
        }

        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        GitRenderer.render_structure(result, format='text')
        sys.stdout = old_stdout
        output = captured_output.getvalue()

        self.assertIn('no commits matched filter', output)
        self.assertIn('~=', output)

    def test_renderer_empty_history_without_filter_shows_no_hint(self):
        """When history is empty and no filter was applied, renderer shows (no commits)."""
        from reveal.adapters.git.renderer import GitRenderer
        from io import StringIO

        result = {
            'type': 'git_ref',
            'ref': 'HEAD',
            'commit': {
                'full_hash': 'abc1234',
                'author': 'Test User',
                'email': 'test@example.com',
                'date': '2026-01-01 00:00:00',
                'full_message': 'test commit\n',
            },
            'history': [],
            'filter_applied': False,
        }

        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()
        GitRenderer.render_structure(result, format='text')
        sys.stdout = old_stdout
        output = captured_output.getvalue()

        self.assertIn('(no commits)', output)
        self.assertNotIn('~=', output)


# ---------------------------------------------------------------------------
# GIT-5: _get_element_content_at_commit — blob I/O + analyzer extraction
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
class TestGetElementContentAtCommit:
    """Tests for _get_element_content_at_commit: the blob→tempfile→analyzer pipeline."""

    def test_returns_function_text_from_head_commit(self, git_repo_py_history):
        from reveal.adapters.git.files import _get_element_content_at_commit
        repo = pygit2.Repository(str(git_repo_py_history))
        head = repo.head.peel(pygit2.Commit)
        content = _get_element_content_at_commit(repo, head, 'calc.py', 'add')
        assert content is not None
        assert 'def add' in content
        assert 'return a + b' in content

    def test_returns_none_for_element_not_in_file(self, git_repo_py_history):
        from reveal.adapters.git.files import _get_element_content_at_commit
        repo = pygit2.Repository(str(git_repo_py_history))
        head = repo.head.peel(pygit2.Commit)
        assert _get_element_content_at_commit(repo, head, 'calc.py', 'nonexistent_func') is None

    def test_returns_none_for_file_not_in_tree(self, git_repo_py_history):
        from reveal.adapters.git.files import _get_element_content_at_commit
        repo = pygit2.Repository(str(git_repo_py_history))
        head = repo.head.peel(pygit2.Commit)
        assert _get_element_content_at_commit(repo, head, 'no_such.py', 'add') is None

    def test_element_content_differs_between_commits_that_changed_it(self, git_repo_py_history):
        """add() at commit3 has extra comment line; commit1 does not — must differ."""
        from reveal.adapters.git.files import _get_element_content_at_commit
        repo = pygit2.Repository(str(git_repo_py_history))
        # Walk newest-first: [commit3, commit2, commit1]
        commits = list(repo.walk(repo.head.target, pygit2.GIT_SORT_TIME))
        commit3 = commits[0]   # "Improve add() with comment"
        commit1 = commits[2]   # "Add calc.py with add()"
        at_head = _get_element_content_at_commit(repo, commit3, 'calc.py', 'add')
        at_first = _get_element_content_at_commit(repo, commit1, 'calc.py', 'add')
        assert at_head is not None and at_first is not None
        assert at_head != at_first

    def test_element_content_identical_when_commit_did_not_touch_it(self, git_repo_py_history):
        """add() at commit2 and commit1 should have identical content."""
        from reveal.adapters.git.files import _get_element_content_at_commit
        repo = pygit2.Repository(str(git_repo_py_history))
        commits = list(repo.walk(repo.head.target, pygit2.GIT_SORT_TIME))
        commit2 = commits[1]   # "Add subtract()"
        commit1 = commits[2]   # "Add calc.py with add()"
        at_commit2 = _get_element_content_at_commit(repo, commit2, 'calc.py', 'add')
        at_commit1 = _get_element_content_at_commit(repo, commit1, 'calc.py', 'add')
        assert at_commit2 is not None and at_commit1 is not None
        assert at_commit2 == at_commit1


# ---------------------------------------------------------------------------
# GIT-5 integration: ?type=history&element= through full GitAdapter stack
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
class TestElementHistoryIntegration:
    """Integration tests for GIT-5: element-scoped history via GitAdapter."""

    def test_add_history_returns_only_commits_that_changed_add(self, git_repo_py_history):
        """add() was touched in commits 1 and 3 (not 2). Expect count=2."""
        adapter = GitAdapter(
            path=str(git_repo_py_history),
            subpath='calc.py',
            query={'type': 'history', 'element': 'add', 'limit': '10'},
        )
        result = adapter.get_structure()
        assert result['type'] == 'git_file_history'
        assert result['count'] == 2
        messages = [c['message'] for c in result['commits']]
        assert any('Improve add()' in m for m in messages)
        assert any('Add calc.py' in m for m in messages)
        assert not any('subtract' in m for m in messages)

    def test_subtract_history_returns_only_commit_that_added_it(self, git_repo_py_history):
        """subtract() was introduced in commit 2 and untouched in commit 3. Expect count=1."""
        adapter = GitAdapter(
            path=str(git_repo_py_history),
            subpath='calc.py',
            query={'type': 'history', 'element': 'subtract', 'limit': '10'},
        )
        result = adapter.get_structure()
        assert result['count'] == 1
        assert 'subtract' in result['commits'][0]['message']

    def test_element_key_present_in_result(self, git_repo_py_history):
        adapter = GitAdapter(
            path=str(git_repo_py_history),
            subpath='calc.py',
            query={'type': 'history', 'element': 'add'},
        )
        result = adapter.get_structure()
        assert result.get('element') == 'add'

    def test_no_element_key_returns_all_file_commits(self, git_repo_py_history):
        """Without ?element=, all 3 commits touching calc.py should be returned."""
        adapter = GitAdapter(
            path=str(git_repo_py_history),
            subpath='calc.py',
            query={'type': 'history', 'limit': '10'},
        )
        result = adapter.get_structure()
        assert result['count'] == 3
        assert 'element' not in result


# ---------------------------------------------------------------------------
# GIT-6 integration: ?type=blame&ignore= through full GitAdapter stack
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
class TestIgnoreBlameIntegration:
    """Integration tests for GIT-6: blame ?ignore= through full GitAdapter stack."""

    def _blame_hashes(self, git_repo, subpath='README.md'):
        """Return the set of commit hashes that appear in the blame for a file."""
        adapter = GitAdapter(path=str(git_repo), subpath=subpath, query={'type': 'blame'})
        result = adapter.get_structure()
        return {h['commit']['hash'] for h in result['hunks']}

    def test_ignore_suppresses_matching_hunks_and_populates_ignored_key(self, git_repo):
        """Ignoring a commit that owns some lines removes those hunks and adds 'ignored'."""
        # README.md has at least two hunks (initial content + updated line).
        # Pick the first hunk's hash as our target — it's a real commit in this blame.
        adapter_base = GitAdapter(path=str(git_repo), subpath='README.md', query={'type': 'blame'})
        base = adapter_base.get_structure()
        target_hash = base['hunks'][0]['commit']['hash']

        adapter = GitAdapter(
            path=str(git_repo),
            subpath='README.md',
            query={'type': 'blame', 'ignore': target_hash},
        )
        result = adapter.get_structure()

        assert result['type'] == 'git_file_blame'
        assert 'ignored' in result
        assert any(e['hash'] == target_hash for e in result['ignored'])
        # Target commit must not appear in remaining hunks
        hunk_hashes = {h['commit']['hash'] for h in result['hunks']}
        assert target_hash not in hunk_hashes

    def test_ignore_with_no_match_leaves_hunks_intact(self, git_repo):
        all_hashes = self._blame_hashes(git_repo)
        adapter = GitAdapter(
            path=str(git_repo),
            subpath='README.md',
            query={'type': 'blame', 'ignore': 'fffffff'},
        )
        result = adapter.get_structure()
        assert 'ignored' not in result
        assert {h['commit']['hash'] for h in result['hunks']} == all_hashes

    def test_ignore_prefix_shorter_than_7_chars_still_matches(self, git_repo):
        """A 4-char prefix is enough to match a 7-char hunk hash."""
        adapter_base = GitAdapter(path=str(git_repo), subpath='README.md', query={'type': 'blame'})
        target_hash = adapter_base.get_structure()['hunks'][0]['commit']['hash']
        short_prefix = target_hash[:4]

        adapter = GitAdapter(
            path=str(git_repo),
            subpath='README.md',
            query={'type': 'blame', 'ignore': short_prefix},
        )
        result = adapter.get_structure()
        assert 'ignored' in result
        assert any(e['hash'].startswith(short_prefix) for e in result['ignored'])

    def test_ignore_does_not_affect_history_queries(self, git_repo):
        """?ignore= is an operational param — must not filter commits in ?type=history."""
        adapter = GitAdapter(
            path=str(git_repo),
            subpath='README.md',
            query={'type': 'history', 'ignore': 'abc1234', 'limit': '10'},
        )
        result = adapter.get_structure()
        # ignore= has no effect on history; both README commits returned
        assert result['count'] >= 2


# ---------------------------------------------------------------------------
# Renderer tests for GIT-5 (Element History header) and GIT-6 (Suppressed block)
# ---------------------------------------------------------------------------

class TestRendererNewFeatures(unittest.TestCase):
    """Renderer output tests for GIT-5 and GIT-6 display logic."""

    def _render(self, result):
        from io import StringIO
        from reveal.adapters.git.renderer import GitRenderer
        old = sys.stdout
        sys.stdout = buf = StringIO()
        GitRenderer.render_structure(result, format='text')
        sys.stdout = old
        return buf.getvalue()

    def _history_result(self, element=None, count=1):
        r = {
            'type': 'git_file_history',
            'path': 'src/app.py',
            'ref': 'HEAD',
            'count': count,
            'commits': [
                {'hash': 'abc1234', 'date': '2026-01-01 00:00:00',
                 'author': 'Alice', 'message': 'Initial work'},
            ],
        }
        if element is not None:
            r['element'] = element
        return r

    def _blame_result(self, hunks, ignored=None):
        r = {
            'type': 'git_file_blame',
            'path': 'src/app.py',
            'ref': 'HEAD',
            'commit': 'abc1234',
            'lines': 10,
            'hunks': hunks,
            'file_content': ['line'] * 10,
            'detail': False,
            'contract_version': '1.0',
            'source_type': 'file',
            'source': 'src/app.py@HEAD',
        }
        if ignored is not None:
            r['ignored'] = ignored
        return r

    # -- GIT-5 renderer --

    def test_element_history_shows_element_header(self):
        output = self._render(self._history_result(element='load_config'))
        self.assertIn('Element History', output)
        self.assertIn('load_config', output)
        self.assertNotIn('File History', output)

    def test_file_history_shows_file_header_without_element(self):
        output = self._render(self._history_result())
        self.assertIn('File History', output)
        self.assertNotIn('Element History', output)

    # -- GIT-6 renderer --

    def test_blame_suppressed_block_appears_when_ignored_present(self):
        hunks = [{
            'lines': {'start': 5, 'count': 3},
            'commit': {'hash': 'def5678', 'author': 'Alice', 'email': 'a@b',
                       'date': '2026-01-01 00:00:00', 'message': 'Real work'},
        }]
        ignored = [{'hash': 'abc1234', 'message': 'Normalize line endings', 'lines': 7}]
        output = self._render(self._blame_result(hunks, ignored=ignored))
        self.assertIn('Suppressed', output)
        self.assertIn('abc1234', output)
        self.assertIn('Normalize line endings', output)
        self.assertIn('7', output)          # line count

    def test_blame_no_suppressed_block_when_no_ignored_key(self):
        hunks = [{
            'lines': {'start': 1, 'count': 5},
            'commit': {'hash': 'abc1234', 'author': 'Alice', 'email': 'a@b',
                       'date': '2026-01-01 00:00:00', 'message': 'Init'},
        }]
        output = self._render(self._blame_result(hunks))
        self.assertNotIn('Suppressed', output)

    def test_blame_suppressed_shows_commit_count(self):
        hunks = []
        ignored = [
            {'hash': 'aaa1111', 'message': 'Format run A', 'lines': 30},
            {'hash': 'bbb2222', 'message': 'Format run B', 'lines': 20},
        ]
        output = self._render(self._blame_result(hunks, ignored=ignored))
        self.assertIn('2', output)          # 2 noise commits
        self.assertIn('50', output)         # 30+20 total lines suppressed
