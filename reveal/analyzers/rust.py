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

    def _is_trait_impl_method(self, node) -> bool:
        """BACK-1291: inside an `impl_item` that names a trait (`impl Display for A`),
        as opposed to an inherent `impl A`. Nested fns inside a method body stop at
        the first enclosing function so a helper isn't mistaken for a trait method."""
        parent = _zero_arg(node, 'parent')
        while parent is not None:
            kind = _zero_arg(parent, 'kind')
            if kind == 'impl_item':
                return parent.child_by_field_name('trait') is not None
            if kind == 'function_item':
                return False
            parent = _zero_arg(parent, 'parent')
        return False

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
