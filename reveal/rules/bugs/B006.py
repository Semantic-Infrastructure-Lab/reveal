"""B006: Silent broad exception handler detector.

Detects broad exception handlers (except Exception:) with only pass statement
and no explanatory comment, which can hide serious bugs.
"""

import ast
import re
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin


class B006(BaseRule, ASTParsingMixin):
    """Detect silent broad exception handlers that swallow errors."""

    code = "B006"
    message = "Broad exception handler with silent pass can hide bugs"
    category = RulePrefix.B
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    version = "1.0.0"

    # Pattern to detect explanatory comments near pass statement
    COMMENT_PATTERN = re.compile(r'#\s*\w+')

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for broad exception handlers with silent pass.

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

        # Split content into lines for comment checking
        lines = content.split('\n')

        # Walk the AST looking for problematic exception handlers
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Check if catching Exception (broad catch)
                if self._is_broad_exception(node):
                    # Check if body is just pass (silent failure)
                    if self._is_silent_pass(node):
                        # Check if there's an explanatory comment
                        if not self._has_explanatory_comment(node, lines):
                            # Get context for the detection
                            try:
                                context = ast.get_source_segment(content, node)
                                if context:
                                    # Show first 2 lines (except line + pass)
                                    context = '\n'.join(context.split('\n')[:2])
                            except Exception:
                                context = None

                            detections.append(self.create_detection(
                                file_path=file_path,
                                line=node.lineno,
                                column=node.col_offset + 1,
                                suggestion=(
                                    "Consider:\n"
                                    "  1. Use specific exception types (ValueError, KeyError, etc.)\n"
                                    "  2. Add logging: logger.debug(f'Ignoring error: {e}')\n"
                                    "  3. Add comment explaining why silence is intentional\n"
                                    "  4. Re-raise if you can't handle: raise"
                                ),
                                context=context
                            ))

        return detections

    def _is_broad_exception(self, node: ast.ExceptHandler) -> bool:
        """Check if exception handler catches Exception (broad catch).

        Args:
            node: AST ExceptHandler node

        Returns:
            True if catches Exception, BaseException, or tuple containing them
        """
        if node.type is None:
            # Bare except - handled by B001
            return False

        # Single exception: except Exception:
        if isinstance(node.type, ast.Name):
            return node.type.id in ('Exception', 'BaseException')

        # Tuple of exceptions: except (ValueError, Exception):
        if isinstance(node.type, ast.Tuple):
            for elt in node.type.elts:
                if isinstance(elt, ast.Name) and elt.id in ('Exception', 'BaseException'):
                    return True

        return False

    def _is_silent_pass(self, node: ast.ExceptHandler) -> bool:
        """Check if exception handler body is just pass.

        Args:
            node: AST ExceptHandler node

        Returns:
            True if body contains only pass statement
        """
        if len(node.body) != 1:
            return False

        return isinstance(node.body[0], ast.Pass)

    def _has_explanatory_comment(self, node: ast.ExceptHandler, lines: List[str]) -> bool:
        """Check if exception handler has an explanatory comment.

        Looks for comments on:
        - The except line itself (inline comment)
        - Any line in the handler body (between except and last statement)

        Args:
            node: AST ExceptHandler node
            lines: Source code lines

        Returns:
            True if meaningful comment found
        """
        if not lines or node.lineno < 1:
            return False

        # Check except line (node.lineno is 1-indexed)
        except_line_idx = node.lineno - 1
        if except_line_idx < len(lines):
            if self.COMMENT_PATTERN.search(lines[except_line_idx]):
                return True

        # Check all lines in the handler body
        if node.body and hasattr(node.body[-1], 'lineno'):
            # Check from line after except to the last statement (inclusive)
            start_line_idx = except_line_idx + 1
            end_line_idx = node.body[-1].lineno  # This is 1-indexed, but we'll use it correctly

            for line_idx in range(start_line_idx, min(end_line_idx, len(lines))):
                if self.COMMENT_PATTERN.search(lines[line_idx]):
                    return True

        return False
