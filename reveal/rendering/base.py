"""Base classes for reveal adapters' renderers.

Provides common functionality for adapter renderers to reduce duplication.
"""

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar

from reveal.utils.json_utils import print_json_result
from reveal.utils.results import outcome_of
from reveal.utils.query_control import BudgetAccounting
from reveal.utils.warning_render import render_meta_warnings


@dataclass(frozen=True)
class RenderOptions:
    """Immutable presentation controls for text bodies."""
    max_examples: Optional[int] = 3


_Item = TypeVar("_Item")


def capped_section(items: Sequence[_Item], limit: Optional[int], format_item: Callable[[_Item], str]) -> List[str]:
    """Render a bounded section with its exact remainder; None shows everything."""
    if limit is not None and limit < 0:
        raise ValueError("Display limit must be nonnegative")
    shown = items if limit is None else items[:limit]
    lines = [format_item(item) for item in shown]
    accounting = BudgetAccounting("text", len(items), len(shown))
    if accounting.remaining:
        lines.append(f"    ... and {accounting.remaining} more")
    return lines


def emit_rendered(render, result: dict, format: str = "text", **kwargs) -> None:
    """Emit a returned text body and diagnostics; legacy print renderers still work."""
    body = render(result, format, **kwargs)
    if isinstance(body, str):
        if body:
            print(body, end="" if body.endswith("\n") else "\n")
        if format != "json" and outcome_of(result) != "failed":
            render_meta_warnings(result)


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
            indent: JSON indentation — unused, kept for signature back-compat
                (delegates to the single JSON-result funnel, print_json_result,
                which always uses indent=2)
            file: Output file (default: stdout)
        """
        print_json_result(result, file=file)

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
            def _render_text(cls, result: dict) -> str:
                return f"Name: {result['name']}\n"

            @classmethod
            def _get_result_type(cls, result: dict) -> str:
                return result.get('type', 'default')
    """

    @classmethod
    def render_structure(cls, result: dict, format: str = 'text') -> Optional[str]:
        """Render adapter structure results.

        Args:
            result: Result dictionary from adapter
            format: Output format ('text' or 'json')
        """
        if cls.should_render_json(format):
            cls.render_json(result)
            return None

        if outcome_of(result) == 'failed':
            detail = result.get('message')
            if detail and detail != result.get('error'):
                print(detail, file=sys.stderr)
            if result.get('next_steps'):
                print("Next Steps:", file=sys.stderr)
                for step in result['next_steps']:
                    print(f"  • {step}", file=sys.stderr)
            return None
        return cls._render_text(result)

    @classmethod
    @abstractmethod
    def _render_text(cls, result: dict) -> Optional[str]:
        """Return a text body (legacy implementations may print and return None).

        Override this method to implement custom text rendering.

        Args:
            result: Result dictionary from adapter
        """
        pass

    @classmethod
    def render_check(cls, result: dict, format: str = 'text') -> Optional[str]:
        """Render health check results.

        Default implementation delegates to render_structure.
        Override for custom check rendering.

        Args:
            result: Check result dictionary
            format: Output format ('text' or 'json')
        """
        return cls.render_structure(result, format)


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
        elif outcome_of(result) == 'failed':
            # An error-only type (codex_error, ...) has no text view, and the router has
            # already printed its error (BACK-1059); a JSON dump would only repeat it.
            return
        else:
            # Fallback to JSON for unknown types
            cls.render_json(result)
