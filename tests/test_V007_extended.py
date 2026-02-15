"""Extended tests for V007: Version consistency validation.

Comprehensive edge case coverage for V007 rule testing.
"""

import unittest
from pathlib import Path
import tempfile
import shutil
from unittest import mock

from reveal.rules.validation.V007 import V007


class TestV007NoRevealRoot(unittest.TestCase):
    """Test V007 when reveal root cannot be found."""

    def setUp(self):
        self.rule = V007()

    def test_no_reveal_root_returns_empty(self):
        """Test that no detections when reveal root not found."""
        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=None):
            detections = self.rule.check(
                file_path="reveal://test",
                structure=None,
                content=""
            )
            self.assertEqual(len(detections), 0)


class TestV007NotDevCheckout(unittest.TestCase):
    """Test V007 when not a dev checkout."""

    def setUp(self):
        self.rule = V007()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_not_dev_checkout_returns_empty(self):
        """Test that no detections for non-dev checkouts."""
        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V007.is_dev_checkout', return_value=False):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 0)


class TestV007PyprojectHandling(unittest.TestCase):
    """Test V007 pyproject.toml handling."""

    def setUp(self):
        self.rule = V007()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_pyproject_creates_detection(self):
        """Test detection when pyproject.toml doesn't exist."""
        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V007.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 1)
                self.assertIn("pyproject.toml not found", detections[0].message)

    def test_invalid_pyproject_version_creates_detection(self):
        """Test detection when version cannot be extracted."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text("""
[project]
name = "reveal"
# No version field
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V007.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 1)
                self.assertIn("Could not extract version", detections[0].message)

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


class TestV007ChangelogValidation(unittest.TestCase):
    """Test V007 CHANGELOG.md validation."""

    def setUp(self):
        self.rule = V007()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_changelog_no_detection(self):
        """Test no detection when CHANGELOG.md doesn't exist."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text("""
[project]
version = "1.0.0"
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V007.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                # Should only detect missing changelog if it exists but has wrong version
                # If missing entirely, no detection
                self.assertEqual(len(detections), 0)

    def test_changelog_missing_version_creates_detection(self):
        """Test detection when CHANGELOG.md missing current version."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text("""
[project]
version = "1.0.0"
""", encoding='utf-8')

        changelog_file = self.project_root / 'CHANGELOG.md'
        changelog_file.write_text("""
# Changelog

## [0.9.0] - 2024-01-01
- Old version
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V007.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 1)
                self.assertIn("CHANGELOG.md missing section", detections[0].message)
                self.assertIn("1.0.0", detections[0].message)

    def test_changelog_read_exception_handled(self):
        """Test exception handling when reading CHANGELOG.md."""
        changelog_file = self.project_root / 'CHANGELOG.md'
        changelog_file.write_text('## [1.0.0]', encoding='utf-8')
        changelog_file.chmod(0o000)

        try:
            result = self.rule._check_changelog(changelog_file, "1.0.0")
            # Should handle exception gracefully
            self.assertFalse(result)
        finally:
            # Restore permissions for cleanup
            changelog_file.chmod(0o644)


class TestV007ReadmeValidation(unittest.TestCase):
    """Test V007 README.md validation."""

    def setUp(self):
        self.rule = V007()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_readme_no_detection(self):
        """Test no detection when README.md doesn't exist."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text("""
[project]
version = "1.0.0"
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V007.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                # No README.md = no detection
                self.assertEqual(len(detections), 0)

    def test_readme_version_mismatch_creates_detection(self):
        """Test detection when README.md version badge mismatches."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text("""
[project]
version = "1.0.0"
""", encoding='utf-8')

        readme_file = self.project_root / 'README.md'
        readme_file.write_text("""
# Project

![Version](https://img.shields.io/badge/version-v0.9.0-blue)
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V007.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 1)
                self.assertIn("README.md version badge mismatch", detections[0].message)
                self.assertIn("0.9.0", detections[0].message)

    def test_readme_pypi_badge_pattern(self):
        """Test extracting version from PyPI badge pattern."""
        readme_file = self.project_root / 'README.md'
        # PyPI badges need the version in the URL for the regex to match
        readme_file.write_text("""
[![Version](https://img.shields.io/pypi/v/reveal-cli/1.2.3)](https://pypi.org/project/reveal-cli/)
""", encoding='utf-8')

        version = self.rule._extract_readme_version(readme_file)
        # The regex looks for version numbers after pypi/v/
        self.assertEqual(version, "1.2.3")


