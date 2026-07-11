"""C# analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.cs', name='C#', icon='#️⃣')
class CSharpAnalyzer(TreeSitterAnalyzer):
    """Analyze C# source files.

    Extracts classes, interfaces, methods automatically using tree-sitter.
    """
    language = 'csharp'

    # ── Interfaces (BACK-403 pt 2) ──────────────────────────────────────────
    # C# shares tree-sitter's 'interface_declaration'/'class_declaration' node
    # kinds with Java and TS, but its own heritage shape is a single 'base_list'
    # child holding every comma-separated base (no extends/implements split —
    # C#'s ': Base, IFoo' syntax doesn't distinguish them, verified via
    # `reveal file.cs --show-ast`). Previously interfaces were invisible to
    # get_structure() (not in CLASS_NODE_TYPES) and class/interface bases fell
    # through to the base class's TS-shaped dispatch, which looks for
    # 'class_heritage'/'extends_type_clause' — neither exists in C#'s grammar —
    # so bases always returned [].

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
        if node_type in ('class_declaration', 'interface_declaration'):
            return self._extract_csharp_base_list(node)
        return super()._extract_class_bases(node)

    def _is_abstract_class_node(self, node) -> bool:
        # public abstract class Shape { ... } — C# emits each modifier keyword
        # as its own separate 'modifier' wrapper node (unlike Java's single
        # grouped 'modifiers' node), each containing one token child.
        for child in _children(node):
            if child.kind() != 'modifier':
                continue
            for sub in _children(child):
                if sub.kind() == 'abstract':
                    return True
        return False

    def _extract_csharp_base_list(self, node) -> List[str]:
        # class Dog : Animal, IAnimal { ... }  /  interface IDerived : IBase { ... }
        base_list = next(
            (c for c in _children(node) if c.kind() == 'base_list'), None
        )
        if base_list is None:
            return []
        names: List[str] = []
        for item in _children(base_list):
            name = self._csharp_base_item_name(item)
            if name:
                names.append(name)
        return names

    def _csharp_base_item_name(self, item) -> Optional[str]:
        kind = item.kind()
        if kind == 'generic_name':
            # IFoo<T> — extract the base identifier, drop the type args
            ident = next(
                (g for g in _children(item) if g.kind() == 'identifier'), None
            )
            return self._get_node_text(ident).strip() if ident is not None else None
        if kind in ('identifier', 'type_identifier'):
            return self._get_node_text(item).strip() or None
        return None
