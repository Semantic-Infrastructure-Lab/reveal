"""Coverage tests for reveal/adapters/diff/git.py.

BACK-505: resolve_git_ref/resolve_git_file/resolve_git_directory/_ls_tree_files/
_fetch_and_analyze_git_file were rewritten from `subprocess` calls to the `git`
CLI to in-process pygit2 (matching resolve_git_adapter's existing pattern).
These tests exercise the pygit2 path against a real temp repo rather than
mocking pygit2's internals, since Tree/Commit/Blob objects are cheap to
produce for real and mocking them faithfully is more fragile than the code
under test.

resolve_git_adapter is unchanged by BACK-505 and keeps its original
sys.modules-based mocking style.
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

from reveal.adapters.diff.git import (
    resolve_git_adapter,
    resolve_git_file,
    resolve_git_directory,
    _fetch_and_analyze_git_file,
    _ls_tree_files,
    _tag_items_with_file,
    resolve_git_ref,
)


# ─── resolve_git_adapter ─────────────────────────────────────────────────────
# Unchanged by BACK-505 — still goes through GitAdapter directly.

class TestResolveGitAdapter:
    def test_import_error_raises_helpful_message(self):
        with patch.dict(sys.modules, {'reveal.adapters.git.adapter': None}):
            with pytest.raises(ImportError, match='GitAdapter not available'):
                resolve_git_adapter('test.py@HEAD')

    def test_colon_format_raises_valueerror(self):
        with pytest.raises(ValueError, match='Git URI format error'):
            resolve_git_adapter('HEAD~1:file.py')

    def test_no_at_no_slash_raises_valueerror(self):
        with pytest.raises(ValueError, match='Git URI must be in format'):
            resolve_git_adapter('main')

    def test_git_adapter_file_result_analyzes_content(self):
        mock_adapter = MagicMock()
        mock_adapter.get_structure.return_value = {
            'type': 'file_at_ref',
            'content': 'def foo(): pass',
            'path': 'test.py',
        }
        mock_adapter_cls = MagicMock(return_value=mock_adapter)

        mock_analyzer = MagicMock()
        mock_analyzer.get_structure.return_value = {'functions': [{'name': 'foo'}]}
        mock_analyzer_cls = MagicMock(return_value=mock_analyzer)

        mock_git_module = MagicMock()
        mock_git_module.GitAdapter = mock_adapter_cls

        with patch.dict(sys.modules, {'reveal.adapters.git.adapter': mock_git_module}):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=mock_analyzer_cls):
                result = resolve_git_adapter('test.py@HEAD')
        assert 'functions' in result

    def test_git_adapter_no_analyzer_raises_valueerror(self):
        mock_adapter = MagicMock()
        mock_adapter.get_structure.return_value = {
            'type': 'file_at_ref',
            'content': 'def foo(): pass',
            'path': 'test.py',
        }
        mock_adapter_cls = MagicMock(return_value=mock_adapter)
        mock_git_module = MagicMock()
        mock_git_module.GitAdapter = mock_adapter_cls

        with patch.dict(sys.modules, {'reveal.adapters.git.adapter': mock_git_module}):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=None):
                with pytest.raises(ValueError, match='No analyzer found'):
                    resolve_git_adapter('test.py@HEAD')

    def test_git_adapter_non_file_result_returned_as_is(self):
        mock_adapter = MagicMock()
        mock_adapter.get_structure.return_value = {'type': 'repository', 'refs': []}
        mock_adapter_cls = MagicMock(return_value=mock_adapter)
        mock_git_module = MagicMock()
        mock_git_module.GitAdapter = mock_adapter_cls

        with patch.dict(sys.modules, {'reveal.adapters.git.adapter': mock_git_module}):
            result = resolve_git_adapter('path/to/dir@HEAD')
        assert result == {'type': 'repository', 'refs': []}

    def test_git_adapter_exception_raises_valueerror(self):
        mock_git_module = MagicMock()
        mock_git_module.GitAdapter = MagicMock(side_effect=RuntimeError('git boom'))

        with patch.dict(sys.modules, {'reveal.adapters.git.adapter': mock_git_module}):
            with pytest.raises(ValueError, match='Failed to resolve git'):
                resolve_git_adapter('test.py@HEAD')


# ─── Real temp repo fixture for the pygit2-backed functions ─────────────────

@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """Create a real git repo with one commit, chdir into it.

    Layout:
        file.py           -> def foo(): pass
        sub/mod.py         -> def bar(): pass
        sub/readme.txt     -> not code, no analyzer
    """
    import pygit2

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    repo = pygit2.init_repository(str(repo_dir))

    (repo_dir / "file.py").write_text("def foo():\n    pass\n")
    sub_dir = repo_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "mod.py").write_text("def bar():\n    pass\n")
    (sub_dir / "readme.txt").write_text("not analyzable\n")

    index = repo.index
    index.add_all()
    index.write()
    tree_oid = index.write_tree()
    author = pygit2.Signature("Test", "test@example.com")
    repo.create_commit("HEAD", author, author, "initial commit", tree_oid, [])

    monkeypatch.chdir(repo_dir)
    return repo_dir


# ─── resolve_git_ref ─────────────────────────────────────────────────────────

class TestResolveGitRef:
    def test_not_in_git_repo_raises_valueerror(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValueError, match='Not in a git repository'):
            resolve_git_ref('HEAD', 'file.py')

    def test_path_not_found_raises_valueerror(self, git_repo):
        with pytest.raises(ValueError, match='Path not found'):
            resolve_git_ref('HEAD', 'missing.py')

    def test_bad_ref_raises_valueerror(self, git_repo):
        with pytest.raises(ValueError):
            resolve_git_ref('not-a-real-ref', 'file.py')

    def test_file_path_routes_to_resolve_git_file(self, git_repo):
        result = resolve_git_ref('HEAD', 'file.py')
        assert any(f['name'] == 'foo' for f in result['functions'])

    def test_directory_path_routes_to_resolve_git_directory(self, git_repo):
        result = resolve_git_ref('HEAD', 'sub')
        assert result['type'] == 'git_directory'
        assert result['file_count'] == 1

    def test_pygit2_missing_raises_importerror(self, git_repo):
        with patch.dict(sys.modules, {'pygit2': None}):
            with pytest.raises(ImportError, match='requires pygit2'):
                resolve_git_ref('HEAD', 'file.py')


# ─── resolve_git_file ─────────────────────────────────────────────────────────

class TestResolveGitFile:
    def test_missing_file_raises_valueerror(self, git_repo):
        with pytest.raises(ValueError):
            resolve_git_file('HEAD', 'missing.py')

    def test_no_analyzer_raises_valueerror(self, git_repo):
        with patch('reveal.adapters.diff.git.get_analyzer', return_value=None):
            with pytest.raises(ValueError, match='No analyzer found'):
                resolve_git_file('HEAD', 'file.py')

    def test_success_returns_structure(self, git_repo):
        result = resolve_git_file('HEAD', 'file.py')
        assert any(f['name'] == 'foo' for f in result['functions'])


# ─── _fetch_and_analyze_git_file ─────────────────────────────────────────────

class TestFetchAndAnalyzeGitFile:
    def test_no_analyzer_returns_empty_dict(self, git_repo):
        with patch('reveal.adapters.diff.git.get_analyzer', return_value=None):
            result = _fetch_and_analyze_git_file('HEAD', 'file.py')
        assert result == {}

    def test_success_returns_structure(self, git_repo):
        result = _fetch_and_analyze_git_file('HEAD', 'file.py')
        assert any(f['name'] == 'foo' for f in result['functions'])


# ─── _ls_tree_files ───────────────────────────────────────────────────────────

class TestLsTreeFiles:
    def test_missing_directory_raises_valueerror(self, git_repo):
        with pytest.raises(ValueError, match='Directory not found'):
            _ls_tree_files('HEAD', 'nosuchdir')

    def test_file_path_raises_valueerror(self, git_repo):
        with pytest.raises(ValueError, match='not a directory'):
            _ls_tree_files('HEAD', 'file.py')

    def test_returns_blob_file_paths_recursively(self, git_repo):
        result = _ls_tree_files('HEAD', 'sub')
        assert 'sub/mod.py' in result
        assert 'sub/readme.txt' in result
        assert len(result) == 2

    def test_root_lists_all_files(self, git_repo):
        result = _ls_tree_files('HEAD', '.')
        assert 'file.py' in result
        assert 'sub/mod.py' in result


# ─── _tag_items_with_file ────────────────────────────────────────────────────

class TestTagItemsWithFile:
    def test_tags_all_items(self):
        struct = {'functions': [{'name': 'foo'}, {'name': 'bar'}]}
        result = _tag_items_with_file(struct, 'myfile.py', 'functions')
        assert all(item['file'] == 'myfile.py' for item in result)
        assert len(result) == 2

    def test_missing_key_returns_empty(self):
        result = _tag_items_with_file({}, 'myfile.py', 'functions')
        assert result == []


# ─── resolve_git_directory ───────────────────────────────────────────────────

class TestResolveGitDirectory:
    def test_skips_files_without_analyzer(self, git_repo):
        with patch('reveal.adapters.diff.git._ls_tree_files', return_value=['dir/main.js']):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=None):
                result = resolve_git_directory('HEAD', 'dir')
        assert result['file_count'] == 0
        assert result['functions'] == []

    def test_skips_files_with_fetch_exception(self, git_repo):
        mock_cls = MagicMock()

        with patch('reveal.adapters.diff.git._ls_tree_files', return_value=['dir/file.py']):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=mock_cls):
                with patch('reveal.adapters.diff.git._fetch_and_analyze_git_file',
                           side_effect=RuntimeError('git exploded')):
                    result = resolve_git_directory('HEAD', 'dir')
        assert result['file_count'] == 0

    def test_skips_empty_struct(self, git_repo):
        mock_cls = MagicMock()

        with patch('reveal.adapters.diff.git._ls_tree_files', return_value=['dir/file.py']):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=mock_cls):
                with patch('reveal.adapters.diff.git._fetch_and_analyze_git_file', return_value={}):
                    result = resolve_git_directory('HEAD', 'dir')
        assert result['file_count'] == 0

    def test_aggregates_functions_and_classes(self, git_repo):
        mock_cls = MagicMock()
        struct = {'functions': [{'name': 'foo'}], 'classes': [{'name': 'Bar'}], 'imports': []}

        with patch('reveal.adapters.diff.git._ls_tree_files', return_value=['dir/file.py']):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=mock_cls):
                with patch('reveal.adapters.diff.git._fetch_and_analyze_git_file', return_value=struct):
                    result = resolve_git_directory('HEAD', 'dir')

        assert result['file_count'] == 1
        assert result['functions'][0]['name'] == 'foo'
        assert result['classes'][0]['name'] == 'Bar'
        assert result['type'] == 'git_directory'

    def test_end_to_end_real_repo(self, git_repo):
        """Full path with no mocking: real repo, real pygit2, real analyzer."""
        result = resolve_git_directory('HEAD', 'sub')
        assert result['file_count'] == 1
        assert any(f['name'] == 'bar' for f in result['functions'])
