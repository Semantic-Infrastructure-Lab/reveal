"""V012: Language count accuracy in documentation.

Validates that README.md language count matches actual registered analyzers.
Prevents documentation drift when new languages are added.

Example violation:
    - README.md claims: "38 languages built-in"
    - Actual registered: 40 language extensions
    - Result: Documentation out of sync

How it counts:
    - Counts unique file extension registrations
    - Each @register() call adds to the count
    - Example: yaml_json.py registers 2 (.yaml, .yml counted as 1, .json as 1)

Note: Checks ALL language count claims in README, not just first occurrence.
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V012(BaseRule):
    """Validate README language count matches registered analyzers."""

    code = "V012"
    message = "Language count mismatch in documentation"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check language count accuracy."""
        detections = []

        # Only run for reveal:// URIs
        if not file_path.startswith('reveal://'):
            return detections

        # Find reveal root
        reveal_root = find_reveal_root()
        if not reveal_root:
            return detections

        project_root = reveal_root.parent
        readme_file = project_root / 'README.md'

        if not readme_file.exists():
            return detections

        # Count actual registered languages
        actual_count = self._count_registered_languages()
        if actual_count is None:
            return detections

        # Extract ALL claimed counts from README
        claims = self._extract_language_count_from_readme(readme_file)

        # Flag ALL incorrect claims
        for line_num, claimed in claims:
            if claimed != actual_count:
                detections.append(self.create_detection(
                    file_path="README.md",
                    line=line_num,
                    message=f"Language count mismatch: claims {claimed}, actual {actual_count}",
                    suggestion=f"Update README.md line {line_num} to: '{actual_count} languages built-in'",
                    context=f"Claimed: {claimed}, Actual: {actual_count} registered language analyzers"
                ))

        return detections

    def _count_registered_languages(self) -> Optional[int]:
        """Count actual registered language analyzers.

        Returns count of unique language names (not extensions).
        Example: .yaml and .yml both count as 1 language (YAML).
        """
        try:
            from reveal.registry import get_all_analyzers
            analyzers = get_all_analyzers()

            # Count unique language names (not extensions)
            # get_all_analyzers() returns {ext: {name, icon, ...}}
            # We want unique 'name' values
            unique_languages = set()
            for analyzer_info in analyzers.values():
                if 'name' in analyzer_info:
                    unique_languages.add(analyzer_info['name'])

            return len(unique_languages)
        except Exception:
            return None

    def _extract_language_count_from_readme(self, readme_file: Path) -> List[Tuple[int, int]]:
        """Extract ALL language count claims from README.

        Returns: List of (line_number, count) tuples

        Looks for patterns like:
        - "38 languages built-in"
        - "Built-in (38):"
        - "Zero config. 38 languages"
        """
        try:
            content = readme_file.read_text()
            lines = content.split('\n')

            claims = []
            for i, line in enumerate(lines, 1):
                # Pattern 1: "N languages built-in"
                matches = re.finditer(r'(\d+)\s+languages?\s+built-in', line, re.IGNORECASE)
                for match in matches:
                    claims.append((i, int(match.group(1))))

                # Pattern 2: "Built-in (N):"
                matches = re.finditer(r'Built-in\s*\((\d+)\):', line)
                for match in matches:
                    claims.append((i, int(match.group(1))))

                # Pattern 3: "Zero config. N languages"
                matches = re.finditer(r'Zero config\.\s*(\d+)\s+languages', line, re.IGNORECASE)
                for match in matches:
                    claims.append((i, int(match.group(1))))

            return claims
        except Exception:
            return []
