"""Go file analyzer - tree-sitter based."""

from typing import List, Optional

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
    IMPORTS_VIA_EXTRACTOR = True  # BACK-1089
    DECLARATION_CATEGORIES = {'interfaces': ('interface_type',)}

    def _get_node_name(self, node) -> Optional[str]:
        # `type Foo interface {...}`: like struct_type, the name is a sibling
        # type_identifier under type_spec, not a child of interface_type.
        if _zero_arg(node, 'kind') == 'interface_type':
            return self._struct_type_name(node)
        return super()._get_node_name(node)

    def _extraction_node(self, node):
        """`type Foo struct {...}` parses the body as a bare `struct_type` /
        `interface_type` under `type_spec`; the `type` keyword and the name sit
        outside it. Widen to the whole declaration (`type_declaration`) when it
        declares just this type; in a grouped `type ( ... )` block, to the one
        spec (`Foo struct {...}`)."""
        if _zero_arg(node, 'kind') not in ('struct_type', 'interface_type'):
            return node
        spec = _zero_arg(node, 'parent')
        if spec is None or _zero_arg(spec, 'kind') not in ('type_spec', 'type_alias'):
            return node
        decl = _zero_arg(spec, 'parent')
        if decl is not None and _zero_arg(decl, 'kind') == 'type_declaration':
            specs = [c for c in _children(decl) if _zero_arg(c, 'kind') in ('type_spec', 'type_alias')]
            if len(specs) == 1:
                return decl
        return spec

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
