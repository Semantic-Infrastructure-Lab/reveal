"""TypeScript-shaped class/interface base-class extraction.

Shared by JavaScript and TypeScript analyzers (BACK-915): the grammar shapes
here (`class_heritage` → `extends_clause`/`implements_clause`,
`extends_type_clause` for interfaces) come from tree-sitter-typescript, but
plain JavaScript's grammar produces the same `class_declaration`/
`class_heritage` node kinds for `class Foo extends Bar { ... }` (see the
BACK-631 note in `_extract_ts_heritage_bases` below) — so this logic is
JS-family, not TypeScript-only, same reasoning as `JSTestCallbackMixin`
(BACK-662) one file over.

`_extract_generic_type_base` is intentionally NOT here — it's also called
directly by `analyzers/scala.py`, so it stays a shared method on
`TreeSitterAnalyzer` in treesitter.py instead of living behind this mixin.
"""

from typing import List

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg


class JSClassBasesMixin:
    """Mix into any JS-family `TreeSitterAnalyzer` subclass for extends/implements support."""

    def _extract_class_bases(self, node) -> List[str]:
        node_type = node.kind()
        if node_type in ('class_declaration', 'abstract_class_declaration'):
            return self._extract_ts_class_bases(node)
        if node_type == 'interface_declaration':
            return self._extract_ts_interface_bases(node)
        return super()._extract_class_bases(node)

    def _extract_ts_class_bases(self, node) -> List[str]:
        # class Foo extends Bar implements IBaz, IQux { ... }
        for child in _children(node):
            if child.kind() == 'class_heritage':
                return self._extract_ts_heritage_bases(child)
        return []

    def _extract_ts_heritage_bases(self, heritage) -> List[str]:
        # BACK-631: the plain-JavaScript grammar has no extends_clause/
        # implements_clause wrapper — `class_heritage` holds the `extends`
        # keyword and the base identifier as flat siblings (TS wraps them in
        # extends_clause). Collect both shapes: nested clause children (TS)
        # and bare identifier/type_identifier children directly under
        # `heritage` (JS) — JS has no `implements`, so only extends applies.
        bases = []
        for heritage_child in _children(heritage):
            if heritage_child.kind() == 'extends_clause':
                bases.extend(self._extract_ts_extends_names(heritage_child))
            elif heritage_child.kind() == 'implements_clause':
                bases.extend(self._extract_ts_implements_names(heritage_child))
            elif _zero_arg(heritage_child, 'kind') in ('identifier', 'type_identifier'):
                text = self._get_node_text(heritage_child).strip()
                if text:
                    bases.append(text)
        return bases

    def _extract_ts_extends_names(self, extends_clause) -> List[str]:
        # extends_clause: "extends <identifier>" or "extends <ns>.<identifier>"
        # (generic type args, if any, are flat siblings here — not nested in
        # a generic_type wrapper — so a dotted base like `React.Component`
        # or `React.Component<Props, State>` both surface as a bare
        # member_expression child; BACK-719 dogfood found this tail-dropped
        # entirely, silently emptying `bases` for any class extending a
        # namespaced base, e.g. every React.Component-based class component)
        names = []
        for item in _children(extends_clause):
            item_kind = _zero_arg(item, 'kind')
            if item_kind in ('identifier', 'type_identifier'):
                text = self._get_node_text(item).strip()
                if text:
                    names.append(text)
            elif item_kind == 'member_expression':
                for child in _children(item):
                    if _zero_arg(child, 'kind') == 'property_identifier':
                        text = self._get_node_text(child).strip()
                        if text:
                            names.append(text)
        return names

    def _extract_ts_implements_names(self, implements_clause) -> List[str]:
        # implements_clause: "implements TypeA, TypeB, ..."
        names = []
        for item in _children(implements_clause):
            if item.kind() == 'generic_type':
                # e.g. implements IFoo<T> — extract base name
                base = self._extract_generic_type_base(item)
                if base:
                    names.append(base)
            elif item.kind() in ('type_identifier', 'identifier'):
                text = self._get_node_text(item).strip()
                if text:
                    names.append(text)
        return names

    def _extract_ts_interface_bases(self, node) -> List[str]:
        # interface IFoo extends IBar, IBaz { ... }
        for child in _children(node):
            if child.kind() == 'extends_type_clause':
                bases = []
                for item in _children(child):
                    if item.kind() in ('type_identifier', 'identifier'):
                        text = self._get_node_text(item).strip()
                        if text:
                            bases.append(text)
                return bases
        return []
