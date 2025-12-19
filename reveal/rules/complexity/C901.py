"""C901: Function complexity detector.

Detects functions that are too complex based on cyclomatic complexity.
Universal rule that works with reveal's structure output.
"""

import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class C901(BaseRule):
    """Detect overly complex functions (cyclomatic complexity)."""

    code = "C901"
    message = "Function is too complex"
    category = RulePrefix.C
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Universal: works on any structured file
    version = "1.0.0"

    # Complexity threshold (standard McCabe threshold)
    THRESHOLD = 10

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
        detections = []

        # Need structure to work
        if not structure:
            return detections

        # Get functions from structure
        functions = structure.get('functions', [])

        for func in functions:
            # Use complexity from structure if available (tree-sitter calculated)
            # Otherwise fall back to manual calculation
            complexity = func.get('complexity')
            if complexity is None:
                complexity = self._calculate_complexity(func, content)

            if complexity > self.THRESHOLD:
                line = func.get('line', 0)
                func_name = func.get('name', '<unknown>')

                detections.append(Detection(
                    file_path=file_path,
                    line=line,
                    rule_code=self.code,
                    message=f"{self.message}: {func_name} (complexity: {complexity}, max: {self.THRESHOLD})",
                    column=1,
                    suggestion="Break into smaller functions or reduce branching",
                    context=f"Function: {func_name}",
                    severity=self.severity,
                    category=self.category
                ))

        return detections

    def _calculate_complexity(self, func: Dict[str, Any], content: str) -> int:
        """
        Calculate cyclomatic complexity for a function.

        This is a simplified heuristic based on counting decision points.
        A proper implementation would use AST analysis.

        Args:
            func: Function metadata from structure
            content: File content

        Returns:
            Estimated complexity score
        """
        # Get function content if we have line numbers
        # Accept both 'end_line' and 'line_end' (tree-sitter uses 'line_end')
        start_line = func.get('line', 0)
        end_line = func.get('end_line') or func.get('line_end') or start_line

        if start_line == 0 or end_line == 0:
            # Fall back to simple heuristics from metadata
            line_count = func.get('line_count', 0)
            return max(1, line_count // 10)  # Very rough estimate

        # Extract function content
        lines = content.splitlines()
        if start_line > len(lines) or end_line > len(lines):
            return 1

        func_content = '\n'.join(lines[start_line - 1:end_line])

        # Calculate complexity: start at 1, add 1 for each decision point
        complexity = 1

        # Decision keywords that increase complexity
        # Each represents a branch in the code flow
        decision_keywords = [
            'if ',
            'elif ',
            'else:',
            'else ',
            'for ',
            'while ',
            'and ',
            'or ',
            'try:',
            'except ',
            'except:',
            'case ',  # match/case in Python 3.10+
            'when ',
        ]

        for keyword in decision_keywords:
            # Count occurrences (simple but effective)
            complexity += func_content.count(keyword)

        # Also check for ternary operators (? : in many languages, if/else in Python expressions)
        complexity += func_content.count(' if ') - func_content.count('if ')  # Ternary in Python

        return complexity
