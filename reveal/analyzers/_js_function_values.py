"""JS-family function-as-value extraction: functions whose name lives on a parent node.

`const f = () => {}`, class-field arrows, object-literal methods of a named object
(`const api = { load: () => {} }`), and CommonJS/prototype assignments
(`module.exports = function main() {}`, `exports.x = ...`, `A.prototype.m = ...`).
One enumerator (`_iter_function_values`) feeds both the outline and by-name lookup, so
the two can't disagree about what exists (the BACK-530 bug class).

Shared by JavaScript, TypeScript and TSX analyzers (BACK-1280: moved out of the
`TreeSitterAnalyzer` base, which used to run this for every language). The grammar shapes
here (`lexical_declaration > variable_declarator`, `public_field_definition` /
`field_definition`) exist only in JS-family grammars, so a language that does not mix this
in never pays for the scan. Same mixin pattern as `JSClassBasesMixin` and
`JSTestCallbackMixin` alongside.
"""

from typing import TYPE_CHECKING, Any, Iterator, List, Optional, Tuple

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..reveal_types import StructureItem

if TYPE_CHECKING:
    from ..treesitter import TreeSitterAnalyzer as _Base
else:
    _Base = object

_FUNCTION_LITERALS = ('arrow_function', 'function_expression', 'generator_function')
# What an object literal's parent must be for its methods to be named API:
# `const api = {...}`, `x = {...}` (incl. module.exports), `export default {...}`.
_NAMED_OBJECT_HOLDERS = ('variable_declarator', 'assignment_expression', 'export_statement')
# Calls whose first argument is the function they return or wrap, whatever follows it (``memo(fn, areEqual)``,
# ``useCallback(fn, deps)``), also as a member call (``React.useCallback``; BACK-2169).
_FUNCTION_WRAPPERS = frozenset({'memo', 'forwardRef', 'useCallback'})
# Scope facts for "does this file call the name this declaration binds" (BACK-2174).
_FUNCTION_SCOPES = frozenset({'function_declaration', 'function_expression', 'generator_function',
                              'generator_function_declaration', 'arrow_function', 'method_definition'})
