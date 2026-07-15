"""Scala analyzer using tree-sitter."""

from typing import List

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.scala', name='Scala', icon='🔴')
class ScalaAnalyzer(TreeSitterAnalyzer):
    """Analyze Scala source files.

    Extracts classes, objects, traits, and functions automatically using tree-sitter.
    """
    language = 'scala'

    # ── Class bases (BACK-645) ──────────────────────────────────────────────
    # `class Foo[T] extends Bar[T] with Baz { ... }` previously fell through
    # to the base class's Python-shaped _extract_class_bases dispatch (looks
    # for an 'argument_list' child — Scala's grammar has none), silently
    # returning []. Real shape (verified via `reveal file.scala --show-ast`):
    # Scala's 'class_definition' node kind collides with Python's (both use
    # the same tree-sitter node name), so this only fires for actual Scala
    # files via the per-analyzer language dispatch — never mis-triggers on
    # Python. An 'extends_clause' child holds both the superclass and every
    # 'with'-mixed-in trait as sibling 'type_identifier'/'generic_type'
    # entries (no distinct node marks the 'with' boundary), so both are
    # collected into one flat bases list — same shape as Java's
    # implements-list handling.

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') != 'class_definition':
            return super()._extract_class_bases(node)
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'extends_clause':
                bases = []
                for item in _children(child):
                    if _zero_arg(item, 'kind') == 'type_identifier':
                        text = self._get_node_text(item).strip()
                        if text:
                            bases.append(text)
                    elif _zero_arg(item, 'kind') == 'generic_type':
                        base = self._extract_generic_type_base(item)
                        if base:
                            bases.append(base)
                return bases
        return []
