"""Java analyzer using tree-sitter."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.java', name='Java', icon='☕')
class JavaAnalyzer(TreeSitterAnalyzer):
    """Analyze Java source files.

    Extracts classes, methods, imports automatically using tree-sitter.
    """
    language = 'java'
