"""Rendering for diff adapter."""

from ...rendering.diff import render_diff
from ...utils.warning_render import render_meta_warnings


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
        if format != 'json':
            # What the comparison could not see (BACK-1732); JSON carries it in meta.
            render_meta_warnings(result)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render element-specific diff.

        Args:
            result: Element diff result
            format: Output format
        """
        render_diff(result, format, is_element=True)
