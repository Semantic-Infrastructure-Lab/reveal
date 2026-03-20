"""Coverage tests for reveal/adapters/diff/git.py.

Targets: lines 46, 71-72, 81-82, 95-130, 152-153, 163, 188, 203-205, 245, 248-249, 251
Current coverage: 71% → target: 90%+

Note: get_analyzer is hoisted to module level → patch reveal.adapters.diff.git.get_analyzer.
      GitAdapter is imported inside resolve_git_adapter → patch via sys.modules.
"""

import sys
import pytest
import subprocess
from pathlib import Path
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

class TestResolveGitAdapter:
    def test_import_error_raises_helpful_message(self):
        """Cover lines 71-72: GitAdapter import fails."""
        with patch.dict(sys.modules, {'reveal.adapters.git.adapter': None}):
            with pytest.raises(ImportError, match='GitAdapter not available'):
                resolve_git_adapter('test.py@HEAD')

    def test_colon_format_raises_valueerror(self):
        """Cover lines 81-82: resource has ':' but no '@'."""
        with pytest.raises(ValueError, match='Git URI format error'):
            resolve_git_adapter('HEAD~1:file.py')

    def test_no_at_no_slash_raises_valueerror(self):
        """Cover lines 89-93: resource has no @ and no /."""
        with pytest.raises(ValueError, match='Git URI must be in format'):
            resolve_git_adapter('main')

    def test_git_adapter_file_result_analyzes_content(self):
        """Cover lines 102-124: GitAdapter returns file type result."""
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
        """Cover line 112: no analyzer found for file type."""
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
        """Cover line 127: non-file result returned directly."""
        mock_adapter = MagicMock()
        mock_adapter.get_structure.return_value = {'type': 'repository', 'refs': []}
        mock_adapter_cls = MagicMock(return_value=mock_adapter)
        mock_git_module = MagicMock()
        mock_git_module.GitAdapter = mock_adapter_cls

        with patch.dict(sys.modules, {'reveal.adapters.git.adapter': mock_git_module}):
            result = resolve_git_adapter('path/to/dir@HEAD')
        assert result == {'type': 'repository', 'refs': []}

    def test_git_adapter_exception_raises_valueerror(self):
        """Cover lines 129-130: any exception wrapped in ValueError."""
        mock_git_module = MagicMock()
        mock_git_module.GitAdapter = MagicMock(side_effect=RuntimeError('git boom'))

        with patch.dict(sys.modules, {'reveal.adapters.git.adapter': mock_git_module}):
            with pytest.raises(ValueError, match='Failed to resolve git'):
                resolve_git_adapter('test.py@HEAD')


# ─── resolve_git_ref ─────────────────────────────────────────────────────────

class TestResolveGitRef:
    def test_not_in_git_repo_raises_valueerror(self):
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(128, 'git')):
            with pytest.raises(ValueError, match='Not in a git repository'):
                resolve_git_ref('HEAD', 'file.py')

    def test_ls_tree_error_raises_valueerror(self):
        """Cover line 46: ls-tree CalledProcessError."""
        err = subprocess.CalledProcessError(128, 'git', stderr='fatal: bad revision')
        err.stderr = 'fatal: bad revision'

        call_count = [0]
        def _mock_run(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return MagicMock(returncode=0)  # rev-parse succeeds
            raise err  # ls-tree fails

        with patch('subprocess.run', side_effect=_mock_run):
            with pytest.raises(ValueError, match='Git error'):
                resolve_git_ref('HEAD', 'file.py')

    def test_path_not_found_raises_valueerror(self):
        call_count = [0]
        def _mock_run(cmd, **kwargs):
            call_count[0] += 1
            m = MagicMock()
            if call_count[0] == 1:
                return m  # rev-parse succeeds
            m.stdout = ''  # empty → path not found
            return m

        with patch('subprocess.run', side_effect=_mock_run):
            with pytest.raises(ValueError, match='Path not found'):
                resolve_git_ref('HEAD', 'missing.py')


# ─── resolve_git_file ─────────────────────────────────────────────────────────

class TestResolveGitFile:
    def test_git_show_error_raises_valueerror(self):
        """Cover lines 152-153: CalledProcessError from git show."""
        err = subprocess.CalledProcessError(128, 'git show', stderr='bad ref')
        err.stderr = 'bad ref'
        with patch('subprocess.run', side_effect=err):
            with pytest.raises(ValueError, match='Failed to get file from git'):
                resolve_git_file('badref', 'file.py')

    def test_no_analyzer_raises_valueerror(self):
        """Cover line 163: no analyzer for path."""
        mock_result = MagicMock()
        mock_result.stdout = 'def foo(): pass'

        with patch('subprocess.run', return_value=mock_result):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=None):
                with pytest.raises(ValueError, match='No analyzer found'):
                    resolve_git_file('HEAD', 'file.py')

    def test_success_returns_structure(self):
        mock_result = MagicMock()
        mock_result.stdout = 'def foo(): pass'
        mock_analyzer = MagicMock()
        mock_analyzer.get_structure.return_value = {'functions': []}
        mock_cls = MagicMock(return_value=mock_analyzer)

        with patch('subprocess.run', return_value=mock_result):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=mock_cls):
                result = resolve_git_file('HEAD', 'test.py')
        assert 'functions' in result


