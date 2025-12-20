"""Tests for reveal/cli/routing.py module."""

import pytest
from pathlib import Path
from argparse import Namespace
from unittest.mock import Mock, patch, MagicMock

from reveal.cli.routing import (
    _format_check_detections,
    _handle_reveal_check,
    _handle_reveal,
    _load_gitignore_patterns,
    _should_skip_file,
    handle_file,
)


class TestFormatCheckDetections:
    """Tests for _format_check_detections function."""

    def test_json_format_with_detections(self, capsys):
        """Test JSON output format with detections."""
        detections = [
            Mock(to_dict=lambda: {'rule': 'V001', 'message': 'Test issue'})
        ]
        _format_check_detections('reveal://test', detections, 'json')

        captured = capsys.readouterr()
        assert '"file": "reveal://test"' in captured.out
        assert '"total": 1' in captured.out
        assert 'V001' in captured.out

    def test_json_format_no_detections(self, capsys):
        """Test JSON output format with no detections."""
        _format_check_detections('reveal://test', [], 'json')

        captured = capsys.readouterr()
        assert '"file": "reveal://test"' in captured.out
        assert '"total": 0' in captured.out

    def test_grep_format(self, capsys):
        """Test grep output format."""
        detection = Mock(
            file_path='test.py',
            line=10,
            column=5,
            rule_code='V001',
            message='Test issue'
        )
        _format_check_detections('reveal://test', [detection], 'grep')

        captured = capsys.readouterr()
        assert 'test.py:10:5:V001:Test issue' in captured.out

    def test_text_format_no_detections(self, capsys):
        """Test text output with no detections."""
        _format_check_detections('reveal://test', [], 'text')

        captured = capsys.readouterr()
        assert '✅ No issues found' in captured.out

    def test_text_format_with_detections(self, capsys):
        """Test text output with detections."""
        detection = Mock(
            line=10,
            column=5,
            __str__=lambda self: 'V001: Test issue at line 10'
        )
        _format_check_detections('reveal://test', [detection], 'text')

        captured = capsys.readouterr()
        assert 'Found 1 issues' in captured.out


class TestHandleRevealCheck:
    """Tests for _handle_reveal_check function."""

    @patch('reveal.cli.routing._format_check_detections')
    def test_with_resource(self, mock_format):
        """Test check handling with resource path."""
        with patch('reveal.rules.RuleRegistry.check_file') as mock_check_file:
            args = Namespace(select=None, ignore=None, format='text')
            mock_check_file.return_value = []

            _handle_reveal_check('test/path', args)

            mock_check_file.assert_called_once()
            call_args = mock_check_file.call_args
            assert call_args[0][0] == 'reveal://test/path'
            mock_format.assert_called_once()

    @patch('reveal.cli.routing._format_check_detections')
    def test_without_resource(self, mock_format):
        """Test check handling without resource path."""
        with patch('reveal.rules.RuleRegistry.check_file') as mock_check_file:
            args = Namespace(select=None, ignore=None, format='text')
            mock_check_file.return_value = []

            _handle_reveal_check(None, args)

            call_args = mock_check_file.call_args
            assert call_args[0][0] == 'reveal://'

    @patch('reveal.cli.routing._format_check_detections')
    def test_with_select_and_ignore(self, mock_format):
        """Test check handling with select and ignore filters."""
        with patch('reveal.rules.RuleRegistry.check_file') as mock_check_file:
            args = Namespace(select='V001,V002', ignore='V003', format='text')
            mock_check_file.return_value = []

            _handle_reveal_check('test', args)

            call_args = mock_check_file.call_args
            assert call_args[1]['select'] == ['V001', 'V002']
            assert call_args[1]['ignore'] == ['V003']


class TestHandleReveal:
    """Tests for _handle_reveal function."""

    @patch('reveal.cli.routing._handle_reveal_check')
    def test_check_mode(self, mock_check):
        """Test routing to check mode."""
        adapter_class = Mock()
        args = Namespace(check=True)

        _handle_reveal(adapter_class, 'test', None, args)

        mock_check.assert_called_once_with('test', args)
        adapter_class.assert_not_called()

    def test_normal_mode(self):
        """Test normal reveal structure mode."""
        with patch('reveal.rendering.render_reveal_structure') as mock_render:
            adapter_class = Mock()
            adapter_instance = Mock()
            adapter_instance.get_structure.return_value = {'test': 'data'}
            adapter_class.return_value = adapter_instance

            args = Namespace(check=False, format='text')

            _handle_reveal(adapter_class, 'test', None, args)

            adapter_class.assert_called_once_with('test')
            adapter_instance.get_structure.assert_called_once()
            mock_render.assert_called_once_with({'test': 'data'}, 'text')

    def test_normal_mode_no_resource(self):
        """Test normal mode without resource."""
        with patch('reveal.rendering.render_reveal_structure') as mock_render:
            adapter_class = Mock()
            adapter_instance = Mock()
            adapter_instance.get_structure.return_value = {}
            adapter_class.return_value = adapter_instance

            args = Namespace(check=False, format='json')

            _handle_reveal(adapter_class, None, None, args)

            adapter_class.assert_called_once_with(None)


class TestLoadGitignorePatterns:
    """Tests for _load_gitignore_patterns function."""

    def test_no_gitignore(self, tmp_path):
        """Test when .gitignore doesn't exist."""
        patterns = _load_gitignore_patterns(tmp_path)
        assert patterns == []

    def test_with_gitignore(self, tmp_path):
        """Test loading patterns from .gitignore."""
        gitignore = tmp_path / '.gitignore'
        gitignore.write_text('*.pyc\n__pycache__/\n# comment\n\n.env')

        patterns = _load_gitignore_patterns(tmp_path)

        assert '*.pyc' in patterns
        assert '__pycache__/' in patterns
        assert '.env' in patterns
        assert '# comment' not in patterns  # Comments should be filtered

    def test_empty_gitignore(self, tmp_path):
        """Test with empty .gitignore file."""
        gitignore = tmp_path / '.gitignore'
        gitignore.write_text('\n\n')

        patterns = _load_gitignore_patterns(tmp_path)
        assert patterns == []


class TestShouldSkipFile:
    """Tests for _should_skip_file function."""

    def test_no_patterns(self):
        """Test with no gitignore patterns."""
        result = _should_skip_file(Path('test.py'), [])
        assert result is False

    def test_matching_pattern(self):
        """Test file matching gitignore pattern."""
        result = _should_skip_file(Path('test.pyc'), ['*.pyc'])
        assert result is True

    def test_non_matching_pattern(self):
        """Test file not matching patterns."""
        result = _should_skip_file(Path('test.py'), ['*.pyc', '*.txt'])
        assert result is False

    def test_directory_pattern(self):
        """Test directory pattern matching."""
        # fnmatch uses shell-style wildcards, so directory patterns work differently
        result = _should_skip_file(Path('__pycache__/test.pyc'), ['*__pycache__*'])
        assert result is True

    def test_multiple_patterns(self):
        """Test multiple patterns."""
        patterns = ['*.pyc', '*.pyo', '__pycache__/', '.env']

        assert _should_skip_file(Path('test.pyc'), patterns) is True
        assert _should_skip_file(Path('test.pyo'), patterns) is True
        assert _should_skip_file(Path('test.py'), patterns) is False
