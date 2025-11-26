"""Go file analyzer - tree-sitter based."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.go', name='Go', icon='')
class GoAnalyzer(TreeSitterAnalyzer):
    """Go file analyzer.

    Full Go support in 3 lines!
    """
    language = 'go'
