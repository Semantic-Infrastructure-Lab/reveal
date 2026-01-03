"""Tests for imports:// URI scheme handler."""

import sys
from io import StringIO
from argparse import Namespace
from unittest.mock import Mock, patch, MagicMock
import pytest

from reveal.cli.scheme_handlers.imports import (
    _render_unused_imports,
    _render_circular_dependencies,
    _render_layer_violations,
    _render_import_summary,
    handle_imports,
)


class TestRenderUnusedImports:
    """Test unused imports rendering."""

    def test_render_no_unused_imports(self, capsys):
        """Test rendering when no unused imports found."""
        result = {'count': 0, 'unused': []}
        _render_unused_imports(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Unused Imports: 0' in captured.out
        assert '✅ No unused imports found!' in captured.out

    def test_render_unused_imports_summary_mode(self, capsys):
        """Test rendering unused imports in summary mode (< 10 imports)."""
        result = {
            'count': 3,
            'unused': [
                {'file': 'app.py', 'line': 5, 'module': 'os'},
                {'file': 'utils.py', 'line': 10, 'module': 'sys'},
                {'file': 'main.py', 'line': 2, 'module': 're'},
            ]
        }
        _render_unused_imports(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Unused Imports: 3' in captured.out
        assert 'app.py:5 - os' in captured.out
        assert 'utils.py:10 - sys' in captured.out
        assert 'main.py:2 - re' in captured.out

    def test_render_unused_imports_summary_mode_many(self, capsys):
        """Test rendering with more than 10 unused imports (summary mode)."""
        unused = [
            {'file': f'file{i}.py', 'line': i, 'module': f'module{i}'}
            for i in range(15)
        ]
        result = {'count': 15, 'unused': unused}
        _render_unused_imports(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Unused Imports: 15' in captured.out
        assert 'file0.py:0 - module0' in captured.out
        assert 'file9.py:9 - module9' in captured.out
        assert '... and 5 more unused imports' in captured.out
        assert 'Run with --verbose to see all 15 unused imports' in captured.out

    def test_render_unused_imports_verbose_mode(self, capsys):
        """Test rendering in verbose mode shows all imports."""
        unused = [
            {'file': f'file{i}.py', 'line': i, 'module': f'module{i}'}
            for i in range(15)
        ]
        result = {'count': 15, 'unused': unused}
        _render_unused_imports(result, verbose=True)

        captured = capsys.readouterr()
        assert 'Unused Imports: 15' in captured.out
        # All 15 should be shown
        for i in range(15):
            assert f'file{i}.py:{i} - module{i}' in captured.out
        # Should not show truncation message
        assert 'and 5 more' not in captured.out


class TestRenderCircularDependencies:
    """Test circular dependency rendering."""

    def test_render_no_circular_dependencies(self, capsys):
        """Test rendering when no circular dependencies found."""
        result = {'count': 0, 'cycles': []}
        _render_circular_dependencies(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Circular Dependencies: 0' in captured.out
        assert '✅ No circular dependencies found!' in captured.out

    def test_render_circular_dependencies_summary_mode(self, capsys):
        """Test rendering circular dependencies in summary mode."""
        result = {
            'count': 3,
            'cycles': [
                ['a.py', 'b.py', 'a.py'],
                ['c.py', 'd.py', 'c.py'],
                ['e.py', 'f.py', 'g.py', 'e.py'],
            ]
        }
        _render_circular_dependencies(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Circular Dependencies: 3' in captured.out
        assert '1. a.py -> b.py -> a.py' in captured.out
        assert '2. c.py -> d.py -> c.py' in captured.out
        assert '3. e.py -> f.py -> g.py -> e.py' in captured.out

    def test_render_circular_dependencies_summary_mode_many(self, capsys):
        """Test rendering with more than 5 cycles (summary mode)."""
        cycles = [[f'file{i}.py', f'file{i+1}.py', f'file{i}.py'] for i in range(8)]
        result = {'count': 8, 'cycles': cycles}
        _render_circular_dependencies(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Circular Dependencies: 8' in captured.out
        assert '1. file0.py -> file1.py -> file0.py' in captured.out
        assert '5. file4.py -> file5.py -> file4.py' in captured.out
        assert '... and 3 more circular dependencies' in captured.out
        assert 'Run with --verbose to see all 8 cycles' in captured.out

    def test_render_circular_dependencies_verbose_mode(self, capsys):
        """Test rendering in verbose mode shows all cycles."""
        cycles = [[f'file{i}.py', f'file{i+1}.py', f'file{i}.py'] for i in range(8)]
        result = {'count': 8, 'cycles': cycles}
        _render_circular_dependencies(result, verbose=True)

        captured = capsys.readouterr()
        assert 'Circular Dependencies: 8' in captured.out
        # All 8 should be shown
        for i in range(8):
            assert f'{i+1}. file{i}.py -> file{i+1}.py -> file{i}.py' in captured.out


class TestRenderLayerViolations:
    """Test layer violation rendering."""

    def test_render_no_violations(self, capsys):
        """Test rendering when no violations found."""
        result = {'count': 0, 'violations': [], 'note': 'All layers respected'}
        _render_layer_violations(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Layer Violations: 0' in captured.out
        assert '✅ All layers respected' in captured.out

    def test_render_no_violations_default_note(self, capsys):
        """Test rendering with default note when no violations."""
        result = {'count': 0, 'violations': []}
        _render_layer_violations(result, verbose=False)

        captured = capsys.readouterr()
        assert '✅ No violations found' in captured.out

    def test_render_layer_violations_summary_mode(self, capsys):
        """Test rendering layer violations in summary mode."""
        result = {
            'count': 3,
            'violations': [
                {'file': 'routes.py', 'line': 10, 'message': 'routes importing from db layer'},
                {'file': 'api.py', 'line': 20, 'message': 'api importing from models'},
                {'file': 'views.py', 'line': 5, 'message': 'views importing from dal'},
            ]
        }
        _render_layer_violations(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Layer Violations: 3' in captured.out
        assert 'routes.py:10 - routes importing from db layer' in captured.out
        assert 'api.py:20 - api importing from models' in captured.out
        assert 'views.py:5 - views importing from dal' in captured.out

    def test_render_layer_violations_summary_mode_many(self, capsys):
        """Test rendering with more than 10 violations (summary mode)."""
        violations = [
            {'file': f'file{i}.py', 'line': i, 'message': f'violation {i}'}
            for i in range(15)
        ]
        result = {'count': 15, 'violations': violations}
        _render_layer_violations(result, verbose=False)

        captured = capsys.readouterr()
        assert 'Layer Violations: 15' in captured.out
        assert 'file0.py:0 - violation 0' in captured.out
        assert 'file9.py:9 - violation 9' in captured.out
        assert '... and 5 more violations' in captured.out
        assert 'Run with --verbose to see all 15 violations' in captured.out

    def test_render_layer_violations_verbose_mode(self, capsys):
        """Test rendering in verbose mode shows all violations."""
        violations = [
            {'file': f'file{i}.py', 'line': i, 'message': f'violation {i}'}
            for i in range(15)
        ]
        result = {'count': 15, 'violations': violations}
        _render_layer_violations(result, verbose=True)

        captured = capsys.readouterr()
        assert 'Layer Violations: 15' in captured.out
        # All 15 should be shown
        for i in range(15):
            assert f'file{i}.py:{i} - violation {i}' in captured.out


class TestRenderImportSummary:
    """Test import summary rendering."""

    def test_render_summary_basic(self, capsys):
        """Test rendering import analysis summary."""
        result = {
            'metadata': {
                'total_files': 42,
                'total_imports': 128,
                'has_cycles': False,
            }
        }
        _render_import_summary(result, 'src/app')

        captured = capsys.readouterr()
        assert 'Import Analysis: src/app' in captured.out
        assert 'Total Files:   42' in captured.out
        assert 'Total Imports: 128' in captured.out
        assert 'Cycles Found:  ✅ No' in captured.out
        assert "reveal 'imports://src/app?unused'" in captured.out

    def test_render_summary_with_cycles(self, capsys):
        """Test rendering summary when cycles are found."""
        result = {
            'metadata': {
                'total_files': 20,
                'total_imports': 50,
                'has_cycles': True,
            }
        }
        _render_import_summary(result, '.')

        captured = capsys.readouterr()
        assert 'Import Analysis: .' in captured.out
        assert 'Cycles Found:  ❌ Yes' in captured.out

    def test_render_summary_missing_metadata(self, capsys):
        """Test rendering summary with missing metadata."""
        result = {}
        _render_import_summary(result, 'app')

        captured = capsys.readouterr()
        assert 'Total Files:   0' in captured.out
        assert 'Total Imports: 0' in captured.out
        assert 'Cycles Found:  ✅ No' in captured.out


class TestHandleImports:
    """Test the main handle_imports function."""

    def test_handle_imports_default_resource(self):
        """Test that empty resource defaults to '.'"""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'import_summary',
            'metadata': {'total_files': 5, 'total_imports': 10, 'has_cycles': False}
        }
        args = Namespace(format='json', verbose=False)

        with patch('reveal.main.safe_json_dumps') as mock_dumps:
            mock_dumps.return_value = '{}'
            handle_imports(mock_adapter, '', None, args)

            # Should call get_structure with imports://.
            mock_adapter.return_value.get_structure.assert_called_once()
            call_uri = mock_adapter.return_value.get_structure.call_args[1]['uri']
            assert call_uri == 'imports://.'

    def test_handle_imports_with_resource(self):
        """Test handle_imports with explicit resource."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'unused_imports',
            'count': 0,
            'unused': []
        }
        args = Namespace(format='json', verbose=False)

        with patch('reveal.main.safe_json_dumps') as mock_dumps:
            mock_dumps.return_value = '{}'
            handle_imports(mock_adapter, 'src/app', None, args)

            call_uri = mock_adapter.return_value.get_structure.call_args[1]['uri']
            assert call_uri == 'imports://src/app'

    def test_handle_imports_json_format(self, capsys):
        """Test JSON output format."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'unused_imports',
            'count': 2,
            'unused': [{'file': 'a.py', 'line': 1, 'module': 'os'}]
        }
        args = Namespace(format='json', verbose=False)

        with patch('reveal.main.safe_json_dumps') as mock_dumps:
            mock_dumps.return_value = '{"count": 2}'
            handle_imports(mock_adapter, 'app', None, args)

            captured = capsys.readouterr()
            assert '{"count": 2}' in captured.out

    def test_handle_imports_text_unused(self, capsys):
        """Test text format for unused imports."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'unused_imports',
            'count': 1,
            'unused': [{'file': 'app.py', 'line': 5, 'module': 'sys'}]
        }
        args = Namespace(format='text', verbose=False)

        handle_imports(mock_adapter, 'app', None, args)

        captured = capsys.readouterr()
        assert 'Unused Imports: 1' in captured.out
        assert 'app.py:5 - sys' in captured.out

    def test_handle_imports_text_circular(self, capsys):
        """Test text format for circular dependencies."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'circular_dependencies',
            'count': 1,
            'cycles': [['a.py', 'b.py', 'a.py']]
        }
        args = Namespace(format='text', verbose=False)

        handle_imports(mock_adapter, 'app', None, args)

        captured = capsys.readouterr()
        assert 'Circular Dependencies: 1' in captured.out
        assert 'a.py -> b.py -> a.py' in captured.out

    def test_handle_imports_text_violations(self, capsys):
        """Test text format for layer violations."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'layer_violations',
            'count': 1,
            'violations': [{'file': 'route.py', 'line': 10, 'message': 'bad import'}]
        }
        args = Namespace(format='text', verbose=False)

        handle_imports(mock_adapter, 'app', None, args)

        captured = capsys.readouterr()
        assert 'Layer Violations: 1' in captured.out
        assert 'route.py:10 - bad import' in captured.out

    def test_handle_imports_text_summary(self, capsys):
        """Test text format for import summary."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'import_summary',  # Need to add type field!
            'metadata': {
                'total_files': 10,
                'total_imports': 30,
                'has_cycles': False
            }
        }
        args = Namespace(format='text', verbose=False)

        handle_imports(mock_adapter, 'app', None, args)

        captured = capsys.readouterr()
        assert 'Import Analysis: app' in captured.out
        assert 'Total Files:   10' in captured.out

    def test_handle_imports_unknown_type_shows_summary(self, capsys):
        """Test unknown result type falls through to summary display."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'unknown_type',
            'metadata': {
                'total_files': 5,
                'total_imports': 15,
                'has_cycles': False
            }
        }
        args = Namespace(format='text', verbose=False)

        handle_imports(mock_adapter, 'app', None, args)

        captured = capsys.readouterr()
        # Unknown types fall through to summary display
        assert 'Import Analysis: app' in captured.out
        assert 'Total Files:   5' in captured.out

    def test_handle_imports_no_type_fallback(self, capsys):
        """Test fallback to JSON when no type field."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {'data': 'something'}
        args = Namespace(format='text', verbose=False)

        with patch('reveal.main.safe_json_dumps') as mock_dumps:
            mock_dumps.return_value = '{"data": "something"}'
            handle_imports(mock_adapter, 'app', None, args)

            captured = capsys.readouterr()
            assert '{"data": "something"}' in captured.out

    def test_handle_imports_with_element(self):
        """Test getting imports for specific file element."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_element.return_value = {
            'file': 'app.py',
            'imports': ['os', 'sys']
        }
        args = Namespace(format='json', verbose=False)

        with patch('reveal.main.safe_json_dumps') as mock_dumps:
            mock_dumps.return_value = '{"file": "app.py"}'
            handle_imports(mock_adapter, 'src', 'app.py', args)

            # Should call get_element, not get_structure
            mock_adapter.return_value.get_element.assert_called_once_with('app.py')
            mock_adapter.return_value.get_structure.assert_not_called()

    def test_handle_imports_element_not_found(self, capsys):
        """Test error handling when element file not found."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_element.return_value = None
        args = Namespace(format='json', verbose=False)

        with pytest.raises(SystemExit) as exc_info:
            handle_imports(mock_adapter, 'src', 'missing.py', args)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: File 'missing.py' not found" in captured.err

    def test_handle_imports_verbose_mode(self, capsys):
        """Test verbose mode is passed through."""
        mock_adapter = Mock()
        mock_adapter.return_value.get_structure.return_value = {
            'type': 'unused_imports',
            'count': 15,
            'unused': [
                {'file': f'file{i}.py', 'line': i, 'module': f'mod{i}'}
                for i in range(15)
            ]
        }
        args = Namespace(format='text', verbose=True)

        handle_imports(mock_adapter, 'app', None, args)

        captured = capsys.readouterr()
        # In verbose mode, all 15 should be shown
        for i in range(15):
            assert f'file{i}.py:{i} - mod{i}' in captured.out
        # Should not show truncation message
        assert 'and 5 more' not in captured.out
