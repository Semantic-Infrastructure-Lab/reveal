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

    # ── extension declarations (BACK-8xx) ───────────────────────────────────
    # tree-sitter-swift parses `extension Foo: Protocol { ... }` as a
    # 'class_declaration' node (same kind as class/struct/enum, distinguished
    # only by a leading 'extension' token child) — so it's already walked by
    # the base class's CLASS_NODE_TYPES scan. But its name isn't a direct
    # `type_identifier` child the way `class Foo` / `struct Foo` are: it's
    # nested one level deeper, under a `user_type` child (the same shape
    # `_extract_swift_inheritance`'s conformance list already handles). Every
    # `_name_via_*` strategy in the shared base class's priority list only
    # looks at *direct* children, so `_get_node_name` returned None for every
    # extension — and `_extract_undecorated_classes` silently `continue`s on
    # any non-anonymous_class node with no name, dropping the ENTIRE
    # extension (not just its bases) from `classes`. Extension-based protocol
    # conformance (`extension SomeType: Drawable { ... }`) is a common Swift
    # idiom for adding conformance separately from a type's primary
    # declaration — this made all such conformances invisible to `contracts`.
    def _get_node_name(self, node) -> Optional[str]:
        if node.kind() == 'class_declaration' and self._is_swift_extension(node):
            name = self._swift_extension_type_name(node)
            if name:
                return name
        return super()._get_node_name(node)

    def _is_swift_extension(self, node) -> bool:
        for child in _children(node):
            if child.kind() == 'extension':
                return True
            if child.kind() in ('class', 'struct', 'enum', 'actor'):
                return False
        return False

    def _swift_extension_type_name(self, node) -> Optional[str]:
        # extension Foo: Bar { ... }  ->  user_type -> type_identifier
        # extension Foo.Bar { ... }   ->  user_type -> user_type -> type_identifier
        # (nested type reference; last type_identifier is the extended type's
        # own simple name, matching how its primary declaration is named).
        for child in _children(node):
            if child.kind() == 'user_type':
                type_identifiers: List[str] = []
                stack = [child]
                while stack:
                    n = stack.pop(0)
                    if n.kind() == 'type_identifier':
                        text = self._get_node_text(n).strip()
                        if text:
                            type_identifiers.append(text)
                    stack.extend(_children(n))
                return type_identifiers[-1] if type_identifiers else None
        return None

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
