"""GDScript file analyzer - for Godot game engine scripts.

Migrated from regex-based parsing to tree-sitter for robust AST extraction.
Tree-sitter handles nested blocks, comments, and edge cases correctly.

Previous implementation: 197 lines of regex patterns
Current implementation: 15 lines using TreeSitterAnalyzer
"""

from typing import List, Optional

from ..core import node_children as _children
from ..core import node_prev_sibling as _prev_sibling
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
    # Godot 4.5 modules/gdscript/gdscript_parser.cpp registers these targets;
    # warning_ignore includes FUNCTION through CLASS_LEVEL. parse_program
    # flushes preceding annotations to the script at pure SCRIPT directives.
    # Leave @abstract undecoded: it can target script, class or function.
    _FUNCTION_ANNOTATIONS = frozenset({'rpc', 'warning_ignore'})
    _SCRIPT_ANNOTATIONS = frozenset({'tool', 'icon', 'static_unload'})

    def _annotation_name(self, node) -> Optional[str]:
        return next((self._get_node_text(child) for child in _children(node)
                     if _zero_arg(child, 'kind') == 'identifier'), None)

    def _extract_decorators(self, node) -> List[str]:
        """Function annotations precede the declaration as sibling nodes."""
        if _zero_arg(node, 'kind') != 'function_definition':
            return []
        decorators: List[str] = []
        sibling = _prev_sibling(node)
        while sibling is not None:
            kind = _zero_arg(sibling, 'kind')
            if kind == 'annotation':
                name = self._annotation_name(sibling)
                if name in self._SCRIPT_ANNOTATIONS:
                    break
                if name in self._FUNCTION_ANNOTATIONS:
                    decorators.insert(0, self._get_node_text(sibling))
            elif kind != 'comment':
                break
            sibling = _prev_sibling(sibling)
        return decorators

    def _extract_class_bases(self, node) -> List[str]:
        """Read only this class's extends type, retaining qualified names."""
        if _zero_arg(node, 'kind') != 'class_definition':
            return super()._extract_class_bases(node)
        return [self._get_node_text(base).strip()
                for child in _children(node)
                if _zero_arg(child, 'kind') == 'extends_statement'
                for base in _children(child)
                if _zero_arg(base, 'kind') == 'type']

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
