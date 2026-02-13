"""Rendering for AST query adapter."""

import sys


class AstRenderer:
    """Renderer for AST query results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render AST query results.

        Args:
            result: Query result dict from AstAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ...rendering import render_ast_structure
        render_ast_structure(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error querying AST: {error}", file=sys.stderr)
