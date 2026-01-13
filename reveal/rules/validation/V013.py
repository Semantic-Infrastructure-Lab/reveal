"""V013: Adapter count accuracy in documentation.

Validates that README.md adapter count matches actual registered URI adapters.
Prevents documentation drift when new adapters are added.

Example violation:
    - README.md claims: "10 adapters"
    - Actual registered: 12 adapters (ast, diff, env, help, imports, json, markdown, mysql, python, reveal, sqlite, stats)
    - Result: Documentation out of sync

Registered adapters:
    - ast:// - AST query adapter
    - diff:// - Structural diff adapter
    - env:// - Environment variables
    - help:// - Help system
    - imports:// - Import analysis
    - json:// - JSON navigation
    - markdown:// - Markdown query
    - mysql:// - MySQL database
    - python:// - Python runtime
    - reveal:// - Self-introspection
    - sqlite:// - SQLite database
    - stats:// - Code statistics
"""

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

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
        """Check adapter count accuracy."""
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

        # Count actual registered adapters
        actual_count = self._count_registered_adapters()
        if actual_count is None:
            return detections

        # Extract claimed count from README
        claimed_count = self._extract_adapter_count_from_readme(readme_file)
        if claimed_count is None:
            return detections

        # Check for mismatch
        if actual_count != claimed_count:
            detections.append(self.create_detection(
                file_path="README.md",
                line=1,
                message=f"Adapter count mismatch: claims {claimed_count}, actual {actual_count}",
                suggestion=f"Update README.md to: '{actual_count} adapters' or verify count logic",
                context=f"Claimed: {claimed_count}, Actual: {actual_count} registered URI adapters"
            ))

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

    def _extract_adapter_count_from_readme(self, readme_file: Path) -> Optional[int]:
        """Extract adapter count claim from README.

        Looks for patterns like:
        - "12 adapters"
        - "(38 languages, 12 adapters)"
        """
        try:
            content = readme_file.read_text()

            # Pattern 1: "N adapters" in quick install comment
            match = re.search(r'(\d+)\s+adapters', content, re.IGNORECASE)
            if match:
                return int(match.group(1))

        except Exception:
            pass

        return None
