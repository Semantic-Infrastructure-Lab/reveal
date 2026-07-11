"""Swift analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.swift', name='Swift', icon='🦅')
class SwiftAnalyzer(TreeSitterAnalyzer):
    """Analyze Swift source files.

    Extracts classes, functions, protocols, structs automatically using tree-sitter.
    Supports iOS, macOS, and Swift-based applications.
    """
    language = 'swift'

    # ── Protocols (BACK-403 pt 2) ───────────────────────────────────────────
    # Swift's protocol is its interface concept, parsed as a distinct
    # 'protocol_declaration' node (like TS's 'interface_declaration'), so it was
    # invisible to get_structure() (not in CLASS_NODE_TYPES). Conformance/
    # inheritance for both classes and protocols is a list of
    # 'inheritance_specifier' children, each wrapping a 'user_type' →
    # 'type_identifier' (verified via `reveal file.swift --show-ast`) — the base
    # class's TS-shaped dispatch looks for 'class_heritage'/'extends_type_clause'
    # (neither exists in Swift), so bases always returned []. Swift has no
    # abstract-class keyword, so _is_abstract_class_node stays the base no-op:
    # the protocol is the only abstraction form. Note tree-sitter-swift emits
    # 'class_declaration' for class/struct/enum alike (distinguished by a token
    # child) — a struct/enum conforming to a protocol correctly reads as an
    # implementing type, consistent with the "concrete type with bases" model.

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        interfaces = self._extract_interface_declarations('protocol_declaration')
        if interfaces:
            if head or tail or range:
                interfaces = self._apply_semantic_slice(interfaces, head, tail, range)
            structure['interfaces'] = interfaces
        return structure

    def _extract_class_bases(self, node) -> List[str]:
        if node.kind() in ('class_declaration', 'protocol_declaration'):
            return self._extract_swift_inheritance(node)
        return super()._extract_class_bases(node)

    def _extract_swift_inheritance(self, node) -> List[str]:
        # class Circle: Base, Drawable  /  protocol Drawable: Shape
        # Each conformed/inherited type is a separate 'inheritance_specifier'
        # child wrapping a 'user_type' → 'type_identifier' (or a bare
        # 'type_identifier' in simpler grammars — both handled).
        names: List[str] = []
        for child in _children(node):
            if child.kind() != 'inheritance_specifier':
                continue
            name = self._swift_specifier_name(child)
            if name:
                names.append(name)
        return names

    def _swift_specifier_name(self, specifier) -> Optional[str]:
        for child in _children(specifier):
            if child.kind() == 'user_type':
                for sub in _children(child):
                    if sub.kind() == 'type_identifier':
                        text = self._get_node_text(sub).strip()
                        if text:
                            return text
            elif child.kind() == 'type_identifier':
                text = self._get_node_text(child).strip()
                if text:
                    return text
        return None
