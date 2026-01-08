"""V007: Version consistency across project files.

Validates that the version number is consistent across all key files.
Critical for releases - prevents version mismatches that confuse users.

Example violation:
    - pyproject.toml: 0.22.0
    - CHANGELOG.md: [0.21.0] (outdated)
    - Result: Version mismatch detected

Checks:
    - pyproject.toml (source of truth)
    - CHANGELOG.md (must have section for current version)
    - reveal/docs/AGENT_HELP.md (version reference)
    - reveal/docs/AGENT_HELP_FULL.md (version reference)
    - ROADMAP.md (current version reference)
    - README.md (version badge, if present)
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V007(BaseRule):
    """Validate version consistency across project files."""

    code = "V007"
    message = "Version mismatch across project files"
    category = RulePrefix.M  # Maintainability
    severity = Severity.HIGH  # Blocker for releases
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for version consistency."""
        detections = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections

        project_root = reveal_root.parent

        # Get canonical version (source of truth)
        canonical_version = self._get_canonical_version(project_root, detections)
        if not canonical_version:
            return detections

        # Check all project files against canonical version
        self._check_project_files(
            project_root, reveal_root, canonical_version, detections
        )

        return detections

    def _get_canonical_version(
        self, project_root: Path, detections: List[Detection]
    ) -> Optional[str]:
        """Extract canonical version from pyproject.toml."""
        pyproject_file = project_root / 'pyproject.toml'
        if not pyproject_file.exists():
            detections.append(self.create_detection(
                file_path="pyproject.toml",
                line=1,
                message="pyproject.toml not found (source of truth for version)",
                suggestion="Create pyproject.toml with version field"
            ))
            return None

        canonical_version = self._extract_version_from_pyproject(pyproject_file)
        if not canonical_version:
            detections.append(self.create_detection(
                file_path="pyproject.toml",
                line=1,
                message="Could not extract version from pyproject.toml",
                suggestion="Add version = \"X.Y.Z\" to [project] section"
            ))
            return None

        return canonical_version

    def _check_project_files(
        self,
        project_root: Path,
        reveal_root: Path,
        canonical: str,
        detections: List[Detection]
    ) -> None:
        """Check all project files for version consistency."""
        self._check_changelog_version(project_root, canonical, detections)
        self._check_roadmap_version(project_root, canonical, detections)
        self._check_readme_version(project_root, canonical, detections)
        self._check_agent_help_versions(reveal_root, canonical, detections)

    def _check_changelog_version(
        self, project_root: Path, canonical: str, detections: List[Detection]
    ) -> None:
        """Check CHANGELOG.md has section for current version."""
        changelog_file = project_root / 'CHANGELOG.md'
        if not changelog_file.exists():
            return

        changelog_version = self._check_changelog(changelog_file, canonical)
        if not changelog_version:
            detections.append(self.create_detection(
                file_path="CHANGELOG.md",
                line=1,
                message=f"CHANGELOG.md missing section for v{canonical}",
                suggestion=f"Add section: ## [{canonical}] - YYYY-MM-DD",
                context=f"Expected version: {canonical}"
            ))

    def _check_roadmap_version(
        self, project_root: Path, canonical: str, detections: List[Detection]
    ) -> None:
        """Check ROADMAP.md current version matches."""
        roadmap_file = project_root / 'ROADMAP.md'
        if not roadmap_file.exists():
            return

        roadmap_version = self._extract_roadmap_version(roadmap_file)
        if roadmap_version and roadmap_version != canonical:
            detections.append(self.create_detection(
                file_path="ROADMAP.md",
                line=1,
                message=f"ROADMAP.md version mismatch: "
                       f"v{roadmap_version} != v{canonical}",
                suggestion=f"Update '**Current version:** v{roadmap_version}' "
                          f"to '**Current version:** v{canonical}'",
                context=f"Found: v{roadmap_version}, Expected: v{canonical}"
            ))

    def _check_readme_version(
        self, project_root: Path, canonical: str, detections: List[Detection]
    ) -> None:
        """Check README.md version badge (if present)."""
        readme_file = project_root / 'README.md'
        if not readme_file.exists():
            return

        readme_version = self._extract_readme_version(readme_file)
        if readme_version and readme_version != canonical:
            detections.append(self.create_detection(
                file_path="README.md",
                line=1,
                message=f"README.md version badge mismatch: "
                       f"{readme_version} != {canonical}",
                suggestion=f"Update version badge to {canonical}",
                context=f"Found: {readme_version}, Expected: {canonical}"
            ))

    def _check_agent_help_versions(
        self, reveal_root: Path, canonical: str, detections: List[Detection]
    ) -> None:
        """Check AGENT_HELP*.md version references."""
        self._validate_agent_help_file(
            reveal_root, 'AGENT_HELP.md', canonical, detections
        )
        self._validate_agent_help_file(
            reveal_root, 'AGENT_HELP_FULL.md', canonical, detections
        )

    def _validate_agent_help_file(
        self,
        reveal_root: Path,
        filename: str,
        canonical: str,
        detections: List[Detection]
    ) -> None:
        """Validate a single AGENT_HELP*.md file version."""
        # AGENT_HELP files are in reveal/docs/
        file_path = reveal_root / 'docs' / filename
        if not file_path.exists():
            return

        found_version = self._extract_version_from_markdown(file_path)
        if found_version and found_version != canonical:
            detections.append(self.create_detection(
                file_path=f"reveal/docs/{filename}",
                line=1,
                message=f"{filename} version mismatch: "
                       f"{found_version} != {canonical}",
                suggestion=f"Update version reference to {canonical}",
                context=f"Found: {found_version}, Expected: {canonical}"
            ))

    def _extract_version_from_pyproject(self, pyproject_file: Path) -> Optional[str]:
        """Extract version from pyproject.toml."""
        try:
            content = pyproject_file.read_text()
            # Match: version = "X.Y.Z"
            pattern = r'^version\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+)["\']'
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _check_changelog(self, changelog_file: Path, version: str) -> bool:
        """Check if CHANGELOG.md has a section for the given version."""
        try:
            content = changelog_file.read_text()
            # Match: ## [X.Y.Z] - YYYY-MM-DD or ## [X.Y.Z] (unreleased)
            pattern = rf'##\s*\[{re.escape(version)}\]'
            return bool(re.search(pattern, content, re.IGNORECASE))
        except Exception:
            pass
        return False

    def _extract_version_from_markdown(self, md_file: Path) -> Optional[str]:
        """Extract version from markdown file (AGENT_HELP*.md)."""
        try:
            content = md_file.read_text()
            # Match: **Version:** X.Y.Z or Version: X.Y.Z
            match = re.search(r'\*\*Version:\*\*\s*([0-9]+\.[0-9]+\.[0-9]+)', content)
            if not match:
                match = re.search(r'Version:\s*([0-9]+\.[0-9]+\.[0-9]+)', content)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _extract_roadmap_version(self, roadmap_file: Path) -> Optional[str]:
        """Extract version from ROADMAP.md.

        Looks for pattern: **Current version:** vX.Y.Z
        """
        try:
            content = roadmap_file.read_text()
            # Match: **Current version:** v0.27.1 or **Current version:** 0.27.1
            pattern = r'\*\*Current version:\*\*\s*v?([0-9]+\.[0-9]+\.[0-9]+)'
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _extract_readme_version(self, readme_file: Path) -> Optional[str]:
        """Extract version from README.md badges (optional check).

        Only returns a version if a badge pattern is found.
        Common patterns:
        - ![Version](https://img.shields.io/badge/version-vX.Y.Z-blue)
        - [![Version](https://img.shields.io/pypi/v/reveal-cli.svg)]
        """
        try:
            content = readme_file.read_text()
            # Match shield.io badge with version
            match = re.search(r'badge/version-v?([0-9]+\.[0-9]+\.[0-9]+)', content)
            if match:
                return match.group(1)
            # Match PyPI version badge
            match = re.search(r'pypi/v/reveal-cli.*?([0-9]+\.[0-9]+\.[0-9]+)', content)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None
