"""Renderer for markdown query results."""

import sys

from ...rendering.adapters.markdown_query import render_markdown_query
from ...utils.results import outcome_of
from ...utils.warning_render import meta_warning_lines


class MarkdownRenderer:
    """Renderer for markdown query results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render markdown query results.

        Args:
            result: Structure dict from MarkdownQueryAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        render_markdown_query(result, format)
        if (format != 'json' and result.get('type') in ('markdown_query', 'markdown_aggregate')
                and 'analysis' in result and outcome_of(result) != 'failed'):
            for line in meta_warning_lines(result):
                print(line, file=sys.stderr if format == 'grep' else sys.stdout)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific markdown file frontmatter.

        Args:
            result: Element dict from MarkdownQueryAdapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        render_markdown_query(result, format, single_file=True)
