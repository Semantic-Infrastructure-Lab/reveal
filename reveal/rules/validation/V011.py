"""V011: Release readiness validation.

Pre-release checklist to ensure documentation is ready for release.
Run before executing ./scripts/release.sh

Example violation:
    - Version: 0.28.0 (from pyproject.toml)
    - CHANGELOG.md has [0.28.0] section ✅
    - CHANGELOG.md has date (not Unreleased) ✅
    - ROADMAP.md mentions 0.28.0 in "What We've Shipped" ❌
    - Result: Not ready for release
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V011(BaseRule):
    """Validate release readiness checklist."""

    code = "V011"
    message = "Not ready for release"
    category = RulePrefix.M  # Maintainability
    severity = Severity.HIGH  # Blocker for releases
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check release readiness."""
        detections = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections

        project_root = reveal_root.parent

        # Get canonical version from pyproject.toml
        pyproject_file = project_root / 'pyproject.toml'
        if not pyproject_file.exists():
            return detections

        canonical_version = self._extract_version_from_pyproject(pyproject_file)
        if not canonical_version:
            return detections

        # Check 1: CHANGELOG.md has dated entry (not Unreleased)
        changelog_file = project_root / 'CHANGELOG.md'
        if changelog_file.exists():
            if not self._changelog_has_dated_entry(changelog_file, canonical_version):
                detections.append(self.create_detection(
                    file_path="CHANGELOG.md",
                    line=1,
                    message=f"CHANGELOG.md [{canonical_version}] section missing date or marked Unreleased",
                    suggestion=f"Update section to: ## [{canonical_version}] - YYYY-MM-DD",
                    context=f"Version: {canonical_version}"
                ))

        # Check 2: ROADMAP.md mentions version in "What We've Shipped"
        roadmap_file = project_root / 'ROADMAP.md'
        if roadmap_file.exists():
            if not self._roadmap_has_shipped_section(roadmap_file, canonical_version):
                detections.append(self.create_detection(
                    file_path="ROADMAP.md",
                    line=1,
                    message=f"ROADMAP.md doesn't mention v{canonical_version} in 'What We've Shipped'",
                    suggestion=f"Add v{canonical_version} section to 'What We've Shipped'",
                    context=f"Version: {canonical_version}"
                ))

        # Check 3: ROADMAP.md current version is set correctly
        if roadmap_file.exists():
            roadmap_version = self._extract_roadmap_version(roadmap_file)
            if roadmap_version and roadmap_version != canonical_version:
                detections.append(self.create_detection(
                    file_path="ROADMAP.md",
                    line=1,
                    message=f"ROADMAP.md '**Current version:**' not updated (v{roadmap_version} != v{canonical_version})",
                    suggestion=f"Update to: **Current version:** v{canonical_version}",
                    context=f"Found: v{roadmap_version}, Expected: v{canonical_version}"
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

    def _changelog_has_dated_entry(self, changelog_file: Path, version: str) -> bool:
        """Check if CHANGELOG.md has a dated entry for the given version.

        Returns False if:
        - No section for version
        - Section exists but marked as "Unreleased"
        - Section exists but has no date

        Returns True if:
        - Section exists with a date: ## [X.Y.Z] - YYYY-MM-DD
        """
        try:
            content = changelog_file.read_text()

            # Match: ## [X.Y.Z] - YYYY-MM-DD
            # Must have a date, not "Unreleased"
            pattern = rf'##\s*\[{re.escape(version)}\]\s*-\s*(\d{{4}}-\d{{2}}-\d{{2}})'
            match = re.search(pattern, content)

            if match:
                return True

            # Check if it exists but without date
            pattern_no_date = rf'##\s*\[{re.escape(version)}\]'
            if re.search(pattern_no_date, content):
                # Section exists but no date - not ready
                return False

            # Section doesn't exist at all - not ready
            return False

        except Exception:
            pass
        return False

    def _roadmap_has_shipped_section(self, roadmap_file: Path, version: str) -> bool:
        """Check if ROADMAP.md mentions version in 'What We've Shipped' section.

        Looks for:
        1. "What We've Shipped" heading
        2. Within that section, a heading with the version number
        """
        try:
            content = roadmap_file.read_text()

            # Find "What We've Shipped" section
            shipped_match = re.search(r'##\s*What We\'ve Shipped', content, re.IGNORECASE)
            if not shipped_match:
                return False

            # Get content after "What We've Shipped"
            shipped_start = shipped_match.end()

            # Find next top-level heading (## or #) to delimit section
            next_section = re.search(r'\n##?\s+', content[shipped_start:])
            if next_section:
                shipped_end = shipped_start + next_section.start()
                shipped_section = content[shipped_start:shipped_end]
            else:
                # No next section, use rest of document
                shipped_section = content[shipped_start:]

            # Check if version appears in shipped section
            # Look for: ### v0.28.0 or ### v0.28.0 - Title
            version_pattern = rf'###\s*v?{re.escape(version)}'
            if re.search(version_pattern, shipped_section):
                return True

            return False

        except Exception:
            pass
        return False

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
