"""Scala analyzer using tree-sitter."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.scala', name='Scala', icon='🔴')
class ScalaAnalyzer(TreeSitterAnalyzer):
    """Analyze Scala source files.

    Extracts classes, objects, traits, and functions automatically using tree-sitter.
    """
    language = 'scala'
