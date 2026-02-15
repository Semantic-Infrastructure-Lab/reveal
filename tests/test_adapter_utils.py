"""Tests for reveal/rules/validation/adapter_utils.py

Tests utility functions for adapter discovery, class retrieval, and line finding
used across multiple validation rules.
"""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from reveal.rules.validation.adapter_utils import (
    find_adapter_file,
    get_adapter_schemes,
    get_adapter_class,
    get_renderer_class,
    get_adapter_and_renderer,
    find_class_definition_line,
    find_method_definition_line,
    find_init_definition_line,
)


class TestFindAdapterFile(unittest.TestCase):
    """Tests for find_adapter_file function."""

    def test_adapters_dir_not_exists(self):
        """Should return None when adapters directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            result = find_adapter_file(reveal_root, 'git')
            self.assertIsNone(result)

    def test_direct_file_pattern(self):
        """Should find adapter with direct file pattern (scheme.py)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            adapters_dir.mkdir()

            # Create env.py adapter
            adapter_file = adapters_dir / 'env.py'
            adapter_file.write_text('# EnvAdapter')

            result = find_adapter_file(reveal_root, 'env')
            self.assertEqual(result, adapter_file)

    def test_named_adapter_file_pattern(self):
        """Should find adapter with _adapter suffix (scheme_adapter.py)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            adapters_dir.mkdir()

            # Create json_adapter.py
            adapter_file = adapters_dir / 'json_adapter.py'
            adapter_file.write_text('# JsonAdapter')

            result = find_adapter_file(reveal_root, 'json')
            self.assertEqual(result, adapter_file)

    def test_package_adapter_file_pattern(self):
        """Should find adapter in package with adapter.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            git_dir = adapters_dir / 'git'
            git_dir.mkdir(parents=True)

            # Create git/adapter.py
            adapter_file = git_dir / 'adapter.py'
            adapter_file.write_text('# GitAdapter')

            result = find_adapter_file(reveal_root, 'git')
            self.assertEqual(result, adapter_file)

    def test_package_init_file_pattern(self):
        """Should find adapter in package __init__.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            mysql_dir = adapters_dir / 'mysql'
            mysql_dir.mkdir(parents=True)

            # Create mysql/__init__.py
            adapter_file = mysql_dir / '__init__.py'
            adapter_file.write_text('# MySQLAdapter')

            result = find_adapter_file(reveal_root, 'mysql')
            self.assertEqual(result, adapter_file)

    def test_pattern_precedence(self):
        """Should prefer direct file over other patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            test_dir = adapters_dir / 'test'
            test_dir.mkdir(parents=True)

            # Create multiple patterns
            direct_file = adapters_dir / 'test.py'
            direct_file.write_text('# Direct')

            named_file = adapters_dir / 'test_adapter.py'
            named_file.write_text('# Named')

            package_file = test_dir / 'adapter.py'
            package_file.write_text('# Package')

            # Should find direct file first
            result = find_adapter_file(reveal_root, 'test')
            self.assertEqual(result, direct_file)

    def test_no_matching_pattern(self):
        """Should return None when no pattern matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            adapters_dir.mkdir()

            # Create unrelated file
            (adapters_dir / 'other.py').write_text('# Other')

            result = find_adapter_file(reveal_root, 'nonexistent')
            self.assertIsNone(result)


class TestGetAdapterSchemes(unittest.TestCase):
    """Tests for get_adapter_schemes function."""

    @patch('reveal.adapters.base.list_supported_schemes')
    def test_success(self, mock_list_schemes):
        """Should return sorted list of schemes."""
        mock_list_schemes.return_value = ['git', 'env', 'ast', 'diff']

        result = get_adapter_schemes()

        self.assertEqual(result, ['ast', 'diff', 'env', 'git'])
        mock_list_schemes.assert_called_once()

    @patch('reveal.adapters.base.list_supported_schemes')
    def test_exception_returns_empty(self, mock_list_schemes):
        """Should return empty list on exception."""
        mock_list_schemes.side_effect = Exception('Import failed')

        result = get_adapter_schemes()

        self.assertEqual(result, [])

    @patch('reveal.adapters.base.list_supported_schemes')
    def test_empty_schemes(self, mock_list_schemes):
        """Should handle empty schemes list."""
        mock_list_schemes.return_value = []

        result = get_adapter_schemes()

        self.assertEqual(result, [])


class TestGetAdapterClass(unittest.TestCase):
    """Tests for get_adapter_class function."""

    @patch('reveal.adapters.base.get_adapter_class')
    def test_success(self, mock_get_adapter):
        """Should return adapter class for valid scheme."""
        mock_adapter = MagicMock()
        mock_adapter.__name__ = 'GitAdapter'
        mock_get_adapter.return_value = mock_adapter

        result = get_adapter_class('git')

        self.assertEqual(result, mock_adapter)
        mock_get_adapter.assert_called_once_with('git')

    @patch('reveal.adapters.base.get_adapter_class')
    def test_exception_returns_none(self, mock_get_adapter):
        """Should return None on exception."""
        mock_get_adapter.side_effect = Exception('Adapter not found')

        result = get_adapter_class('nonexistent')

        self.assertIsNone(result)

    @patch('reveal.adapters.base.get_adapter_class')
    def test_none_scheme(self, mock_get_adapter):
        """Should handle None scheme gracefully."""
        mock_get_adapter.side_effect = Exception('Invalid scheme')

        result = get_adapter_class(None)

        self.assertIsNone(result)


class TestGetRendererClass(unittest.TestCase):
    """Tests for get_renderer_class function."""

    @patch('reveal.adapters.base.get_renderer_class')
    def test_success(self, mock_get_renderer):
        """Should return renderer class for valid scheme."""
        mock_renderer = MagicMock()
        mock_renderer.__name__ = 'GitRenderer'
        mock_get_renderer.return_value = mock_renderer

        result = get_renderer_class('git')

        self.assertEqual(result, mock_renderer)
        mock_get_renderer.assert_called_once_with('git')

    @patch('reveal.adapters.base.get_renderer_class')
    def test_exception_returns_none(self, mock_get_renderer):
        """Should return None on exception."""
        mock_get_renderer.side_effect = Exception('Renderer not found')

        result = get_renderer_class('nonexistent')

        self.assertIsNone(result)

    @patch('reveal.adapters.base.get_renderer_class')
    def test_none_scheme(self, mock_get_renderer):
        """Should handle None scheme gracefully."""
        mock_get_renderer.side_effect = Exception('Invalid scheme')

        result = get_renderer_class(None)

        self.assertIsNone(result)


class TestGetAdapterAndRenderer(unittest.TestCase):
    """Tests for get_adapter_and_renderer function."""

    @patch('reveal.rules.validation.adapter_utils.get_renderer_class')
    @patch('reveal.rules.validation.adapter_utils.get_adapter_class')
    def test_both_found(self, mock_get_adapter, mock_get_renderer):
        """Should return both adapter and renderer."""
        mock_adapter = MagicMock()
        mock_renderer = MagicMock()
        mock_get_adapter.return_value = mock_adapter
        mock_get_renderer.return_value = mock_renderer

        adapter, renderer = get_adapter_and_renderer('git')

        self.assertEqual(adapter, mock_adapter)
        self.assertEqual(renderer, mock_renderer)

    @patch('reveal.rules.validation.adapter_utils.get_renderer_class')
    @patch('reveal.rules.validation.adapter_utils.get_adapter_class')
    def test_only_adapter_found(self, mock_get_adapter, mock_get_renderer):
        """Should return adapter and None for renderer."""
        mock_adapter = MagicMock()
        mock_get_adapter.return_value = mock_adapter
        mock_get_renderer.return_value = None

        adapter, renderer = get_adapter_and_renderer('git')

        self.assertEqual(adapter, mock_adapter)
        self.assertIsNone(renderer)

    @patch('reveal.rules.validation.adapter_utils.get_renderer_class')
    @patch('reveal.rules.validation.adapter_utils.get_adapter_class')
    def test_only_renderer_found(self, mock_get_adapter, mock_get_renderer):
        """Should return None for adapter and renderer."""
        mock_renderer = MagicMock()
        mock_get_adapter.return_value = None
        mock_get_renderer.return_value = mock_renderer

        adapter, renderer = get_adapter_and_renderer('git')

        self.assertIsNone(adapter)
        self.assertEqual(renderer, mock_renderer)

    @patch('reveal.rules.validation.adapter_utils.get_renderer_class')
    @patch('reveal.rules.validation.adapter_utils.get_adapter_class')
    def test_neither_found(self, mock_get_adapter, mock_get_renderer):
        """Should return None for both."""
        mock_get_adapter.return_value = None
        mock_get_renderer.return_value = None

        adapter, renderer = get_adapter_and_renderer('nonexistent')

        self.assertIsNone(adapter)
        self.assertIsNone(renderer)


class TestFindClassDefinitionLine(unittest.TestCase):
    """Tests for find_class_definition_line function."""

    def test_class_found(self):
        """Should return line number where class is defined."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''# Header comment
