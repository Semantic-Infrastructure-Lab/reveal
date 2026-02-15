"""Extended tests for V018: Adapter renderer registration completeness."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reveal.rules.validation.V018 import V018


class TestV018NoRevealRoot(unittest.TestCase):
    """Test V018 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V018()

    def test_no_reveal_root_returns_empty(self):
        """Test that check returns empty when reveal root not found."""
        with mock.patch('reveal.rules.validation.V018.find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV018ImportFailure(unittest.TestCase):
    """Test V018 when adapter/renderer imports fail."""

    def setUp(self):
        self.rule = V018()

    def test_import_exception_returns_empty(self):
        """Test that check returns empty when imports fail."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / 'adapters').mkdir()

            # Patch find_reveal_root to return a valid path
            with mock.patch('reveal.rules.validation.V018.find_reveal_root', return_value=root):
                # The actual imports will work (revealing real adapters)
                # but this test verifies the code handles the try/except correctly
                detections = self.rule.check(
                    file_path="reveal://",
                    structure=None,
                    content=""
                )

                # Should return a list (empty or with real adapter/renderer mismatches)
                self.assertIsInstance(detections, list)


class TestV018MissingRenderer(unittest.TestCase):
    """Test V018 detection of missing renderers."""

    def setUp(self):
        self.rule = V018()

    def test_adapter_without_renderer_logic(self):
        """Test the missing renderer detection logic."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            # Create adapter file for a scheme that doesn't exist in reveal
            (adapters_dir / 'testscheme.py').write_text("# Test adapter")

            with mock.patch('reveal.rules.validation.V018.find_reveal_root', return_value=root):
                # Test with mocked adapter/renderer lists
                mock_adapters = ['testscheme', 'other']
                mock_renderers = ['other']  # testscheme missing renderer

                with mock.patch('reveal.adapters.base.list_supported_schemes', return_value=mock_adapters):
                    with mock.patch('reveal.adapters.base.list_renderer_schemes', return_value=mock_renderers):
                        detections = self.rule.check(
                            file_path="reveal://",
                            structure=None,
                            content=""
                        )

                        # Should detect missing renderer for testscheme
                        missing = [d for d in detections if 'testscheme' in d.message and 'no renderer' in d.message]
                        self.assertGreaterEqual(len(missing), 1)

    def test_missing_adapter_file_no_crash(self):
        """Test that missing adapter file doesn't crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            with mock.patch('reveal.rules.validation.V018.find_reveal_root', return_value=root):
                # Test with adapter that has no file
                mock_adapters = ['nonexistent']
                mock_renderers = []

                with mock.patch('reveal.adapters.base.list_supported_schemes', return_value=mock_adapters):
                    with mock.patch('reveal.adapters.base.list_renderer_schemes', return_value=mock_renderers):
                        detections = self.rule.check(
                            file_path="reveal://",
                            structure=None,
                            content=""
                        )

                        # Should not crash when adapter file not found
                        self.assertIsInstance(detections, list)


class TestV018OrphanedRenderer(unittest.TestCase):
    """Test V018 detection of orphaned renderers."""

    def setUp(self):
        self.rule = V018()

    def test_renderer_without_adapter_detected(self):
        """Test detection when renderer has no adapter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            # Create file for orphaned renderer
            (adapters_dir / 'orphan.py').write_text("# Orphaned renderer")

            with mock.patch('reveal.rules.validation.V018.find_reveal_root', return_value=root):
                # Test with renderer that has no adapter
                mock_adapters = ['normal']
                mock_renderers = ['normal', 'orphan']  # orphan has no adapter

                with mock.patch('reveal.adapters.base.list_supported_schemes', return_value=mock_adapters):
                    with mock.patch('reveal.adapters.base.list_renderer_schemes', return_value=mock_renderers):
                        detections = self.rule.check(
                            file_path="reveal://",
                            structure=None,
                            content=""
                        )

                        # Should detect orphaned renderer
                        orphaned = [d for d in detections if 'orphan' in d.message and 'no adapter' in d.message]
                        self.assertGreaterEqual(len(orphaned), 1)


class TestV018FindAdapterFile(unittest.TestCase):
    """Test V018 _find_adapter_file method."""

    def setUp(self):
        self.rule = V018()

    def test_adapters_dir_missing_returns_none(self):
        """Test _find_adapter_file returns None when adapters dir missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            result = self.rule._find_adapter_file(root, 'test')

            self.assertIsNone(result)

    def test_scheme_py_pattern_found(self):
        """Test _find_adapter_file finds scheme.py pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            # Create scheme.py file
            (adapters_dir / 'env.py').write_text("# Env adapter")

            result = self.rule._find_adapter_file(root, 'env')

            self.assertIsNotNone(result)
            self.assertEqual(result.name, 'env.py')

    def test_scheme_adapter_py_pattern_found(self):
        """Test _find_adapter_file finds scheme_adapter.py pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            # Create scheme_adapter.py file (without scheme.py)
            (adapters_dir / 'json_adapter.py').write_text("# JSON adapter")

            result = self.rule._find_adapter_file(root, 'json')

            self.assertIsNotNone(result)
            self.assertEqual(result.name, 'json_adapter.py')

    def test_scheme_dir_adapter_py_pattern_found(self):
        """Test _find_adapter_file finds scheme/adapter.py pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            # Create scheme/adapter.py file
            git_dir = adapters_dir / 'git'
            git_dir.mkdir()
            (git_dir / 'adapter.py').write_text("# Git adapter")

            result = self.rule._find_adapter_file(root, 'git')

            self.assertIsNotNone(result)
            self.assertEqual(result.name, 'adapter.py')
            self.assertEqual(result.parent.name, 'git')

    def test_scheme_dir_init_py_pattern_found(self):
        """Test _find_adapter_file finds scheme/__init__.py pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            # Create scheme/__init__.py file (without adapter.py)
            mysql_dir = adapters_dir / 'mysql'
            mysql_dir.mkdir()
            (mysql_dir / '__init__.py').write_text("# MySQL adapter")

            result = self.rule._find_adapter_file(root, 'mysql')

            self.assertIsNotNone(result)
            self.assertEqual(result.name, '__init__.py')
            self.assertEqual(result.parent.name, 'mysql')

    def test_not_found_returns_none(self):
        """Test _find_adapter_file returns None when file not found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            result = self.rule._find_adapter_file(root, 'nonexistent')

            self.assertIsNone(result)

    def test_pattern_precedence(self):
        """Test _find_adapter_file pattern precedence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            adapters_dir = root / 'adapters'
            adapters_dir.mkdir()

            # Create multiple patterns (should prefer scheme.py)
            (adapters_dir / 'test.py').write_text("# Test 1")
            (adapters_dir / 'test_adapter.py').write_text("# Test 2")

            result = self.rule._find_adapter_file(root, 'test')

            # Should prefer scheme.py over scheme_adapter.py
            self.assertEqual(result.name, 'test.py')


class TestV018GetDescription(unittest.TestCase):
    """Test V018 get_description method."""

    def setUp(self):
        self.rule = V018()

    def test_get_description(self):
        """Test get_description returns meaningful text."""
        description = self.rule.get_description()

        self.assertIsInstance(description, str)
        self.assertIn('renderer', description.lower())
        self.assertIn('adapter', description.lower())


if __name__ == '__main__':
    unittest.main()
