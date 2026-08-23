"""Rust file analyzer - tree-sitter based."""

from typing import List

from ..core import node_prev_sibling as _prev_sibling
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.rs', name='Rust', icon='')
class RustAnalyzer(TreeSitterAnalyzer):
    """Rust file analyzer.

    Full Rust support in 3 lines!
    """
    language = 'rust'

    def _extract_decorators(self, node) -> List[str]:
        """Rust attributes (BACK-1087, D1 Phase-2b): unlike every other
        Phase-2a/2b language (Java/C#/Kotlin/Swift/PHP all attach annotations
        as a direct child), tree-sitter emits `#[derive(Debug)]` etc. as a
        PRECEDING SIBLING of the struct/fn/enum/impl/trait node it annotates,
        not a child of it -- verified via direct tree-sitter parse of
        `#[derive(Debug)]\nstruct Reporter { total: i32 }`. Walk backward
        through preceding siblings collecting consecutive 'attribute_item'
        nodes, stopping at the first non-attribute sibling (e.g. a comment
        means the run of attributes ended before this item).
        """
        decorators: List[str] = []
        sib = _prev_sibling(node)
        while sib is not None and _zero_arg(sib, 'kind') == 'attribute_item':
            decorators.insert(0, self._get_node_text(sib))
            sib = _prev_sibling(sib)
        return decorators
