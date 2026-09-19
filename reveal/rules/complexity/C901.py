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
                complexity = self._calculate_complexity_heuristic(func, content)

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

    def _calculate_complexity_heuristic(self, func: Dict[str, Any], content: str) -> int:
        """
        Calculate complexity using heuristics for non-Python files.

        Counts control flow keywords as a proxy for cyclomatic complexity.
        Less accurate than McCabe but works for any language.

        Args:
            func: Function metadata from structure
            content: File content

        Returns:
            Estimated complexity score
        """
        # Get function content if we have line numbers
        start_line = func.get('line', 0)
        end_line = func.get('line_end') or start_line

        if start_line == 0 or end_line == 0:
            # Fall back to line count heuristic
            line_count = int(func.get('line_count', 0))
            return max(1, line_count // 10)

        # Extract function content
        lines = content.splitlines()
        if start_line > len(lines) or end_line > len(lines):
            return 1

        func_content = '\n'.join(lines[start_line - 1:end_line])

        # Start at 1 (base complexity)
        complexity = 1

        # Control flow patterns that add complexity
        # These are language-agnostic patterns
        patterns = [
            ' if ', ' if(',       # conditionals
            ' else if ', 'elif ',  # else-if chains
            ' for ', ' for(',     # loops
            ' while ', ' while(',
            ' && ', ' and ',      # boolean operators
            ' || ', ' or ',
            ' case ',             # switch/match cases
            ' catch ', ' catch(',  # exception handling
            ' except ',
            ' ? ',                # ternary operator
        ]

        for pattern in patterns:
            complexity += func_content.count(pattern)

        return complexity
