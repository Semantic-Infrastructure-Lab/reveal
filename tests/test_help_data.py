"""Tests for adapters/help_data module.

Tests the HelpDataLoader class which loads help documentation from YAML files.
"""

import unittest
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path
import tempfile
import yaml

from reveal.adapters.help_data import HelpDataLoader, load_help_data


class TestHelpDataLoader(unittest.TestCase):
    """Test HelpDataLoader functionality."""

    def setUp(self):
        """Clear cache before each test."""
        HelpDataLoader.clear_cache()

    def tearDown(self):
        """Clear cache after each test."""
        HelpDataLoader.clear_cache()

    def test_load_existing_help_data(self):
        """Test loading existing help data file (mysql.yaml exists in repo)."""
        help_data = HelpDataLoader.load('mysql')

        self.assertIsNotNone(help_data)
        self.assertIsInstance(help_data, dict)
        self.assertIn('name', help_data)
        self.assertEqual(help_data['name'], 'mysql')

    def test_load_nonexistent_file_returns_none(self):
        """Test that loading nonexistent file returns None and logs error."""
        with self.assertLogs('reveal.adapters.help_data', level='ERROR') as cm:
            result = HelpDataLoader.load('nonexistent_adapter_xyz')

        self.assertIsNone(result)
        self.assertTrue(any('not found' in log for log in cm.output))

    def test_load_empty_file_returns_none(self):
        """Test that empty YAML file returns None and logs error."""
        # Mock open to return empty content
        with patch('builtins.open', mock_open(read_data='')):
            # Mock exists() to return True so we get past the file existence check
            with patch.object(Path, 'exists', return_value=True):
                with self.assertLogs('reveal.adapters.help_data', level='ERROR') as cm:
                    result = HelpDataLoader.load('empty_adapter')

        self.assertIsNone(result)
        self.assertTrue(any('empty' in log for log in cm.output))

    def test_load_invalid_yaml_returns_none(self):
        """Test that invalid YAML returns None and logs error."""
        invalid_yaml = "name: test\n  invalid: [\n  unclosed"

        with patch('builtins.open', mock_open(read_data=invalid_yaml)):
            with patch.object(Path, 'exists', return_value=True):
                with self.assertLogs('reveal.adapters.help_data', level='ERROR') as cm:
                    result = HelpDataLoader.load('invalid_yaml_adapter')

        self.assertIsNone(result)
        self.assertTrue(any('Failed to parse YAML' in log for log in cm.output))

    def test_load_general_exception_returns_none(self):
        """Test that general exceptions are caught and return None."""
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            with patch.object(Path, 'exists', return_value=True):
                with self.assertLogs('reveal.adapters.help_data', level='ERROR') as cm:
                    result = HelpDataLoader.load('permission_error_adapter')

        self.assertIsNone(result)
        self.assertTrue(any('Failed to load help data' in log for log in cm.output))

    def test_cache_functionality(self):
        """Test that cache works correctly (loads once, returns cached on second call)."""
        # First load - should hit filesystem
        first_result = HelpDataLoader.load('mysql')
        self.assertIsNotNone(first_result)

        # Verify it's in cache
        self.assertIn('mysql', HelpDataLoader._cache)

        # Second load - should return cached version
        with self.assertLogs('reveal.adapters.help_data', level='DEBUG') as cm:
            second_result = HelpDataLoader.load('mysql')

        self.assertEqual(first_result, second_result)
        self.assertTrue(any('loaded from cache' in log for log in cm.output))

    def test_clear_cache(self):
        """Test that clear_cache() removes all cached entries."""
        # Load something to populate cache
        HelpDataLoader.load('mysql')
        self.assertGreater(len(HelpDataLoader._cache), 0)

        # Clear cache
        with self.assertLogs('reveal.adapters.help_data', level='DEBUG') as cm:
            HelpDataLoader.clear_cache()

        self.assertEqual(len(HelpDataLoader._cache), 0)
        self.assertTrue(any('cache cleared' in log for log in cm.output))

    def test_load_help_data_convenience_function(self):
        """Test convenience function delegates to HelpDataLoader.load()."""
        result = load_help_data('mysql')

        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result['name'], 'mysql')


if __name__ == '__main__':
    unittest.main()
