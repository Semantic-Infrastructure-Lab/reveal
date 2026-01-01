"""Comprehensive tests for reveal.cli.routing module.

Tests cover:
- URI scheme handlers (env, ast, help, python, json, reveal, stats, mysql)
- handle_uri and handle_adapter dispatching
- Gitignore pattern loading and filtering
- File collection for recursive checking
- Check detection formatting
"""

import sys
import pytest
from pathlib import Path
from argparse import Namespace
from unittest.mock import Mock, patch, MagicMock, call
from io import StringIO

from reveal.cli.routing import (
    _handle_env,
    _handle_ast,
    _handle_help,
    _handle_python,
    _handle_json,
    _handle_reveal,
    _handle_stats,
    _handle_mysql,
    handle_uri,
    handle_adapter,
    _load_gitignore_patterns,
    _should_skip_file,
    _format_check_detections,
    SCHEME_HANDLERS,
)


# ==============================================================================
# Test Scheme Handlers
# ==============================================================================


class TestHandleEnv:
    """Tests for _handle_env (env:// URIs)."""

    def test_handle_env_list_all_variables(self, capsys):
        """Test listing all environment variables."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {
            'variables': {'PATH': '/usr/bin', 'HOME': '/home/user'}
        }

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_env_structure') as mock_render:
            _handle_env(mock_adapter_class, '', None, args)

        mock_adapter.get_structure.assert_called_once_with(show_secrets=False)
        mock_render.assert_called_once()

    def test_handle_env_get_specific_variable_from_resource(self, capsys):
        """Test getting specific environment variable from resource."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = {
            'name': 'PATH',
            'value': '/usr/bin'
        }

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_env_variable') as mock_render:
            _handle_env(mock_adapter_class, 'PATH', None, args)

        mock_adapter.get_element.assert_called_once_with('PATH', show_secrets=False)
        mock_render.assert_called_once()

    def test_handle_env_get_specific_variable_from_element(self, capsys):
        """Test getting specific environment variable from element."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = {
            'name': 'HOME',
            'value': '/home/user'
        }

        args = Namespace(check=False, format='json')

        with patch('reveal.rendering.render_env_variable') as mock_render:
            _handle_env(mock_adapter_class, '', 'HOME', args)

        mock_adapter.get_element.assert_called_once_with('HOME', show_secrets=False)
        mock_render.assert_called_once()

    def test_handle_env_variable_not_found(self, capsys):
        """Test error when environment variable not found."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = None

        args = Namespace(check=False, format='text')

        with pytest.raises(SystemExit) as exc_info:
            _handle_env(mock_adapter_class, 'NONEXISTENT', None, args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Environment variable 'NONEXISTENT' not found" in captured.err

    def test_handle_env_check_flag_warning(self, capsys):
        """Test warning message when --check flag used with env://."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {'variables': {}}

        args = Namespace(check=True, format='text')

        with patch('reveal.rendering.render_env_structure'):
            _handle_env(mock_adapter_class, '', None, args)

        captured = capsys.readouterr()
        assert "--check is not supported for env://" in captured.err


class TestHandleAst:
    """Tests for _handle_ast (ast:// URIs)."""

    def test_handle_ast_with_path_and_query(self):
        """Test AST with both path and query parameters."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {'type': 'ast'}

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_ast_structure') as mock_render:
            _handle_ast(mock_adapter_class, 'file.py?depth=2', None, args)

        mock_adapter_class.assert_called_once_with('file.py', 'depth=2')
        mock_render.assert_called_once()

    def test_handle_ast_with_path_only(self):
        """Test AST with path but no query."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {'type': 'ast'}

        args = Namespace(check=False, format='json')

        with patch('reveal.rendering.render_ast_structure') as mock_render:
            _handle_ast(mock_adapter_class, 'file.py', None, args)

        mock_adapter_class.assert_called_once_with('file.py', None)
        mock_render.assert_called_once()

    def test_handle_ast_defaults_to_current_directory(self):
        """Test AST defaults to current directory when no path given."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {'type': 'ast'}

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_ast_structure'):
            _handle_ast(mock_adapter_class, '', None, args)

        mock_adapter_class.assert_called_once_with('.', None)

    def test_handle_ast_check_flag_warning(self, capsys):
        """Test warning message when --check flag used with ast://."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {'type': 'ast'}

        args = Namespace(check=True, format='text')

        with patch('reveal.rendering.render_ast_structure'):
            _handle_ast(mock_adapter_class, 'file.py', None, args)

        captured = capsys.readouterr()
        assert "--check is not supported for ast://" in captured.err


class TestHandleHelp:
    """Tests for _handle_help (help:// URIs)."""

    def test_handle_help_list_all_topics(self):
        """Test listing all help topics."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {
            'available_topics': ['intro', 'adapters', 'rules']
        }

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_help') as mock_render:
            _handle_help(mock_adapter_class, '', None, args)

        mock_render.assert_called_once()
        assert mock_render.call_args[1]['list_mode'] is True

    def test_handle_help_get_specific_topic_from_resource(self):
        """Test getting specific help topic from resource."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = {
            'topic': 'adapters',
            'content': 'Help about adapters'
        }

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_help') as mock_render:
            _handle_help(mock_adapter_class, 'adapters', None, args)

        mock_adapter.get_element.assert_called_once_with('adapters')
        mock_render.assert_called_once()

    def test_handle_help_get_specific_topic_from_element(self):
        """Test getting specific help topic from element."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = {
            'topic': 'rules',
            'content': 'Help about rules'
        }

        args = Namespace(check=False, format='json')

        with patch('reveal.rendering.render_help') as mock_render:
            _handle_help(mock_adapter_class, '', 'rules', args)

        mock_adapter.get_element.assert_called_once_with('rules')
        mock_render.assert_called_once()

    def test_handle_help_topic_not_found(self, capsys):
        """Test error when help topic not found."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = None
        mock_adapter.get_structure.return_value = {
            'available_topics': ['intro', 'adapters', 'rules']
        }

        args = Namespace(check=False, format='text')

        with pytest.raises(SystemExit) as exc_info:
            _handle_help(mock_adapter_class, 'nonexistent', None, args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Help topic 'nonexistent' not found" in captured.err
        assert "Available topics:" in captured.err


class TestHandlePython:
    """Tests for _handle_python (python:// URIs)."""

    def test_handle_python_list_all_info(self):
        """Test listing all Python environment info."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {
            'version': '3.10.12',
            'packages': []
        }

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_python_structure') as mock_render:
            _handle_python(mock_adapter_class, '', None, args)

        mock_adapter.get_structure.assert_called_once()
        mock_render.assert_called_once()

    def test_handle_python_get_specific_element_from_resource(self):
        """Test getting specific Python element from resource."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = {'element': 'version'}

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_python_element') as mock_render:
            _handle_python(mock_adapter_class, 'version', None, args)

        mock_adapter.get_element.assert_called_once_with('version')
        mock_render.assert_called_once()

    def test_handle_python_element_not_found(self, capsys):
        """Test error when Python element not found."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = None

        args = Namespace(check=False, format='text')

        with pytest.raises(SystemExit) as exc_info:
            _handle_python(mock_adapter_class, 'nonexistent', None, args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Python element 'nonexistent' not found" in captured.err
        assert "Available elements:" in captured.err


class TestHandleJson:
    """Tests for _handle_json (json:// URIs)."""

    def test_handle_json_with_path_and_query(self):
        """Test JSON with both path and query."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {'key': 'value'}

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_json_result') as mock_render:
            _handle_json(mock_adapter_class, 'data.json?path=$.users', None, args)

        mock_adapter_class.assert_called_once_with('data.json', 'path=$.users')
        mock_render.assert_called_once()

    def test_handle_json_with_path_only(self):
        """Test JSON with path but no query."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {'key': 'value'}

        args = Namespace(check=False, format='json')

        with patch('reveal.rendering.render_json_result') as mock_render:
            _handle_json(mock_adapter_class, 'data.json', None, args)

        mock_adapter_class.assert_called_once_with('data.json', None)
        mock_render.assert_called_once()

    def test_handle_json_adapter_value_error(self, capsys):
        """Test error handling when adapter raises ValueError."""
        mock_adapter_class = Mock()
        mock_adapter_class.side_effect = ValueError("Invalid JSON query")

        args = Namespace(check=False, format='text')

        with pytest.raises(SystemExit) as exc_info:
            _handle_json(mock_adapter_class, 'data.json', None, args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid JSON query" in captured.err


class TestHandleReveal:
    """Tests for _handle_reveal (reveal:// URIs)."""

    def test_handle_reveal_get_structure(self):
        """Test getting reveal structure."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {
            'files': ['reveal/__init__.py']
        }

        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_reveal_structure') as mock_render:
            _handle_reveal(mock_adapter_class, '', None, args)

        mock_adapter.get_structure.assert_called_once()
        mock_render.assert_called_once()

    def test_handle_reveal_with_check_flag(self):
        """Test reveal with --check flag (runs validation rules)."""
        mock_adapter_class = Mock()
        args = Namespace(
            check=True,
            format='text',
            select=None,
            ignore=None
        )

        with patch('reveal.cli.routing._handle_reveal_check') as mock_check:
            _handle_reveal(mock_adapter_class, 'adapters', None, args)

        mock_check.assert_called_once_with('adapters', args)

    def test_handle_reveal_element_extraction(self):
        """Test reveal element extraction."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = {'element': 'data'}

        args = Namespace(check=False, format='text')

        _handle_reveal(mock_adapter_class, 'file.py', 'function_name', args)

        mock_adapter.get_element.assert_called_once_with('file.py', 'function_name', args)

    def test_handle_reveal_element_not_found(self, capsys):
        """Test error when reveal element not found."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = None

        args = Namespace(check=False, format='text')

        with pytest.raises(SystemExit) as exc_info:
            _handle_reveal(mock_adapter_class, 'file.py', 'nonexistent', args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Could not extract 'nonexistent'" in captured.err


class TestHandleStats:
    """Tests for _handle_stats (stats:// URIs)."""

    def test_handle_stats_requires_path(self, capsys):
        """Test error when stats:// called without path."""
        mock_adapter_class = Mock()
        args = Namespace(check=False, format='text', hotspots=False)

        with pytest.raises(SystemExit) as exc_info:
            _handle_stats(mock_adapter_class, '', None, args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "stats:// requires a path" in captured.err

    def test_handle_stats_directory_analysis(self):
        """Test stats analysis of directory."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {
            'summary': {
                'total_files': 10,
                'total_lines': 1000,
                'total_code_lines': 800,
                'total_functions': 50,
                'total_classes': 5,
                'avg_complexity': 3.5,
                'avg_quality_score': 85.2
            }
        }

        args = Namespace(
            check=False,
            format='text',
            hotspots=False,
            min_lines=None,
            max_lines=None,
            min_complexity=None,
            max_complexity=None,
            min_functions=None
        )

        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            _handle_stats(mock_adapter_class, './src', None, args)

        mock_adapter.get_structure.assert_called_once()

    def test_handle_stats_with_hotspots_flag(self):
        """Test stats with --hotspots flag."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {
            'summary': {
                'total_files': 10,
                'total_lines': 1000,
                'total_code_lines': 800,
                'total_functions': 50,
                'total_classes': 5,
                'avg_complexity': 3.5,
                'avg_quality_score': 85.2
            },
            'hotspots': []
        }

        args = Namespace(
            check=False,
            format='text',
            hotspots=True,
            min_lines=None,
            max_lines=None,
            min_complexity=None,
            max_complexity=None,
            min_functions=None
        )

        with patch('sys.stdout', new_callable=StringIO):
            _handle_stats(mock_adapter_class, './src', None, args)

        # Should request hotspots from adapter
        call_kwargs = mock_adapter.get_structure.call_args[1]
        assert call_kwargs.get('hotspots') is True

    def test_handle_stats_specific_file_element(self):
        """Test stats for specific file (element)."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = {
            'file': 'file.py',
            'lines': 100
        }

        args = Namespace(check=False, format='json', hotspots=False)

        with patch('sys.stdout', new_callable=StringIO):
            _handle_stats(mock_adapter_class, './src', 'file.py', args)

        mock_adapter.get_element.assert_called_once_with('file.py')


class TestHandleMysql:
    """Tests for _handle_mysql (mysql:// URIs)."""

    def test_handle_mysql_connection(self):
        """Test MySQL connection handling."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter.element = None  # No element specified
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_structure.return_value = {
            'databases': ['db1', 'db2']
        }

        args = Namespace(check=False, format='text')

        with patch('reveal.cli.routing._render_mysql_result') as mock_render:
            _handle_mysql(mock_adapter_class, 'localhost/mydb', None, args)

        mock_adapter.get_structure.assert_called_once()
        mock_render.assert_called_once()


# ==============================================================================
# Test URI and Adapter Handling
# ==============================================================================


class TestHandleUri:
    """Tests for handle_uri function."""

    def test_handle_uri_valid_scheme(self):
        """Test handling valid URI scheme."""
        args = Namespace(check=False, format='text')

        with patch('reveal.adapters.base.get_adapter_class') as mock_get_adapter:
            with patch('reveal.cli.routing.handle_adapter') as mock_handle:
                mock_adapter_class = Mock()
                mock_get_adapter.return_value = mock_adapter_class

                handle_uri('env://PATH', None, args)

                mock_get_adapter.assert_called_once_with('env')
                mock_handle.assert_called_once_with(
                    mock_adapter_class, 'env', 'PATH', None, args
                )

    def test_handle_uri_invalid_format(self, capsys):
        """Test error on invalid URI format."""
        args = Namespace(check=False, format='text')

        with pytest.raises(SystemExit) as exc_info:
            handle_uri('not-a-uri', None, args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid URI format" in captured.err

    def test_handle_uri_unsupported_scheme(self, capsys):
        """Test error on unsupported URI scheme."""
        args = Namespace(check=False, format='text')

        with patch('reveal.adapters.base.get_adapter_class') as mock_get:
            with patch('reveal.adapters.base.list_supported_schemes') as mock_list:
                mock_get.return_value = None
                mock_list.return_value = ['env', 'ast', 'help']

                with pytest.raises(SystemExit) as exc_info:
                    handle_uri('unsupported://resource', None, args)

                assert exc_info.value.code == 1
                captured = capsys.readouterr()
                assert "Unsupported URI scheme: unsupported://" in captured.err
                assert "Supported schemes:" in captured.err


class TestHandleAdapter:
    """Tests for handle_adapter function."""

    def test_handle_adapter_dispatches_to_handler(self):
        """Test adapter dispatches to correct handler."""
        mock_adapter_class = Mock()
        mock_adapter = Mock()
        mock_adapter_class.return_value = mock_adapter
        mock_adapter.get_element.return_value = {
            'name': 'PATH',
            'value': '/usr/bin'
        }
        args = Namespace(check=False, format='text')

        with patch('reveal.rendering.render_env_variable') as mock_render:
            handle_adapter(mock_adapter_class, 'env', 'PATH', None, args)

            # Verify the adapter was called
            mock_adapter.get_element.assert_called_once_with('PATH', show_secrets=False)
            mock_render.assert_called_once()

    def test_handle_adapter_unknown_scheme_error(self, capsys):
        """Test error when scheme has no handler."""
        mock_adapter_class = Mock()
        args = Namespace(check=False, format='text')

        with pytest.raises(SystemExit) as exc_info:
            handle_adapter(mock_adapter_class, 'unknown', 'resource', None, args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No handler for scheme 'unknown'" in captured.err


# ==============================================================================
# Test Gitignore Functions
# ==============================================================================


class TestGitignoreFunctions:
    """Tests for gitignore pattern loading and filtering."""

    def test_load_gitignore_patterns(self, tmp_path):
        """Test loading gitignore patterns from file."""
        gitignore = tmp_path / '.gitignore'
        gitignore.write_text('*.pyc\n__pycache__/\n# comment\n\n.DS_Store\n')

        patterns = _load_gitignore_patterns(tmp_path)

        assert '*.pyc' in patterns
        assert '__pycache__/' in patterns
        assert '.DS_Store' in patterns
        assert '# comment' not in patterns  # Comments filtered
        assert '' not in patterns  # Empty lines filtered

    def test_load_gitignore_no_file(self, tmp_path):
        """Test loading when no .gitignore exists."""
        patterns = _load_gitignore_patterns(tmp_path)
        assert patterns == []

    def test_load_gitignore_read_error(self, tmp_path):
        """Test handling read errors gracefully."""
        # Create directory where file should be (causes read error)
        gitignore_dir = tmp_path / '.gitignore'
        gitignore_dir.mkdir()

        patterns = _load_gitignore_patterns(tmp_path)
        assert patterns == []

    def test_should_skip_file_matches_pattern(self):
        """Test file is skipped when matching pattern."""
        patterns = ['*.pyc', '__pycache__/*', 'build/']

        assert _should_skip_file(Path('test.pyc'), patterns) is True
        assert _should_skip_file(Path('__pycache__/module.cpython-310.pyc'), patterns) is True

    def test_should_skip_file_no_match(self):
        """Test file is not skipped when not matching any pattern."""
        patterns = ['*.pyc', '__pycache__/*']

        assert _should_skip_file(Path('test.py'), patterns) is False
        assert _should_skip_file(Path('src/main.py'), patterns) is False

    def test_should_skip_file_empty_patterns(self):
        """Test no files skipped with empty pattern list."""
        assert _should_skip_file(Path('any_file.py'), []) is False


# ==============================================================================
# Test Detection Formatting
# ==============================================================================


class TestFormatCheckDetections:
    """Tests for _format_check_detections function."""

    def test_format_detections_json(self, capsys):
        """Test JSON format output."""
        mock_detection = Mock()
        mock_detection.to_dict.return_value = {
            'rule': 'V001',
            'message': 'Test issue',
            'line': 10,
            'column': 5
        }
        detections = [mock_detection]

        _format_check_detections('test.py', detections, 'json')

        captured = capsys.readouterr()
        assert '"file": "test.py"' in captured.out
        assert '"total": 1' in captured.out

    def test_format_detections_grep(self, capsys):
        """Test grep format output."""
        mock_detection = Mock()
        mock_detection.file_path = 'test.py'
        mock_detection.line = 10
        mock_detection.column = 5
        mock_detection.rule_code = 'V001'
        mock_detection.message = 'Test issue'
        detections = [mock_detection]

        _format_check_detections('test.py', detections, 'grep')

        captured = capsys.readouterr()
        assert 'test.py:10:5:V001:Test issue' in captured.out

    def test_format_detections_text_with_issues(self, capsys):
        """Test text format with issues found."""
        mock_detection = Mock()
        mock_detection.line = 10
        mock_detection.column = 5
        mock_detection.__str__ = Mock(return_value='V001: Test issue at line 10')
        detections = [mock_detection]

        _format_check_detections('test.py', detections, 'text')

        captured = capsys.readouterr()
        assert 'test.py: Found 1 issues' in captured.out
        assert 'V001: Test issue at line 10' in captured.out

    def test_format_detections_text_no_issues(self, capsys):
        """Test text format with no issues."""
        _format_check_detections('test.py', [], 'text')

        captured = capsys.readouterr()
        assert 'test.py: ✅ No issues found' in captured.out


# ==============================================================================
# Test SCHEME_HANDLERS Registry
# ==============================================================================


class TestSchemeHandlers:
    """Tests for SCHEME_HANDLERS dispatch table."""

    def test_scheme_handlers_contains_all_schemes(self):
        """Test all known schemes are registered."""
        expected_schemes = ['env', 'ast', 'help', 'python', 'json', 'reveal', 'stats', 'mysql']

        for scheme in expected_schemes:
            assert scheme in SCHEME_HANDLERS, f"Scheme '{scheme}' not in SCHEME_HANDLERS"

    def test_scheme_handlers_functions_are_callable(self):
        """Test all handlers are callable functions."""
        for scheme, handler in SCHEME_HANDLERS.items():
            assert callable(handler), f"Handler for '{scheme}' is not callable"
