"""Extended tests for V011: Release readiness validation.

Comprehensive edge case coverage for V011 rule testing.
"""

import sys
import unittest
from pathlib import Path
import tempfile
import shutil
from unittest import mock
import pytest

from reveal.rules.validation.V011 import V011


class TestV011NoRevealRoot(unittest.TestCase):
    """Test V011 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V011()

    def test_no_reveal_root_returns_empty(self):
        """Test that no detections when reveal root not found."""
        with mock.patch('reveal.rules.validation.V011.find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV011NotDevCheckout(unittest.TestCase):
    """Test V011 when not a dev checkout."""

    def setUp(self):
        self.rule = V011()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_not_dev_checkout_returns_empty(self):
        """Test that no detections for non-dev checkouts."""
        with mock.patch('reveal.rules.validation.V011.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V011.is_dev_checkout', return_value=False):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 0)


class TestV011PyprojectHandling(unittest.TestCase):
    """Test V011 pyproject.toml handling."""

    def setUp(self):
        self.rule = V011()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_pyproject_returns_empty(self):
        """Test that no detections when pyproject.toml missing."""
        with mock.patch('reveal.rules.validation.V011.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V011.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                # No version = no checks = no detections
                self.assertEqual(len(detections), 0)

    def test_pyproject_exists_no_version_returns_empty(self):
        """Test no detections when pyproject.toml has no version."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text('[project]\nname = "reveal"\n', encoding='utf-8')

        with mock.patch('reveal.rules.validation.V011.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V011.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                # No version extractable = no checks
                self.assertEqual(len(detections), 0)

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod does not restrict access on Windows")
    def test_pyproject_read_exception_handled(self):
        """Test exception handling when reading pyproject.toml."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text('version = "1.0.0"', encoding='utf-8')
        pyproject_file.chmod(0o000)

        try:
            version = self.rule._extract_version_from_pyproject(pyproject_file)
            # Should handle exception gracefully
            self.assertIsNone(version)
        finally:
            # Restore permissions for cleanup
            pyproject_file.chmod(0o644)


class TestV011ChangelogValidation(unittest.TestCase):
    """Test V011 CHANGELOG.md validation."""

    def setUp(self):
        self.rule = V011()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_changelog_no_detection(self):
        """Test no detection when CHANGELOG.md doesn't exist."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text('version = "1.0.0"', encoding='utf-8')

        with mock.patch('reveal.rules.validation.V011.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V011.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                # No CHANGELOG.md = no detection (optional check)
                self.assertEqual(len(detections), 0)

    def test_changelog_missing_dated_entry_creates_detection(self):
        """Test detection when CHANGELOG.md missing dated entry."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text('version = "1.0.0"', encoding='utf-8')

        changelog_file = self.project_root / 'CHANGELOG.md'
        changelog_file.write_text("""
# Changelog

## [1.0.0] (Unreleased)
- New feature
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V011.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V011.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 1)
                self.assertIn("CHANGELOG.md", detections[0].message)
                self.assertIn("missing date", detections[0].message)

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod does not restrict access on Windows")
    def test_changelog_read_exception_handled(self):
        """Test exception handling when reading CHANGELOG.md."""
        changelog_file = self.project_root / 'CHANGELOG.md'
        changelog_file.write_text('## [1.0.0] - 2024-01-01', encoding='utf-8')
        changelog_file.chmod(0o000)

        try:
            result = self.rule._changelog_has_dated_entry(changelog_file, "1.0.0")
            # Should handle exception gracefully
            self.assertFalse(result)
        finally:
            # Restore permissions for cleanup
            changelog_file.chmod(0o644)

    def test_changelog_section_exists_but_no_date(self):
        """Test detection when section exists without date."""
        changelog_file = self.project_root / 'CHANGELOG.md'
        changelog_file.write_text("""
## [1.0.0]
- Changes
""", encoding='utf-8')

        result = self.rule._changelog_has_dated_entry(changelog_file, "1.0.0")
        self.assertFalse(result)


class TestV011RoadmapValidation(unittest.TestCase):
    """Test V011 ROADMAP.md validation."""

    def setUp(self):
        self.rule = V011()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_roadmap_no_detection(self):
        """Test no detection when ROADMAP.md doesn't exist."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text('version = "1.0.0"', encoding='utf-8')

        with mock.patch('reveal.rules.validation.V011.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V011.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                # No ROADMAP.md = no detection (optional check)
                self.assertEqual(len(detections), 0)

    def test_roadmap_missing_shipped_section_creates_detection(self):
        """Test detection when ROADMAP.md missing version in shipped section."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text('version = "1.0.0"', encoding='utf-8')

        roadmap_file = self.project_root / 'ROADMAP.md'
        roadmap_file.write_text("""
# Roadmap

## What We've Shipped

### v0.9.0
- Old version
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V011.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V011.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 1)
                self.assertIn("ROADMAP.md", detections[0].message)
                self.assertIn("What We've Shipped", detections[0].message)

    def test_roadmap_no_shipped_section_creates_detection(self):
        """Test detection when ROADMAP.md has no 'What We've Shipped' section."""
        roadmap_file = self.project_root / 'ROADMAP.md'
        roadmap_file.write_text("""
# Roadmap

## Future Plans
- Something
""", encoding='utf-8')

        result = self.rule._roadmap_has_shipped_section(roadmap_file, "1.0.0")
        self.assertFalse(result)

    @pytest.mark.skipif(sys.platform == 'win32', reason="chmod does not restrict access on Windows")
    def test_roadmap_read_exception_handled(self):
        """Test exception handling when reading ROADMAP.md."""
        roadmap_file = self.project_root / 'ROADMAP.md'
        roadmap_file.write_text("## What We've Shipped\n### v1.0.0", encoding='utf-8')
        roadmap_file.chmod(0o000)

        try:
            result = self.rule._roadmap_has_shipped_section(roadmap_file, "1.0.0")
            # Should handle exception gracefully
            self.assertFalse(result)
        finally:
            # Restore permissions for cleanup
            roadmap_file.chmod(0o644)


class TestV011VersionExtractionHelpers(unittest.TestCase):
    """Test V011 version extraction helper methods."""

    def setUp(self):
        self.rule = V011()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_extract_version_from_pyproject_success(self):
        """Test successful version extraction."""
        pyproject_file = Path(self.tmpdir) / 'pyproject.toml'
        pyproject_file.write_text("""
[project]
version = "1.2.3"
""", encoding='utf-8')

        version = self.rule._extract_version_from_pyproject(pyproject_file)
        self.assertEqual(version, "1.2.3")

    def test_changelog_has_dated_entry_success(self):
        """Test successful dated entry detection."""
        changelog_file = Path(self.tmpdir) / 'CHANGELOG.md'
        changelog_file.write_text("""
## [1.0.0] - 2024-01-01
""", encoding='utf-8')

        result = self.rule._changelog_has_dated_entry(changelog_file, "1.0.0")
        self.assertTrue(result)

    def test_roadmap_has_shipped_section_success(self):
        """Test successful shipped section detection."""
        roadmap_file = Path(self.tmpdir) / 'ROADMAP.md'
        roadmap_file.write_text("""
## What We've Shipped

### v1.0.0 - Cool Feature
""", encoding='utf-8')

        result = self.rule._roadmap_has_shipped_section(roadmap_file, "1.0.0")
        self.assertTrue(result)

    def test_roadmap_version_without_v_prefix(self):
        """Test roadmap version detection without v prefix."""
        roadmap_file = Path(self.tmpdir) / 'ROADMAP.md'
        roadmap_file.write_text("""
## What We've Shipped

### 1.0.0
""", encoding='utf-8')

        result = self.rule._roadmap_has_shipped_section(roadmap_file, "1.0.0")
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
