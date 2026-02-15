"""Tests for reveal/rules/validation/utils.py

Tests utility functions for finding reveal root and detecting development checkouts.
"""

import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from reveal.rules.validation.utils import find_reveal_root, is_dev_checkout


class TestFindRevealRoot(unittest.TestCase):
    """Tests for find_reveal_root function."""

    @patch.dict(os.environ, {'REVEAL_DEV_ROOT': ''}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_env_var_valid_path(self, mock_cwd):
        """Should use REVEAL_DEV_ROOT when set and valid."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dev_root = Path(tmpdir) / 'reveal'
            dev_root.mkdir()
            (dev_root / 'analyzers').mkdir()
            (dev_root / 'rules').mkdir()

            # Set environment variable
            os.environ['REVEAL_DEV_ROOT'] = str(dev_root)

            # Mock cwd to not interfere
            mock_cwd.return_value = Path('/unrelated')

            result = find_reveal_root()

            self.assertEqual(result, dev_root)

    @patch.dict(os.environ, {'REVEAL_DEV_ROOT': '/nonexistent'}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_env_var_invalid_path(self, mock_cwd):
        """Should ignore REVEAL_DEV_ROOT when path invalid."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock cwd to return temp dir with reveal structure
            project_root = Path(tmpdir)
            reveal_dir = project_root / 'reveal'
            reveal_dir.mkdir()
            (reveal_dir / 'analyzers').mkdir()
            (reveal_dir / 'rules').mkdir()
            (project_root / 'pyproject.toml').touch()

            mock_cwd.return_value = project_root

            result = find_reveal_root()

            # Should find via cwd, not env var
            self.assertEqual(result, reveal_dir)

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_git_checkout_in_cwd(self, mock_cwd):
        """Should find reveal directory in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_dir = project_root / 'reveal'
            reveal_dir.mkdir()
            (reveal_dir / 'analyzers').mkdir()
            (reveal_dir / 'rules').mkdir()
            (project_root / 'pyproject.toml').touch()

            mock_cwd.return_value = project_root

            result = find_reveal_root()

            self.assertEqual(result, reveal_dir)

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_git_checkout_in_parent(self, mock_cwd):
        """Should search parent directories for reveal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / 'project'
            project_root.mkdir()
            reveal_dir = project_root / 'reveal'
            reveal_dir.mkdir()
            (reveal_dir / 'analyzers').mkdir()
            (reveal_dir / 'rules').mkdir()
            (project_root / 'pyproject.toml').touch()

            # Start in subdirectory
            subdir = project_root / 'tests' / 'unit'
            subdir.mkdir(parents=True)

            mock_cwd.return_value = subdir

            result = find_reveal_root()

            self.assertEqual(result, reveal_dir)

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_git_checkout_without_pyproject(self, mock_cwd):
        """Should not match reveal directory without pyproject.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_dir = project_root / 'reveal'
            reveal_dir.mkdir()
            (reveal_dir / 'analyzers').mkdir()
            (reveal_dir / 'rules').mkdir()
            # No pyproject.toml

            mock_cwd.return_value = project_root

            # Should fall back to installed package location
            result = find_reveal_root()

            # Result depends on where tests are running, but shouldn't be reveal_dir
            self.assertNotEqual(result, reveal_dir)

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_installed_package_fallback(self, mock_cwd):
        """Should fall back to installed package when no git checkout found."""
        # Mock cwd to unrelated path
        mock_cwd.return_value = Path('/unrelated')

        result = find_reveal_root()

        # Should find installed package (where this test file is running from)
        self.assertIsNotNone(result)
        self.assertTrue((result / 'analyzers').exists())
        self.assertTrue((result / 'rules').exists())

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_dev_only_flag_excludes_installed(self, mock_cwd):
        """Should not return installed package when dev_only=True."""
        # Mock cwd to unrelated path
        mock_cwd.return_value = Path('/unrelated')

        result = find_reveal_root(dev_only=True)

        # Should return None (no dev checkout, and dev_only excludes installed)
        self.assertIsNone(result)

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_dev_only_flag_allows_dev_checkout(self, mock_cwd):
        """Should return dev checkout even with dev_only=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_dir = project_root / 'reveal'
            reveal_dir.mkdir()
            (reveal_dir / 'analyzers').mkdir()
            (reveal_dir / 'rules').mkdir()
            (project_root / 'pyproject.toml').touch()

            mock_cwd.return_value = project_root

            result = find_reveal_root(dev_only=True)

            self.assertEqual(result, reveal_dir)

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_search_depth_limit(self, mock_cwd):
        """Should stop searching after 10 parent levels."""
        # Create deep directory structure (> 10 levels)
        with tempfile.TemporaryDirectory() as tmpdir:
            deep_path = Path(tmpdir)
            for i in range(15):
                deep_path = deep_path / f'level{i}'
                deep_path.mkdir(parents=True, exist_ok=True)

            mock_cwd.return_value = deep_path

            # Should not find anything and fall back to installed
            result = find_reveal_root()

            # Should find installed package, not search all 15 levels
            self.assertIsNotNone(result)

    @patch.dict(os.environ, {}, clear=True)
    @patch('reveal.rules.validation.utils.Path.cwd')
    def test_no_reveal_found(self, mock_cwd):
        """Should return None when no reveal found and dev_only=True."""
        # Mock cwd to temporary directory with no reveal structure
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_cwd.return_value = Path(tmpdir)

            result = find_reveal_root(dev_only=True)

            self.assertIsNone(result)


class TestIsDevCheckout(unittest.TestCase):
    """Tests for is_dev_checkout function."""

    def test_none_reveal_root(self):
        """Should return False for None."""
        result = is_dev_checkout(None)
        self.assertFalse(result)

    def test_dev_checkout_with_pyproject(self):
        """Should return True when pyproject.toml exists in parent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_dir = project_root / 'reveal'
            reveal_dir.mkdir()
            (project_root / 'pyproject.toml').touch()

            result = is_dev_checkout(reveal_dir)

            self.assertTrue(result)

    def test_installed_package_without_pyproject(self):
        """Should return False when no pyproject.toml in parent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate installed package structure (no pyproject.toml)
            site_packages = Path(tmpdir) / 'site-packages'
            reveal_dir = site_packages / 'reveal'
            reveal_dir.mkdir(parents=True)

            result = is_dev_checkout(reveal_dir)

            self.assertFalse(result)

    def test_nested_directory(self):
        """Should check parent directory, not reveal directory itself."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_dir = project_root / 'reveal'
            reveal_dir.mkdir()

            # Put pyproject.toml in parent (project_root), not reveal_dir
            (project_root / 'pyproject.toml').touch()

            result = is_dev_checkout(reveal_dir)

            self.assertTrue(result)

    def test_pyproject_in_wrong_location(self):
        """Should not find pyproject.toml if it's in reveal dir instead of parent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            reveal_dir = project_root / 'reveal'
            reveal_dir.mkdir()

            # Put pyproject.toml in reveal_dir (wrong location)
            (reveal_dir / 'pyproject.toml').touch()

            result = is_dev_checkout(reveal_dir)

            self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
