"""Java analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
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
        if node_type in ('class_declaration', 'record_declaration'):
            # BACK-810/811: 'record_declaration' (Java 16+ records) shares
            # 'class_declaration''s 'superclass'/'super_interfaces' child
            # shapes (minus 'superclass', since a record can never extend a
            # class — verified via direct tree-sitter parse: `record Point(
            # int x, int y) implements Named { }` produces a bare
            # 'super_interfaces' child, no 'superclass'). Before this fix,
            # 'record_declaration' fell through to the base
            # TreeSitterAnalyzer._extract_class_bases, which only recognizes
            # 'class_declaration'/'abstract_class_declaration'/
            # 'interface_declaration' and otherwise returns [] — a Java
            # node fell straight through with no bases. A
            # record implementing an interface was therefore invisible to
            # `contracts`' implementer classification entirely (bases==[]
            # means _classify_ts's 'implementation' branch never fires).
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
                    name = self._java_simple_type_name(c)
                    if name:
                        bases.append(name)
            elif child.kind() == 'super_interfaces':
                bases.extend(self._extract_java_type_list(child))
        return bases

    def _java_simple_type_name(self, node) -> Optional[str]:
        """Peel a Java heritage-clause type node down to its simple name.

        BACK-810/BACK-812: `_extract_java_class_bases`/`_extract_java_type_list`
        previously only recognized a BARE `type_identifier` child directly
        under `superclass`/`type_list` — correct for `extends Animal` /
        `implements Foo`, but Java's grammar wraps a base carrying type
        arguments in a `generic_type` node (`extends Bar<Baz>`, `implements
        B<C>` — confirmed via direct tree-sitter parse: `generic_type` wraps
        a `type_identifier`/`scoped_type_identifier` PLUS a sibling
        `type_arguments` node) and wraps a package/outer-class-qualified
        base in a `scoped_type_identifier` (`extends pkg.Bar`, left-
        recursively nested for multi-segment paths like
        `java.util.Map.Entry`). Neither wrapper kind matched the old bare
        `type_identifier` check, so ANY generic or qualified base name was
        silently dropped from `bases` entirely — not a rare shape: it's the
        dominant idiom for a typed abstract-base/generic-interface
        implementer (`extends AbstractIndexAnalyzerProvider<ArabicAnalyzer>`,
        `implements ActionListener<Response>`, etc.), confirmed to account
        for the large majority of `contracts` implementer false negatives
        measured against samples/java (Elasticsearch).
        """
        kind = _zero_arg(node, 'kind')
        if kind == 'type_identifier':
            text = self._get_node_text(node).strip()
            return text or None
        if kind == 'generic_type':
            for c in _children(node):
                if _zero_arg(c, 'kind') in ('type_identifier', 'scoped_type_identifier'):
                    return self._java_simple_type_name(c)
            return None
        if kind == 'scoped_type_identifier':
            # Left-recursively nested (`java.util.Map.Entry` is
            # scoped_type_identifier(scoped_type_identifier(scoped_type_identifier(
            # type_identifier, type_identifier), type_identifier), type_identifier)) —
            # the base's own simple name is always the RIGHTMOST type_identifier child.
            last_name = None
            for c in _children(node):
                if _zero_arg(c, 'kind') == 'type_identifier':
                    last_name = self._get_node_text(c).strip()
            return last_name or None
        return None

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
        # 'type_list' child holding comma-separated base-type nodes — each
        # one a bare 'type_identifier', a 'generic_type' (has type args), or
        # a 'scoped_type_identifier' (package/outer-class qualified) — see
        # `_java_simple_type_name`.
        names: List[str] = []
        for child in _children(wrapper_node):
            if child.kind() != 'type_list':
                continue
            for item in _children(child):
                name = self._java_simple_type_name(item)
                if name:
                    names.append(name)
        return names
