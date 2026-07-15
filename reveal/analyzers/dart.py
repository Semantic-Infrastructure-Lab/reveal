"""Dart analyzer using tree-sitter."""

from typing import List

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.dart', name='Dart', icon='🎯')
class DartAnalyzer(TreeSitterAnalyzer):
    """Analyze Dart source files.

    Extracts classes, functions, widgets automatically using tree-sitter.
    Supports Flutter and Dart-based applications.
    """
    language = 'dart'

    # ── Class bases (BACK-645) ──────────────────────────────────────────────
    # `class Foo extends Bar implements Baz, Qux { ... }` previously fell
    # through to the base class's Python-shaped _extract_class_bases dispatch
    # (looks for an 'argument_list' child — Dart's grammar has none), silently
    # returning []. Real shape (verified via `reveal file.dart --show-ast`):
    # Dart's 'class_definition' node kind collides with Python's/Scala's (all
    # three use the same tree-sitter node name), so this only fires for
    # actual Dart files via the per-analyzer language dispatch. Two separate
    # wrapper children — 'superclass' (extends) and 'interfaces' (implements)
    # — each hold direct 'type_identifier' children; a generic superclass
    # like 'extends Bar<T>' still exposes 'Bar' as a direct child with 'T'
    # nested one level deeper inside 'type_arguments', so the direct-children
    # filter naturally excludes the type parameter.

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') != 'class_definition':
            return super()._extract_class_bases(node)
        bases = []
        for child in _children(node):
            if _zero_arg(child, 'kind') in ('superclass', 'interfaces'):
                for item in _children(child):
                    if _zero_arg(item, 'kind') == 'type_identifier':
                        text = self._get_node_text(item).strip()
                        if text:
                            bases.append(text)
        return bases
