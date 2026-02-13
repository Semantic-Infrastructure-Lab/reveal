"""Rendering for diff adapter."""

import sys


class DiffRenderer:
    """Renderer for diff comparison results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render diff structure comparison.

        Args:
            result: Diff result from adapter
            format: Output format (text, json, grep)
        """
        from ...rendering.diff import render_diff
        render_diff(result, format, is_element=False)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render element-specific diff.

        Args:
            result: Element diff result
            format: Output format
        """
        from ...rendering.diff import render_diff
        render_diff(result, format, is_element=True)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render error message.

        Args:
            error: Exception to render
        """
        print(f"Error: {error}", file=sys.stderr)
        if isinstance(error, ValueError):
            print(file=sys.stderr)
            print("Examples:", file=sys.stderr)
            print("  reveal diff://app.py:backup/app.py", file=sys.stderr)
            print("  reveal diff://env://:env://production", file=sys.stderr)
            print("  reveal diff://mysql://prod/db:mysql://staging/db", file=sys.stderr)
            print(file=sys.stderr)
            print("Learn more: reveal help://diff", file=sys.stderr)
