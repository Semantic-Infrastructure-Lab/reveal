"""B003: @property with complex body detector.

Detects @property methods that are too complex. Properties should be simple
getters - if they have significant logic, they should be regular methods.
"""

import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class B003(BaseRule):
    """Detect @property methods with overly complex bodies."""

    code = "B003"
    message = "@property is too complex - properties should be simple getters"
    category = RulePrefix.B
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.0.0"

    # Properties over this line count are flagged
    MAX_PROPERTY_LINES = 8

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for @property methods that are too long/complex.

        Properties should be simple attribute accessors. Complex logic belongs
        in regular methods.

        Args:
            file_path: Path to Python file
            structure: Parsed structure with functions and decorators
            content: File content

        Returns:
            List of detections
        """
        detections = []

        if not structure:
            return detections

        # Check all functions
        for func in structure.get('functions', []):
            decorators = func.get('decorators', [])
            name = func.get('name', '')
            line = func.get('line', 0)
            line_count = func.get('line_count', 0)

            # Check if it's a property (but not cached_property)
            # cached_property is OK to be complex since it's computed once and cached
            is_property = any(
                d == '@property' or
                (d.startswith('@property') and 'cached' not in d) or
                d.endswith('.getter')
                for d in decorators
            )

            # Exclude cached_property - it's OK to be complex
            is_cached = any(
                '@cached_property' in d
                for d in decorators
            )

            if is_cached:
                continue

            if not is_property:
                continue

            # Check if property is too complex (too many lines)
            if line_count > self.MAX_PROPERTY_LINES:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=f"@property '{name}' is {line_count} lines (max {self.MAX_PROPERTY_LINES})",
                    suggestion=f"Consider converting to a regular method: def get_{name}(self)",
                    context=f"@property with {line_count} lines - properties should be simple getters"
                ))

        return detections
