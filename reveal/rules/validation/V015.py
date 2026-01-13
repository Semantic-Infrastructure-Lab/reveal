"""V015: Rules count accuracy in documentation.

Validates that README.md rules count matches actual registered rules.
Prevents documentation drift when new rules are added.

Example violation:
    - README.md claims: "41 built-in rules"
    - Actual registered: 47 rules
    - Result: Documentation out of sync

How it counts:
    - Counts all rules from reveal.registry.get_all_rules()
    - Excludes non-rule entries (utils, __init__)
    - Example: B001-B005, C901-C905, D001-D002, E501, F001-F005, I001-I004,
               L001-L003, M101-M103, N001-N003, R913, S701, U501-U502, V001-V015
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root


class V015(BaseRule):
    """Validate README rules count matches registered rules."""

    code = "V015"
    message = "Rules count mismatch in documentation"
    category = RulePrefix.V
    severity = Severity.MEDIUM  # Important for releases
    file_patterns = ['*']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check rules count accuracy."""
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

        # Count actual registered rules
        actual_count = self._count_registered_rules()
        if actual_count is None:
            return detections

        # Extract ALL claimed counts from README
        claims = self._extract_rules_count_from_readme(readme_file)

        # Flag ALL incorrect claims
        for line_num, claimed in claims:
            if claimed != actual_count:
                detections.append(self.create_detection(
                    file_path="README.md",
                    line=line_num,
                    message=f"Rules count mismatch: claims {claimed}, actual {actual_count}",
                    suggestion=f"Update README.md line {line_num} to: '{actual_count} built-in rules'",
                    context=f"Claimed: {claimed}, Actual: {actual_count} registered rules"
                ))

        return detections

    def _count_registered_rules(self) -> Optional[int]:
        """Count actual registered rules (excludes utils.py, __init__.py).

        Counts actual rule files in reveal/rules/ directory tree.
        """
        try:
            # Find reveal root
            reveal_root = find_reveal_root()
            if not reveal_root:
                return None

            rules_dir = reveal_root / 'rules'
            if not rules_dir.exists():
                return None

            # Count rule files (exclude utils.py and __init__.py)
            count = 0
            for category_dir in rules_dir.iterdir():
                if not category_dir.is_dir() or category_dir.name.startswith('_'):
                    continue

                for rule_file in category_dir.glob('*.py'):
                    # Skip utils and __init__
                    if rule_file.stem in ('utils', '__init__'):
                        continue
                    # Skip files starting with _
                    if rule_file.stem.startswith('_'):
                        continue

                    count += 1

            return count
        except Exception:
            return None

    def _extract_rules_count_from_readme(self, readme_file: Path) -> List[Tuple[int, int]]:
        """Extract ALL rules count claims from README.

        Returns: List of (line_number, count) tuples

        Looks for patterns like:
        - "41 built-in rules"
        - "**41 built-in rules**"
        - "41 built-in rule" (singular)
        """
        try:
            content = readme_file.read_text()
            lines = content.split('\n')

            claims = []
            for i, line in enumerate(lines, 1):
                # Pattern: "N built-in rules" (with optional bold)
                matches = re.finditer(r'(\d+)\s+built-in\s+rules?', line, re.IGNORECASE)
                for match in matches:
                    claims.append((i, int(match.group(1))))

            return claims
        except Exception:
            return []
