"""F001: Missing front matter in markdown file.

Detects markdown files that lack YAML front matter.
Only applies to markdown files (.md, .markdown).

Example violation:
    # My Document

    Content here...

Should be:
    ---
    title: My Document
    ---

    Content here...
"""

from typing import List, Dict, Any, Optional
from ..base import BaseRule, Detection, RulePrefix, Severity


class F001(BaseRule):
    """Detect missing YAML front matter in markdown files."""

    code = "F001"
    message = "Markdown file missing front matter"
    category = RulePrefix.M  # Maintainability
    severity = Severity.LOW  # Not critical, but good practice
    file_patterns = ['.md', '.markdown']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check if markdown file has front matter.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure with 'frontmatter' key if --frontmatter enabled
            content: File content

        Returns:
            Detection if no front matter found, empty list otherwise
        """
        detections = []

        # If structure is None, can't check (no markdown analysis done)
        if structure is None:
            return detections

        # Check if frontmatter key exists and is None
        # (None means markdown analyzer found no front matter)
        frontmatter = structure.get('frontmatter')

        if frontmatter is None:
            detections.append(self.create_detection(
                file_path=file_path,
                line=1,
                message=self.message,
                suggestion="Add YAML front matter at the start of the file:\n"
                          "---\n"
                          "title: Document Title\n"
                          "---"
            ))

        return detections
