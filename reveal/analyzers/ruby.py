"""Ruby analyzer using tree-sitter."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.rb', name='Ruby', icon='💎')
class RubyAnalyzer(TreeSitterAnalyzer):
    """Analyze Ruby source files.

    Extracts classes, methods, modules automatically using tree-sitter.
    """
    language = 'ruby'
