"""Tests for reveal/cli/file_checker.py module."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from reveal.cli.file_checker import (
    load_gitignore_patterns,
    should_skip_file,
    collect_files_to_check,
    check_and_report_file,
)


class TestLoadGitignorePatterns:
    """Tests for load_gitignore_patterns function."""

    def test_no_gitignore(self, tmp_path):
        """Test when .gitignore doesn't exist."""
        patterns = load_gitignore_patterns(tmp_path)
        assert patterns == []

    def test_with_gitignore(self, tmp_path):
        """Test loading patterns from .gitignore."""
        gitignore = tmp_path / '.gitignore'
        gitignore.write_text('*.pyc\n__pycache__/\n# comment\n\n.env\n')

        patterns = load_gitignore_patterns(tmp_path)

        assert '*.pyc' in patterns
        assert '__pycache__/' in patterns
        assert '.env' in patterns
        assert '# comment' not in patterns  # Comments should be filtered
        assert '' not in patterns  # Empty lines should be filtered

    def test_empty_gitignore(self, tmp_path):
        """Test with empty .gitignore file."""
        gitignore = tmp_path / '.gitignore'
        gitignore.write_text('\n\n')

        patterns = load_gitignore_patterns(tmp_path)
        assert patterns == []

    def test_whitespace_only_gitignore(self, tmp_path):
        """Test with whitespace-only lines."""
        gitignore = tmp_path / '.gitignore'
        gitignore.write_text('   \n\t\n  \t  \n')

        patterns = load_gitignore_patterns(tmp_path)
        assert patterns == []

    def test_gitignore_with_inline_comments(self, tmp_path):
        """Test gitignore with various comment styles."""
        gitignore = tmp_path / '.gitignore'
        gitignore.write_text('*.pyc\n# Full line comment\n.env  # Not a comment\n')

        patterns = load_gitignore_patterns(tmp_path)
        assert '*.pyc' in patterns
        assert '.env  # Not a comment' in patterns  # Simple parser doesn't strip inline
        assert '# Full line comment' not in patterns

    def test_gitignore_read_error(self, tmp_path):
        """Test handling of read errors."""
        gitignore = tmp_path / '.gitignore'
        gitignore.write_text('*.pyc')
        gitignore.chmod(0o000)  # Remove read permissions

        try:
            patterns = load_gitignore_patterns(tmp_path)
            assert patterns == []  # Should return empty list on error
        finally:
            gitignore.chmod(0o644)  # Restore permissions


class TestShouldSkipFile:
    """Tests for should_skip_file function."""

    def test_no_patterns(self):
        """Test with no gitignore patterns."""
        result = should_skip_file(Path('test.py'), [])
        assert result is False

    def test_matching_pattern(self):
        """Test file matching gitignore pattern."""
        result = should_skip_file(Path('test.pyc'), ['*.pyc'])
        assert result is True

    def test_non_matching_pattern(self):
        """Test file not matching patterns."""
        result = should_skip_file(Path('test.py'), ['*.pyc', '*.txt'])
        assert result is False

    def test_directory_pattern(self):
        """Test directory pattern matching."""
        result = should_skip_file(Path('__pycache__/test.pyc'), ['*__pycache__*'])
        assert result is True

    def test_multiple_patterns(self):
        """Test multiple patterns."""
        patterns = ['*.pyc', '*.pyo', '__pycache__/', '.env']

        assert should_skip_file(Path('test.pyc'), patterns) is True
        assert should_skip_file(Path('test.pyo'), patterns) is True
        assert should_skip_file(Path('test.py'), patterns) is False

    def test_nested_path_pattern(self):
        """Test pattern matching on nested paths."""
        patterns = ['build/*', 'dist/*']

        assert should_skip_file(Path('build/output.txt'), patterns) is True
        assert should_skip_file(Path('dist/wheel.whl'), patterns) is True
        assert should_skip_file(Path('src/main.py'), patterns) is False

    def test_exact_filename_match(self):
        """Test exact filename matching."""
        patterns = ['.env', 'secrets.yaml']

        assert should_skip_file(Path('.env'), patterns) is True
        assert should_skip_file(Path('secrets.yaml'), patterns) is True
        assert should_skip_file(Path('config.yaml'), patterns) is False


