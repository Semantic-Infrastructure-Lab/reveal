"""JS-family function-as-value extraction: `const f = () => {}` and class-field arrows.

Shared by JavaScript, TypeScript and TSX analyzers (BACK-1280: moved out of the
`TreeSitterAnalyzer` base, which used to run this for every language). The grammar shapes
here (`lexical_declaration > variable_declarator`, `public_field_definition` /
`field_definition`) exist only in JS-family grammars, so a language that does not mix this
in never pays for the scan. Same mixin pattern as `JSClassBasesMixin` and
`JSTestCallbackMixin` alongside.
"""

from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..reveal_types import StructureItem

if TYPE_CHECKING:
    from ..treesitter import TreeSitterAnalyzer as _Base
else:
    _Base = object


class JSFunctionValueMixin(_Base):
    """Mix in ahead of `TreeSitterAnalyzer` for arrow-const / class-field function extraction."""

    # ── JS-family class-field arrow method (`foo = (...) => {}`) ────────────
    # BACK-519: `public_field_definition` (TS/TSX) / `field_definition` (JS)
    # class members were entirely absent from FUNCTION_NODE_TYPES, so every
    # class method written as an arrow-function field (a common pattern for
    # binding `this`, e.g. React class components) was invisible to
    # get_structure()/calls://check/hotspots/testability/element-nav with no
    # warning. Verified on a real 426KB TSX file (excalidraw's App.tsx): 113
    # such fields class-wide, 0 extracted pre-fix. Only node kinds unique to
    # JS-family grammars, so this is a no-op for every other language.

    _CLASS_FIELD_NODE_TYPES = ('public_field_definition', 'field_definition')

    def _extract_class_field_functions(self) -> List[StructureItem]:
        """Extract class-field arrow/function-expression methods (`foo = () => {}`)."""
        funcs = []
        for field_type in self._CLASS_FIELD_NODE_TYPES:
            for field_node in self._find_nodes_by_type(field_type):
                name_node = value_node = None
                for ch in _children(field_node):
                    if _zero_arg(ch, 'kind') in ('property_identifier', 'private_property_identifier') and name_node is None:
                        name_node = ch
                    elif _zero_arg(ch, 'kind') in ('arrow_function', 'function_expression'):
                        value_node = ch
                if name_node and value_node:
                    funcs.append(self._build_function_dict(
                        value_node, self._get_node_text(name_node), []
                    ))
        return funcs

    # ── JS-family arrow-function-as-const (`const f = (...) => {}`) ─────────
    # BACK-431 Issue G tier B dogfood audit (mysterious-probe-0703, real
    # excalidraw source): this pattern was TypeScript/TSX-only special-case
    # logic that get_structure()/--outline used, but plain JavaScript had no
    # equivalent at all (`const f = () => {}` was invisible even to
    # --outline) — and neither language's nav-flag lookup
    # (file_handler._find_element_node) called it, so `reveal file.ts f
    # --varflow x` failed with "could not find function" for a function
    # --outline listed a moment earlier. Promoted here so every JS-family
    # grammar (lexical_declaration is JS/TS/TSX/JSX-specific — a no-op for
    # every other language) gets both get_structure() coverage and nav-flag
    # resolution from one shared implementation.

    def _arrow_or_fn_value(self, variable_declarator_node) -> Tuple[Optional[Any], Optional[Any]]:
        """Return (name_node, value_node) for a variable_declarator, or (None, None).

        BACK-726 (sideeffects-recall-oracle/tsx, eighteenth language, pre-flight
        check on a synthetic HOC-wrapped component): `const Name =
        React.forwardRef((props, ref) => {...})` / `React.memo(...)` — the
        dominant "named component wrapped in a higher-order function" shape in
        modern React/TSX (47 corpus occurrences of forwardRef/memo alone in
        samples/tsx/excalidraw) — was entirely invisible to both
        get_structure()/--outline and bare-name lookup. The declarator's value
        child is a `call_expression` (the HOC call), not a bare
        `arrow_function`/`function_expression`/`generator_function` directly,
        so the original direct-child-kind check never matched at all — same
        "wrapped one level deeper than the direct-child check expects" shape as
        prior loops' constructor/instance_expression findings, just one call
        deeper. Fixed by falling through to the call's own direct argument
        list when the value is a call_expression, looking for the single
        function-literal argument (the render/component callback every real
        corpus site — forwardRef, memo, styled-component render props — passes
        as exactly one argument; a curried second call like
        `connect(...)(Component)` has no function literal at this level and is
        correctly left unmatched, not mis-attributed).
        """
        name_node = value_node = None
        for ch in _children(variable_declarator_node):
            if _zero_arg(ch, 'kind') == 'identifier' and name_node is None:
                name_node = ch
            elif _zero_arg(ch, 'kind') in ('arrow_function', 'function_expression', 'generator_function'):
                value_node = ch
            elif _zero_arg(ch, 'kind') == 'call_expression' and value_node is None:
                value_node = self._call_wrapped_function_literal(ch)
        return name_node, value_node

    @staticmethod
    def _call_wrapped_function_literal(call_expression_node) -> Optional[Any]:
        """Return the sole function-literal argument of a call, or None.

        BACK-726: supports the `HOC(...)((...) => {...})` shape — looks only
        at the call's own direct `arguments` list (not nested calls), so a
        curried `outer(...)(inner)` HOC only matches at the level that
        actually carries the function literal.
        """
        for ch in _children(call_expression_node):
            if _zero_arg(ch, 'kind') != 'arguments':
                continue
            candidates = [
                arg for arg in _children(ch)
                if _zero_arg(arg, 'kind') in ('arrow_function', 'function_expression', 'generator_function')
            ]
            if len(candidates) == 1:
                return candidates[0]
        return None

    def _extract_language_specific_functions(self) -> List[StructureItem]:
        """Arrow-const and class-field function values, in that order."""
        return [*self._extract_arrow_functions(), *self._extract_class_field_functions(),
                *super()._extract_language_specific_functions()]

    def _extract_arrow_functions(self) -> List[StructureItem]:
        """Extract named arrow/function-expression declarations (const X = () => {}),
        at module scope or nested inside another function's body.

        BACK-643: this used to gate on `_is_module_scope_decl`, so a local
        `const name = (...) => {}` declared inside another function's body
        was invisible to both get_structure()/--outline and bare-name
        lookup (`_find_named_function_value` below) — even though a plain
        `function name() {}` in the exact same nested position was already
        found at any depth via `_extract_undecorated_functions`'s unscoped
        tree walk. `_arrow_or_fn_value` only matches a variable_declarator
        whose value is an actual function literal, so dropping the scope
        gate only brings named function-valued consts to parity with
        function declarations — it does not start flagging arbitrary local
        variables. As with declaration lookup, an ambiguous name reused at
        multiple nesting depths resolves to the first tree-walk match; a
        qualifier syntax to disambiguate is a separate, larger change.
        """
        funcs = []
        for decl_node in self._find_nodes_by_type('lexical_declaration'):
            for child in _children(decl_node):
                if _zero_arg(child, 'kind') != 'variable_declarator':
                    continue
                name_node, value_node = self._arrow_or_fn_value(child)
                if name_node and value_node:
                    funcs.append(self._build_function_dict(
                        value_node, self._get_node_text(name_node), []
                    ))
        return funcs

    def _find_named_function_value(self, name: str):
        """Resolve a named arrow/function-expression value to its function
        node, for bare-name lookup by both the plain element extractor
        (display.element._try_treesitter_extraction) and nav-flag lookup
        (file_handler._find_element_node).

        Covers two JS-family shapes that carry their name on a parent node
        rather than the (anonymous) arrow node itself:
          1. `const name = (...) => {}` (lexical_declaration) at module
             scope or nested inside another function's body — BACK-643:
             previously module-scope-only, so a local named arrow-const was
             listed nowhere and this lookup always missed it, and
          2. class-field methods `name = (...) => {}` (public_field_definition
             / field_definition) — BACK-527: previously only get_structure()
             saw these (via _extract_class_field_functions), so they listed in
             --outline but `reveal file.tsx name` returned "not found".
        """
        # 1. `const name = (...) => {}`, module scope or nested
        for decl_node in self._find_nodes_by_type('lexical_declaration'):
            for child in _children(decl_node):
                if _zero_arg(child, 'kind') != 'variable_declarator':
                    continue
                name_node, value_node = self._arrow_or_fn_value(child)
                if name_node and value_node and self._get_node_text(name_node) == name:
                    return value_node

        # 2. class-field arrow method `name = (...) => {}`
        for field_type in self._CLASS_FIELD_NODE_TYPES:
            for field_node in self._find_nodes_by_type(field_type):
                name_node = value_node = None
                for ch in _children(field_node):
                    if _zero_arg(ch, 'kind') in ('property_identifier', 'private_property_identifier') and name_node is None:
                        name_node = ch
                    elif _zero_arg(ch, 'kind') in ('arrow_function', 'function_expression'):
                        value_node = ch
                if name_node and value_node and self._get_node_text(name_node) == name:
                    return value_node

        # 3. Language-specific fallback, no-op unless a subclass defines one.
        return super()._find_named_function_value(name)
