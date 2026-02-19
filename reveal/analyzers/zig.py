"""Zig analyzer using tree-sitter."""
from typing import Any, Dict, List, Optional
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.zig', name='Zig', icon='⚡')
class ZigAnalyzer(TreeSitterAnalyzer):
    """Zig language analyzer.

    Supports Zig source files with functions, structs, enums, tests, and more.
    """
    language = 'zig'

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
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
        return bool(decl_node.prev_sibling and
                    decl_node.prev_sibling.type == 'pub')

    def _find_fn_proto(self, decl_node):
        """Find FnProto child node in declaration."""
        for child in decl_node.children:
            if child.type == 'FnProto':
                return child
        return None

    def _extract_function_name(self, fn_proto) -> Optional[str]:
        """Extract function name from FnProto node."""
        for fn_child in fn_proto.children:
            if fn_child.type == 'fn':
                # Next sibling should be the identifier (function name)
                next_sib = fn_child.next_sibling
                if next_sib and next_sib.type == 'IDENTIFIER':
                    return self._get_node_text(next_sib)
        return None

    def _get_param_name(self, param_decl) -> Optional[str]:
        """Get the identifier name from a ParamDecl node, or None."""
        for p in param_decl.children:
            if p.type == 'IDENTIFIER':
                return self._get_node_text(p)
        return None

    def _extract_param_names(self, fn_proto) -> List[str]:
        """Extract parameter names from FnProto node."""
        params = []
        for fn_child in fn_proto.children:
            if fn_child.type == 'ParamDeclList':
                for param_child in fn_child.children:
                    if param_child.type == 'ParamDecl':
                        name = self._get_param_name(param_child)
                        if name:
                            params.append(name)
        return params

    def _build_function_signature(self, fn_name: str, params: List[str]) -> str:
        """Build function signature string."""
        return f"{fn_name}({', '.join(params)})" if params else fn_name

    def _build_function_info(self, decl_node, fn_name: str, signature: str, has_pub: bool) -> Dict[str, Any]:
        """Build function information dictionary."""
        func_info = {
            'line': decl_node.start_point[0] + 1,
            'name': fn_name,
            'signature': signature,
        }
        if has_pub:
            func_info['visibility'] = 'pub'
        return func_info

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
        return bool(node.prev_sibling and node.prev_sibling.type == 'pub')

    def _find_var_decl_in_node(self, decl_node) -> Any:
        """Find VarDecl child node in a Decl node."""
        for child in decl_node.children:
            if child.type == 'VarDecl':
                return child
        return None

    def _extract_var_name_and_container(self, var_decl) -> tuple:
        """Extract variable name and ContainerDecl from VarDecl node.

        Returns:
            Tuple of (var_name, container_decl)
        """
        var_name = None
        container_decl = None

        for var_child in var_decl.children:
            if var_child.type == 'IDENTIFIER':
                var_name = self._get_node_text(var_child)
            elif var_child.type == 'ContainerDecl':
                container_decl = var_child

        return var_name, container_decl

    def _is_correct_container_type(self, container_decl, container_type: str) -> bool:
        """Check if ContainerDecl is of the specified type (struct/enum/union)."""
        for cont_child in container_decl.children:
            if cont_child.type == container_type:
                return True
        return False

    def _extract_container_field_names(self, member) -> List[str]:
        """Extract field names from a ContainerField node."""
        for field_child in member.children:
            if field_child.type == 'IDENTIFIER':
                return [self._get_node_text(field_child)]
        return []

    def _extract_container_members(self, container_decl) -> List[str]:
        """Extract member field names from a ContainerDecl."""
        members = []
        for cont_child in container_decl.children:
            if cont_child.type == 'ContainerDeclAuto':
                for member in cont_child.children:
                    if member.type == 'ContainerField':
                        members.extend(self._extract_container_field_names(member))
        return members

    def _build_container_info(
        self, decl_node, var_name: str, members: List[str], has_pub: bool
    ) -> Dict[str, Any]:
        """Build container information dictionary."""
        container_info = {
            'line': decl_node.start_point[0] + 1,
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

    def _extract_tests(self) -> List[Dict[str, Any]]:
        """Extract test blocks."""
        tests = []

        test_nodes = self._find_nodes_by_type('TestDecl')

        for test_node in test_nodes:
            test_name = None

            # Look for the test name (string literal)
            for child in test_node.children:
                if child.type == 'STRINGLITERALSINGLE':
                    test_name = self._get_node_text(child)
                    # Remove quotes
                    if test_name.startswith('"') and test_name.endswith('"'):
                        test_name = test_name[1:-1]
                    break

            if test_name:
                tests.append({
                    'line': test_node.start_point[0] + 1,
                    'name': test_name,
                })

        return tests