class TestV007AgentHelpValidation(unittest.TestCase):
    """Test V007 AGENT_HELP*.md validation."""

    def setUp(self):
        self.rule = V007()
        self.tmpdir = tempfile.mkdtemp()
        self.reveal_root = Path(self.tmpdir) / 'reveal'
        self.reveal_root.mkdir()
        self.docs_dir = self.reveal_root / 'docs'
        self.docs_dir.mkdir()
        self.project_root = Path(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_agent_help_version_mismatch_creates_detection(self):
        """Test detection when AGENT_HELP.md version mismatches."""
        pyproject_file = self.project_root / 'pyproject.toml'
        pyproject_file.write_text("""
[project]
version = "1.0.0"
""", encoding='utf-8')

        agent_help_file = self.docs_dir / 'AGENT_HELP.md'
        agent_help_file.write_text("""
# Agent Help

**Version:** 0.9.0
""", encoding='utf-8')

        with mock.patch('reveal.rules.validation.V007.find_reveal_root', return_value=self.reveal_root):
            with mock.patch('reveal.rules.validation.V007.is_dev_checkout', return_value=True):
                detections = self.rule.check(
                    file_path="reveal://test",
                    structure=None,
                    content=""
                )
                self.assertEqual(len(detections), 1)
                self.assertIn("AGENT_HELP.md version mismatch", detections[0].message)
                self.assertIn("0.9.0", detections[0].message)

    def test_agent_help_read_exception_handled(self):
        """Test exception handling when reading AGENT_HELP.md."""
        agent_help_file = self.docs_dir / 'AGENT_HELP.md'
        agent_help_file.write_text('**Version:** 1.0.0', encoding='utf-8')
        agent_help_file.chmod(0o000)

        try:
            version = self.rule._extract_version_from_markdown(agent_help_file)
            # Should handle exception gracefully
            self.assertIsNone(version)
        finally:
            # Restore permissions for cleanup
            agent_help_file.chmod(0o644)


class TestV007VersionExtractionHelpers(unittest.TestCase):
    """Test V007 version extraction helper methods."""

    def setUp(self):
        self.rule = V007()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_extract_version_from_pyproject_success(self):
        """Test successful version extraction from pyproject.toml."""
        pyproject_file = Path(self.tmpdir) / 'pyproject.toml'
        pyproject_file.write_text("""
[project]
name = "reveal"
version = "1.2.3"
""", encoding='utf-8')

        version = self.rule._extract_version_from_pyproject(pyproject_file)
        self.assertEqual(version, "1.2.3")

    def test_extract_version_from_pyproject_single_quotes(self):
        """Test version extraction with single quotes."""
        pyproject_file = Path(self.tmpdir) / 'pyproject.toml'
        pyproject_file.write_text("""
version = '1.2.3'
""", encoding='utf-8')

        version = self.rule._extract_version_from_pyproject(pyproject_file)
        self.assertEqual(version, "1.2.3")

    def test_check_changelog_version_found(self):
        """Test successful changelog version detection."""
        changelog_file = Path(self.tmpdir) / 'CHANGELOG.md'
        changelog_file.write_text("""
## [1.0.0] - 2024-01-01
""", encoding='utf-8')

        result = self.rule._check_changelog(changelog_file, "1.0.0")
        self.assertTrue(result)

    def test_check_changelog_version_not_found(self):
        """Test changelog version not found."""
        changelog_file = Path(self.tmpdir) / 'CHANGELOG.md'
        changelog_file.write_text("""
## [0.9.0] - 2024-01-01
""", encoding='utf-8')

        result = self.rule._check_changelog(changelog_file, "1.0.0")
        self.assertFalse(result)

    def test_extract_version_from_markdown_success(self):
        """Test successful version extraction from markdown."""
        md_file = Path(self.tmpdir) / 'AGENT_HELP.md'
        md_file.write_text("""
**Version:** 1.2.3
""", encoding='utf-8')

        version = self.rule._extract_version_from_markdown(md_file)
        self.assertEqual(version, "1.2.3")

    def test_extract_version_from_markdown_not_found(self):
        """Test markdown version not found."""
        md_file = Path(self.tmpdir) / 'AGENT_HELP.md'
        md_file.write_text("""
Some content without version
""", encoding='utf-8')

        version = self.rule._extract_version_from_markdown(md_file)
        self.assertIsNone(version)

    def test_extract_readme_version_badge_pattern(self):
        """Test README version badge extraction."""
        readme_file = Path(self.tmpdir) / 'README.md'
        readme_file.write_text("""
![Version](https://img.shields.io/badge/version-v1.2.3-blue)
""", encoding='utf-8')

        version = self.rule._extract_readme_version(readme_file)
        self.assertEqual(version, "1.2.3")

    def test_extract_readme_version_no_badge(self):
        """Test README without version badge."""
        readme_file = Path(self.tmpdir) / 'README.md'
        readme_file.write_text("""
# Project

Some content
""", encoding='utf-8')

        version = self.rule._extract_readme_version(readme_file)
        self.assertIsNone(version)


if __name__ == '__main__':
    unittest.main()