import os

class GitAdapter:
    """Git adapter class."""
    pass
''')

            result = find_class_definition_line(file_path, 'GitAdapter')
            self.assertEqual(result, 4)

    def test_class_not_found(self):
        """Should return 1 when class not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''import os

def some_function():
    pass
''')

            result = find_class_definition_line(file_path, 'GitAdapter')
            self.assertEqual(result, 1)

    def test_file_not_exists(self):
        """Should return 1 when file doesn't exist."""
        file_path = Path('/nonexistent/file.py')

        result = find_class_definition_line(file_path, 'GitAdapter')
        self.assertEqual(result, 1)

    def test_partial_match_not_found(self):
        """Should not match partial class names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class GitAdapterBase:
    pass

class MyGitAdapter:
    pass
''')

            # Should not match GitAdapterBase or MyGitAdapter
            result = find_class_definition_line(file_path, 'GitAdapter')
            self.assertEqual(result, 1)

    def test_class_in_docstring_matches(self):
        """Simple string matching means it matches in docstrings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''"""
This is about class GitAdapter but not the real definition.
"""

def factory():
    return "class GitAdapter"
''')

            # Simple string matching finds first occurrence (in docstring at line 2)
            result = find_class_definition_line(file_path, 'GitAdapter')
            self.assertEqual(result, 2)


class TestFindMethodDefinitionLine(unittest.TestCase):
    """Tests for find_method_definition_line function."""

    def test_method_found(self):
        """Should return line number where method is defined."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class GitAdapter:
    def __init__(self, uri):
        pass

    def get_element(self, selector):
        pass
''')

            result = find_method_definition_line(file_path, 'get_element')
            self.assertEqual(result, 5)

    def test_method_not_found(self):
        """Should return 1 when method not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class GitAdapter:
    def __init__(self, uri):
        pass
''')

            result = find_method_definition_line(file_path, 'get_element')
            self.assertEqual(result, 1)

    def test_file_not_exists(self):
        """Should return 1 when file doesn't exist."""
        file_path = Path('/nonexistent/file.py')

        result = find_method_definition_line(file_path, 'get_element')
        self.assertEqual(result, 1)

    def test_dunder_method_found(self):
        """Should find dunder methods like __init__."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class GitAdapter:
    def __init__(self, uri):
        pass
''')

            result = find_method_definition_line(file_path, '__init__')
            self.assertEqual(result, 2)

    def test_partial_match_found(self):
        """Simple substring matching means it matches partial names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class GitAdapter:
    def get_element_by_id(self):
        pass

    def _get_element(self):
        pass
