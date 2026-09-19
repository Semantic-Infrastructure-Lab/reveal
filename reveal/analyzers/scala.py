"""Scala analyzer using tree-sitter."""

from typing import List, Optional

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

    # ── Callee naming (BACK-915 slice 4) ──────────────────────────────────────

    # ── Node naming (BACK-918/BACK-915) ─────────────────────────────────────
    def _name_via_scala_operator_function(self, kids) -> Optional[str]:
        # Scala symbolic-name method definitions: `def +(o)`, `def ::(x)`,
        # `def *` (Slick projection), and any operator overload. The name is
        # an `operator_identifier` node (not an identifier-family kind any
        # earlier strategy recognizes), the sibling right after the `def`
        # keyword. Same invisibility class as Swift's operator overloads,
        # C#'s operator_declaration, and Ruby's `operator` kind: without
        # this, every symbolic-named def was absent from
        # --outline/get_structure(), so any call inside its body had no
        # caller scope to attribute to. Found via the calls-recall-oracle
        # Scala measurement (BACK-730, twelfth language): the sole residual
        # miss was a `Some(...)` call inside GitBucket's Slick `def *`
        # projection in Repository.scala.
        #
        # No language gate needed here (unlike when this lived on the
        # shared base) -- only reachable via ScalaAnalyzer polymorphism now
        # (BACK-918 push-down). Python's function_definition also has a
        # `def` keyword child, but is always followed by an `identifier`,
        # never an `operator_identifier`, so this would have been safe
        # unguarded even on the shared base; the explicit `language`
        # check that used to gate it is gone, dispatch now does that job.
        for i, child in enumerate(kids):
            if _zero_arg(child, 'kind') == 'def' and i + 1 < len(kids):
                nxt = kids[i + 1]
                if _zero_arg(nxt, 'kind') == 'operator_identifier':
                    text = self._get_node_text(nxt).strip()
                    if text:
                        return text
        return None
