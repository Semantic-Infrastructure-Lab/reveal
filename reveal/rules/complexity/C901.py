"""C901: Function complexity detector.

Detects functions that are too complex based on cyclomatic complexity.
Reads the same per-function score `ast://` and `stats://` report (BACK-1081), for
every language, so one function has one number across commands. That score counts
boolean operators and ternaries as decisions, like radon, lizard and SonarQube;
Python's `mccabe`/Ruff C901 does not, so Python scores here run higher than Ruff's.
A line-count heuristic is the fallback for analyzers that report no score.
"""

from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from reveal.complexity import fallback_complexity


class C901(BaseRule):
    """Detect overly complex functions (cyclomatic complexity).

    Uses the analyzer's per-function cyclomatic complexity (the value `ast://`
    reports) for every language; falls back to a heuristic when an analyzer
    supplies none.
    """

    code = "C901"
    message = "Function is too complex"
    category = RulePrefix.C
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Universal: works on any structured file
    version = "1.2.0"  # v1.2.0: one shared complexity number (was McCabe for Python, BACK-1081)

    # Default complexity threshold - matches Ruff's default
    # Can be overridden in .reveal.yaml:
    #   rules:
    #     C901:
    #       threshold: 15
    DEFAULT_THRESHOLD = 10

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check functions for excessive complexity.

        Args:
            file_path: Path to file
            structure: Parsed structure from reveal analyzer
            content: File content

        Returns:
            List of detections
        """
        detections: List[Detection] = []

        # Need structure to work
        if not structure:
            return detections

        # Get threshold from config (allows per-project customization)
        threshold = self.get_threshold('threshold', self.DEFAULT_THRESHOLD)

        # Get functions from structure
        functions = structure.get('functions', [])

        for func in functions:
            func_name = func.get('name', '<unknown>')

            # Priority: 1) structure complexity (shared with ast://), 2) heuristic
            if func.get('complexity') is not None:
                complexity = func['complexity']
            else:
                complexity = fallback_complexity(func, content)

            if complexity > threshold:
                line = func.get('line', 0)

                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=f"{self.message}: {func_name} (complexity: {complexity}, max: {threshold})",
                    column=1,
                    suggestion="Break into smaller functions or reduce branching",
                    context=f"Function: {func_name}",
                ))

        return detections
