"""Zig analyzer using tree-sitter."""
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.zig', name='Zig', icon='⚡')
class ZigAnalyzer(TreeSitterAnalyzer):
    """Zig language analyzer.

    Zig is a general-purpose systems programming language
    designed as an alternative to C with simpler memory management.
    """
    language = 'zig'
