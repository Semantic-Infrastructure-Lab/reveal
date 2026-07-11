"""Kotlin analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional, Set

from ..core import node_children as _children
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.kt', name='Kotlin', icon='🔷')
@register('.kts', name='Kotlin Script', icon='📜')
class KotlinAnalyzer(TreeSitterAnalyzer):
    """Analyze Kotlin source files.

    Extracts classes, functions, interfaces automatically using tree-sitter.
    Supports both .kt (Kotlin) and .kts (Kotlin Script) files.
    """
    language = 'kotlin'

    # ── Interfaces (BACK-403 pt 2) ──────────────────────────────────────────
    # Unlike Java/C#/TS, Kotlin has no distinct interface node kind: an
    # interface parses as a 'class_declaration' carrying an 'interface' token
    # child (a regular class carries a 'class' token; an enum class carries both
    # 'enum' and 'class') — verified via `reveal file.kt --show-ast`. So every
    # interface was already extracted, but mislabelled as a class. We repartition
    # here: after the base walk populates structure['classes'] with all
    # class_declarations, interface-flavoured ones are moved into an
    # 'interfaces' bucket so the contracts classifier sees them as contracts,
    # not concrete implementations. Bases (for both classes and interfaces) are a
    # list of 'delegation_specifier' children, each wrapping either a 'user_type'
    # (plain supertype) or a 'constructor_invocation' → 'user_type' (superclass
    # constructor call). Abstract classes carry a 'modifiers' → 'abstract' token.

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        interface_lines = self._interface_declaration_lines()
        if not interface_lines:
            return structure
        classes = structure.get('classes', [])
        remaining: List[Dict[str, Any]] = []
        interfaces: List[Dict[str, Any]] = []
        for cls in classes:
            if cls.get('line') in interface_lines:
                # An interface can't be abstract-modified; drop the stray flag if
                # the base walk happened to set one so it renders as a contract.
                cls.pop('is_abstract', None)
                interfaces.append(cls)
            else:
                remaining.append(cls)
        if interfaces:
            structure['classes'] = remaining
            structure['interfaces'] = interfaces
        return structure

    def _interface_declaration_lines(self) -> Set[int]:
        """Start lines of class_declaration nodes that are actually interfaces.

        A Kotlin interface is a class_declaration whose direct children include
        an 'interface' token (regular/enum classes have a 'class' token instead).
        """
        lines: Set[int] = set()
        for node in self._find_nodes_by_type('class_declaration'):
            for child in _children(node):
                if child.kind() == 'interface':
                    lines.add(node.start_position().row + 1)
                    break
        return lines

    def _extract_class_bases(self, node) -> List[str]:
        if node.kind() == 'class_declaration':
            return self._extract_kotlin_delegation(node)
        return super()._extract_class_bases(node)

    def _extract_kotlin_delegation(self, node) -> List[str]:
        # class Circle : Base(), Drawable  /  interface Drawable : Shape
        names: List[str] = []
        for child in _children(node):
            if child.kind() != 'delegation_specifier':
                continue
            name = self._kotlin_delegation_name(child)
            if name:
                names.append(name)
        return names

    def _kotlin_delegation_name(self, specifier) -> Optional[str]:
        for child in _children(specifier):
            if child.kind() == 'constructor_invocation':
                # Base() — the invoked supertype is a nested user_type
                name = self._kotlin_user_type_name(child)
                if name:
                    return name
            elif child.kind() == 'user_type':
                return self._kotlin_first_type_identifier(child)
        return None

    def _kotlin_user_type_name(self, container) -> Optional[str]:
        for child in _children(container):
            if child.kind() == 'user_type':
                return self._kotlin_first_type_identifier(child)
        return None

    def _kotlin_first_type_identifier(self, user_type) -> Optional[str]:
        # Take only the leading type_identifier (the base name); skip nested
        # type_arguments so a generic supertype List<Foo> yields 'List', not 'Foo'.
        for child in _children(user_type):
            if child.kind() == 'type_identifier':
                text = self._get_node_text(child).strip()
                if text:
                    return text
        return None

    def _is_abstract_class_node(self, node) -> bool:
        # abstract class Base { ... } — unlike Java's flat 'modifiers' → 'abstract',
        # Kotlin wraps it a level deeper: 'modifiers' → 'inheritance_modifier' →
        # 'abstract' token (verified via --show-ast). Scan the modifiers subtree
        # for the token so the exact wrapper kind doesn't have to be hard-coded.
        for child in _children(node):
            if child.kind() != 'modifiers':
                continue
            for sub in _children(child):
                if sub.kind() == 'abstract':
                    return True
                for leaf in _children(sub):
                    if leaf.kind() == 'abstract':
                        return True
        return False
