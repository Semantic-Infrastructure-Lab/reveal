"""F003: Required field missing from front matter.

Schema-aware rule that validates required fields are present.
Only runs when --validate-schema is used.

Example violation (session schema):
    ---
    type: session
    ---

    Missing required field: session_id

Should be:
    ---
    session_id: garnet-ember-0102
    topics: [reveal, schema-validation]
    type: session
    ---
"""

from typing import List, Dict, Any, Optional
from ..base import BaseRule, Detection, RulePrefix, Severity
from . import get_validation_schema


class F003(BaseRule):
    """Detect required fields missing from front matter."""

    code = "F003"
    message = "Required field missing from front matter"
    category = RulePrefix.M  # Maintainability
    severity = Severity.MEDIUM  # Schema violation
    file_patterns = ['.md', '.markdown']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for missing required fields.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure with 'frontmatter' key
            content: File content

        Returns:
            Detection for each missing required field
        """
        detections = []

        # Get validation schema (set by CLI handler)
        schema = get_validation_schema()
        if not schema:
            # No schema context, skip validation
            return detections

        # Need structure with frontmatter
        if structure is None:
            return detections

        frontmatter = structure.get('frontmatter')
        if frontmatter is None:
            # No front matter - F001 will handle this
            return detections

        # Get front matter data
        data = frontmatter.get('data', {})
        line = frontmatter.get('line_start', 1)

        # Get required fields from schema
        required_fields = schema.get('required_fields', [])

        # Check each required field
        for field in required_fields:
            if field not in data:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=f"Required field '{field}' missing from front matter",
                    suggestion=f"Add '{field}' to front matter",
                    context=f"Schema: {schema.get('name', 'unknown')}"
                ))

        return detections
