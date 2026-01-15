"""Version extraction utilities for validation rules.

Consolidates version extraction logic used across multiple validation rules
(V007, V011, V014) to reduce duplication and improve maintainability.
"""

import re
from pathlib import Path
from typing import Optional


# Regex patterns
SEMVER_PATTERN = r'([0-9]+\.[0-9]+\.[0-9]+)'


def extract_version_from_pyproject(pyproject_file: Path) -> Optional[str]:
    """Extract version from pyproject.toml.

    Args:
        pyproject_file: Path to pyproject.toml

    Returns:
        Version string (e.g. "0.35.0") or None if not found

    Example:
        >>> pyproject = Path("pyproject.toml")
        >>> version = extract_version_from_pyproject(pyproject)
        >>> print(version)  # "0.35.0"
    """
    try:
        content = pyproject_file.read_text()
        # Match: version = "X.Y.Z" in [project] section
        pattern = rf'^version\s*=\s*["\']({SEMVER_PATTERN})["\']'
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def extract_version_from_roadmap(roadmap_file: Path) -> Optional[str]:
    """Extract version from ROADMAP.md.

    Looks for pattern: **Current version:** vX.Y.Z or **Current version:** X.Y.Z

    Args:
        roadmap_file: Path to ROADMAP.md

    Returns:
        Version string (e.g. "0.35.0") or None if not found

    Example:
        >>> roadmap = Path("ROADMAP.md")
        >>> version = extract_version_from_roadmap(roadmap)
        >>> print(version)  # "0.35.0"
    """
    try:
        content = roadmap_file.read_text()
        # Match: **Current version:** v0.27.1 or **Current version:** 0.27.1
        pattern = rf'\*\*Current version:\*\*\s*v?{SEMVER_PATTERN}'
        match = re.search(pattern, content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def extract_version_from_readme(readme_file: Path) -> Optional[str]:
    """Extract version from README.md.

    Looks for first semantic version in file.

    Args:
        readme_file: Path to README.md

    Returns:
        Version string (e.g. "0.35.0") or None if not found
    """
    try:
        content = readme_file.read_text()
        # Find first semver pattern
        match = re.search(SEMVER_PATTERN, content)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def extract_version_from_markdown(markdown_file: Path, pattern: Optional[str] = None) -> Optional[str]:
    """Extract version from any markdown file using custom or default pattern.

    Args:
        markdown_file: Path to markdown file
        pattern: Optional regex pattern to find version (must have capture group for version)
                If None, uses default SEMVER_PATTERN

    Returns:
        Version string or None if not found

    Example:
        >>> priorities = Path("PRIORITIES.md")
        >>> # Extract from "## Reveal v0.35.0 Release"
        >>> version = extract_version_from_markdown(priorities, r'## Reveal v' + SEMVER_PATTERN)
        >>> print(version)  # "0.35.0"
    """
    try:
        content = markdown_file.read_text()
        search_pattern = pattern if pattern else SEMVER_PATTERN
        match = re.search(search_pattern, content)
        if match:
            # Return first capture group
            return match.group(1)
    except Exception:
        pass
    return None


def extract_changelog_version_line(changelog_file: Path, version: str) -> Optional[int]:
    """Find line number of changelog entry for given version.

    Args:
        changelog_file: Path to CHANGELOG.md
        version: Version to find (e.g. "0.35.0")

    Returns:
        Line number (1-indexed) of changelog entry, or None if not found

    Example:
        >>> changelog = Path("CHANGELOG.md")
        >>> line = extract_changelog_version_line(changelog, "0.35.0")
        >>> print(f"Version 0.35.0 documented at line {line}")
    """
    try:
        content = changelog_file.read_text()
        # Match: ## [0.35.0] or ## [v0.35.0]
        pattern = rf'##\s*\[v?{re.escape(version)}\]'

        for i, line in enumerate(content.split('\n'), 1):
            if re.search(pattern, line):
                return i
    except Exception:
        pass
    return None


def check_version_in_changelog(changelog_file: Path, version: str) -> bool:
    """Check if version has entry in changelog.

    Args:
        changelog_file: Path to CHANGELOG.md
        version: Version to check

    Returns:
        True if version found in changelog, False otherwise

    Example:
        >>> changelog = Path("CHANGELOG.md")
        >>> if check_version_in_changelog(changelog, "0.35.0"):
        ...     print("Version documented")
    """
    return extract_changelog_version_line(changelog_file, version) is not None
