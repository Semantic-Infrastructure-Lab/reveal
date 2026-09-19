"""GDScript file analyzer - for Godot game engine scripts.

Migrated from regex-based parsing to tree-sitter for robust AST extraction.
Tree-sitter handles nested blocks, comments, and edge cases correctly.

Previous implementation: 197 lines of regex patterns
Current implementation: 15 lines using TreeSitterAnalyzer
"""

from typing import Optional

from ..core import node_children as _children
from ..core.callees.gdscript import site_for as gdscript_site_for
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.gd', name='GDScript', icon='')
class GDScriptAnalyzer(TreeSitterAnalyzer):
    """GDScript file analyzer for Godot Engine.

    Extracts classes, functions, signals, and variables using tree-sitter.
    Full GDScript support in 3 lines - tree-sitter handles all parsing!
    """
    language = 'gdscript'
    IMPORTS_VIA_EXTRACTOR = True  # BACK-1089

    # ── Callee naming (BACK-915 slice 4) ──────────────────────────────────────

    CALLEE_KIND_HOOKS = {'attribute_call': '_callee_name_attribute_call'}

    def _callee_name_attribute_call(self, call_node) -> Optional[str]:
        """GDScript `self.foo()` / `obj.method()` / `Class.new()` / chained
        `a.b().c()` -- 'attribute_call'. Unlike Java/Ruby's method_invocation/
        call (an explicit 'object'/'receiver' field on the SAME node), the
        receiver here is a preceding SIBLING inside the enclosing 'attribute'
        node's flat (receiver, '.', segment, '.', segment, ...) child list --
        this node itself only ever holds its own name + arguments. Reconstructs
        the qualified callee name (`self.setup`, `obj.method`, `Foo.new`,
        chained `a.b().c`) by slicing raw source text from the enclosing
        attribute's start up to (excluding) the '.' immediately preceding this
        node -- there's no receiver *node* to read text from directly, so this
        mirrors Java/Ruby's receiver-qualified convention using a text span
        instead of a field lookup.
        """
        site = gdscript_site_for(call_node, self._get_node_text)
        if site is not None:
            return site.qualified if site.member else None
        # An `attribute_call` outside an `attribute` node has no receiver: just its name.
        name_node = next(
            (c for c in _children(call_node) if _zero_arg(c, 'kind') == 'identifier'), None
        )
        return self._get_node_text(name_node) if name_node is not None else None
