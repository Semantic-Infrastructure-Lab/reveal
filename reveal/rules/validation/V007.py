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
    - reveal/AGENT_HELP.md (version reference)
    - reveal/AGENT_HELP_FULL.md (version reference)
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity


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
        reveal_root = self._find_reveal_root()
        if not reveal_root:
            return detections

        project_root = reveal_root.parent

        # Get canonical version from pyproject.toml
        pyproject_file = project_root / 'pyproject.toml'
        if not pyproject_file.exists():
            detections.append(self.create_detection(
                file_path="pyproject.toml",
                line=1,
                message="pyproject.toml not found (source of truth for version)",
                suggestion="Create pyproject.toml with version field"
            ))
            return detections

        canonical_version = self._extract_version_from_pyproject(pyproject_file)
        if not canonical_version:
            detections.append(self.create_detection(
                file_path="pyproject.toml",
                line=1,
                message="Could not extract version from pyproject.toml",
                suggestion="Add version = \"X.Y.Z\" to [project] section"
            ))
            return detections

        # Check CHANGELOG.md
        changelog_file = project_root / 'CHANGELOG.md'
        if changelog_file.exists():
            changelog_version = self._check_changelog(changelog_file, canonical_version)
            if not changelog_version:
                detections.append(self.create_detection(
                    file_path="CHANGELOG.md",
                    line=1,
                    message=f"CHANGELOG.md missing section for v{canonical_version}",
                    suggestion=f"Add section: ## [{canonical_version}] - YYYY-MM-DD",
                    context=f"Expected version: {canonical_version}"
                ))

        # Check AGENT_HELP.md
        agent_help = reveal_root / 'AGENT_HELP.md'
        if agent_help.exists():
            help_version = self._extract_version_from_markdown(agent_help)
            if help_version and help_version != canonical_version:
                detections.append(self.create_detection(
                    file_path="reveal/AGENT_HELP.md",
                    line=1,
                    message=f"AGENT_HELP.md version mismatch: {help_version} != {canonical_version}",
                    suggestion=f"Update version reference to {canonical_version}",
                    context=f"Found: {help_version}, Expected: {canonical_version}"
                ))

        # Check AGENT_HELP_FULL.md
        agent_help_full = reveal_root / 'AGENT_HELP_FULL.md'
        if agent_help_full.exists():
            help_full_version = self._extract_version_from_markdown(agent_help_full)
            if help_full_version and help_full_version != canonical_version:
                detections.append(self.create_detection(
                    file_path="reveal/AGENT_HELP_FULL.md",
                    line=1,
                    message=f"AGENT_HELP_FULL.md version mismatch: {help_full_version} != {canonical_version}",
                    suggestion=f"Update version reference to {canonical_version}",
                    context=f"Found: {help_full_version}, Expected: {canonical_version}"
                ))

        return detections

    def _extract_version_from_pyproject(self, pyproject_file: Path) -> Optional[str]:
        """Extract version from pyproject.toml."""
        try:
            content = pyproject_file.read_text()
            # Match: version = "X.Y.Z"
            match = re.search(r'^version\s*=\s*["\']([0-9]+\.[0-9]+\.[0-9]+)["\']', content, re.MULTILINE)
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

    def _find_reveal_root(self) -> Optional[Path]:
        """Find reveal's root directory."""
        current = Path(__file__).parent.parent.parent

        if (current / 'analyzers').exists() and (current / 'rules').exists():
            return current

        for _ in range(5):
            if (current / 'reveal' / 'analyzers').exists():
                return current / 'reveal'
            current = current.parent
            if current == current.parent:
                break

        return None
