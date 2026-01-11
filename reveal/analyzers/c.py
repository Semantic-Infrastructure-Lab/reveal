"""C file analyzer - tree-sitter based."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.c', '.h', name='C', icon='🔧')
class CAnalyzer(TreeSitterAnalyzer):
    """C file analyzer.

    Full C support with automatic extraction:
    - Functions
    - Structs
    - Includes
    - Element extraction
    """
    language = 'c'
