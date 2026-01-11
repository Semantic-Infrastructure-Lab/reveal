"""Dart analyzer using tree-sitter."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.dart', name='Dart', icon='🎯')
class DartAnalyzer(TreeSitterAnalyzer):
    """Analyze Dart source files.

    Extracts classes, functions, widgets automatically using tree-sitter.
    Supports Flutter and Dart-based applications.
    """
    language = 'dart'
