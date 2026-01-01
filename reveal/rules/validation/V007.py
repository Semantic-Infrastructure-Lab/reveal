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
    - ROADMAP.md (current version reference)
    - README.md (version badge, if present)
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

        # Check ROADMAP.md
        roadmap_file = project_root / 'ROADMAP.md'
        if roadmap_file.exists():
            roadmap_version = self._extract_roadmap_version(roadmap_file)
            if roadmap_version and roadmap_version != canonical_version:
                detections.append(self.create_detection(
                    file_path="ROADMAP.md",
                    line=1,
                    message=f"ROADMAP.md version mismatch: v{roadmap_version} != v{canonical_version}",
                    suggestion=f"Update '**Current version:** v{roadmap_version}' to '**Current version:** v{canonical_version}'",
                    context=f"Found: v{roadmap_version}, Expected: v{canonical_version}"
                ))

        # Check README.md (optional - only if version badge exists)
        readme_file = project_root / 'README.md'
        if readme_file.exists():
            readme_version = self._extract_readme_version(readme_file)
            if readme_version and readme_version != canonical_version:
                detections.append(self.create_detection(
                    file_path="README.md",
                    line=1,
                    message=f"README.md version badge mismatch: {readme_version} != {canonical_version}",
                    suggestion=f"Update version badge to {canonical_version}",
                    context=f"Found: {readme_version}, Expected: {canonical_version}"
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

    def _extract_roadmap_version(self, roadmap_file: Path) -> Optional[str]:
        """Extract version from ROADMAP.md.

        Looks for pattern: **Current version:** vX.Y.Z
        """
        try:
            content = roadmap_file.read_text()
            # Match: **Current version:** v0.27.1 or **Current version:** 0.27.1
            match = re.search(r'\*\*Current version:\*\*\s*v?([0-9]+\.[0-9]+\.[0-9]+)', content)
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

    def _find_reveal_root(self) -> Optional[Path]:
        """Find reveal's root directory.

        Priority:
        1. REVEAL_DEV_ROOT environment variable (explicit override)
        2. Git checkout in CWD or parent directories (prefer development)
        3. Installed package location (fallback)
        """
        import os

        # 1. Explicit override via environment
        env_root = os.getenv('REVEAL_DEV_ROOT')
        if env_root:
            dev_root = Path(env_root)
            if (dev_root / 'analyzers').exists() and (dev_root / 'rules').exists():
                return dev_root

        # 2. Search from CWD for git checkout (prefer development over installed)
        cwd = Path.cwd()
        for _ in range(10):  # Search up to 10 levels
            # Check for reveal git checkout patterns
            reveal_dir = cwd / 'reveal'
            if (reveal_dir / 'analyzers').exists() and (reveal_dir / 'rules').exists():
                # Verify it's a git checkout by checking for pyproject.toml in parent
                if (cwd / 'pyproject.toml').exists():
                    return reveal_dir
            cwd = cwd.parent
            if cwd == cwd.parent:  # Reached root
                break

        # 3. Fallback to installed package location
        installed = Path(__file__).parent.parent.parent
        if (installed / 'analyzers').exists() and (installed / 'rules').exists():
            return installed

        return None
