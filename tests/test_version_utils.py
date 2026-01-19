"""Tests for version extraction utilities.

Tests reveal.rules.validation.version_utils module which provides
version extraction from various project files.
"""

import pytest
import tempfile
from pathlib import Path

from reveal.rules.validation.version_utils import (
    extract_version_from_pyproject,
    extract_version_from_roadmap,
    extract_version_from_readme,
    extract_version_from_markdown,
    extract_changelog_version_line,
    check_version_in_changelog,
    SEMVER_PATTERN,
)


class TestExtractVersionFromPyproject:
    """Tests for extract_version_from_pyproject."""

    def test_extracts_version_from_standard_pyproject(self):
        """Extract version from standard pyproject.toml format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('''[project]
name = "my-package"
version = "1.2.3"
description = "A test package"
''')
            f.flush()

            version = extract_version_from_pyproject(Path(f.name))
            assert version == "1.2.3"

    def test_extracts_version_with_single_quotes(self):
        """Extract version with single quotes."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('''[project]
version = '0.39.0'
''')
            f.flush()

            version = extract_version_from_pyproject(Path(f.name))
            assert version == "0.39.0"

    def test_returns_none_for_missing_version(self):
        """Return None when version not found."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('''[project]
name = "no-version"
''')
            f.flush()

            version = extract_version_from_pyproject(Path(f.name))
            assert version is None

    def test_returns_none_for_nonexistent_file(self):
        """Return None for nonexistent file."""
        version = extract_version_from_pyproject(Path("/nonexistent/pyproject.toml"))
        assert version is None

    def test_handles_dynamic_version(self):
        """Handle pyproject with dynamic version (returns None)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('''[project]
name = "dynamic-version"
dynamic = ["version"]
''')
            f.flush()

            version = extract_version_from_pyproject(Path(f.name))
            assert version is None


class TestExtractVersionFromRoadmap:
    """Tests for extract_version_from_roadmap."""

    def test_extracts_version_with_v_prefix(self):
        """Extract version with 'v' prefix."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Project Roadmap

**Current version:** v0.35.0

## Next Release
- Feature A
''')
            f.flush()

            version = extract_version_from_roadmap(Path(f.name))
            assert version == "0.35.0"

    def test_extracts_version_without_v_prefix(self):
        """Extract version without 'v' prefix."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Roadmap

**Current version:** 1.0.0
''')
            f.flush()

            version = extract_version_from_roadmap(Path(f.name))
            assert version == "1.0.0"

    def test_returns_none_for_missing_pattern(self):
        """Return None when pattern not found."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Roadmap

No version info here.
''')
            f.flush()

            version = extract_version_from_roadmap(Path(f.name))
            assert version is None


class TestExtractVersionFromReadme:
    """Tests for extract_version_from_readme."""

    def test_extracts_first_semver(self):
        """Extract first semantic version found."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# My Project

Current version: 2.1.0

Previous version was 2.0.0.
''')
            f.flush()

            version = extract_version_from_readme(Path(f.name))
            assert version == "2.1.0"

    def test_extracts_version_from_badge(self):
        """Extract version from badge URL."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Project

![Version](https://img.shields.io/badge/version-3.0.0-blue)
''')
            f.flush()

            version = extract_version_from_readme(Path(f.name))
            assert version == "3.0.0"


class TestExtractVersionFromMarkdown:
    """Tests for extract_version_from_markdown."""

    def test_extracts_with_default_pattern(self):
        """Extract using default semver pattern."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("Version 1.2.3 is the latest.")
            f.flush()

            version = extract_version_from_markdown(Path(f.name))
            assert version == "1.2.3"

    def test_extracts_with_custom_pattern(self):
        """Extract using custom pattern."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Priorities

## Reveal v0.35.0 Release
- Feature A
''')
            f.flush()

            pattern = r'## Reveal v(' + SEMVER_PATTERN + ')'
            version = extract_version_from_markdown(Path(f.name), pattern)
            assert version == "0.35.0"


class TestExtractChangelogVersionLine:
    """Tests for extract_changelog_version_line."""

    def test_finds_version_line_number(self):
        """Find line number of changelog version entry."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            # Write line by line for predictable line numbers
            f.write("# Changelog\n")           # line 1
            f.write("\n")                       # line 2
            f.write("## [0.39.0] - 2026-01-19\n")  # line 3
            f.write("\n")                       # line 4
            f.write("### Added\n")              # line 5
            f.write("- New feature\n")          # line 6
            f.write("\n")                       # line 7
            f.write("## [0.38.0] - 2026-01-18\n")  # line 8
            f.write("\n")                       # line 9
            f.write("### Fixed\n")              # line 10
            f.write("- Bug fix\n")              # line 11
            f.flush()

            line = extract_changelog_version_line(Path(f.name), "0.39.0")
            assert line == 3  # ## [0.39.0] is on line 3

            line = extract_changelog_version_line(Path(f.name), "0.38.0")
            assert line == 8  # ## [0.38.0] is on line 8

    def test_finds_version_with_v_prefix(self):
        """Find version entry with v prefix."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Changelog

## [v1.0.0] - 2026-01-01
''')
            f.flush()

            line = extract_changelog_version_line(Path(f.name), "1.0.0")
            assert line == 3

    def test_returns_none_for_missing_version(self):
        """Return None when version not in changelog."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Changelog

## [0.1.0] - 2025-01-01
''')
            f.flush()

            line = extract_changelog_version_line(Path(f.name), "9.9.9")
            assert line is None


class TestCheckVersionInChangelog:
    """Tests for check_version_in_changelog."""

    def test_returns_true_when_found(self):
        """Return True when version exists in changelog."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Changelog

## [1.0.0] - 2026-01-01
- Release
''')
            f.flush()

            assert check_version_in_changelog(Path(f.name), "1.0.0") is True

    def test_returns_false_when_not_found(self):
        """Return False when version not in changelog."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('''# Changelog

## [1.0.0] - 2026-01-01
''')
            f.flush()

            assert check_version_in_changelog(Path(f.name), "2.0.0") is False


class TestSemverPattern:
    """Tests for SEMVER_PATTERN constant."""

    def test_pattern_matches_standard_semver(self):
        """Pattern matches standard X.Y.Z versions."""
        import re
        assert re.search(SEMVER_PATTERN, "1.2.3")
        assert re.search(SEMVER_PATTERN, "0.0.1")
        assert re.search(SEMVER_PATTERN, "10.20.30")

    def test_pattern_captures_version(self):
        """Pattern captures version in group 1."""
        import re
        match = re.search(SEMVER_PATTERN, "version 1.2.3 released")
        assert match.group(1) == "1.2.3"
