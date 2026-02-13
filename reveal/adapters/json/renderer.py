"""Renderer for JSON navigation adapter results."""

import sys


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

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error querying JSON: {error}", file=sys.stderr)
