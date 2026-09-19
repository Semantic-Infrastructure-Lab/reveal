"""Go file analyzer - tree-sitter based."""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.go', name='Go', icon='')
class GoAnalyzer(TreeSitterAnalyzer):
    """Go file analyzer.

    Structs and functions come from the shared tree-sitter walk. Interfaces
    (BACK-1088) are a distinct `interface_type` node under `type_spec` and are
    collected into `structure['interfaces']`, like Java/C#/Swift.
    """
    language = 'go'

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        interfaces = self._extract_interface_declarations('interface_type')
        if interfaces:
            if head or tail or range:
                interfaces = self._apply_semantic_slice(interfaces, head, tail, range)
            structure['interfaces'] = interfaces
        return structure

    def _get_node_name(self, node) -> Optional[str]:
        # `type Foo interface {...}`: like struct_type, the name is a sibling
        # type_identifier under type_spec, not a child of interface_type.
        if _zero_arg(node, 'kind') == 'interface_type':
            return self._struct_type_name(node)
        return super()._get_node_name(node)

    def _extract_class_bases(self, node) -> List[str]:
        """Embedded types: interface embedding (`type_elem` children of an
        interface_type) and struct embedding (a `field_declaration` carrying a
        type but no field name). Go has no inheritance, so embedding is the
        closest thing to bases."""
        kind = _zero_arg(node, 'kind')
        if kind == 'interface_type':
            return [n for n in (self._embedded_type_name(c) for c in _children(node)
                                if _zero_arg(c, 'kind') == 'type_elem') if n]
        if kind == 'struct_type':
            fields = [f for lst in _children(node)
                      if _zero_arg(lst, 'kind') == 'field_declaration_list'
                      for f in _children(lst) if _zero_arg(f, 'kind') == 'field_declaration']
            return [n for n in (self._embedded_type_name(f) for f in fields
                                if not any(_zero_arg(c, 'kind') == 'field_identifier'
                                           for c in _children(f))) if n]
        return super()._extract_class_bases(node)

    def _embedded_type_name(self, node) -> Optional[str]:
        """Text of the embedded type in a type_elem/field_declaration (a leading
        `*` is dropped). None for unions/constraints (`~int | string`), which
        have no single type child."""
        for child in _children(node):
            if _zero_arg(child, 'kind') in ('type_identifier', 'qualified_type'):
                return self._get_node_text(child)
        return None
