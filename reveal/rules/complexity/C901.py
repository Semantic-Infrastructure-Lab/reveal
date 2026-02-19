"""C901: Function complexity detector.

Detects functions that are too complex based on cyclomatic complexity.
Uses McCabe algorithm for Python (matching Ruff/flake8), with heuristic
fallback for other languages.
"""

import logging
from typing import List, Dict, Any, Optional

from mccabe import PathGraphingAstVisitor  # type: ignore[import-untyped]

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin

logger = logging.getLogger(__name__)


class C901(BaseRule, ASTParsingMixin):
    """Detect overly complex functions (cyclomatic complexity).

    Uses the McCabe algorithm for Python files, matching Ruff's C901 rule.
    For non-Python files, uses a heuristic based on control flow keywords.
    """

    code = "C901"
    message = "Function is too complex"
    category = RulePrefix.C
    severity = Severity.MEDIUM
    file_patterns = ['*']  # Universal: works on any structured file
    version = "1.1.0"  # v1.1.0: McCabe-based calculation (aligned with Ruff)

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

        # For Python files, use McCabe on the whole file for accuracy
        is_python = file_path.endswith('.py')
        mccabe_results = {}
        if is_python and content:
            mccabe_results = self._get_mccabe_complexity(content, file_path)

        # Get functions from structure
        functions = structure.get('functions', [])

        for func in functions:
            func_name = func.get('name', '<unknown>')

            # Priority: 1) McCabe result, 2) structure complexity, 3) heuristic
            if func_name in mccabe_results:
                complexity = mccabe_results[func_name]
            elif func.get('complexity') is not None:
                complexity = func['complexity']
            else:
                complexity = self._calculate_complexity_heuristic(func, content)

            if complexity > threshold:
                line = func.get('line', 0)

                detections.append(Detection(
                    file_path=file_path,
                    line=line,
                    rule_code=self.code,
                    message=f"{self.message}: {func_name} (complexity: {complexity}, max: {threshold})",
                    column=1,
                    suggestion="Break into smaller functions or reduce branching",
                    context=f"Function: {func_name}",
                    severity=self.severity,
                    category=self.category
                ))

        return detections

    def _get_mccabe_complexity(self, content: str, file_path: str = "<unknown>") -> Dict[str, int]:
        """
        Calculate McCabe cyclomatic complexity for all functions in Python code.

        Uses the same algorithm as Ruff and flake8-mccabe for consistent results.
        Shares the cached AST tree with other rules via ASTParsingMixin.

        Args:
            content: Python source code
            file_path: Path for error messages and cache key

        Returns:
            Dict mapping function names to complexity scores
        """
        results = {}
        try:
            tree = self._parse_python(content, file_path)
            if tree is None:
                return results
            visitor = PathGraphingAstVisitor()
            visitor.preorder(tree, visitor)

            for graph in visitor.graphs.values():
                # Graph entity is the function/method name
                name = graph.entity
                # Handle method names (Class.method -> method)
                if '.' in name:
                    name = name.split('.')[-1]
                results[name] = graph.complexity()
        except Exception as e:
            logger.debug(f"McCabe analysis failed: {e}")

        return results

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
        end_line = func.get('end_line') or func.get('line_end') or start_line

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
