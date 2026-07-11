"""Java analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.java', name='Java', icon='☕')
class JavaAnalyzer(TreeSitterAnalyzer):
    """Analyze Java source files.

    Extracts classes, interfaces, methods, imports automatically using tree-sitter.
    """
    language = 'java'

    # ── Interfaces (BACK-403 pt 2) ──────────────────────────────────────────
    # Java's 'interface_declaration' was previously invisible to get_structure()
    # entirely (not in CLASS_NODE_TYPES) and its bases fell through to the base
    # class's TS-shaped _extract_class_bases dispatch (which looks for
    # 'extends_type_clause' — a TS-only child), silently returning []. Both
    # gaps closed here with Java's real grammar shapes (verified via
    # `reveal file.java --show-ast`): class bases are two separate children
    # ('superclass' for extends, 'super_interfaces' for implements — both
    # wrapping a 'type_list' of 'type_identifier's for the interfaces case),
    # and interface extends is a third shape ('extends_interfaces' wrapping
    # its own 'type_list').

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        interfaces = self._extract_interface_declarations()
        if interfaces:
            if head or tail or range:
                interfaces = self._apply_semantic_slice(interfaces, head, tail, range)
            structure['interfaces'] = interfaces
        return structure

    def _extract_class_bases(self, node) -> List[str]:
        node_type = node.kind()
        if node_type == 'class_declaration':
            return self._extract_java_class_bases(node)
        if node_type == 'interface_declaration':
            return self._extract_java_interface_bases(node)
        return super()._extract_class_bases(node)

    def _extract_java_class_bases(self, node) -> List[str]:
        # class Dog extends Animal implements Derived, Other { ... }
        bases: List[str] = []
        for child in _children(node):
            if child.kind() == 'superclass':
                for c in _children(child):
                    if c.kind() == 'type_identifier':
                        text = self._get_node_text(c).strip()
                        if text:
                            bases.append(text)
            elif child.kind() == 'super_interfaces':
                bases.extend(self._extract_java_type_list(child))
        return bases

    def _extract_java_interface_bases(self, node) -> List[str]:
        # interface Derived extends Base, Other { ... }
        for child in _children(node):
            if child.kind() == 'extends_interfaces':
                return self._extract_java_type_list(child)
        return []

    def _is_abstract_class_node(self, node) -> bool:
        # public abstract class Shape { ... } — 'abstract' is a token child of
        # a single grouped 'modifiers' node, not a distinct node kind.
        for child in _children(node):
            if child.kind() != 'modifiers':
                continue
            for sub in _children(child):
                if sub.kind() == 'abstract':
                    return True
        return False

    def _extract_java_type_list(self, wrapper_node) -> List[str]:
        # Both 'super_interfaces' and 'extends_interfaces' wrap a single
        # 'type_list' child holding comma-separated 'type_identifier's.
        names: List[str] = []
        for child in _children(wrapper_node):
            if child.kind() != 'type_list':
                continue
            for item in _children(child):
                if item.kind() == 'type_identifier':
                    text = self._get_node_text(item).strip()
                    if text:
                        names.append(text)
        return names
