"""Enhanced error classes with actionable suggestions.

This module provides error classes that include:
- Clear error messages
- Detailed context
- Actionable suggestions for resolution
- Consistent formatting
"""

from typing import List, Optional, Dict, Any
from pathlib import Path


class RevealError(Exception):
    """Base error class for Reveal with actionable suggestions.

    Attributes:
        message: The error message
        details: Optional detailed error information
        suggestions: List of actionable suggestions
        context: Optional context dictionary for debugging
    """

    def __init__(
        self,
        message: str,
        details: Optional[str] = None,
        suggestions: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.details = details
        self.suggestions = suggestions or []
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Format error with details and suggestions."""
        parts = [f"Error: {self.message}"]

        if self.details:
            parts.append(f"\nDetails: {self.details}")

        if self.context:
            parts.append("\nContext:")
            for key, value in self.context.items():
                parts.append(f"  {key}: {value}")

        if self.suggestions:
            parts.append("\nSuggestions:")
            for suggestion in self.suggestions:
                parts.append(f"  - {suggestion}")

        return "\n".join(parts)


class AnalyzerNotFoundError(RevealError):
    """Error raised when no analyzer is found for a file type."""

    def __init__(
        self,
        path: str,
        allow_fallback: bool = True,
        similar_extensions: Optional[List[str]] = None
    ):
        file_path = Path(path)
        ext = file_path.suffix or '(no extension)'
        file_name = file_path.name

        message = f"No analyzer found for file '{file_name}' (extension: {ext})"

        suggestions = []

        if not allow_fallback:
            suggestions.append(f"Enable tree-sitter fallback: reveal {path} (remove --no-fallback)")

        suggestions.extend([
            "View all supported file types: reveal --list-supported",
        ])

        if similar_extensions:
            suggestions.append(
                f"Similar supported extensions: {', '.join(sorted(similar_extensions)[:5])}"
            )

        suggestions.append(
            f"Request support for {ext}: https://github.com/Semantic-Infrastructure-Lab/reveal/issues"
        )

        context = {
            'file': path,
            'extension': ext,
            'fallback_enabled': allow_fallback
        }

        super().__init__(
            message=message,
            suggestions=suggestions,
            context=context
        )
