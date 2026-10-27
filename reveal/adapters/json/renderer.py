"""Renderer for JSON navigation adapter results."""

from ...utils.results import outcome_of
from ...utils.warning_render import render_meta_warnings


class JsonRenderer:
    """Renderer for JSON navigation results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render JSON query results.

        Args:
            result: Query result dict from JsonAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ...rendering import render_json_result
        render_json_result(result, format)
        # unknown_filter_field; the ?sort=/?limit= notes (unknown_sort_field, sort_failed,
        # truncated) are printed once by the output seam, and a failed result's error by
        # the router (BACK-2297).
        if format == 'text' and outcome_of(result) != 'failed':
            render_meta_warnings(result)
