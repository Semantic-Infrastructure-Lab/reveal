"""Mixins for reveal's rule system.

Provides reusable functionality that can be mixed into rule classes
to reduce boilerplate and ensure consistent behavior.
"""

import ast
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ASTParsingMixin:
    """Mixin for rules that need to parse Python AST.

    Provides safe AST parsing with consistent error handling.
    Rules can inherit from both BaseRule and this mixin.

    Example:
        class B001(BaseRule, ASTParsingMixin):
            def check(self, file_path, structure, content):
                tree = self._parse_python(content, file_path)
                if tree is None:
                    return []  # Syntax error, skip
                # ... use tree
    """

    def _parse_python(self, content: str, file_path: str = "<unknown>") -> Optional[ast.AST]:
        """Parse Python content into AST.

        Args:
            content: Python source code
            file_path: Path for error messages (default: "<unknown>")

        Returns:
            AST tree if parsing succeeds, None on SyntaxError
        """
        try:
            return ast.parse(content, filename=file_path)
        except SyntaxError as e:
            logger.debug(f"Syntax error in {file_path}: {e}")
            return None
        except Exception as e:
            # Catch unexpected errors (e.g., encoding issues)
            logger.debug(f"Failed to parse {file_path}: {e}")
            return None

    def _parse_python_or_skip(self, content: str, file_path: str = "<unknown>") -> tuple[Optional[ast.AST], list]:
        """Parse Python or return empty detections list.

        Convenience method for common pattern in check() methods.

        Args:
            content: Python source code
            file_path: Path for error messages

        Returns:
            Tuple of (tree, detections) where:
            - tree is AST or None
            - detections is empty list (for early return on parse failure)

        Example:
            def check(self, file_path, structure, content):
                tree, detections = self._parse_python_or_skip(content, file_path)
                if tree is None:
                    return detections
                # ... analyze tree
        """
        tree = self._parse_python(content, file_path)
        return tree, []
