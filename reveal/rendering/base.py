"""Base classes for reveal adapters' renderers.

Provides common functionality for adapter renderers to reduce duplication.
"""

import json
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class RendererMixin:
    """Mixin providing common rendering utilities.

    Add this mixin to adapter renderer classes to get shared functionality.

    Example:
        class MyRenderer(RendererMixin):
            def render_structure(self, result, format='text'):
                if self.should_render_json(format):
                    self.render_json(result)
                    return
                # ... custom text rendering
    """

    @staticmethod
    def should_render_json(format: str) -> bool:
        """Check if output should be JSON format.

        Args:
            format: Output format string

        Returns:
            True if format is 'json'
        """
        return format == 'json'

    @staticmethod
    def render_json(result: dict, indent: int = 2, file=None) -> None:
        """Render result as JSON.

        Args:
            result: Dictionary to render
            indent: JSON indentation (default: 2)
            file: Output file (default: stdout)
        """
        print(json.dumps(result, indent=indent, default=str), file=file or sys.stdout)

    @staticmethod
    def print_header(title: str, subtitle: Optional[str] = None) -> None:
        """Print a formatted header.

        Args:
            title: Main title
            subtitle: Optional subtitle
        """
        print(title)
        if subtitle:
            print(subtitle)
        print()

    @staticmethod
    def print_section(title: str, items: Dict[str, Any], indent: int = 2) -> None:
        """Print a key-value section.

        Args:
            title: Section title
            items: Dictionary of items to display
            indent: Number of spaces for indentation
        """
        print(f"{title}:")
        prefix = " " * indent
        for key, value in items.items():
            print(f"{prefix}{key}: {value}")
        print()

    @staticmethod
    def print_list(title: str, items: list, prefix: str = "  ", bullet: str = "•") -> None:
        """Print a bulleted list.

        Args:
            title: List title
            items: Items to display
            prefix: Line prefix (default: 2 spaces)
            bullet: Bullet character (default: •)
        """
        print(f"{title}:")
        for item in items:
            print(f"{prefix}{bullet} {item}")
        print()

    @staticmethod
    def print_status(label: str, passed: bool, message: Optional[str] = None) -> None:
        """Print a status line with pass/fail indicator.

        Args:
            label: Status label
            passed: Whether status is passing
            message: Optional additional message
        """
        icon = '\u2705' if passed else '\u274c'
        line = f"{label}: {icon}"
        if message:
            line += f" {message}"
        print(line)

    @staticmethod
    def print_error(message: str, details: Optional[str] = None) -> None:
        """Print an error message to stderr.

        Args:
            message: Error message
            details: Optional additional details
        """
        print(f"Error: {message}", file=sys.stderr)
        if details:
            print("", file=sys.stderr)
            print(details, file=sys.stderr)


class BaseRenderer(ABC, RendererMixin):
    """Abstract base class for adapter renderers.

    Inherit from this class and implement _render_text() for custom
    text rendering. JSON rendering is handled automatically.

    Example:
        class MyRenderer(BaseRenderer):
            @classmethod
            def _render_text(cls, result: dict) -> None:
                # Custom text rendering
                print(f"Name: {result['name']}")

            @classmethod
            def _get_result_type(cls, result: dict) -> str:
                return result.get('type', 'default')
    """

    @classmethod
    def render_structure(cls, result: dict, format: str = 'text') -> None:
        """Render adapter structure results.

        Args:
            result: Result dictionary from adapter
            format: Output format ('text' or 'json')
        """
        if cls.should_render_json(format):
            cls.render_json(result)
            return

        cls._render_text(result)

    @classmethod
    @abstractmethod
    def _render_text(cls, result: dict) -> None:
        """Render result as text output.

        Override this method to implement custom text rendering.

        Args:
            result: Result dictionary from adapter
        """
        pass

    @classmethod
    def render_check(cls, result: dict, format: str = 'text') -> None:
        """Render health check results.

        Default implementation delegates to render_structure.
        Override for custom check rendering.

        Args:
            result: Check result dictionary
            format: Output format ('text' or 'json')
        """
        cls.render_structure(result, format)


class TypeDispatchRenderer(BaseRenderer):
    """Base renderer that dispatches to type-specific methods.

    Automatically routes to _render_{type}() methods based on
    result['type'] value. Useful when adapters return multiple
    result types.

    Example:
        class MyRenderer(TypeDispatchRenderer):
            @classmethod
            def _render_overview(cls, result: dict) -> None:
                print(f"Overview: {result['name']}")

            @classmethod
            def _render_details(cls, result: dict) -> None:
                print(f"Details: {result['data']}")

        # Automatically routes:
        # result['type'] == 'overview' -> _render_overview()
        # result['type'] == 'details' -> _render_details()
    """

    @classmethod
    def _render_text(cls, result: dict) -> None:
        """Dispatch to type-specific renderer.

        Looks for a method named _render_{type}() where {type} is
        the value of result['type']. Falls back to JSON if no
        matching method found.
        """
        result_type = result.get('type', 'default')

        # Convert type to method name (e.g., 'ssl_certificate' -> '_render_ssl_certificate')
        method_name = f'_render_{result_type}'
        method = getattr(cls, method_name, None)

        if method and callable(method):
            method(result)
        else:
            # Fallback to JSON for unknown types
            cls.render_json(result)
