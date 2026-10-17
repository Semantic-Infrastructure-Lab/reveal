"""Lua analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional, Tuple

from ..reveal_types import StructureItem
from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.lua', name='Lua', icon='🌙')
class LuaAnalyzer(TreeSitterAnalyzer):
    """Analyze Lua source files.

    Extracts functions automatically using tree-sitter.
    """
    language = 'lua'
    IMPORTS_VIA_EXTRACTOR = True  # BACK-1089

    # ── Lua function-expression-as-value (`name = function(...) ... end`) ───
    # BACK-758 (Lua calls-recall-oracle pre-flight, BACK-730 sixteenth
    # language): a bare `function_definition` (Lua's node kind for an
    # anonymous function literal -- coincidentally the same string Python's
    # own `def` uses, but a structurally distinct grammar in this language)
    # carries no name of its own; the name lives on the enclosing
    # assignment/field, exactly the shape `_arrow_or_fn_value` already
    # handles for JS/TS `const f = () => {}`. Without an equivalent here,
    # `local NOOP = function() ... end`, `M.setter = function(x) ... end`
    # (module-table method idiom), bare `setter = function(x) ... end`
    # (no `local`), and table-constructor fields (`{ __call = function()
    # ... end }`, Lua's metatable/dispatch-table idiom) were ALL entirely
    # invisible to get_structure()/--outline -- not just their calls, the
    # whole scope -- found via a real Kong corpus grep (643 occurrences of
    # `= function(` across 176 files). `local function name() ... end` /
    # `function name() ... end` (both `function_declaration`, already
    # extracted above) are unaffected; this only covers the
    # value-is-a-bare-function_definition shape. (BACK-915: pushed down
    # from treesitter.py's shared base onto its two extension-point hooks.)
    _LUA_ASSIGN_TARGET_KINDS = ('identifier', 'dot_index_expression')

    def _lua_function_expr_name(self, target_node) -> Optional[str]:
        """Return the bare name for a Lua assignment/field target node.

        `identifier` -> its own text; `dot_index_expression` (`M.setter`)
        -> just the final segment, matching `_name_via_dot_index`'s
        existing convention for `function M.setter(...)` declarations.
        """
        kind = _zero_arg(target_node, 'kind')
        if kind == 'identifier':
            return self._get_node_text(target_node)
        if kind == 'dot_index_expression':
            return self._get_node_text(target_node).rsplit('.', 1)[-1]
        return None

    def _lua_table_field_name_value(
        self, field_node, value_kind: str = 'function_definition',
    ) -> Tuple[Optional[Any], Optional[Any]]:
        """Return (name_node, value_node) for a Lua table-constructor `field`
        with a literal key and requested value kind (a function by default), or
        (None, None) for a computed key (`{ [expr] = function() end }`) or a
        positional value (no key at all).

        A computed key's bracketed expression (`[CONTENT_TYPE_POST] =
        function...`) also parses its inner expression as a bare
        `identifier` child of the same `field` node -- found via a real
        Kong corpus false positive (`pdk/service/request.lua`'s
        `[CONTENT_TYPE_POST] = function(...)`/`[CONTENT_TYPE_FORM_DATA] =
        function(...)` dynamic dispatch table): naively taking "the first
        identifier child" misattributed the value function's calls to the
        KEY EXPRESSION's name, not a real function name at all. A literal
        string-key field's identifier is always the field's structural
        FIRST child; a computed key's is preceded by a `[` token — that
        ordering is the only reliable distinguishing signal.
        """
        kids = _children(field_node)
        if not kids or _zero_arg(kids[0], 'kind') != 'identifier':
            return None, None
        name_node = kids[0]
        value_node = next(
            (c for c in kids if _zero_arg(c, 'kind') == value_kind), None
        )
        return (name_node, value_node) if value_node else (None, None)

    def _lua_assignment_pairs(self, statement) -> List[Tuple[Any, Any]]:
        """Pair positional assignment targets and values before filtering functions."""
        children = _children(statement)
        targets = next((c for c in children if _zero_arg(c, 'kind') == 'variable_list'), None)
        values = next((c for c in children if _zero_arg(c, 'kind') == 'expression_list'), None)
        if targets is None or values is None:
            return []
        return list(zip([c for c in _children(targets) if _zero_arg(c, 'is_named')],
                        [c for c in _children(values) if _zero_arg(c, 'is_named')]))

    def _lua_named_function_values(self) -> List[Tuple[str, Any]]:
        """(name, function_definition node) for every function literal bound to a name.

        Assignment sites (`local N = function`, `N = function`, `M.k = function`)
        and table-constructor fields with a literal key. Anything else (an
        anonymous function passed as an argument) gets no entry of its own.
        """
        found: List[Tuple[str, Any]] = []

        # `local NAME = function...` / `NAME = function...` / `M.k = function...`
        for stmt in self._find_nodes_by_type('assignment_statement'):
            for target_node, value_node in self._lua_assignment_pairs(stmt):
                if _zero_arg(value_node, 'kind') != 'function_definition':
                    continue
                name = self._lua_function_expr_name(target_node)
                if name:
                    found.append((name, value_node))

        # Table-constructor field: `{ key = function(...) ... end }`
        for field in self._find_nodes_by_type('field'):
            name_node, value_node = self._lua_table_field_name_value(field)
            if name_node and value_node:
                found.append((self._get_node_text(name_node), value_node))
        return found

    def _extract_language_specific_functions(self) -> List[StructureItem]:
        """Extract `name = function(...) ... end` at assignment or table-field sites."""
        return [self._build_function_dict(value_node, name, [])
                for name, value_node in self._lua_named_function_values()]

    def _function_scope_has_own_entry(self, node) -> bool:
        """An anonymous `function_definition` (e.g. a callback argument) has no entry
        of its own, so its calls must stay with the enclosing function (BACK-1313)."""
        if _zero_arg(node, 'kind') != 'function_definition':
            return True
        starts = getattr(self, '_lua_named_starts', None)
        if starts is None:
            starts = self._lua_named_starts = {
                _zero_arg(v, 'start_byte') for _, v in self._lua_named_function_values()}
        return _zero_arg(node, 'start_byte') in starts

    def _find_named_language_specific_function(self, name: str):
        """Resolve `name` against Lua's `name = function...`/table-field
        function-value shapes (BACK-758) — the lookup counterpart to
        `_extract_language_specific_functions` above.
        """
        return next((node for found_name, node in self._lua_named_function_values()
                     if found_name == name), None)

    def _lua_binding_path(self, node) -> Optional[str]:
        """Literal assignment/table-field path; computed and call-derived owners decline."""
        parent = _zero_arg(node, 'parent')
        kind = _zero_arg(parent, 'kind') if parent is not None else None
        if kind == 'expression_list':
            statement = _zero_arg(parent, 'parent')
            span = (_zero_arg(node, 'start_byte'), _zero_arg(node, 'end_byte'))
            for target, value in self._lua_assignment_pairs(statement):
                if ((_zero_arg(value, 'start_byte'), _zero_arg(value, 'end_byte')) == span
                        and _zero_arg(target, 'kind') in self._LUA_ASSIGN_TARGET_KINDS):
                    return self._get_node_text(target)
        elif kind == 'field':
            name, value = self._lua_table_field_name_value(parent, _zero_arg(node, 'kind'))
            if name is not None and value is not None:
                owner = self._lua_binding_path(_zero_arg(parent, 'parent'))
                if owner:
                    return f'{owner}.{self._get_node_text(name)}'
        return None

    def _function_value_owner(self, node) -> Optional[str]:
        """Owner of a Lua declaration or named literal through the resolver's value hook."""
        kind = _zero_arg(node, 'kind')
        if kind == 'function_declaration':
            name = node.child_by_field_name('name')
            path = self._get_node_text(name).replace(':', '.') if name is not None else None
        elif kind == 'function_definition':
            path = self._lua_binding_path(node)
        else:
            path = None
        return path.rpartition('.')[0] or None if path else None

    def _find_named_function_values(self, name: str) -> List[Any]:
        """All matching bound literals and qualified declarations; never first-only."""
        declarations = [node for node in self._find_nodes_by_type('function_declaration')
                        if self._get_node_name(node) == name and self._function_value_owner(node)]
        return declarations + [node for found_name, node in self._lua_named_function_values()
                               if found_name == name]

    # ── Node naming (BACK-918/BACK-915) ─────────────────────────────────────
    def _name_via_dot_index(self, kids) -> Optional[str]:
        # Lua `function table.name(...)` / `function tbl.a.b(...)` — an
        # extremely common module-method idiom (BACK-431 Issue G tier B
        # dogfood audit: found via real Kong source,
        # `kong/concurrency.lua`'s entire public API is declared this way).
        # The name is a `dot_index_expression`
        # ("concurrency.with_worker_mutex"), a kind absent from every check
        # above; return just the final segment, matching how every other
        # bare-name function lookup in reveal works.
        for child in kids:
            if _zero_arg(child, 'kind') == 'dot_index_expression':
                return self._get_node_text(child).rsplit('.', 1)[-1]
        return None

    def _name_via_method_index(self, kids) -> Optional[str]:
        # BACK-722 Lua sideeffects-recall-oracle pre-flight: Lua `function
        # table:name(...)` — the colon-method idiom, Lua's closest
        # equivalent to a receiver method (implicitly takes `self` as the
        # first parameter). Verified via real Kong source (kong/db/*.lua,
        # kong/plugins/*/handler.lua) that this is the DOMINANT OOP
        # method-definition idiom in this corpus — more common than the dot
        # form `_name_via_dot_index` already handles. The name is a
        # `method_index_expression` ("connector:query"), a distinct
        # tree-sitter-lua node kind from `dot_index_expression` (same
        # grammar family as Go's `selector_expression` vs Kotlin/Swift's
        # `navigation_expression` split) — absent from every check above,
        # so every `function X:y(...)` was entirely invisible to --outline
        # and errored outright on a direct name lookup before this fix.
        # Return just the final segment, matching every other bare-name
        # function lookup in reveal (and `_name_via_dot_index`'s
        # convention).
        for child in kids:
            if _zero_arg(child, 'kind') == 'method_index_expression':
                return self._get_node_text(child).rsplit(':', 1)[-1]
        return None