_DECLARATIONS = ('lexical_declaration', 'variable_declaration')
_NAMED_DECLARATIONS = ('function_declaration', 'generator_function_declaration', 'class_declaration')


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
        name_node = value_node = call = None
        for ch in _children(variable_declarator_node):
            if _zero_arg(ch, 'kind') == 'identifier' and name_node is None:
                name_node = ch
            elif _zero_arg(ch, 'kind') in ('arrow_function', 'function_expression', 'generator_function'):
                value_node = ch
            elif _zero_arg(ch, 'kind') == 'call_expression' and value_node is None:
                call = ch
                value_node = self._call_wrapped_function_literal(ch)
        if value_node is not None and call is not None and not self._plain_call_is_function(call, name_node):
            value_node = None
        return name_node, value_node

    def _call_wrapped_function_literal(self, call_expression_node) -> Optional[Any]:
        """Return the function literal a call wraps, or None.

        A component wrapper (``memo``, ``React.forwardRef``) may carry more arguments (a
        comparator), nest another wrapper (``memo(forwardRef(fn))``) or sit in
        ``Object.assign(wrapper(fn), {...})`` (BACK-1830); any other plain call wraps its sole
        function-literal argument.

        BACK-2169: a member call (``xs.map(fn)``, ``items.find(fn)``) returns the method's value, not
        the function it is given, so it never wraps; ``React.memo`` / ``Object.assign`` are still
        wrappers by name. A plain call (``derived(fn)``) wraps only when the file calls the name it is assigned to (BACK-2174).

        BACK-726: supports the `HOC(...)((...) => {...})` shape — looks only
        at the call's own direct `arguments` list (not nested calls), so a
        curried `outer(...)(inner)` HOC only matches at the level that
        actually carries the function literal.
        """
        for ch in _children(call_expression_node):
            if _zero_arg(ch, 'kind') != 'arguments':
                continue
            if self._is_wrapper_call(call_expression_node):
                # The component is the first argument; a trailing comparator is not it.
                return self._wrapper_first_argument(call_expression_node, ch)
            if self._callee_parts(call_expression_node)[0]:
                return None
            candidates = [
                arg for arg in _children(ch)
                if _zero_arg(arg, 'kind') in ('arrow_function', 'function_expression', 'generator_function')
            ]
            if len(candidates) == 1:
                return candidates[0]
        return None

    def _plain_call_is_function(self, call, name_node) -> bool:
        """Whether `const NAME = callee(fn)` binds a function.

        BACK-2174: a declared wrapper (``memo``, ``useCallback``) returns its function. Any other plain call
        (``setTimeout(fn)``, ``derived(fn)``, ``useMemo(fn)``) returns a value, and the file only shows it is a
        function when it calls or constructs the name this declaration binds.
        """
        if self._is_wrapper_call(call):
            return True
        return name_node is not None and self._is_called_in_scope(
            _zero_arg(name_node, 'parent'), self._get_node_text(name_node))

    def _called_index(self) -> dict:
        """name -> calls and `new` expressions whose callee is that bare identifier, built once per tree."""
        index = getattr(self, '_call_index_cache', None)
        if index is None:
            index = {}
            for kind in ('call_expression', 'new_expression'):
                for call in self._find_nodes_by_type(kind):
                    callee = call.child_by_field_name('function') or call.child_by_field_name('constructor')
                    if callee is not None and _zero_arg(callee, 'kind') == 'identifier':
                        index.setdefault(self._get_node_text(callee), []).append(call)
            self._call_index_cache = index
        return index

    def _declaring_scope(self, declarator):
        """The node whose span a declarator's name is visible in: its block (`let`/`const`), or the function
        or program (`var`)."""
        declaration = _zero_arg(declarator, 'parent')
        hoisted = declaration is not None and _zero_arg(declaration, 'kind') == 'variable_declaration'
        node = _zero_arg(declaration, 'parent') if declaration is not None else None
        while node is not None:
            kind = _zero_arg(node, 'kind')
            if kind == 'program' or kind in _FUNCTION_SCOPES or (kind == 'statement_block' and not hoisted):
                return node
            node = _zero_arg(node, 'parent')
        return None

    def _is_called_in_scope(self, declarator, name: str) -> bool:
        """Whether a call or `new` of NAME inside the declaration's scope refers to this declaration."""
        scope = self._declaring_scope(declarator)
        if scope is None:
            return False
        low, high = _zero_arg(scope, 'start_byte'), _zero_arg(scope, 'end_byte')
        return any(low <= _zero_arg(call, 'start_byte') < high and not self._is_shadowed(call, scope, name)
                   for call in self._called_index().get(name, ()))

    def _is_shadowed(self, call, scope, name: str) -> bool:
        """Whether something between `call` and `scope` binds NAME again (parameter, block declaration, catch
        or loop variable, or a function's own name). Over-reports on a parameter default that merely reads NAME,
        which can only withhold a function claim. A `var` in a nested block is not followed."""
        span = (_zero_arg(scope, 'start_byte'), _zero_arg(scope, 'end_byte'))
        node = _zero_arg(call, 'parent')
        while node is not None and (_zero_arg(node, 'start_byte'), _zero_arg(node, 'end_byte')) != span:
            if self._node_rebinds(node, name):
                return True
            node = _zero_arg(node, 'parent')
        return False

    def _node_rebinds(self, node, name: str) -> bool:
        kind = _zero_arg(node, 'kind')
        if kind in _FUNCTION_SCOPES:
            own = node.child_by_field_name('name')
            params = node.child_by_field_name('parameters') or node.child_by_field_name('parameter')
            return (own is not None and self._get_node_text(own) == name) or self._mentions(params, name)
        if kind == 'catch_clause':
            return self._mentions(node.child_by_field_name('parameter'), name)
        if kind == 'for_in_statement':
            return self._mentions(node.child_by_field_name('left'), name)
        if kind in ('statement_block', 'for_statement'):
            return self._block_declares(node, name)
        return False

    def _block_declares(self, block, name: str) -> bool:
        for child in _children(block):
            kind = _zero_arg(child, 'kind')
            if kind in _DECLARATIONS:
                if any(self._mentions(d.child_by_field_name('name'), name)
                       for d in _children(child) if _zero_arg(d, 'kind') == 'variable_declarator'):
                    return True
            elif kind in _NAMED_DECLARATIONS:
                declared = child.child_by_field_name('name')
                if declared is not None and self._get_node_text(declared) == name:
                    return True
        return False

    def _mentions(self, node, name: str) -> bool:
        """Whether an identifier spelled NAME occurs anywhere under `node`."""
        stack = [node] if node is not None else []
        while stack:
            current = stack.pop()
            if _zero_arg(current, 'kind') in ('identifier', 'shorthand_property_identifier_pattern') \
                    and self._get_node_text(current) == name:
                return True
            stack.extend(_children(current))
        return False

    def _callee_parts(self, call) -> Tuple[str, str]:
        """(object text, property or identifier name) of a call's callee, '' when not a plain name."""
        callee = next(iter(_children(call)), None)
        kind = _zero_arg(callee, 'kind') if callee is not None else None
        if callee is not None and kind == 'identifier':
            return '', self._get_node_text(callee)
        if callee is not None and kind == 'member_expression':
            obj = callee.child_by_field_name('object')
            prop = callee.child_by_field_name('property')
            if obj is not None and prop is not None:
                return self._get_node_text(obj), self._get_node_text(prop)
        return '', ''

    def _is_wrapper_call(self, call) -> bool:
        obj, name = self._callee_parts(call)
        return name in _FUNCTION_WRAPPERS or (obj, name) == ('Object', 'assign')

    def _wrapper_first_argument(self, call, arguments) -> Optional[Any]:
        """The component a ``memo`` / ``forwardRef`` / ``Object.assign`` call is given first."""
        is_assign = self._callee_parts(call) == ('Object', 'assign')
        first = next((a for a in _children(arguments)
                      if _zero_arg(a, 'kind') not in ('(', ')', ',')), None)
        if first is None:
            return None
        if _zero_arg(first, 'kind') in _FUNCTION_LITERALS:
            return first
        if _zero_arg(first, 'kind') == 'call_expression':
            return self._call_wrapped_function_literal(first)
        return None

    def _extract_language_specific_functions(self) -> List[StructureItem]:
        """Every function value, then any subclass's own."""
        return [*(self._build_function_dict(value, name, []) for name, value in self._iter_function_values()),
                *super()._extract_language_specific_functions()]

    def _iter_function_values(self) -> Iterator[Tuple[str, Any]]:
        """(name, function node) for every JS-family function value, in shape
        order: declarations, class fields, object-literal methods, assignments.

        BACK-643: a `const name = ...` counts at any depth, not only module
        scope -- a nested `function name() {}` already did, and
        `_arrow_or_fn_value` only matches a declarator whose value is a
        function literal, so this brings function-valued consts to parity
        without flagging arbitrary locals. BACK-1410 added the last two shapes.
        """
        # 1. `const name = (...) => {}` / `var name = function () {}`
        for kind in ('lexical_declaration', 'variable_declaration'):
            for decl_node in self._find_nodes_by_type(kind):
                for child in _children(decl_node):
                    if _zero_arg(child, 'kind') != 'variable_declarator':
                        continue
                    name_node, value_node = self._arrow_or_fn_value(child)
                    if name_node and value_node:
                        yield self._get_node_text(name_node), value_node

        # 2. class-field arrow method `name = (...) => {}`
        for field_type in self._CLASS_FIELD_NODE_TYPES:
            for field_node in self._find_nodes_by_type(field_type):
                name_node = value_node = None
                for ch in _children(field_node):
                    if _zero_arg(ch, 'kind') in ('property_identifier', 'private_property_identifier') and name_node is None:
                        name_node = ch
                    elif _zero_arg(ch, 'kind') in _FUNCTION_LITERALS:
                        value_node = ch
                if name_node and value_node:
                    yield self._get_node_text(name_node), value_node

        # 3. `key: (...) => {}` in an object literal that has a name of its own:
        # `const api = {...}`, `module.exports = {...}`, `export default {...}`.
        # Only direct members -- arrows in an inline argument object
        # (`fetch(url, { onDone: () => {} })`) are callbacks, not API.
        for pair in self._find_nodes_by_type('pair'):
            obj = _zero_arg(pair, 'parent')
            holder = _zero_arg(obj, 'parent') if obj is not None else None
            if holder is None or _zero_arg(holder, 'kind') not in _NAMED_OBJECT_HOLDERS:
                continue
            key = pair.child_by_field_name('key')
            value = pair.child_by_field_name('value')
            if (key is not None and value is not None and _zero_arg(key, 'kind') == 'property_identifier'
                    and _zero_arg(value, 'kind') in _FUNCTION_LITERALS):
                yield self._get_node_text(key), value

        # 4. CommonJS and prototype assignments
        for assignment in self._find_nodes_by_type('assignment_expression'):
            name = self._assigned_function_name(assignment)
            if name:
                yield name, assignment.child_by_field_name('right')

    def _assigned_function_name(self, assignment) -> Optional[str]:
        """Name of a function assigned to an exported or prototype slot:
        `module.exports = function main() {}` -> main (an anonymous one has no
        name to list); `module.exports.x = ...`, `exports.x = ...` and
        `A.prototype.x = ...` -> x. Any other assignment is not a definition."""
        left = assignment.child_by_field_name('left')
        right = assignment.child_by_field_name('right')
        if left is None or right is None or _zero_arg(right, 'kind') not in _FUNCTION_LITERALS:
            return None
        if _zero_arg(left, 'kind') != 'member_expression':
            return None
        if self._get_node_text(left) == 'module.exports':
            own_name = right.child_by_field_name('name')
            return self._get_node_text(own_name) if own_name is not None else None
        owner = left.child_by_field_name('object')
        prop = left.child_by_field_name('property')
        owner_text = self._get_node_text(owner) if owner is not None else ''
        if prop is not None and (owner_text in ('module.exports', 'exports') or owner_text.endswith('.prototype')):
            return self._get_node_text(prop)
        return None

    def _function_value_owner(self, value) -> Optional[str]:
        """What a function value is a member of, when no class encloses it:
        the named object of an object-literal method (`api` for
        `const api = { load: ... }`, `module.exports`), or the target of an
        assignment (`exports`, `A` for `A.prototype.m = ...`). Lets
        element_resolve qualify it (`api.load`) and resolve `api.load`."""
        parent = _zero_arg(value, 'parent')
        kind = _zero_arg(parent, 'kind') if parent is not None else None
        if kind == 'pair':
            obj = _zero_arg(parent, 'parent')
            holder = _zero_arg(obj, 'parent') if obj is not None else None
            holder_kind = _zero_arg(holder, 'kind') if holder is not None else None
            if holder_kind == 'variable_declarator':
                name = holder.child_by_field_name('name')
                return self._get_node_text(name) if name is not None else None
            if holder_kind == 'assignment_expression':
                left = holder.child_by_field_name('left')
                return self._get_node_text(left) if left is not None else None
            return 'default' if holder_kind == 'export_statement' else None
        if kind == 'assignment_expression':
            left = parent.child_by_field_name('left')
            owner = left.child_by_field_name('object') if left is not None else None
            if owner is None or _zero_arg(left, 'kind') != 'member_expression':
                return None
            text = self._get_node_text(owner)
            return text[:-len('.prototype')] if text.endswith('.prototype') else text
        return None

    def _find_named_function_value(self, name: str):
        """Resolve a function value by name to its function node (first in
        shape order), for element and nav-flag lookup; see _iter_function_values
        for the shapes (BACK-527/643/1410)."""
        node = next(self._iter_named_function_values(name), None)
        if node is not None:
            return node
        # Language-specific fallback, no-op unless a subclass defines one.
        return super()._find_named_function_value(name)

    def _find_named_function_values(self, name: str) -> List[Any]:
        """Every function value named `name` (BACK-1400)."""
        return list(self._iter_named_function_values(name)) or super()._find_named_function_values(name)

    def _iter_named_function_values(self, name: str):
        return (value for value_name, value in self._iter_function_values() if value_name == name)
