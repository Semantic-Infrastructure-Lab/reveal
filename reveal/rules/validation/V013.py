"""V013: Adapter count accuracy in documentation.

Validates that README.md adapter counts match actual registered URI adapters.
Prevents documentation drift when new adapters are added.

Example violation:
    - README.md claims: "10 adapters"
    - Actual registered: 14 adapters
    - Result: Documentation out of sync

Checks:
    - README.md: ALL numeric claims about adapters
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V013(BaseRule):
    """Validate README adapter count matches registered adapters."""

    code = "V013"
    message = "Adapter count mismatch in documentation"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check adapter count accuracy across documentation files."""
        detections: List[Dict[str, Any]] = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections

        project_root = reveal_root.parent

        # Count actual registered adapters
        actual_count = self._count_registered_adapters()
        if actual_count is None:
            return detections

        # Check README.md claims
        readme_file = project_root / 'README.md'
        if readme_file.exists():
            detections.extend(self._check_readme_adapter_count(readme_file, actual_count, project_root))

        return detections

    def _count_registered_adapters(self) -> Optional[int]:
        """Count actual registered URI adapters.

        Returns count of registered URI schemes (ast://, diff://, etc.).
        """
        try:
            from reveal.adapters.base import list_supported_schemes
            schemes = list_supported_schemes()
            return len(schemes)
        except Exception:
            return None

    def _check_readme_adapter_count(self, readme_file: Path, actual_count: int, project_root: Path) -> List[Detection]:
        """Check all adapter count claims in README.md."""
        detections: List[Dict[str, Any]] = []
        claims = self._extract_adapter_count_from_readme(readme_file)

        for line_num, claimed in claims:
            if claimed != actual_count:
                detections.append(self.create_detection(
                    file_path="README.md",
                    line=line_num,
                    message=f"Adapter count mismatch: claims {claimed}, actual {actual_count}",
                    suggestion=f"Update README.md line {line_num} to: '{actual_count} adapters'",
                    context=f"Claimed: {claimed}, Actual: {actual_count} registered URI adapters"
                ))

        return detections

    def _extract_adapter_count_from_readme(self, readme_file: Path) -> List[Tuple[int, int]]:
        """Extract ALL adapter count claims from README.

        Returns: List of (line_number, count) tuples

        Looks for patterns like:
        - "12 adapters"
        - "(38 languages, 12 adapters)"
        - "**10 Built-in Adapters:**"
        """
        try:
            content = readme_file.read_text()
            lines = content.split('\n')

            claims = []
            for i, line in enumerate(lines, 1):
                # Pattern 1: "N adapters" (case insensitive)
                matches = re.finditer(r'(\d+)\s+adapters?', line, re.IGNORECASE)
                for match in matches:
                    claims.append((i, int(match.group(1))))

                # Pattern 2: "**N Built-in Adapters**"
                matches = re.finditer(r'\*\*(\d+)\s+Built-in\s+Adapters?', line)
                for match in matches:
                    claims.append((i, int(match.group(1))))

            return claims
        except Exception:
            return []
