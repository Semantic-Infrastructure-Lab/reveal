"""F004: Field type mismatch in front matter.

Schema-aware rule that validates field types match schema expectations.
Only runs when --validate-schema is used.

Example violation (session schema):
    ---
    session_id: garnet-ember-0102
    topics: "single-topic"    # Should be list, not string
    ---

Should be:
    ---
    session_id: garnet-ember-0102
    topics: [single-topic]
    ---
"""

from typing import List, Dict, Any, Optional
from ..base import BaseRule, Detection, RulePrefix, Severity
from . import get_validation_schema, validate_type


class F004(BaseRule):
    """Detect field type mismatches in front matter."""

    code = "F004"
    message = "Field type mismatch in front matter"
    category = RulePrefix.F
    severity = Severity.MEDIUM  # Schema violation
    file_patterns = ['.md', '.markdown']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check for field type mismatches.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure with 'frontmatter' key
            content: File content

        Returns:
            Detection for each type mismatch
        """
        detections: List[Detection] = []

        # Get validation schema
        schema = get_validation_schema()
        if not schema:
            return detections

        # Need structure with frontmatter
        if structure is None:
            return detections

        frontmatter = structure.get('frontmatter')
        if frontmatter is None:
            return detections

        # Get front matter data
        data = frontmatter.get('data', {})
        line = frontmatter.get('line_start', 1)

        # Get field types from schema
        field_types = schema.get('field_types', {})

        # Check each field that has a type constraint
        for field, expected_type in field_types.items():
            if field in data:
                value = data[field]

                # Validate type
                if not validate_type(value, expected_type):
                    # Get actual type name
                    actual_type = type(value).__name__
                    if actual_type == 'bool':
                        actual_type = 'boolean'
                    elif actual_type == 'int':
                        actual_type = 'integer'
                    elif actual_type == 'str':
                        actual_type = 'string'

                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=line,
                        message=f"Field '{field}' has wrong type "
                               f"(expected {expected_type}, got {actual_type})",
                        suggestion=f"Change '{field}' to {expected_type}",
                        context=f"Schema: {schema.get('name', 'unknown')}"
                    ))

        return detections
