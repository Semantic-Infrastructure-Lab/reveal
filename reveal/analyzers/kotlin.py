"""Kotlin analyzer using tree-sitter."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.kt', name='Kotlin', icon='🔷')
@register('.kts', name='Kotlin Script', icon='📜')
class KotlinAnalyzer(TreeSitterAnalyzer):
    """Analyze Kotlin source files.

    Extracts classes, functions, interfaces automatically using tree-sitter.
    Supports both .kt (Kotlin) and .kts (Kotlin Script) files.
    """
    language = 'kotlin'
