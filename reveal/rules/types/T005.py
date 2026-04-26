"""T005: Annotation coverage reporter.

Reports functions with incomplete type annotations so you can build a
prioritized migration checklist. Unlike mypy's --any-exprs-report (file-level
ratio), this emits one detection per function with a precise summary:
  "process_trade: 2/3 params annotated, return unannotated"

Only fires on functions that are *partially* annotated (at least one param
or return annotation exists). Fully unannotated functions are skipped to
avoid flooding on legacy codebases.
"""

import ast
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin


class T005(BaseRule, ASTParsingMixin):
    """Report functions with partial type annotations."""

    code = "T005"
    message = "Function has incomplete type annotations"
    category = RulePrefix.T
    severity = Severity.LOW
    file_patterns = ['.py']
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        for node in self._ast_walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._check_function(node, file_path, content, detections)

        return detections

    def _check_function(self,
                        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
                        file_path: str,
                        content: str,
                        detections: List[Detection]) -> None:
        args = func_node.args
        all_args = (
            args.posonlyargs
            + args.args
            + args.kwonlyargs
            + ([args.vararg] if args.vararg else [])
            + ([args.kwarg] if args.kwarg else [])
        )
        params = [a for a in all_args if a.arg not in ('self', 'cls')]

        annotated_params = sum(1 for a in params if a.annotation is not None)
        total_params = len(params)
        has_return = func_node.returns is not None

        # Fully annotated — nothing to report
        if annotated_params == total_params and has_return:
            return

        # Completely unannotated — skip (not a migration target yet)
        if annotated_params == 0 and not has_return:
            return

        parts = []
        if total_params > 0 and annotated_params < total_params:
            parts.append(f"{annotated_params}/{total_params} params annotated")
        if not has_return:
            parts.append("return unannotated")

        if not parts:
            return

        missing_names = [a.arg for a in params if a.annotation is None]

        try:
            context = ast.get_source_segment(content, func_node)
            if context:
                context = context.split('\n')[0]
                if not context.endswith(':'):
                    context += '...'
        except Exception:
            context = None

        summary = ', '.join(parts)
        suggestion = f"Annotate: {', '.join(missing_names)}" if missing_names else None

        detections.append(self.create_detection(
            file_path=file_path,
            line=func_node.lineno,
            message=f"{func_node.name}: {summary}",
            suggestion=suggestion,
            context=context,
        ))
