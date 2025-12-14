"""B004: @property without return statement detector.

Detects @property methods that don't have a return statement.
Properties that don't return anything will return None, which is almost always a bug.
"""

import re
import logging
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class B004(BaseRule):
    """Detect @property methods without return statement."""

    code = "B004"
    message = "@property has no return statement"
    category = RulePrefix.B
    severity = Severity.HIGH
    file_patterns = ['.py']
    version = "1.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for @property methods without return statements.

        Properties without return will return None, which is almost always
        unintended. Exceptions: properties that raise, or abstract properties.

        Args:
            file_path: Path to Python file
            structure: Parsed structure with functions and decorators
            content: File content

        Returns:
            List of detections
        """
        detections = []

        if not structure or not content:
            return detections

        lines = content.split('\n')

        # Check all functions
        for func in structure.get('functions', []):
            decorators = func.get('decorators', [])
            name = func.get('name', '')
            line = func.get('line', 0)
            line_count = func.get('line_count', 0)

            # Check if it's a property
            is_property = any(
                d in ['@property', '@cached_property'] or
                d.startswith('@property') or
                d.endswith('.getter')
                for d in decorators
            )

            if not is_property:
                continue

            # Skip abstract properties (they may not have implementation)
            is_abstract = any('@abstractmethod' in d for d in decorators)
            if is_abstract:
                continue

            # Extract the function body from content
            if line <= 0 or line_count <= 0:
                continue

            # Get function lines (1-indexed to 0-indexed)
            start_idx = line - 1
            end_idx = min(start_idx + line_count, len(lines))
            func_lines = lines[start_idx:end_idx]
            func_body = '\n'.join(func_lines)

            # Check if there's a return statement
            # Use regex to find 'return' that's not in a string or comment
            has_return = self._has_return_statement(func_body)

            # Also check for raise (valid - property can raise instead of return)
            has_raise = self._has_raise_statement(func_body)

            # Check for ... (Ellipsis - stub)
            has_ellipsis = re.search(r'^\s*\.\.\.\s*$', func_body, re.MULTILINE)

            if not has_return and not has_raise and not has_ellipsis:
                msg = f"@property '{name}' has no return (will return None)"
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=msg,
                    suggestion="Add return statement or convert to a method",
                    context=f"@property\ndef {name}(self): ..."
                ))

        return detections

    def _has_return_statement(self, code: str) -> bool:
        """Check if code has a return statement (not in string/comment)."""
        # Remove strings and comments first
        cleaned = self._remove_strings_and_comments(code)
        # Look for return keyword followed by word boundary
        return bool(re.search(r'\breturn\b', cleaned))

    def _has_raise_statement(self, code: str) -> bool:
        """Check if code has a raise statement (not in string/comment)."""
        cleaned = self._remove_strings_and_comments(code)
        return bool(re.search(r'\braise\b', cleaned))

    def _remove_strings_and_comments(self, code: str) -> str:
        """Remove string literals and comments from code."""
        # Remove triple-quoted strings
        code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
        code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)
        # Remove single-line strings
        code = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '', code)
        code = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", '', code)
        # Remove comments
        code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        return code
