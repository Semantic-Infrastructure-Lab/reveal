"""B006: Silent broad exception handler detector.

Detects broad exception handlers (except Exception:) with only pass statement
and no explanatory comment, which can hide serious bugs.
"""

import ast
import re
import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class B006(BaseRule):
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
        detections = []

        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as e:
            logger.debug(f"Syntax error in {file_path}, skipping B006 check: {e}")
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
        - The pass line (inline comment)

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

        # Check pass line (should be next line in most cases)
        if node.body and hasattr(node.body[0], 'lineno'):
            pass_line_idx = node.body[0].lineno - 1
            if pass_line_idx < len(lines):
                if self.COMMENT_PATTERN.search(lines[pass_line_idx]):
                    return True

        return False
