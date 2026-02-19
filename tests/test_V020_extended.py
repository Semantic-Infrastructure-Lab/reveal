"""Extended tests for V020: Adapter element/structure contract validation.

These tests complement the existing tests in test_validation_rules.py by focusing
on edge cases and uncovered code paths to boost coverage from 65% to 80%+.
"""

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from reveal.rules.validation.V020 import V020


class TestV020ExtendedCoverage(unittest.TestCase):
    """Extended tests for V020 to cover additional code paths."""

    def setUp(self):
        self.rule = V020()

    @patch('reveal.rules.validation.V020.find_reveal_root')
    def test_check_no_reveal_root(self, mock_find_root):
        """Should return empty when reveal root not found."""
        mock_find_root.return_value = None

        detections = self.rule.check(
            file_path='reveal://',
            structure=None,
            content=''
        )

        self.assertEqual(len(detections), 0)

    @patch('reveal.rules.validation.V020.find_reveal_root')
    @patch('reveal.adapters.base.list_supported_schemes')
    @patch('reveal.adapters.base.get_adapter_class')
    @patch('reveal.adapters.base.get_renderer_class')
    def test_check_missing_adapter_class(self, mock_get_renderer, mock_get_adapter,
                                        mock_list_schemes, mock_find_root):
        """Should skip when adapter class not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            (reveal_root / 'adapters').mkdir()

            mock_find_root.return_value = reveal_root
            mock_list_schemes.return_value = ['test']
            mock_get_adapter.return_value = None  # No adapter
            mock_get_renderer.return_value = MagicMock()

            detections = self.rule.check(
                file_path='reveal://',
                structure=None,
                content=''
            )

            # Should skip (no adapter class)
            self.assertEqual(len(detections), 0)

    @patch('reveal.rules.validation.V020.find_reveal_root')
    @patch('reveal.adapters.base.list_supported_schemes')
    @patch('reveal.adapters.base.get_adapter_class')
    @patch('reveal.adapters.base.get_renderer_class')
    def test_check_missing_renderer_class(self, mock_get_renderer, mock_get_adapter,
                                         mock_list_schemes, mock_find_root):
        """Should skip when renderer class not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            (reveal_root / 'adapters').mkdir()

            mock_find_root.return_value = reveal_root
            mock_list_schemes.return_value = ['test']
            mock_get_adapter.return_value = MagicMock()
            mock_get_renderer.return_value = None  # No renderer

            detections = self.rule.check(
                file_path='reveal://',
                structure=None,
                content=''
            )

            # Should skip (no renderer class)
            self.assertEqual(len(detections), 0)

    @patch('reveal.rules.validation.V020.find_reveal_root')
    @patch('reveal.adapters.base.list_supported_schemes')
    @patch('reveal.adapters.base.get_adapter_class')
    @patch('reveal.adapters.base.get_renderer_class')
    def test_check_missing_adapter_file(self, mock_get_renderer, mock_get_adapter,
                                       mock_list_schemes, mock_find_root):
        """Should skip when adapter file not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            (reveal_root / 'adapters').mkdir()

            mock_find_root.return_value = reveal_root
            mock_list_schemes.return_value = ['nonexistent']

            mock_adapter = MagicMock()
            mock_adapter.__name__ = 'TestAdapter'
            mock_get_adapter.return_value = mock_adapter

            mock_renderer = MagicMock()
            mock_get_renderer.return_value = mock_renderer

            detections = self.rule.check(
                file_path='reveal://',
                structure=None,
                content=''
            )

            # Should skip (no adapter file found)
            self.assertEqual(len(detections), 0)

    @patch('reveal.rules.validation.V020.find_reveal_root')
    @patch('reveal.adapters.base.list_supported_schemes')
    @patch('reveal.adapters.base.get_adapter_class')
    @patch('reveal.adapters.base.get_renderer_class')
    def test_check_missing_get_element(self, mock_get_renderer, mock_get_adapter,
                                      mock_list_schemes, mock_find_root):
        """Should detect when adapter missing get_element but renderer has render_element."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            adapters_dir.mkdir()

            # Create adapter file
            adapter_file = adapters_dir / 'test.py'
            adapter_file.write_text('class TestAdapter:\n    pass\n')

            mock_find_root.return_value = reveal_root
            mock_list_schemes.return_value = ['test']

            # Adapter without get_element
            mock_adapter = MagicMock()
            mock_adapter.__name__ = 'TestAdapter'
            mock_adapter.get_structure = MagicMock()
            delattr(mock_adapter, 'get_element')  # Remove get_element
            mock_get_adapter.return_value = mock_adapter

            # Renderer with render_element
            mock_renderer = MagicMock()
            mock_renderer.render_element = MagicMock()
            mock_get_renderer.return_value = mock_renderer

            detections = self.rule.check(
                file_path='reveal://',
                structure=None,
                content=''
            )

            # Should detect missing get_element
            self.assertGreater(len(detections), 0)
            self.assertIn('get_element', detections[0].message)

    @patch('reveal.rules.validation.V020.find_reveal_root')
    @patch('reveal.adapters.base.list_supported_schemes')
    @patch('reveal.adapters.base.get_adapter_class')
    @patch('reveal.adapters.base.get_renderer_class')
    def test_check_missing_get_structure(self, mock_get_renderer, mock_get_adapter,
                                        mock_list_schemes, mock_find_root):
        """Should detect when adapter missing get_structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            adapters_dir.mkdir()

            # Create adapter file
            adapter_file = adapters_dir / 'test.py'
            adapter_file.write_text('class TestAdapter:\n    pass\n')

            mock_find_root.return_value = reveal_root
            mock_list_schemes.return_value = ['test']

            # Adapter without get_structure
            mock_adapter = MagicMock()
            mock_adapter.__name__ = 'TestAdapter'
            delattr(mock_adapter, 'get_structure')  # Remove get_structure
            mock_get_adapter.return_value = mock_adapter

            mock_renderer = MagicMock()
            mock_get_renderer.return_value = mock_renderer

            detections = self.rule.check(
                file_path='reveal://',
                structure=None,
                content=''
            )

            # Should detect missing get_structure
            self.assertGreater(len(detections), 0)
            self.assertIn('get_structure', detections[0].message)

    def test_test_get_element_error_handling_cannot_instantiate_no_args(self):
        """Should handle adapters that can't be instantiated without args."""
        mock_adapter_class = MagicMock()
        mock_adapter_class.side_effect = TypeError('Missing required argument')

        with tempfile.TemporaryDirectory() as tmpdir:
            adapter_file = Path(tmpdir) / 'test.py'
            adapter_file.write_text('class TestAdapter:\n    pass\n')

            result = self.rule._test_get_element_error_handling(
                'test',
                mock_adapter_class,
                adapter_file
            )

            # Should return None (can't test)
            self.assertIsNone(result)

    def test_test_get_element_error_handling_crashes_with_exception(self):
        """Should detect when get_element crashes instead of returning None."""
        mock_adapter = MagicMock()
        mock_adapter.get_element.side_effect = ValueError('Element not found')

        mock_adapter_class = MagicMock(return_value=mock_adapter)

        with tempfile.TemporaryDirectory() as tmpdir:
            adapter_file = Path(tmpdir) / 'test.py'
            adapter_file.write_text('def get_element():\n    pass\n')

            result = self.rule._test_get_element_error_handling(
                'test',
                mock_adapter_class,
                adapter_file
            )

            # Should detect crash
            self.assertIsNotNone(result)
            self.assertIn('crashes', result.message)
            self.assertIn('ValueError', result.message)

    def test_test_get_element_error_handling_returns_none(self):
        """Should accept when get_element properly returns None."""
        mock_adapter = MagicMock()
        mock_adapter.get_element.return_value = None

        mock_adapter_class = MagicMock(return_value=mock_adapter)

        with tempfile.TemporaryDirectory() as tmpdir:
            adapter_file = Path(tmpdir) / 'test.py'
            adapter_file.write_text('class TestAdapter:\n    pass\n')

            result = self.rule._test_get_element_error_handling(
                'test',
                mock_adapter_class,
                adapter_file
            )

            # Should return None (correct behavior)
            self.assertIsNone(result)

    def test_test_get_element_error_handling_outer_exception(self):
        """Should handle exceptions during adapter instantiation."""
        mock_adapter_class = MagicMock()
        mock_adapter_class.side_effect = RuntimeError('Instantiation failed')

        with tempfile.TemporaryDirectory() as tmpdir:
            adapter_file = Path(tmpdir) / 'test.py'
            adapter_file.write_text('class TestAdapter:\n    pass\n')

            result = self.rule._test_get_element_error_handling(
                'test',
                mock_adapter_class,
                adapter_file
            )

            # Should return None (can't test)
            self.assertIsNone(result)

    def test_find_line_matching_class_found(self):
        """Should find class definition line via _find_line_matching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter_file = Path(tmpdir) / 'test.py'
            adapter_file.write_text('''# Header
import os

class TestAdapter:
    pass
''')

            result = self.rule._find_line_matching(adapter_file, 'class TestAdapter')
            self.assertEqual(result, 4)

    def test_find_line_matching_class_not_found(self):
        """Should return 1 when pattern not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter_file = Path(tmpdir) / 'test.py'
            adapter_file.write_text('# No class here\n')

            result = self.rule._find_line_matching(adapter_file, 'class TestAdapter')
            self.assertEqual(result, 1)

    def test_find_line_matching_file_not_exists(self):
        """Should return 1 when file doesn't exist."""
        result = self.rule._find_line_matching(Path('/nonexistent.py'), 'class TestAdapter')
        self.assertEqual(result, 1)

    def test_find_line_matching_method_found(self):
        """Should find method definition line via _find_line_matching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter_file = Path(tmpdir) / 'test.py'
            adapter_file.write_text('''class TestAdapter:
    def get_element(self, name):
        pass
''')

            result = self.rule._find_line_matching(adapter_file, 'def get_element')
            self.assertEqual(result, 2)

    def test_find_line_matching_method_not_found(self):
        """Should return 1 when method not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            adapter_file = Path(tmpdir) / 'test.py'
            adapter_file.write_text('class TestAdapter:\n    pass\n')

            result = self.rule._find_line_matching(adapter_file, 'def get_element')
            self.assertEqual(result, 1)

    def test_find_line_matching_nonexistent_file(self):
        """Should return 1 when file doesn't exist."""
        result = self.rule._find_line_matching(Path('/nonexistent.py'), 'def get_element')
        self.assertEqual(result, 1)

    def test_find_adapter_file_direct_pattern(self):
        """Should find adapter with direct file pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            adapters_dir.mkdir()

            adapter_file = adapters_dir / 'test.py'
            adapter_file.write_text('# Adapter')

            result = self.rule._find_adapter_file(reveal_root, 'test')
            self.assertEqual(result, adapter_file)

    def test_find_adapter_file_no_adapters_dir(self):
        """Should return None when adapters directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)

            result = self.rule._find_adapter_file(reveal_root, 'test')
            self.assertIsNone(result)

    def test_find_adapter_file_not_found(self):
        """Should return None when adapter file not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reveal_root = Path(tmpdir)
            adapters_dir = reveal_root / 'adapters'
            adapters_dir.mkdir()

            result = self.rule._find_adapter_file(reveal_root, 'nonexistent')
            self.assertIsNone(result)

    def test_get_description(self):
        """Should return detailed rule description."""
        description = self.rule.get_description()

        self.assertIn('get_element', description)
        self.assertIn('get_structure', description)
        self.assertIn('renderer', description)


if __name__ == '__main__':
    unittest.main()
