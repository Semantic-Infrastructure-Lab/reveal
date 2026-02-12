"""F002: Empty front matter in markdown file.

Detects markdown files with front matter that contains no fields.
Only applies to markdown files (.md, .markdown).

Example violation:
    ---
    ---

    Content here...

Should have fields:
    ---
    title: My Document
    type: article
    ---

    Content here...
"""

from typing import List, Dict, Any, Optional
from ..base import BaseRule, Detection, RulePrefix, Severity


class F002(BaseRule):
    """Detect empty YAML front matter in markdown files."""

    code = "F002"
    message = "Front matter is empty (no fields)"
    category = RulePrefix.F
    severity = Severity.LOW  # Not critical, but suspicious
    file_patterns = ['.md', '.markdown']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check if front matter has any fields.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure with 'frontmatter' key if --frontmatter enabled
            content: File content

        Returns:
            Detection if front matter is empty, empty list otherwise
        """
        detections: List[Detection] = []

        # If structure is None, can't check
        if structure is None:
            return detections

        frontmatter = structure.get('frontmatter')

        # Only check if frontmatter exists (not None)
        if frontmatter is not None:
            # Frontmatter structure has 'data' field with actual metadata
            data = frontmatter.get('data', {})

            if not data or len(data) == 0:
                line = frontmatter.get('line_start', 1)
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=self.message,
                    suggestion="Add metadata fields to front matter (title, type, tags, etc.)"
                ))

        return detections
