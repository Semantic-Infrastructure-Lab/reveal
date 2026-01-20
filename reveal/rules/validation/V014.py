"""V014: ROADMAP.md version consistency.

Validates that ROADMAP.md current version matches canonical version (pyproject.toml).

Example violation:
    - pyproject.toml: version = "0.40.0"
    - ROADMAP.md: **Current version**: v0.39.0
    - Result: Stale version in roadmap doc

Checks:
    - ROADMAP.md (if exists)
    - Looks for pattern: **Current version**: vX.Y.Z
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V014(BaseRule):
    """Validate ROADMAP.md current version matches pyproject.toml."""

    code = "V014"
    message = "ROADMAP.md version mismatch"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check ROADMAP.md version consistency."""
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

        # Check ROADMAP.md
        roadmap_file = project_root / 'ROADMAP.md'
        if roadmap_file.exists():
            self._check_roadmap_version(
                roadmap_file, canonical_version, project_root, detections
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

    def _check_roadmap_version(
        self,
        roadmap_file: Path,
        canonical: str,
        project_root: Path,
        detections: List[Detection]
    ) -> None:
        """Check ROADMAP.md current version matches canonical."""
        roadmap_version = self._extract_roadmap_version(roadmap_file)

        if roadmap_version and roadmap_version != canonical:
            # Get relative path for cleaner error messages
            try:
                rel_path = roadmap_file.relative_to(project_root)
            except ValueError:
                rel_path = roadmap_file

            detections.append(self.create_detection(
                file_path=str(rel_path),
                line=1,
                message=f"ROADMAP.md version mismatch: "
                       f"v{roadmap_version} != v{canonical}",
                suggestion=f"Update '**Current version**: v{roadmap_version}' "
                          f"to '**Current version**: v{canonical}'",
                context=f"Found: v{roadmap_version}, Expected: v{canonical}"
            ))

    def _extract_roadmap_version(self, roadmap_file: Path) -> Optional[str]:
        """Extract version from ROADMAP.md.

        Looks for pattern: **Current version**: vX.Y.Z
        """
        try:
            content = roadmap_file.read_text()
            # Match: **Current version**: v0.40.0
            pattern = r'\*\*Current [Vv]ersion\*\*:\s*v?([0-9]+\.[0-9]+\.[0-9]+)'
            match = re.search(pattern, content)
            if match:
                return match.group(1)
        except Exception:
            pass

        return None
