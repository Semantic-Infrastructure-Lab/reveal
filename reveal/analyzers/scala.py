"""Scala analyzer using tree-sitter."""

from typing import List, Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer

# Scala type-node kinds that can appear as the constructed type in an
# `instance_expression` (`new X(...)`) — used by _scala_simple_type_name /
# nav_calls._extract_scala_instance_callee to peel qualified/generic types
# down to the simple class name (BACK-747).
_SCALA_TYPE_KINDS = frozenset({
    'type_identifier', 'generic_type', 'stable_type_identifier', 'field_expression',
})


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

    def _callee_name_scala_instance(self, call_node) -> Optional[str]:
        # Scala: new ClassName(args) / new ArrayList[String](args) /
        # new java.io.File(args) — instance_expression. A DISTINCT node
        # kind from PHP/C#/C++'s object_creation_expression/new_expression
        # despite the identical source shape (BACK-730 note #17):
        # child(0) is the literal 'new' token, so the generic
        # _callee_name_generic fallback returned the bare keyword "new" as
        # the callee, not the class name. Mirrors
        # nav_calls.py:_extract_scala_instance_callee (the ast:// nav path,
        # fixed separately under BACK-718/720 — that fix never touched this
        # get_structure()/calls:// path, which is exactly the gap flagged
        # in BACK-730 note #17).
        for child in _children(call_node):
            if _zero_arg(child, 'kind') in _SCALA_TYPE_KINDS:
                name = self._scala_simple_type_name(child)
                if name:
                    return f"new {name}"
        return None

    def _scala_simple_type_name(self, type_node) -> Optional[str]:
        # Simple (last) name of a Scala constructor type, unwrapping every
        # nesting seen in practice:
        #   type_identifier            -> `File`          (new File)
        #   generic_type               -> recurse on base (new Array[Byte])
        #   stable_type_identifier     -> trailing name   (new java.io.File,
        #                                                   BACK-747; also the
        #                                                   base of a qualified
        #                                                   generic new scala.
        #                                                   Array[Byte])
        #   field_expression           -> last dotted seg (older grammar shape)
        kind = _zero_arg(type_node, 'kind')
        if kind == 'type_identifier':
            return self._get_node_text(type_node).strip() or None
        if kind == 'generic_type':
            base = next((c for c in _children(type_node)
                         if _zero_arg(c, 'kind') in _SCALA_TYPE_KINDS), None)
            return self._scala_simple_type_name(base) if base is not None else None
        if kind == 'stable_type_identifier':
            names = [c for c in _children(type_node)
                     if _zero_arg(c, 'kind') == 'type_identifier']
            return (self._get_node_text(names[-1]).strip() or None) if names else None
        if kind == 'field_expression':
            text = self._get_node_text(type_node).strip()
            return text.split('.')[-1] if text else None
        return None

    def _callee_name_scala_infix(self, call_node) -> Optional[str]:
        # Scala infix method calls: `a :: b`, `list map doubler`,
        # `xs filterNot q` — every single-argument method can be called without
        # a dot or parens, and operators ARE methods (`a + b` desugars to
        # `a.+(b)`). tree-sitter parses all of these to `infix_expression`, a
        # node kind that was entirely absent from CALL_NODE_TYPES, so every
        # infix call was silently invisible to calls:// (BACK-746, twelfth
        # calls-recall language). The `operator` field holds the method name —
        # an `identifier` for alphabetic infix (`map`, `filterNot`) or an
        # `operator_identifier` for symbolic operators (`::`, `+`). Emit the
        # bare name (no "new "/qualifier), matching the plain-call convention.
        op = call_node.child_by_field_name('operator')
        if op is not None:
            text = self._get_node_text(op).strip()
            if text:
                return text
        # Fallback: middle child (left, OP, right) if the field is unavailable.
        kids = _children(call_node)
        if len(kids) >= 3:
            text = self._get_node_text(kids[1]).strip()
            if text:
                return text
        return None
