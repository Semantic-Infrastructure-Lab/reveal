"""Zig analyzer using tree-sitter.

Two Zig grammars are in use (BACK-2540). tree-sitter-language-pack up to 1.24 ships a
fieldless PascalCase grammar (`Decl` > `FnProto`, `VarDecl`, `ContainerDecl`, `TestDecl`);
1.25 replaced it with a fielded snake_case one (`function_declaration`, `variable_declaration`,
`struct_declaration`, `test_declaration`). The two share no declaration kinds, so every
method below dispatches on the node's own kind and needs no grammar switch. The PascalCase
branches are the legacy grammar: delete them once the pack floor reaches 1.25.
"""
from typing import Any, Dict, Iterator, List, Optional
from ..reveal_types import StructureItem
from ..registry import register
from ..treesitter import TreeSitterAnalyzer
from ..complexity import calculate_complexity
from ..core import node_children as _children, node_next_sibling as _next_sibling, node_prev_sibling as _prev_sibling
from ..core.treesitter_compat import _zero_arg
from ..core.nav_calls import range_calls
from ..utils.results import ResultBuilder
from reveal.reveal_types import CONTRACT_VERSION

# The 1.25 grammar's declaration kinds (module docstring).
FUNCTION_KIND = 'function_declaration'
VARIABLE_KIND = 'variable_declaration'
TEST_KIND = 'test_declaration'
CONTAINER_KINDS = {
    'struct_declaration': 'struct', 'enum_declaration': 'enum',
    'union_declaration': 'union', 'opaque_declaration': 'opaque',
}
# Legacy grammar kinds whose node the 1.25 kind replaces.
_LEGACY_FUNCTION_KIND = 'Decl'
_LEGACY_VARIABLE_KIND = 'VarDecl'
_LEGACY_TEST_KIND = 'TestDecl'


def is_function_node(node) -> bool:
    """A Zig function declaration in either grammar (a legacy `Decl` only when it holds an `FnProto`)."""
    kind = _zero_arg(node, 'kind')
    if kind == FUNCTION_KIND:
        return True
    return kind == _LEGACY_FUNCTION_KIND and any(
        _zero_arg(child, 'kind') == 'FnProto' for child in _children(node))


def is_binding(var_node) -> bool:
    """A 1.25 `variable_declaration` that declares (`const`/`var`). The 1.25 grammar also parses a
    plain assignment (`x = y`, `self.f = y`, `_ = y`, `x += 1`) as a keyword-less
    `variable_declaration`; that is a write, not a declaration."""
    return any(_zero_arg(child, 'kind') in ('const', 'var') for child in _children(var_node))


