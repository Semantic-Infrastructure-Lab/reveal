"""R913: Too many arguments to function detector.

Detects functions with excessive parameter counts that hurt readability and testability.
"""

import ast
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin


class R913(BaseRule, ASTParsingMixin):
    """Detect functions with too many arguments (>5 is a code smell)."""

    code = "R913"
    message = "Too many arguments to function"
    category = RulePrefix.R  # Refactoring
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.0.0"

    # Threshold for "too many" (configurable in future)
    MAX_ARGS = 5

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for functions with too many arguments using AST parsing.

        Args:
            file_path: Path to Python file
            structure: Parsed structure (not used, we parse AST ourselves)
            content: File content

        Returns:
            List of detections
        """
        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        # Walk the AST looking for function definitions
        for node in self._ast_walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Count arguments (exclude self, cls, *args, **kwargs)
                args = node.args

                # Count positional and keyword-only args
                total_args = len(args.args) + len(args.kwonlyargs)

                # Exclude 'self' or 'cls' for methods
                if args.args and args.args[0].arg in ('self', 'cls'):
                    total_args -= 1

                # Don't count *args or **kwargs as violations
                # (they're often used to reduce argument lists)

                if total_args > self.MAX_ARGS:
                    # Build argument list for context
                    arg_names = [a.arg for a in args.args]
                    if args.kwonlyargs:
                        arg_names.extend([a.arg for a in args.kwonlyargs])

                    # Get the function signature as context
                    try:
                        context = ast.get_source_segment(content, node)
                        if context:
                            # Just show the def line
                            context = context.split('\n')[0]
                    except Exception:
                        context = f"def {node.name}(...)"

                    suggestion = (
                        f"Reduce to {self.MAX_ARGS} or fewer arguments. "
                        f"Consider: 1) Using a config object/dataclass, "
                        f"2) Breaking function into smaller pieces, "
                        f"3) Using **kwargs for optional params"
                    )

                    detections.append(self.create_detection(
                        file_path=file_path,
                        line=node.lineno,
                        message=f"{self.message} ({total_args} > {self.MAX_ARGS}): {node.name}()",
                        column=node.col_offset + 1,
                        suggestion=suggestion,
                        context=context
                    ))

        return detections
