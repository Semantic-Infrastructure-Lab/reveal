"""TypeScript (.ts) and TypeScript React (.tsx) file analyzers."""

from typing import Any, Dict, List, Optional
from ..core import node_children as _children
from ..core import node_prev_sibling as _prev_sibling
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer
from ._js_callee_names import JSCalleeNameMixin
from ._js_class_bases import JSClassBasesMixin
from ._js_test_callbacks import JSTestCallbackMixin


class _TypeScriptBase(
    JSCalleeNameMixin, JSClassBasesMixin, JSTestCallbackMixin, TreeSitterAnalyzer
):
    """Shared extraction for TypeScript (.ts) and TypeScript React (.tsx)."""

    # ── Test callbacks ────────────────────────────────────────────────────
    # Arrow-function-as-const extraction (`const f = () => {}`) lives in the
    # shared TreeSitterAnalyzer base (treesitter.py) — it's a JS-family
    # grammar shape, not TypeScript-specific; see that class's
    # _extract_arrow_functions()/_find_named_arrow_function() docstrings.
    # describe()/it() callback extraction (BACK-334/BACK-530) lives in
    # JSTestCallbackMixin (BACK-662: promoted out of this file so plain
    # JavaScript gets the same test-block support — see javascript.py).

    def _extract_functions(self) -> List[Dict[str, Any]]:
        funcs = super()._extract_functions()
        funcs.extend(self._extract_test_callbacks())
        return funcs

    def _extract_decorators(self, node) -> List[str]:
        """TypeScript decorators (BACK-1087, D1): a class-level '@Foo'/'@Foo(...)'
        is a direct 'decorator' child of the class_declaration node itself --
        verified via direct tree-sitter parse of `@Component class Foo {}`.

        Method-level decorators (`class Foo { @Input() bar() {} }`) are a
        PRECEDING SIBLING of the method_definition node inside class_body,
        not a child of the method node -- same shape class as Rust's
        attribute_item (BACK-1087 Phase-2b), verified via direct tree-sitter
        parse of `class Foo { @Input() bar() {} }`. Walk backward through
        preceding siblings collecting consecutive 'decorator' nodes.
        """
        if _zero_arg(node, 'kind') == 'method_definition':
            decorators: List[str] = []
            sib = _prev_sibling(node)
            while sib is not None and _zero_arg(sib, 'kind') == 'decorator':
                decorators.insert(0, self._get_node_text(sib))
                sib = _prev_sibling(sib)
            return decorators
        return [
            self._get_node_text(child)
            for child in _children(node)
            if _zero_arg(child, 'kind') == 'decorator'
        ]

    # ── TypeScript type declarations ──────────────────────────────────────────

    def _extract_ts_types(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract interface, type alias, and enum declarations."""
        interfaces: List[Dict[str, Any]] = []
        types: List[Dict[str, Any]] = []
        enums: List[Dict[str, Any]] = []

        for node_type, bucket in (
            ('interface_declaration', interfaces),
            ('type_alias_declaration', types),
            ('enum_declaration', enums),
        ):
            for node in self._find_nodes_by_type(node_type):
                name = self._get_node_name(node)
                if not name:
                    continue
                line_start = _zero_arg(node, 'start_position').row + 1
                line_end = _zero_arg(node, 'end_position').row + 1
                entry: Dict[str, Any] = {
                    'line': line_start,
                    'line_end': line_end,
                    'name': name,
                    'line_count': line_end - line_start + 1,
                    'decorators': [],
                    'bases': self._extract_class_bases(node),
                }
                bucket.append(entry)

        return {'interfaces': interfaces, 'types': types, 'enums': enums}

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        for key, items in self._extract_ts_types().items():
            if items:
                if head or tail or range:
                    items = self._apply_semantic_slice(items, head, tail, range)
                structure[key] = items
        return structure


@register('.ts', name='TypeScript', icon='')
class TypeScriptAnalyzer(_TypeScriptBase):
    """TypeScript (.ts) file analyzer."""
    language = 'typescript'


@register('.tsx', name='TypeScript React', icon='')
class TSXAnalyzer(_TypeScriptBase):
    """TypeScript React (.tsx) file analyzer — uses JSX-aware tree-sitter grammar."""
    language = 'tsx'