# ─── _fetch_and_analyze_git_file ─────────────────────────────────────────────

class TestFetchAndAnalyzeGitFile:
    def test_no_analyzer_returns_empty_dict(self):
        """Cover line 188: no analyzer → return {}."""
        mock_result = MagicMock()
        mock_result.stdout = 'const x = 1;'

        with patch('subprocess.run', return_value=mock_result):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=None):
                result = _fetch_and_analyze_git_file('HEAD', 'file.js')
        assert result == {}

    def test_success_returns_structure(self):
        mock_result = MagicMock()
        mock_result.stdout = 'def foo(): pass'
        mock_analyzer = MagicMock()
        mock_analyzer.get_structure.return_value = {'structure': {'functions': [{'name': 'foo'}]}}
        mock_cls = MagicMock(return_value=mock_analyzer)

        with patch('subprocess.run', return_value=mock_result):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=mock_cls):
                result = _fetch_and_analyze_git_file('HEAD', 'test.py')
        assert 'functions' in result


# ─── _ls_tree_files ───────────────────────────────────────────────────────────

class TestLsTreeFiles:
    def test_subprocess_error_raises_valueerror(self):
        """Cover lines 203-205: CalledProcessError → ValueError."""
        err = subprocess.CalledProcessError(128, 'git ls-tree', stderr='fatal error')
        err.stderr = 'fatal error'
        with patch('subprocess.run', side_effect=err):
            with pytest.raises(ValueError, match='Git error'):
                _ls_tree_files('HEAD', 'somedir')

    def test_empty_output_raises_valueerror(self):
        """Cover line 203: empty stdout → ValueError."""
        mock_result = MagicMock()
        mock_result.stdout = ''
        with patch('subprocess.run', return_value=mock_result):
            with pytest.raises(ValueError, match='Directory not found'):
                _ls_tree_files('HEAD', 'somedir')

    def test_returns_blob_file_paths(self):
        mock_result = MagicMock()
        mock_result.stdout = (
            '100644 blob abc123\tsomedir/file1.py\n'
            '100644 blob def456\tsomedir/file2.py\n'
            '040000 tree ghi789\tsomedir/subdir\n'
        )
        with patch('subprocess.run', return_value=mock_result):
            result = _ls_tree_files('HEAD', 'somedir')
        assert 'somedir/file1.py' in result
        assert 'somedir/file2.py' in result
        assert 'somedir/subdir' not in result


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
    def test_skips_files_without_analyzer(self):
        """Cover line 245: no analyzer → continue."""
        with patch('reveal.adapters.diff.git._ls_tree_files', return_value=['dir/main.js']):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=None):
                result = resolve_git_directory('HEAD', 'dir')
        assert result['file_count'] == 0
        assert result['functions'] == []

    def test_skips_files_with_fetch_exception(self):
        """Cover lines 248-249: _fetch_and_analyze_git_file raises → continue."""
        mock_cls = MagicMock()

        with patch('reveal.adapters.diff.git._ls_tree_files', return_value=['dir/file.py']):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=mock_cls):
                with patch('reveal.adapters.diff.git._fetch_and_analyze_git_file',
                           side_effect=RuntimeError('git exploded')):
                    result = resolve_git_directory('HEAD', 'dir')
        assert result['file_count'] == 0

    def test_skips_empty_struct(self):
        """Cover line 251: struct is empty dict → continue."""
        mock_cls = MagicMock()

        with patch('reveal.adapters.diff.git._ls_tree_files', return_value=['dir/file.py']):
            with patch('reveal.adapters.diff.git.get_analyzer', return_value=mock_cls):
                with patch('reveal.adapters.diff.git._fetch_and_analyze_git_file', return_value={}):
                    result = resolve_git_directory('HEAD', 'dir')
        assert result['file_count'] == 0

    def test_aggregates_functions_and_classes(self):
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
