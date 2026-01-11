"""PHP analyzer using tree-sitter."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.php', name='PHP', icon='🐘')
class PhpAnalyzer(TreeSitterAnalyzer):
    """Analyze PHP source files.

    Extracts classes, functions, namespaces automatically using tree-sitter.
    """
    language = 'php'