class TestCollectFilesToCheck:
    """Tests for collect_files_to_check function."""

    def test_empty_directory(self, tmp_path):
        """Test collecting files from empty directory."""
        files = collect_files_to_check(tmp_path, [])
        assert files == []

    def test_python_files(self, tmp_path):
        """Test collecting Python files."""
        (tmp_path / 'test1.py').write_text('# Test file 1')
        (tmp_path / 'test2.py').write_text('# Test file 2')
        (tmp_path / 'readme.txt').write_text('Not Python')

        with patch('reveal.base.get_analyzer') as mock_get_analyzer:
            # Mock get_analyzer to return True for .py files, False for others
            def analyzer_mock(path, allow_fallback=True):
                return Mock() if path.endswith('.py') else None
            mock_get_analyzer.side_effect = analyzer_mock

            files = collect_files_to_check(tmp_path, [])

        assert len(files) == 2
        assert all(f.suffix == '.py' for f in files)

    def test_excluded_directories(self, tmp_path):
        """Test that excluded directories are skipped."""
        # Create excluded directories
        for dirname in ['.git', '__pycache__', 'node_modules', '.venv', 'venv']:
            subdir = tmp_path / dirname
            subdir.mkdir()
            (subdir / 'file.py').write_text('# Should be skipped')

        # Create included file
        (tmp_path / 'included.py').write_text('# Should be included')

        with patch('reveal.base.get_analyzer') as mock_get_analyzer:
            mock_get_analyzer.return_value = Mock()  # Return analyzer for all files
            files = collect_files_to_check(tmp_path, [])

        # Should only find the file in the root directory
        assert len(files) == 1
        assert files[0].name == 'included.py'

    def test_gitignore_patterns(self, tmp_path):
        """Test that gitignore patterns are respected."""
        (tmp_path / 'keep.py').write_text('# Keep this')
        (tmp_path / 'ignore.pyc').write_text('# Ignore this')
        (tmp_path / 'also_ignore.py').write_text('# Also ignore')

        patterns = ['*.pyc', 'also_ignore.py']

        with patch('reveal.base.get_analyzer') as mock_get_analyzer:
            mock_get_analyzer.return_value = Mock()
            files = collect_files_to_check(tmp_path, patterns)

        assert len(files) == 1
        assert files[0].name == 'keep.py'

    def test_nested_structure(self, tmp_path):
        """Test collecting files from nested directory structure."""
        # Create nested structure
        (tmp_path / 'src').mkdir()
        (tmp_path / 'src' / 'lib').mkdir()
        (tmp_path / 'src' / 'app.py').write_text('# App')
        (tmp_path / 'src' / 'lib' / 'utils.py').write_text('# Utils')

        with patch('reveal.base.get_analyzer') as mock_get_analyzer:
            mock_get_analyzer.return_value = Mock()
            files = collect_files_to_check(tmp_path, [])

        assert len(files) == 2
        file_names = {f.name for f in files}
        assert file_names == {'app.py', 'utils.py'}


class TestCheckAndReportFile:
    """Tests for check_and_report_file function."""

    def test_no_issues(self, tmp_path, capsys):
        """Test checking file with no issues."""
        test_file = tmp_path / 'clean.py'
        test_file.write_text('# Clean code')

        with patch('reveal.base.get_analyzer') as mock_get_analyzer, \
             patch('reveal.rules.RuleRegistry.check_file') as mock_check_file:

            # Mock analyzer
            mock_analyzer = Mock()
            mock_analyzer.get_structure.return_value = {}
            mock_analyzer.content = '# Clean code'
            mock_get_analyzer.return_value = lambda path: mock_analyzer

            # No detections
            mock_check_file.return_value = []

            issue_count = check_and_report_file(test_file, tmp_path, None, None)

        assert issue_count == 0
        captured = capsys.readouterr()
        assert captured.out == ''  # No output when no issues

    def test_with_issues(self, tmp_path, capsys):
        """Test checking file with issues."""
        test_file = tmp_path / 'buggy.py'
        test_file.write_text('# Buggy code')

        # Mock detection
        mock_detection = Mock()
        mock_detection.line = 10
        mock_detection.column = 5
        mock_detection.rule_code = 'B001'
        mock_detection.message = 'Test issue'
        mock_detection.severity.value = 'HIGH'
        mock_detection.suggestion = 'Fix it'
        mock_detection.context = 'More info'

        with patch('reveal.base.get_analyzer') as mock_get_analyzer, \
             patch('reveal.rules.RuleRegistry.check_file') as mock_check_file:

            # Mock analyzer
            mock_analyzer = Mock()
            mock_analyzer.get_structure.return_value = {}
            mock_analyzer.content = '# Buggy code'
            mock_get_analyzer.return_value = lambda path: mock_analyzer

            # Return one detection
            mock_check_file.return_value = [mock_detection]

            issue_count = check_and_report_file(test_file, tmp_path, None, None)

        assert issue_count == 1
        captured = capsys.readouterr()
        assert 'buggy.py' in captured.out
        assert 'B001' in captured.out
        assert 'Test issue' in captured.out

    def test_file_without_analyzer(self, tmp_path):
        """Test file that has no analyzer."""
        test_file = tmp_path / 'unknown.xyz'
        test_file.write_text('Unknown file type')

        with patch('reveal.base.get_analyzer') as mock_get_analyzer:
            # No analyzer available
            mock_get_analyzer.return_value = None

            issue_count = check_and_report_file(test_file, tmp_path, None, None)

        assert issue_count == 0

    def test_file_processing_error(self, tmp_path):
        """Test handling of file processing errors."""
        test_file = tmp_path / 'error.py'
        test_file.write_text('# Will error')

        with patch('reveal.base.get_analyzer') as mock_get_analyzer:
            # Analyzer raises exception
            mock_analyzer = Mock()
            mock_analyzer.get_structure.side_effect = Exception("Parse error")
            mock_get_analyzer.return_value = lambda path: mock_analyzer

            # Should handle error gracefully
            issue_count = check_and_report_file(test_file, tmp_path, None, None)

        assert issue_count == 0  # Returns 0 on error

    def test_select_and_ignore_filters(self, tmp_path):
        """Test that select and ignore filters are passed through."""
        test_file = tmp_path / 'test.py'
        test_file.write_text('# Test')

        with patch('reveal.base.get_analyzer') as mock_get_analyzer, \
             patch('reveal.rules.RuleRegistry.check_file') as mock_check_file:

            mock_analyzer = Mock()
            mock_analyzer.get_structure.return_value = {}
            mock_analyzer.content = '# Test'
            mock_get_analyzer.return_value = lambda path: mock_analyzer
            mock_check_file.return_value = []

            check_and_report_file(test_file, tmp_path, ['B001', 'B002'], ['V001'])

            # Verify filters were passed to RuleRegistry
            call_args = mock_check_file.call_args
            assert call_args[1]['select'] == ['B001', 'B002']
            assert call_args[1]['ignore'] == ['V001']
