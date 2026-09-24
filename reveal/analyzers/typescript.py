"""TypeScript (.ts) and TypeScript React (.tsx) file analyzers."""

from typing import List
from ..reveal_types import StructureItem
from ..core import node_children as _children
from ..core import node_prev_sibling as _prev_sibling
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer
from ._js_class_bases import JSClassBasesMixin
from ._js_function_values import JSFunctionValueMixin
from ._js_test_callbacks import JSTestCallbackMixin


class _TypeScriptBase(
    JSClassBasesMixin, JSFunctionValueMixin, JSTestCallbackMixin, TreeSitterAnalyzer
):
    """Shared extraction for TypeScript (.ts) and TypeScript React (.tsx)."""

    # ── Test callbacks ────────────────────────────────────────────────────
    # Arrow-function-as-const extraction (`const f = () => {}`) lives in the
    # JSFunctionValueMixin (_js_function_values.py) — it's a JS-family
    # grammar shape, not TypeScript-specific.
    # describe()/it() callback extraction (BACK-334/BACK-530) lives in
    # JSTestCallbackMixin (BACK-662: promoted out of this file so plain
    # JavaScript gets the same test-block support — see javascript.py).

    def _extract_functions(self) -> List[StructureItem]:
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
    # Built into the cached structure by the base (BACK-1409); this used to be
    # an uncached get_structure override doing the same walk.
    DECLARATION_CATEGORIES = {
        'interfaces': ('interface_declaration',),
        'types': ('type_alias_declaration',),
        'enums': ('enum_declaration',),
        'namespaces': ('internal_module',),  # `namespace NS {}` (BACK-1410)
    }


@register('.ts', name='TypeScript', icon='')
@register('.mts', name='TypeScript Module', icon='')
@register('.cts', name='TypeScript CommonJS', icon='')
class TypeScriptAnalyzer(_TypeScriptBase):
    """TypeScript (.ts) file analyzer."""
    language = 'typescript'


@register('.tsx', name='TypeScript React', icon='')
class TSXAnalyzer(_TypeScriptBase):
    """TypeScript React (.tsx) file analyzer — uses JSX-aware tree-sitter grammar."""
    language = 'tsx'
