"""C905: Nesting depth too high detector.

Detects functions with excessive nesting depth.
Deep nesting indicates complex control flow that's hard to reason about.
"""

import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class C905(BaseRule):
    """Detect functions with excessive nesting depth."""

    code = "C905"
    message = "Nesting depth too high"
    category = RulePrefix.C
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Universal: works on any structured file
    version = "1.0.0"

    # Depth threshold (standard recommendation)
    MAX_DEPTH = 4

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check functions for excessive nesting depth.

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
            depth = func.get('depth', 0)

            # Skip if no depth available
            if depth == 0:
                continue

            # Check if depth exceeds threshold
            if depth > self.MAX_DEPTH:
                line = func.get('line', 0)
                func_name = func.get('name', '<unknown>')

                detections.append(Detection(
                    file_path=file_path,
                    line=line,
                    rule_code=self.code,
                    message=f"{self.message}: {func_name} (depth: {depth}, max: {self.MAX_DEPTH})",
                    column=1,
                    suggestion=(
                        f"Reduce nesting depth from {depth} to {self.MAX_DEPTH} or less. "
                        f"Strategies: 1) Use early returns/guard clauses, "
                        f"2) Extract nested blocks into helper functions, "
                        f"3) Use lookup tables instead of nested if/else, "
                        f"4) Consider polymorphism or strategy pattern"
                    ),
                    context=f"Function: {func_name} (nesting depth: {depth})",
                    severity=Severity.MEDIUM,
                    category=self.category
                ))

        return detections
