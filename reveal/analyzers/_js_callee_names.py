"""JS-family callee-name resolution for `new` expressions.

Shared by JavaScript and TypeScript analyzers (BACK-915 slice 4): `new
Foo(args)` parses to a `new_expression` node, the SAME kind C++ and Dart use
for their own `new`-shaped calls, but with a distinct grammar shape (the
callee sits in a 'constructor' field, not C++'s 'type' field or Dart's
flat, field-less siblings). treesitter.py's `_callee_name_new_expression`
dispatches structurally by which field is populated and defers to this
mixin's `_callee_name_js_new` hook for the 'constructor'-field case — same
reasoning as `JSClassBasesMixin`/`JSTestCallbackMixin` one file over: this
is JS-family, not TypeScript-only, so plain JavaScript needs it too.
"""

from typing import Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg


class JSCalleeNameMixin:
    """Mix into any JS-family `TreeSitterAnalyzer` subclass for `new` callee-name support."""

    def _callee_name_js_new(self, call_node) -> Optional[str]:
        # JS/TS/TSX: new ClassName(args) / new ns.ClassName(args) —
        # new_expression, the SAME node kind C++ uses but a completely
        # different grammar shape: the callee sits in a field named
        # 'constructor' (identifier, or member_expression for a dotted form
        # like `new a.b.ClassName()`), not C++'s 'type' field.
        # child_by_field_name('type') is always None on a JS new_expression,
        # so every `new Foo()` call was silently invisible to calls:// (found
        # via the calls-recall-oracle JS/TSX pre-flight dump, 13th language,
        # BACK-730). Dispatched structurally by treesitter.py's
        # _callee_name_new_expression (checks which field is populated)
        # rather than by self.language, so tree-sitter fallback languages
        # with no dedicated analyzer class still resolve correctly.
        ctor_node = call_node.child_by_field_name('constructor')
        if ctor_node is None:
            return None
        kind = _zero_arg(ctor_node, 'kind')
        if kind == 'identifier':
            name = self._get_node_text(ctor_node).strip()
            return f"new {name}" if name else None
        if kind == 'member_expression':
            prop = None
            for child in _children(ctor_node):
                if _zero_arg(child, 'kind') == 'property_identifier':
                    prop = child
            if prop is not None:
                name = self._get_node_text(prop).strip()
                return f"new {name}" if name else None
        return None
