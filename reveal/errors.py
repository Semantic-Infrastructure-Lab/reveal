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
            suggestions.append(f"Enable tree-sitter fallback: reveal {path} --allow-fallback")

        suggestions.extend([
            f"Use generic text analyzer: reveal {path} --analyzer text",
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


class InvalidPathError(RevealError):
    """Error raised when a path is invalid or doesn't exist."""

    def __init__(self, path: str, reason: str = "Path does not exist"):
        suggestions = [
            f"Check the path is correct: {path}",
            "Verify the file exists and is readable",
            "Use absolute path if relative path isn't working"
        ]

        super().__init__(
            message=f"Invalid path: {path}",
            details=reason,
            suggestions=suggestions,
            context={'path': path}
        )


class ConfigurationError(RevealError):
    """Error raised for configuration issues."""

    def __init__(
        self,
        message: str,
        config_file: Optional[str] = None,
        config_key: Optional[str] = None
    ):
        suggestions = []

        if config_file:
            suggestions.append(f"Check configuration file: {config_file}")

        if config_key:
            suggestions.append(f"Verify configuration key: {config_key}")

        suggestions.extend([
            "View current configuration: reveal config show",
            "Reset to defaults: reveal config reset",
            "Documentation: reveal config --help"
        ])

        context = {}
        if config_file:
            context['config_file'] = config_file
        if config_key:
            context['config_key'] = config_key

        super().__init__(
            message=message,
            suggestions=suggestions,
            context=context
        )


class AdapterError(RevealError):
    """Error raised for adapter-related issues."""

    def __init__(
        self,
        adapter_name: str,
        message: str,
        details: Optional[str] = None
    ):
        suggestions = [
            f"Check {adapter_name} adapter configuration",
            f"View {adapter_name} help: reveal --explain {adapter_name}",
            "Check adapter documentation: reveal --adapters"
        ]

        super().__init__(
            message=message,
            details=details,
            suggestions=suggestions,
            context={'adapter': adapter_name}
        )


class QuerySyntaxError(RevealError):
    """Error raised for query syntax errors."""

    def __init__(
        self,
        query: str,
        position: Optional[int] = None,
        expected: Optional[str] = None
    ):
        message = f"Invalid query syntax: {query}"

        if position is not None:
            message += f" (at position {position})"

        details = None
        if expected:
            details = f"Expected: {expected}"

        suggestions = [
            "Check query syntax: reveal --help query",
            "View examples: reveal --help examples",
            "Query reference: reveal --help operators"
        ]

        context = {'query': query}
        if position is not None:
            context['position'] = position

        super().__init__(
            message=message,
            details=details,
            suggestions=suggestions,
            context=context
        )


class RuleError(RevealError):
    """Error raised for rule-related issues."""

    def __init__(
        self,
        rule_code: str,
        message: str,
        file_path: Optional[str] = None
    ):
        suggestions = [
            f"View rule documentation: reveal --explain-rule {rule_code}",
            "Disable rule: reveal --disable {rule_code}",
            "Configure rule threshold: reveal config set rules.{rule_code}.threshold <value>"
        ]

        if file_path:
            suggestions.insert(0, f"Check file: {file_path}")

        context = {'rule': rule_code}
        if file_path:
            context['file'] = file_path

        super().__init__(
            message=message,
            suggestions=suggestions,
            context=context
        )
