"""T004: Implicit Optional parameter detector (PEP 484 violation).

Detects function parameters with type hints that have None as default value
without using Optional[], which violates PEP 484 and causes mypy errors.

Examples:
    # ❌ Bad (implicit Optional)
    def func(path: Path = None):
        pass

    # ✅ Good (explicit Optional)
    def func(path: Optional[Path] = None):
        pass
"""

import ast
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin


class T004(BaseRule, ASTParsingMixin):
    """Detect implicit Optional parameters (PEP 484 violation)."""

    code = "T004"
    message = "Parameter has type hint with None default but missing Optional[]"
    category = RulePrefix.T
    severity = Severity.HIGH  # PEP 484 violation, causes mypy errors
    file_patterns = ['.py']
    version = "1.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for implicit Optional parameters.

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
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_function_params(node, file_path, content, detections)

        return detections

    def _check_function_params(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef, file_path: str,
                               content: str, detections: List[Detection]) -> None:
        """Check all parameters in a function definition."""
        args = func_node.args

        # Check regular args with defaults
        defaults_offset = len(args.args) - len(args.defaults)
        for i, (arg, default) in enumerate(zip(args.args[defaults_offset:], args.defaults)):
            if self._is_implicit_optional(arg, default):
                self._add_detection(func_node, arg, file_path, content, detections)

        # Check keyword-only args with defaults
        for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults):
            if kw_default and self._is_implicit_optional(arg, kw_default):
                self._add_detection(func_node, arg, file_path, content, detections)

    def _is_implicit_optional(self, arg: ast.arg, default: ast.expr | None) -> bool:
        """Check if parameter has type hint with None default but no Optional."""
        # Default must exist
        if default is None:
            return False

        # Must have a type annotation
        if not arg.annotation:
            return False

        # Must have None as default
        if not isinstance(default, ast.Constant) or default.value is not None:
            return False

        # Check if annotation already includes Optional
        annotation_str = ast.unparse(arg.annotation)

        # Already has Optional - OK
        if 'Optional[' in annotation_str:
            return False

        # Already has Union with None - OK
        if 'Union[' in annotation_str and 'None' in annotation_str:
            return False

        # Has | None (Python 3.10+) - OK
        if '| None' in annotation_str or 'None |' in annotation_str:
            return False

        # Type hint with None default but no Optional - PEP 484 violation!
        return True

    def _add_detection(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef, arg: ast.arg,
                      file_path: str, content: str, detections: List[Detection]) -> None:
        """Add detection for implicit Optional parameter."""
        type_str = ast.unparse(arg.annotation) if arg.annotation else "Any"

        # Get context (function signature line)
        try:
            context = ast.get_source_segment(content, func_node)
            if context:
                # Show just the signature line
                context = context.split('\n')[0]
                if not context.endswith(':'):
                    context += '...'
        except Exception:
            context = None

        detections.append(self.create_detection(
            file_path=file_path,
            line=arg.lineno,
            column=arg.col_offset + 1,
            suggestion=(
                f"Add Optional to type hint:\n"
                f"  {arg.arg}: Optional[{type_str}] = None\n\n"
                f"Or use Python 3.10+ union syntax:\n"
                f"  {arg.arg}: {type_str} | None = None\n\n"
                f"PEP 484 prohibits implicit Optional. Without Optional[], "
                f"mypy treats this as a type error."
            ),
            context=context
        ))
