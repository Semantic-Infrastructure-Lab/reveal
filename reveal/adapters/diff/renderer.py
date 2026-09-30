"""Rendering for diff adapter."""

from ...rendering.diff import render_diff


class DiffRenderer:
    """Renderer for diff comparison results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render diff structure comparison.

        Args:
            result: Diff result from adapter
            format: Output format (text, json, grep)
        """
        render_diff(result, format, is_element=False)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render element-specific diff.

        Args:
            result: Element diff result
            format: Output format
        """
        render_diff(result, format, is_element=True)
