"""B002: @staticmethod with self parameter detector.

Detects @staticmethod methods that incorrectly have 'self' as first parameter.
This is a common mistake - if the method uses self, it shouldn't be static.
"""

import re
import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class B002(BaseRule):
    """Detect @staticmethod methods with 'self' parameter."""

    code = "B002"
    message = "@staticmethod should not have 'self' parameter"
    category = RulePrefix.B
    severity = Severity.HIGH
    file_patterns = ['.py']
    version = "1.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for @staticmethod methods with self parameter.

        Uses reveal's structure data (with decorator extraction) to find
        staticmethod decorators, then checks if the signature starts with 'self'.

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
            signature = func.get('signature', '')
            name = func.get('name', '')
            line = func.get('line', 0)

            # Check if it's a staticmethod
            is_staticmethod = any(
                '@staticmethod' in d for d in decorators
            )

            if not is_staticmethod:
                continue

            # Check if signature starts with 'self'
            # Signature format: "(self, arg1, arg2)" or "(self)"
            sig_match = re.match(r'\(\s*self\s*[,)]', signature)
            if sig_match:
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=f"@staticmethod '{name}' has 'self' parameter - remove @staticmethod or self",
                    suggestion="Either remove @staticmethod (if method needs instance) or remove 'self' parameter (if truly static)",
                    context=f"@staticmethod\ndef {name}{signature}"
                ))

        return detections
