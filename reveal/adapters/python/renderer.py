"""Renderer for Python adapter results."""


class PythonRenderer:
    """Renderer for Python runtime inspection results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render Python environment overview.

        Args:
            result: Structure dict from PythonAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ...rendering import render_python_structure
        render_python_structure(result, format)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific Python element.

        Args:
            result: Element dict from PythonAdapter.get_element()
            format: Output format ('text', 'json', 'grep')
        """
        from ...rendering import render_python_element
        render_python_element(result, format)