''')

            # Substring matching finds first occurrence (get_element_by_id at line 2)
            result = find_method_definition_line(file_path, 'get_element')
            self.assertEqual(result, 2)

    def test_method_in_docstring_matches(self):
        """Simple string matching means it matches in docstrings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class GitAdapter:
    """def get_element is not here"""

    def other_method(self):
        return "def get_element"
''')

            # Simple string matching finds first occurrence (in docstring at line 2)
            result = find_method_definition_line(file_path, 'get_element')
            self.assertEqual(result, 2)


class TestFindInitDefinitionLine(unittest.TestCase):
    """Tests for find_init_definition_line function."""

    def test_init_found(self):
        """Should return line number where __init__ is defined."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class GitAdapter:
    """Git adapter class."""

    def __init__(self, uri):
        self.uri = uri
''')

            result = find_init_definition_line(file_path)
            self.assertEqual(result, 4)

    def test_init_not_found(self):
        """Should return 1 when __init__ not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class GitAdapter:
    def get_element(self, selector):
        pass
''')

            result = find_init_definition_line(file_path)
            self.assertEqual(result, 1)

    def test_file_not_exists(self):
        """Should return 1 when file doesn't exist."""
        file_path = Path('/nonexistent/file.py')

        result = find_init_definition_line(file_path)
        self.assertEqual(result, 1)

    def test_multiple_classes(self):
        """Should find first __init__ in file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'test.py'
            file_path.write_text('''class FirstClass:
    def __init__(self):
        pass

class SecondClass:
    def __init__(self):
        pass
''')

            # Should find first __init__
            result = find_init_definition_line(file_path)
            self.assertEqual(result, 2)


if __name__ == '__main__':
    unittest.main()
