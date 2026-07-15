"""Ruby analyzer using tree-sitter."""

from typing import List

from ..core import node_children as _children
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.rb', name='Ruby', icon='💎')
class RubyAnalyzer(TreeSitterAnalyzer):
    """Analyze Ruby source files.

    Extracts classes, methods, modules automatically using tree-sitter.
    """
    language = 'ruby'

    # ── Class bases (BACK-645) ──────────────────────────────────────────────
    # `class Foo < Bar` / `class Foo < ActiveSupport::Logger::SimpleFormatter`
    # previously fell through to the base class's Python-shaped
    # _extract_class_bases dispatch (looks for an 'argument_list' child —
    # Ruby's grammar has none), silently returning []. Real shape (verified
    # via `reveal file.rb --show-ast`): a 'superclass' child wrapping either a
    # bare 'constant' or a dotted-path 'scope_resolution' node — both cases
    # captured by taking the whole child's text (a nested scope_resolution
    # already renders its full 'A::B::C' text as one node).

    def _extract_class_bases(self, node) -> List[str]:
        if node.kind() != 'class':
            return super()._extract_class_bases(node)
        for child in _children(node):
            if child.kind() == 'superclass':
                for item in _children(child):
                    if item.kind() in ('constant', 'scope_resolution'):
                        text = self._get_node_text(item).strip()
                        return [text] if text else []
        return []
