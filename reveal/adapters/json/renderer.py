"""Renderer for JSON navigation adapter results."""


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
        if format == 'text':
            # json:// keeps its disclosures at the top level (unknown_filter_field,
            # sort_failed); the text view shows them too, not only --format json.
            for warning in result.get('warnings') or []:
                print(f"  \u26a0 {warning.get('message', warning.get('type', ''))}")
