"""Renderer for markdown query results."""

import sys


class MarkdownRenderer:
    """Renderer for markdown query results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render markdown query results.

        Args:
            result: Structure dict from MarkdownQueryAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ...rendering.adapters.markdown_query import render_markdown_query
        render_markdown_query(result, format)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific markdown file frontmatter.

        Args:
            result: Element dict from MarkdownQueryAdapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        from ...rendering.adapters.markdown_query import render_markdown_query
        render_markdown_query(result, format, single_file=True)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error querying markdown: {error}", file=sys.stderr)