@register('.zig', name='Zig', icon='⚡')
class ZigAnalyzer(TreeSitterAnalyzer):
    """Zig language analyzer.

    Supports Zig source files with functions, structs, enums, tests, and more.
    """
    language = 'zig'
    IMPORTS_VIA_EXTRACTOR = True  # BACK-1089

    # BACK-2123: enums, unions and tests are built into the structure the shared
    # builder caches (TreeSitterAnalyzer._get_or_build_structure), so a warm Zig
    # query never re-extracts. The entries are not node kinds: `enum` and `union`
    # are container types, `test` names both grammars' test declarations;
    # _extract_declarations below maps each to the Zig extractor.
    DECLARATION_CATEGORIES = {
        'enums': ('enum',),
        'unions': ('union',),
        'tests': ('test',),
    }

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Extract Zig code structure (cached by the shared builder, BACK-2123)."""
        structure = self._get_or_build_structure()
        if not structure:
            return {}

        # The shared builder also records `called_by` on functions; Zig's outline
        # never carried it and its shape is unchanged. A new dict per function: a
        # disk-cache hit is shared with later hits.
        data = {k: v for k, v in structure.items() if v}
        if 'functions' in data:
            data['functions'] = [{k: v for k, v in func.items() if k != 'called_by'}
                                 for func in data['functions']]

        return ResultBuilder.create(
            result_type='zig_structure',
            source=self.path,
            data=data,
            contract_version=CONTRACT_VERSION,
            parse_mode='tree_sitter_full',
            confidence=1.0,
        )

    def _extract_structs(self) -> List[StructureItem]:
        """Zig structs are `const Name = struct {...}` declarations, not a node kind."""
        return self._extract_container_decls('struct')

    def _extract_declarations(self, node_kind: str) -> List[StructureItem]:
        """The Zig extractor behind each DECLARATION_CATEGORIES entry."""
        if node_kind == 'test':
            return self._extract_tests()
        return self._extract_container_decls(node_kind)

    # -- Declaration nodes, either grammar -------------------------------------------------
    # One grammar is present per tree, so each list below is in tree order.

    def _function_nodes(self) -> List[Any]:
        """Every function declaration: a 1.25 `function_declaration`, or a legacy `Decl` holding an `FnProto`."""
        return [node for node in self._find_nodes_by_type(_LEGACY_FUNCTION_KIND) if is_function_node(node)] + \
            self._find_nodes_by_type(FUNCTION_KIND)

    def _variable_nodes(self) -> List[Any]:
        """Every variable declaration: a legacy `VarDecl`, or a 1.25 `variable_declaration` that declares
        (`const`/`var`), not one of the assignments that grammar parses with the same kind."""
        return self._find_nodes_by_type(_LEGACY_VARIABLE_KIND) + [
            node for node in self._find_nodes_by_type(VARIABLE_KIND) if is_binding(node)]

    def _test_nodes(self) -> List[Any]:
        """Every test declaration (`test "name" {}`, `test Ident {}`, `test {}`)."""
        return self._find_nodes_by_type(_LEGACY_TEST_KIND) + self._find_nodes_by_type(TEST_KIND)

    def _is_pub(self, node) -> bool:
        """`pub` is a child token of a 1.25 declaration and the previous sibling of a legacy `Decl`."""
        if _zero_arg(node, 'kind') in (FUNCTION_KIND, VARIABLE_KIND):
            return any(_zero_arg(child, 'kind') == 'pub' for child in _children(node))
        previous = _prev_sibling(node)
        return bool(previous and _zero_arg(previous, 'kind') == 'pub')

    def _member_declaration(self, var_node):
        """The declaration a file- or container-level variable belongs to (its span and `pub`), or None
        for a variable declared inside a function body. A legacy `VarDecl` is wrapped in a `Decl`
        only at those levels; a 1.25 `variable_declaration` is the declaration itself."""
        parent = _zero_arg(var_node, 'parent')
        if parent is None:
            return None
        if _zero_arg(var_node, 'kind') == _LEGACY_VARIABLE_KIND:
            return parent if _zero_arg(parent, 'kind') == _LEGACY_FUNCTION_KIND else None
        parent_kind = _zero_arg(parent, 'kind')
        return var_node if parent_kind == 'source_file' or parent_kind in CONTAINER_KINDS else None

    # -- Functions --------------------------------------------------------------------------

    def _find_fn_proto(self, decl_node):
        """Find the FnProto child of a legacy `Decl`."""
        for child in _children(decl_node):
            if _zero_arg(child, 'kind') == 'FnProto':
                return child
        return None

    def _function_name(self, node) -> Optional[str]:
        """Name of a function declaration in either grammar."""
        if _zero_arg(node, 'kind') == FUNCTION_KIND:
            name = node.child_by_field_name('name')
            return self._get_node_text(name) if name is not None else None
        fn_proto = self._find_fn_proto(node)
        return self._extract_function_name(fn_proto) if fn_proto else None

    def _get_node_name(self, node) -> Optional[str]:
        """Override: a Zig function is a legacy `Decl` or a 1.25 `function_declaration`; both are in
        the shared FUNCTION_NODE_TYPES so nav flags like --varflow/--exits resolve a function by name
        via the generic file_handler lookup (outline used a bespoke extractor while every
        single-function nav flag used the generic search, which never matched Zig's grammar).
        A legacy `Decl` may also wrap a struct/enum/union/var; it has no FnProto child, so this
        returns None and falls through."""
        if is_function_node(node):
            return self._function_name(node)
        if _zero_arg(node, 'kind') == _LEGACY_FUNCTION_KIND:
            return None
        return super()._get_node_name(node)

    def _extract_function_name(self, fn_proto) -> Optional[str]:
        """Extract function name from a legacy FnProto node."""
        for fn_child in _children(fn_proto):
            if _zero_arg(fn_child, 'kind') == 'fn':
                # Next sibling should be the identifier (function name)
                next_sib = _next_sibling(fn_child)
                if next_sib and _zero_arg(next_sib, 'kind') == 'IDENTIFIER':
                    return self._get_node_text(next_sib)
        return None

    def _function_value_owner(self, node) -> Optional[str]:
        """Owner for qualified declaration candidates through the function-value hook."""
        if not is_function_node(node):
            return None
        parts: List[str] = []
        parent = _zero_arg(node, 'parent')
        while parent is not None:
            kind = _zero_arg(parent, 'kind')
            if kind == 'ContainerDecl' or kind in CONTAINER_KINDS:
                name, declaration = self._container_binding(parent)
                if not name:
                    return None  # Anonymous/call-derived containers do not inherit an outer owner.
                parts.insert(0, name)
                parent = declaration
            elif is_function_node(parent):
                break  # A local named container belongs to its binding, not its enclosing function.
            parent = _zero_arg(parent, 'parent')
        return '.'.join(parts) or None

    def _container_binding(self, container) -> tuple:
        """The declaration binding this exact container, not an enclosing type: the nearest
        enclosing legacy `Decl` or declaring `variable_declaration`, when its value is this container."""
        declaration = _zero_arg(container, 'parent')
        while declaration is not None and not (
                _zero_arg(declaration, 'kind') == _LEGACY_FUNCTION_KIND
                or (_zero_arg(declaration, 'kind') == VARIABLE_KIND and is_binding(declaration))):
            declaration = _zero_arg(declaration, 'parent')
        if declaration is None:
            return None, None
        variable = (declaration if _zero_arg(declaration, 'kind') == VARIABLE_KIND
                    else self._find_var_decl_in_node(declaration))
        if variable is None:
            return None, None
        name, value = self._extract_var_name_and_container(variable)
        if value is None or (
                _zero_arg(value, 'start_byte'), _zero_arg(value, 'end_byte')) != (
                _zero_arg(container, 'start_byte'), _zero_arg(container, 'end_byte')):
            return None, None
        return name, declaration

    def _find_named_function_values(self, name: str) -> List[Any]:
        """All named methods in verified containers, including declaration nodes."""
        return [node for node in self._function_nodes()
                if self._get_node_name(node) == name and self._function_value_owner(node)]

    def _get_param_name(self, param_decl) -> Optional[str]:
        """Get the identifier name from a legacy ParamDecl node, or None."""
        for p in _children(param_decl):
            if _zero_arg(p, 'kind') == 'IDENTIFIER':
                return self._get_node_text(p)
        return None

    def _iter_param_decl_names(self, param_decl_list) -> Iterator[str]:
        """Yield parameter names from a legacy ParamDeclList node."""
        for param_child in _children(param_decl_list):
            if _zero_arg(param_child, 'kind') == 'ParamDecl':
                name = self._get_param_name(param_child)
                if name:
                    yield name

    def _function_params(self, node) -> List[str]:
        """Parameter names of a function declaration in either grammar; `...` has none."""
        if _zero_arg(node, 'kind') == FUNCTION_KIND:
            names: List[str] = []
            for child in _children(node):
                if _zero_arg(child, 'kind') != 'parameters':
                    continue
                for param in _children(child):
                    name = param.child_by_field_name('name') if _zero_arg(param, 'kind') == 'parameter' else None
                    if name is not None and _zero_arg(name, 'kind') == 'identifier':
                        names.append(self._get_node_text(name))
            return names
        fn_proto = self._find_fn_proto(node)
        for fn_child in _children(fn_proto) if fn_proto else []:
            if _zero_arg(fn_child, 'kind') == 'ParamDeclList':
                return list(self._iter_param_decl_names(fn_child))
        return []

    def _build_function_signature(self, fn_name: str, params: List[str]) -> str:
        """Build function signature string (params only, no name — matches display convention)."""
        return f"({', '.join(params)})" if params else ""

    def _build_function_info(self, decl_node, fn_name: str, signature: str, has_pub: bool) -> StructureItem:
        """Build function information dictionary."""
        line_start = _zero_arg(decl_node, 'start_position').row + 1
        line_end = _zero_arg(decl_node, 'end_position').row + 1
        func_info: StructureItem = {
            'line': line_start,
            'line_end': line_end,
            'name': fn_name,
            'signature': signature,
            'calls': self._extract_calls(decl_node, line_start, line_end),
            # Nested `fn` decls (a `fn Type() type { return struct { fn m() ... } }`
            # generic) have their own entries; do not fold them into the enclosing one.
            'complexity': calculate_complexity(decl_node, is_function_node),
        }
        if has_pub:
            func_info['visibility'] = 'pub'
        return func_info

    def _extract_calls(self, node, line_start: int, line_end: int) -> List[str]:
        """Callee names reachable from `node`, deduped in first-seen order.

        The legacy grammar has no call-expression wrapper node — `foo(x)` / `a.b.c(x)` parse
        as a single `SuffixExpr` (see `nav_calls._extract_zig_suffix_calls`),
        so `calls://` (which walks `CALL_NODE_TYPES` — Python `call`, JS/Rust
        `call_expression`, etc.) previously saw zero callees for every Zig
        function, reporting live functions as having no callers (BACK-660).
        Reusing `range_calls` here — the same decoder `--calls` already uses —
        covers both grammars: the 1.25 grammar's `call_expression` and `builtin_function`
        are ordinary CALL_NODE_TYPES members.
        """
        seen: List[str] = []
        seen_set = set()
        for call in range_calls(node, line_start, line_end, self._get_node_text):
            callee = call['callee']
            if callee and callee not in seen_set:
                seen.append(callee)
                seen_set.add(callee)
        return seen

    def _extract_functions(self) -> List[StructureItem]:
        """Extract function definitions."""
        functions = []
        for node in self._function_nodes():
            fn_name = self._function_name(node)
            if not fn_name:
                continue
            signature = self._build_function_signature(fn_name, self._function_params(node))
            functions.append(self._build_function_info(node, fn_name, signature, self._is_pub(node)))
        return functions

    # -- Containers -------------------------------------------------------------------------

    def _find_var_decl_in_node(self, decl_node) -> Any:
        """Find the VarDecl child of a legacy `Decl` node."""
        for child in _children(decl_node):
            if _zero_arg(child, 'kind') == _LEGACY_VARIABLE_KIND:
                return child
        return None

    def _extract_var_name_and_container(self, var_decl) -> tuple:
        """(name, container) of a variable declaration in either grammar (a node from
        `_variable_nodes()`). The container is its value only when that value is a container
        literal itself, not a call or an `if` producing one.
        """
        var_name = None
        container_decl = None
        if _zero_arg(var_decl, 'kind') == VARIABLE_KIND:
            for child in _children(var_decl):
                kind = _zero_arg(child, 'kind')
                if kind == 'identifier' and var_name is None:
                    var_name = self._get_node_text(child)  # the first identifier; a type annotation follows it
                elif kind in CONTAINER_KINDS:
                    container_decl = child
            return var_name, container_decl

        for var_child in _children(var_decl):
            if _zero_arg(var_child, 'kind') == 'IDENTIFIER':
                var_name = self._get_node_text(var_child)
            candidate = self._unwrap_expression(var_child)
            if _zero_arg(candidate, 'kind') == 'ContainerDecl':
                container_decl = candidate

        return var_name, container_decl

    def _unwrap_expression(self, node):
        """Unwrap only single-child legacy expression shells; calls/operators remain intact."""
        while _zero_arg(node, 'kind') in ('ErrorUnionExpr', 'SuffixExpr'):
            children = _children(node)
            if len(children) != 1:
                break
            node = children[0]
        return node

    def _is_correct_container_type(self, container_decl, container_type: str) -> bool:
        """Check if a container is of the specified type (struct/enum/union)."""
        kind = _zero_arg(container_decl, 'kind')
        if kind in CONTAINER_KINDS:
            return CONTAINER_KINDS[kind] == container_type  # `union(enum)` is a union_declaration
        for cont_child in _children(container_decl):
            if _zero_arg(cont_child, 'kind') == 'ContainerDeclType':
                children = _children(cont_child)
                # The declared kind is first: union(enum) is a union, not an enum.
                return bool(children and _zero_arg(children[0], 'kind') == container_type)
            if _zero_arg(cont_child, 'kind') == container_type:
                return True
        return False

    def _field_name(self, field, is_enum: bool) -> Optional[str]:
        """Name of a 1.25 `container_field`. An enum field is its name (`_`, the non-exhaustive
        marker, is none). A struct or union field is named only when it is typed (`x: T`): a tuple
        field (`struct { u32, Foo }`) holds its type in the `name` field."""
        name = field.child_by_field_name('name')
        if name is None or _zero_arg(name, 'kind') != 'identifier':
            return None
        text = self._get_node_text(name)
        if is_enum:
            return text if text and text != '_' else None
        return text if text and field.child_by_field_name('type') is not None else None

    def _extract_container_field_names(self, member) -> List[str]:
        """Extract field names from a legacy ContainerField node."""
        parent = _zero_arg(member, 'parent')
        is_enum = parent is not None and self._is_correct_container_type(parent, 'enum')
        for field_child in _children(member):
            candidate = self._unwrap_expression(field_child) if is_enum else field_child
            if _zero_arg(candidate, 'kind') == 'IDENTIFIER':
                name = self._get_node_text(candidate)
                return [] if is_enum and name == '_' else [name]
        return []

    def _extract_fields_from_auto(self, cont_decl_auto) -> List[str]:
        """Extract field names from a legacy ContainerDeclAuto node."""
        fields = []
        for member in _children(cont_decl_auto):
            if _zero_arg(member, 'kind') == 'ContainerField':
                fields.extend(self._extract_container_field_names(member))
        return fields

    def _extract_container_members(self, container_decl) -> List[str]:
        """Direct field names of a container, in either grammar (not nested types or methods)."""
        if _zero_arg(container_decl, 'kind') in CONTAINER_KINDS:
            is_enum = self._is_correct_container_type(container_decl, 'enum')
            names = (self._field_name(child, is_enum) for child in _children(container_decl)
                     if _zero_arg(child, 'kind') == 'container_field')
            return [name for name in names if name]
        members = []
        for cont_child in _children(container_decl):
            if _zero_arg(cont_child, 'kind') == 'ContainerField':
                members.extend(self._extract_container_field_names(cont_child))
            elif _zero_arg(cont_child, 'kind') == 'ContainerDeclAuto':
                members.extend(self._extract_fields_from_auto(cont_child))
        return members

    def _build_container_info(
        self, decl_node, var_name: str, members: List[str], has_pub: bool
    ) -> StructureItem:
        """Build container information dictionary."""
        container_info: StructureItem = {
            'line': _zero_arg(decl_node, 'start_position').row + 1,
            'line_end': _zero_arg(decl_node, 'end_position').row + 1,
            'name': var_name,
            'members': members,
        }

        if has_pub:
            container_info['visibility'] = 'pub'

        return container_info

    def _extract_container_decls(self, container_type: str) -> List[StructureItem]:
        """Extract file- and container-level struct, enum, or union definitions."""
        containers: List[StructureItem] = []
        for var_node in self._variable_nodes():
            declaration = self._member_declaration(var_node)
            if declaration is None:
                continue
            var_name, container_decl = self._extract_var_name_and_container(var_node)
            if not container_decl or not var_name:
                continue
            if not self._is_correct_container_type(container_decl, container_type):
                continue
            members = self._extract_container_members(container_decl)
            containers.append(self._build_container_info(declaration, var_name, members, self._is_pub(declaration)))
        return containers

    # -- Tests ------------------------------------------------------------------------------

    def _get_test_name(self, test_node) -> Optional[str]:
        """Extract the name string from a test declaration, or None.

        `test "name" {}` names itself via a string child (legacy STRINGLITERALSINGLE, 1.25
        `string`); `test SomeType {}` (the idiomatic way to colocate tests with a
        generic type/fn, e.g. testing a `pub fn Foo(comptime T: type) type`
        factory) names itself via a bare identifier child instead — without
        this second case, every identifier-named test (and every call made
        from inside one) was entirely absent from get_structure(), not just
        blind to its calls (BACK-755, found via the Zig calls-recall-oracle
        measurement, BACK-730). `test {}` has no name.
        """
        for child in _children(test_node):
            kind = _zero_arg(child, 'kind')
            if kind in ('STRINGLITERALSINGLE', 'string'):
                name = self._get_node_text(child)
                return name[1:-1] if name.startswith('"') and name.endswith('"') else name
            if kind in ('IDENTIFIER', 'identifier'):
                return self._get_node_text(child)
        return None

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a named function or test from Zig source."""
        if element_type == 'function' and self.tree:
            for node in self._function_nodes():
                if self._function_name(node) == name:
                    return {
                        'name': name,
                        'line_start': _zero_arg(node, 'start_position').row + 1,
                        'line_end': _zero_arg(node, 'end_position').row + 1,
                        'source': self._get_node_text(node),
                    }
        if element_type == 'test' and self.tree:
            test_nodes = self._find_named_test_callbacks(name)
            if test_nodes:
                test_node = test_nodes[0]
                return {
                    'name': name,
                    'line_start': _zero_arg(test_node, 'start_position').row + 1,
                    'line_end': _zero_arg(test_node, 'end_position').row + 1,
                    'source': self._get_node_text(test_node),
                }
        return super().extract_element(element_type, name)

    def _extract_tests(self) -> List[StructureItem]:
        """Extract test blocks.

        `line_end` was missing here (BACK-661) even though `_build_function_info`
        sets it for functions — the outline rendered every test as `[0 lines]`,
        indistinguishable from an empty test, because nothing else in the dict
        conveyed the real span.
        """
        tests: List[StructureItem] = []
        for test_node in self._test_nodes():
            test_name = self._get_test_name(test_node)
            if test_name:
                line_start = _zero_arg(test_node, 'start_position').row + 1
                line_end = _zero_arg(test_node, 'end_position').row + 1
                tests.append({
                    'line': line_start,
                    'line_end': line_end,
                    'name': test_name,
                    # A function called only from a test block previously
                    # reported zero callers via calls:// (same failure mode
                    # as BACK-660, one hop further in) — mirrors TS/JS test
                    # callbacks, which get 'calls' via _build_function_dict.
                    'calls': self._extract_calls(test_node, line_start, line_end),
                })
        return tests

    def _find_named_test_callbacks(self, name: str) -> List[Any]:
        """Resolve a Zig `test "name" {}` block back to its test declaration node(s),
        every same-named one in tree order (BACK-1400).

        Generic hook name shared with the JS/TS Jest/Vitest resolver
        (`_js_test_callbacks.py`) — `element_resolve._unnamed_kind_matches`
        looks for this method on any analyzer via `getattr`, so implementing
        it is enough to make
        `reveal file.zig "test name"` resolve exactly what `--outline`
        lists (BACK-661: previously the outline advertised all 62 test names
        as addressable handles that direct extraction then rejected, because
        'test'/'TestDecl' was never in `ELEMENT_TYPE_MAP`/`FUNCTION_NODE_TYPES`
        and this hook didn't exist for Zig).
        """
        return [test_node for test_node in self._test_nodes()
                if self._get_test_name(test_node) == name]
