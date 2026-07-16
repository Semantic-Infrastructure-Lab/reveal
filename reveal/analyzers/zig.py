"""Zig analyzer using tree-sitter."""
from typing import Any, Dict, List, Optional
from ..registry import register
from ..treesitter import TreeSitterAnalyzer
from ..core import node_children as _children, node_next_sibling as _next_sibling, node_prev_sibling as _prev_sibling
from ..adapters.ast.nav_calls import range_calls


@register('.zig', name='Zig', icon='⚡')
class ZigAnalyzer(TreeSitterAnalyzer):
    """Zig language analyzer.

    Supports Zig source files with functions, structs, enums, tests, and more.
    """
    language = 'zig'

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract Zig code structure."""
        if not self.tree:
            return {}

        structure = {}

        # Extract Zig elements
        structure['functions'] = self._extract_functions()
        structure['structs'] = self._extract_container_decls('struct')
        structure['enums'] = self._extract_container_decls('enum')
        structure['unions'] = self._extract_container_decls('union')
        structure['tests'] = self._extract_tests()

        # Apply semantic slicing to each category
        if head or tail or range:
            for category in structure:
                structure[category] = self._apply_semantic_slice(
                    structure[category], head, tail, range
                )

        # Remove empty categories and add output contract fields
        return {
            'contract_version': '1.0',
            'type': 'zig_structure',
            'source': str(self.path),
            'source_type': 'file',
            **{k: v for k, v in structure.items() if v},
        }

    def _has_pub_visibility(self, decl_node) -> bool:
        """Check if declaration has pub keyword."""
        return bool(_prev_sibling(decl_node) and
                    _prev_sibling(decl_node).kind() == 'pub')

    def _find_fn_proto(self, decl_node):
        """Find FnProto child node in declaration."""
        for child in _children(decl_node):
            if child.kind() == 'FnProto':
                return child
        return None

    def _get_node_name(self, node) -> Optional[str]:
        """Override: Zig's grammar wraps functions in a 'Decl' node (added to
        the shared FUNCTION_NODE_TYPES so nav flags like --varflow/--exits can
        resolve a function by name via the generic file_handler lookup, which
        was previously blind to Zig entirely — outline used a bespoke
        extractor while every single-function nav flag used the generic
        FUNCTION_NODE_TYPES search, which never matched Zig's grammar).
        A bare 'Decl' may also wrap a struct/enum/union/var — those have no
        FnProto child, so this correctly returns None and falls through."""
        if node.kind() == 'Decl':
            fn_proto = self._find_fn_proto(node)
            return self._extract_function_name(fn_proto) if fn_proto else None
        return super()._get_node_name(node)

    def _extract_function_name(self, fn_proto) -> Optional[str]:
        """Extract function name from FnProto node."""
        for fn_child in _children(fn_proto):
            if fn_child.kind() == 'fn':
                # Next sibling should be the identifier (function name)
                next_sib = _next_sibling(fn_child)
                if next_sib and next_sib.kind() == 'IDENTIFIER':
                    return self._get_node_text(next_sib)
        return None

    def _get_param_name(self, param_decl) -> Optional[str]:
        """Get the identifier name from a ParamDecl node, or None."""
        for p in _children(param_decl):
            if p.kind() == 'IDENTIFIER':
                return self._get_node_text(p)
        return None

    def _iter_param_decl_names(self, param_decl_list) -> List[str]:
        """Yield parameter names from a ParamDeclList node."""
        for param_child in _children(param_decl_list):
            if param_child.kind() == 'ParamDecl':
                name = self._get_param_name(param_child)
                if name:
                    yield name

    def _extract_param_names(self, fn_proto) -> List[str]:
        """Extract parameter names from FnProto node."""
        for fn_child in _children(fn_proto):
            if fn_child.kind() == 'ParamDeclList':
                return list(self._iter_param_decl_names(fn_child))
        return []

    def _build_function_signature(self, fn_name: str, params: List[str]) -> str:
        """Build function signature string (params only, no name — matches display convention)."""
        return f"({', '.join(params)})" if params else ""

    def _build_function_info(self, decl_node, fn_name: str, signature: str, has_pub: bool) -> Dict[str, Any]:
        """Build function information dictionary."""
        line_start = decl_node.start_position().row + 1
        line_end = decl_node.end_position().row + 1
        func_info = {
            'line': line_start,
            'line_end': line_end,
            'name': fn_name,
            'signature': signature,
            'calls': self._extract_calls(decl_node, line_start, line_end),
        }
        if has_pub:
            func_info['visibility'] = 'pub'
        return func_info

    def _extract_calls(self, node, line_start: int, line_end: int) -> List[str]:
        """Callee names reachable from `node`, deduped in first-seen order.

        Zig has no call-expression wrapper node — `foo(x)` / `a.b.c(x)` parse
        as a single `SuffixExpr` (see `nav_calls._extract_zig_suffix_calls`),
        so `calls://` (which walks `CALL_NODE_TYPES` — Python `call`, JS/Rust
        `call_expression`, etc.) previously saw zero callees for every Zig
        function, reporting live functions as having no callers (BACK-660).
        Reusing `range_calls` here — the same decoder `--calls` already uses
        — rather than teaching `CALL_NODE_TYPES` a shape it can't represent
        (call-or-not depends on a child node, not the node's own kind).
        """
        seen: List[str] = []
        seen_set = set()
        for call in range_calls(node, line_start, line_end, self._get_node_text):
            callee = call['callee']
            if callee and callee not in seen_set:
                seen.append(callee)
                seen_set.add(callee)
        return seen

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract function definitions."""
        functions = []
        decl_nodes = self._find_nodes_by_type('Decl')

        for decl_node in decl_nodes:
            # Check visibility and find function prototype
            has_pub = self._has_pub_visibility(decl_node)
            fn_proto = self._find_fn_proto(decl_node)

            if not fn_proto:
                continue

            # Extract function details
            fn_name = self._extract_function_name(fn_proto)
            if not fn_name:
                continue

            params = self._extract_param_names(fn_proto)
            signature = self._build_function_signature(fn_name, params)
            func_info = self._build_function_info(decl_node, fn_name, signature, has_pub)

            functions.append(func_info)

        return functions

    def _has_pub_keyword(self, node) -> bool:
        """Check if node has a pub keyword as previous sibling."""
        return bool(_prev_sibling(node) and _prev_sibling(node).kind() == 'pub')

    def _find_var_decl_in_node(self, decl_node) -> Any:
        """Find VarDecl child node in a Decl node."""
        for child in _children(decl_node):
            if child.kind() == 'VarDecl':
                return child
        return None

    def _extract_var_name_and_container(self, var_decl) -> tuple:
        """Extract variable name and ContainerDecl from VarDecl node.

        Returns:
            Tuple of (var_name, container_decl)
        """
        var_name = None
        container_decl = None

        for var_child in _children(var_decl):
            if var_child.kind() == 'IDENTIFIER':
                var_name = self._get_node_text(var_child)
            elif var_child.kind() == 'ContainerDecl':
                container_decl = var_child

        return var_name, container_decl

    def _is_correct_container_type(self, container_decl, container_type: str) -> bool:
        """Check if ContainerDecl is of the specified type (struct/enum/union)."""
        for cont_child in _children(container_decl):
            if cont_child.kind() == container_type:
                return True
        return False

    def _extract_container_field_names(self, member) -> List[str]:
        """Extract field names from a ContainerField node."""
        for field_child in _children(member):
            if field_child.kind() == 'IDENTIFIER':
                return [self._get_node_text(field_child)]
        return []

    def _extract_fields_from_auto(self, cont_decl_auto) -> List[str]:
        """Extract field names from a ContainerDeclAuto node."""
        fields = []
        for member in _children(cont_decl_auto):
            if member.kind() == 'ContainerField':
                fields.extend(self._extract_container_field_names(member))
        return fields

    def _extract_container_members(self, container_decl) -> List[str]:
        """Extract member field names from a ContainerDecl."""
        members = []
        for cont_child in _children(container_decl):
            if cont_child.kind() == 'ContainerDeclAuto':
                members.extend(self._extract_fields_from_auto(cont_child))
        return members

    def _build_container_info(
        self, decl_node, var_name: str, members: List[str], has_pub: bool
    ) -> Dict[str, Any]:
        """Build container information dictionary."""
        container_info = {
            'line': decl_node.start_position().row + 1,
            'name': var_name,
            'members': members,
        }

        if has_pub:
            container_info['visibility'] = 'pub'

        return container_info

    def _extract_container_decls(self, container_type: str) -> List[Dict[str, Any]]:
        """Extract struct, enum, or union definitions."""
        containers = []
        decl_nodes = self._find_nodes_by_type('Decl')

        for decl_node in decl_nodes:
            # Check visibility
            has_pub = self._has_pub_keyword(decl_node)

            # Find VarDecl
            var_decl = self._find_var_decl_in_node(decl_node)
            if not var_decl:
                continue

            # Extract name and container declaration
            var_name, container_decl = self._extract_var_name_and_container(var_decl)
            if not container_decl or not var_name:
                continue

            # Verify container type
            if not self._is_correct_container_type(container_decl, container_type):
                continue

            # Extract members and build result
            members = self._extract_container_members(container_decl)
            container_info = self._build_container_info(decl_node, var_name, members, has_pub)
            containers.append(container_info)

        return containers

    def _get_test_name(self, test_node) -> Optional[str]:
        """Extract the name string from a TestDecl node, or None."""
        for child in _children(test_node):
            if child.kind() == 'STRINGLITERALSINGLE':
                name = self._get_node_text(child)
                return name[1:-1] if name.startswith('"') and name.endswith('"') else name
        return None

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a named function or test from Zig source."""
        if element_type == 'function' and self.tree:
            for decl_node in self._find_nodes_by_type('Decl'):
                fn_proto = self._find_fn_proto(decl_node)
                if fn_proto:
                    fn_name = self._extract_function_name(fn_proto)
                    if fn_name == name:
                        return {
                            'name': name,
                            'line_start': decl_node.start_position().row + 1,
                            'line_end': decl_node.end_position().row + 1,
                            'source': self._get_node_text(decl_node),
                        }
        if element_type == 'test' and self.tree:
            test_node = self._find_named_test_callback(name)
            if test_node is not None:
                return {
                    'name': name,
                    'line_start': test_node.start_position().row + 1,
                    'line_end': test_node.end_position().row + 1,
                    'source': self._get_node_text(test_node),
                }
        return super().extract_element(element_type, name)

    def _extract_tests(self) -> List[Dict[str, Any]]:
        """Extract test blocks.

        `line_end` was missing here (BACK-661) even though `_build_function_info`
        sets it for functions — the outline rendered every test as `[0 lines]`,
        indistinguishable from an empty test, because nothing else in the dict
        conveyed the real span.
        """
        tests = []
        for test_node in self._find_nodes_by_type('TestDecl'):
            test_name = self._get_test_name(test_node)
            if test_name:
                line_start = test_node.start_position().row + 1
                line_end = test_node.end_position().row + 1
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

    def _find_named_test_callback(self, name: str):
        """Resolve a Zig `test "name" {}` block back to its `TestDecl` node.

        Generic hook name shared with TypeScript's Jest/Vitest resolver
        (`typescript.py:_find_named_test_callback`) — `display/element.py`'s
        `_try_treesitter_extraction` already looks for this method on any
        analyzer via `getattr`, so implementing it is enough to make
        `reveal file.zig "test name"` resolve exactly what `--outline`
        lists (BACK-661: previously the outline advertised all 62 test names
        as addressable handles that direct extraction then rejected, because
        'test'/'TestDecl' was never in `ELEMENT_TYPE_MAP`/`FUNCTION_NODE_TYPES`
        and this hook didn't exist for Zig).
        """
        for test_node in self._find_nodes_by_type('TestDecl'):
            if self._get_test_name(test_node) == name:
                return test_node
        return None