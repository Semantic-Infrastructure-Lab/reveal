"""V014: PRIORITIES.md version consistency.

Validates that PRIORITIES.md current version matches canonical version (pyproject.toml).
PRIORITIES.md replaced ROADMAP.md as the authoritative roadmap document.

Example violation:
    - pyproject.toml: version = "0.35.0"
    - PRIORITIES.md: **Current Version:** v0.34.0
    - Result: Stale version in planning doc

Checks:
    - internal-docs/planning/PRIORITIES.md (if exists)
    - Looks for pattern: **Current Version:** vX.Y.Z

Note: This is separate from V007 (which checks ROADMAP.md for backward compat).
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V014(BaseRule):
    """Validate PRIORITIES.md current version matches pyproject.toml."""

    code = "V014"
    message = "PRIORITIES.md version mismatch"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check PRIORITIES.md version consistency."""
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
        canonical_version = self._get_canonical_version(project_root)
        if not canonical_version:
            return detections

        # Check PRIORITIES.md (may be in internal-docs/planning/)
        priorities_files = [
            project_root / 'PRIORITIES.md',
            project_root / 'internal-docs' / 'planning' / 'PRIORITIES.md',
        ]

        for priorities_file in priorities_files:
            if priorities_file.exists():
                self._check_priorities_version(
                    priorities_file, canonical_version, project_root, detections
                )

        return detections

    def _get_canonical_version(self, project_root: Path) -> Optional[str]:
        """Extract canonical version from pyproject.toml."""
        pyproject_file = project_root / 'pyproject.toml'
        if not pyproject_file.exists():
            return None

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

    def _check_priorities_version(
        self,
        priorities_file: Path,
        canonical: str,
        project_root: Path,
        detections: List[Detection]
    ) -> None:
        """Check PRIORITIES.md current version matches canonical."""
        priorities_version = self._extract_priorities_version(priorities_file)

        if priorities_version and priorities_version != canonical:
            # Get relative path for cleaner error messages
            try:
                rel_path = priorities_file.relative_to(project_root)
            except ValueError:
                rel_path = priorities_file

            detections.append(self.create_detection(
                file_path=str(rel_path),
                line=1,
                message=f"PRIORITIES.md version mismatch: "
                       f"v{priorities_version} != v{canonical}",
                suggestion=f"Update '**Current Version:** v{priorities_version}' "
                          f"to '**Current Version:** v{canonical}'",
                context=f"Found: v{priorities_version}, Expected: v{canonical}"
            ))

    def _extract_priorities_version(self, priorities_file: Path) -> Optional[str]:
        """Extract version from PRIORITIES.md.

        Looks for pattern: **Current Version:** vX.Y.Z
        """
        try:
            content = priorities_file.read_text()
            # Match: **Current Version:** v0.35.0 or **Current Version:** 0.35.0
            pattern = r'\*\*Current [Vv]ersion:\*\*\s*v?([0-9]+\.[0-9]+\.[0-9]+)'
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        except Exception:
            pass

        return None
