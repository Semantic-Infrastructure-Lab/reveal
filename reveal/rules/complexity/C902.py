"""C902: Function too long detector.

Detects functions that exceed recommended length limits.
Long functions are harder to understand, test, and maintain.
They also consume significant LLM context tokens.
"""

import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class C902(BaseRule):
    """Detect functions that are too long (god functions)."""

    code = "C902"
    message = "Function is too long"
    category = RulePrefix.C
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Universal: works on any structured file
    version = "1.0.0"

    # Length thresholds
    THRESHOLD_WARN = 50   # Warning: getting large
    THRESHOLD_ERROR = 100  # Error: god function

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check functions for excessive length.

        Args:
            file_path: Path to file
            structure: Parsed structure from reveal analyzer
            content: File content

        Returns:
            List of detections
        """
        detections = []

        # Need structure to work
        if not structure:
            return detections

        # Get functions from structure
        functions = structure.get('functions', [])

        for func in functions:
            line_count = func.get('line_count', 0)

            # Skip if no line count available
            if line_count == 0:
                continue

            # Determine severity and message
            if line_count > self.THRESHOLD_ERROR:
                severity = Severity.HIGH
                msg = f"{self.message}: {func.get('name', '<unknown>')} ({line_count} lines, max: {self.THRESHOLD_ERROR})"
                suggestion = (
                    f"Break this {line_count}-line function into smaller, focused functions. "
                    f"God functions are hard to test, maintain, and understand. "
                    f"Target: <{self.THRESHOLD_ERROR} lines per function. "
                    f"LLM cost: ~{line_count * 15} tokens for this function alone."
                )
            elif line_count > self.THRESHOLD_WARN:
                severity = Severity.MEDIUM
                msg = f"{self.message}: {func.get('name', '<unknown>')} ({line_count} lines, consider refactoring at {self.THRESHOLD_ERROR})"
                suggestion = (
                    f"This function is getting large. Consider refactoring if it grows beyond {self.THRESHOLD_ERROR} lines. "
                    f"Extract helper functions for complex logic."
                )
            else:
                continue

            line = func.get('line', 0)
            func_name = func.get('name', '<unknown>')

            detections.append(Detection(
                file_path=file_path,
                line=line,
                rule_code=self.code,
                message=msg,
                column=1,
                suggestion=suggestion,
                context=f"Function: {func_name} ({line_count} lines)",
                severity=severity,
                category=self.category
            ))

        return detections
