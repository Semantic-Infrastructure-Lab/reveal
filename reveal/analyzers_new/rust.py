"""Rust file analyzer - tree-sitter based."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.rs', name='Rust', icon='🦀')
class RustAnalyzer(TreeSitterAnalyzer):
    """Rust file analyzer.

    Full Rust support in 3 lines!
    """
    language = 'rust'
