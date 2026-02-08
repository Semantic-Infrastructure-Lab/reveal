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


class TestGitAdapterBasics:
    """Test basic git adapter functionality."""

    def test_adapter_without_pygit2(self):
        """Test error message when pygit2 is not available."""
        if PYGIT2_AVAILABLE:
            pytest.skip("pygit2 is available")

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
        """Test getting file contents at a ref."""
        adapter = GitAdapter(path=str(git_repo), ref='HEAD', subpath='README.md')
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'file'
        assert structure['path'] == 'README.md'
        assert 'content' in structure
        assert 'Updated content' in structure['content']

    @pytest.mark.skipif(not PYGIT2_AVAILABLE, reason="pygit2 not available")
    def test_get_file_at_tag(self, git_repo):
        """Test getting file contents at a tag."""
        adapter = GitAdapter(path=str(git_repo), ref='v1.0.0', subpath='README.md')
        structure = adapter.get_structure()

        assert structure['type'] == 'git_file'
        assert structure['contract_version'] == '1.0'
        assert structure['source_type'] == 'file'
        assert structure['path'] == 'README.md'
        assert 'content' in structure

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
        """Test getting a file element."""
        adapter = GitAdapter(path=str(git_repo), ref='HEAD')
        element = adapter.get_element('README.md')

        assert element is not None
        assert element['type'] == 'git_file'
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
        self.assertIn('Commits:', output)
