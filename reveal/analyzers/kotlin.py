"""Kotlin analyzer using tree-sitter."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.kt', name='Kotlin', icon='🟣')
class KotlinAnalyzer(TreeSitterAnalyzer):
    """Analyze Kotlin source files.

    Extracts classes, functions, objects automatically using tree-sitter.
    """
    language = 'kotlin'
