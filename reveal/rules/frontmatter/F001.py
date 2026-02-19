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
    category = RulePrefix.F
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
        detections: List[Detection] = []

        # Skip empty content - no meaningful signal
        if not content:
            return detections

        # Check raw content directly - front matter starts with '---\n'
        # This is more reliable than structure-based detection which requires
        # the analyzer to be called with extract_frontmatter=True
        has_frontmatter = content.startswith('---\n') or content.startswith('---\r\n')

        if not has_frontmatter:
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
