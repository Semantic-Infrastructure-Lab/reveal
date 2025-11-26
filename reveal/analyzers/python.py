"""Python file analyzer - tree-sitter based."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.py', name='Python', icon='')
class PythonAnalyzer(TreeSitterAnalyzer):
    """Python file analyzer.

    Gets structure + extraction for FREE from TreeSitterAnalyzer!

    Just 3 lines of code for full Python support!
    """
    language = 'python'
