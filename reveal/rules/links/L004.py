"""L004: Documentation index validator.

Checks that documentation directories have a proper index file (README.md).
This helps users and AI agents find documentation entry points.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class L004(BaseRule):
    """Validate documentation directories have index files."""

    code = "L004"
    message = "Documentation directory missing index"
    category = RulePrefix.L
    severity = Severity.LOW
    file_patterns = ['.md', '.markdown']
    version = "1.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check if documentation directory has an index/README file.

        This rule only triggers when checking directories or files within
        documentation directories.

        Args:
            file_path: Path to file being checked
            structure: Not used for this rule
            content: Not used for this rule

        Returns:
            List of detections if index is missing
        """
        detections: List[Dict[str, Any]] = []
        path = Path(file_path)

        # Check if this is in a docs/ directory
        if 'docs' not in path.parts:
            return detections

        # Find the docs directory
        docs_dir = None
        for i, part in enumerate(path.parts):
            if part == 'docs':
                docs_dir = Path(*path.parts[:i+1])
                break

        if not docs_dir or not docs_dir.exists():
            return detections

        # Check for README.md or INDEX.md
        readme = docs_dir / "README.md"
        index = docs_dir / "INDEX.md"

        if not (readme.exists() or index.exists()):
            # Only report once per directory (use a marker file)
            # To avoid duplicate reports for every file in docs/
            if path.name == sorted(docs_dir.glob("*.md"))[0].name:
                detections.append(Detection(
                    rule_code=self.code,
                    message=self.message,
                    severity=self.severity,
                    file_path=str(docs_dir),
                    line=1,
                    column=1,
                    context=f"Documentation directory has no index: {docs_dir}",
                    suggestion=(
                        f"Create {docs_dir}/README.md with:\n"
                        "  - Navigation by role (users, developers, AI agents)\n"
                        "  - Description of each guide\n"
                        "  - Recommended reading order\n"
                        "  - Quick reference links\n\n"
                        "Benefits:\n"
                        "  - Users can find relevant docs faster\n"
                        "  - AI agents know where to start\n"
                        "  - Clear entry point for documentation\n\n"
                        "Example structure:\n"
                        "  # Documentation Index\n"
                        "  ## For Users\n"
                        "  - [Getting Started](./GETTING_STARTED.md)\n"
                        "  ## For Developers\n"
                        "  - [Contributing](./CONTRIBUTING.md)"
                    )
                ))

        return detections
