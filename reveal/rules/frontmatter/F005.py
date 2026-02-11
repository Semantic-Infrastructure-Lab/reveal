"""F005: Custom validation failed for front matter field.

Schema-aware rule that runs custom validation checks defined in schema.
Only runs when --validate-schema is used.

Example violation (session schema):
    ---
    session_id: invalid_format     # Must match: word-word-MMDD
    topics: []                # Must have at least 1 topic
    ---

Should be:
    ---
    session_id: garnet-ember-0102
    topics: [reveal]
    ---
"""

from typing import List, Dict, Any, Optional
from ..base import BaseRule, Detection, RulePrefix, Severity
from . import get_validation_schema, safe_eval_validation


class F005(BaseRule):
    """Detect custom validation failures in front matter."""

    code = "F005"
    message = "Custom validation failed for front matter field"
    category = RulePrefix.F
    severity = Severity.MEDIUM  # Schema violation
    file_patterns = ['.md', '.markdown']

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        """Check custom validation rules.

        Args:
            file_path: Path to markdown file
            structure: Parsed structure with 'frontmatter' key
            content: File content

        Returns:
            Detection for each failed validation rule
        """
        detections: List[Dict[str, Any]] = []

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

        # Get custom validation rules from schema
        validation_rules = schema.get('validation_rules', [])

        # Run each validation rule
        for rule in validation_rules:
            field = rule.get('field')
            check = rule.get('check')
            message = rule.get('message', 'Validation failed')

            # Skip if field not in data
            if field not in data:
                continue

            value = data[field]

            # Run validation check
            context = {'value': value}
            if not safe_eval_validation(check, context):
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=message,
                    suggestion=f"Fix value of '{field}' field",
                    context=f"Schema: {schema.get('name', 'unknown')} | Check: {check}"
                ))

        return detections
