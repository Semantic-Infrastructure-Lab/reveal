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

    def _is_property_decorator(self, decorators: List[str]) -> bool:
        """Check if decorators include @property or @cached_property.

        Args:
            decorators: List of decorator strings

        Returns:
            True if any decorator is a property decorator
        """
        return any(
            d in ['@property', '@cached_property'] or
            d.startswith('@property') or
            d.endswith('.getter')
            for d in decorators
        )

    def _is_abstract_property(self, decorators: List[str]) -> bool:
        """Check if decorators include @abstractmethod.

        Args:
            decorators: List of decorator strings

        Returns:
            True if any decorator is @abstractmethod
        """
        return any('@abstractmethod' in d for d in decorators)

    def _extract_function_body(self, lines: List[str], line: int, line_count: int) -> Optional[str]:
        """Extract function body from source lines.

        Args:
            lines: Source code split into lines
            line: Starting line number (1-indexed)
            line_count: Number of lines in function

        Returns:
            Function body as string, or None if invalid
        """
        if line <= 0 or line_count <= 0:
            return None

        # Get function lines (1-indexed to 0-indexed)
        start_idx = line - 1
        end_idx = min(start_idx + line_count, len(lines))
        func_lines = lines[start_idx:end_idx]
        return '\n'.join(func_lines)

    def _has_valid_implementation(self, func_body: str) -> bool:
        """Check if function body has valid implementation.

        Valid implementations include:
        - return statement
        - raise statement
        - ... (Ellipsis - stub)

        Args:
            func_body: Function body code

        Returns:
            True if function has valid implementation
        """
        has_return = self._has_return_statement(func_body)
        has_raise = self._has_raise_statement(func_body)
        has_ellipsis = bool(re.search(r'^\s*\.\.\.\s*$', func_body, re.MULTILINE))

        return has_return or has_raise or has_ellipsis

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
        detections: List[Detection] = []

        if not structure or not content:
            return detections

        lines = content.split('\n')

        # Check all functions
        for func in structure.get('functions', []):
            decorators = func.get('decorators', [])
            name = func.get('name', '')
            line = func.get('line', 0)
            line_count = func.get('line_count', 0)

            # Skip non-properties and abstract properties
            if not self._is_property_decorator(decorators):
                continue
            if self._is_abstract_property(decorators):
                continue

            # Extract function body
            func_body = self._extract_function_body(lines, line, line_count)
            if not func_body:
                continue

            # Check for valid implementation (return/raise/ellipsis)
            if not self._has_valid_implementation(func_body):
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
