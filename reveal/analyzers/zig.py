"""Zig analyzer using tree-sitter."""
from typing import Dict, List, Any
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.zig', name='Zig', icon='⚡')
class ZigAnalyzer(TreeSitterAnalyzer):
    """Zig language analyzer.

    Supports Zig source files with functions, structs, enums, tests, and more.
    """
    language = 'zig'

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
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

        # Remove empty categories
        return {k: v for k, v in structure.items() if v}

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract function definitions."""
        functions = []

        # Find all Decl nodes that contain FnProto
        decl_nodes = self._find_nodes_by_type('Decl')

        for decl_node in decl_nodes:
            # Check if this decl has a function prototype
            fn_proto = None
            has_pub = False

            # Check siblings for pub keyword
            if decl_node.prev_sibling and decl_node.prev_sibling.type == 'pub':
                has_pub = True

            for child in decl_node.children:
                if child.type == 'FnProto':
                    fn_proto = child
                    break

            if not fn_proto:
                continue

            # Extract function name and signature
            fn_name = None
            params = []

            for fn_child in fn_proto.children:
                if fn_child.type == 'fn':
                    # Next sibling should be the identifier (function name)
                    next_sib = fn_child.next_sibling
                    if next_sib and next_sib.type == 'IDENTIFIER':
                        fn_name = self._get_node_text(next_sib)
                elif fn_child.type == 'ParamDeclList':
                    # Extract parameter names
                    for param_child in fn_child.children:
                        if param_child.type == 'ParamDecl':
                            # Try to get parameter name
                            for p in param_child.children:
                                if p.type == 'IDENTIFIER':
                                    params.append(self._get_node_text(p))
                                    break

            if fn_name:
                signature = f"{fn_name}({', '.join(params)})" if params else fn_name

                func_info = {
                    'line': decl_node.start_point[0] + 1,
                    'name': fn_name,
                    'signature': signature,
                }

                if has_pub:
                    func_info['visibility'] = 'pub'

                functions.append(func_info)

        return functions

    def _extract_container_decls(self, container_type: str) -> List[Dict[str, Any]]:
        """Extract struct, enum, or union definitions."""
        containers = []

        # Find VarDecl nodes that define containers
        decl_nodes = self._find_nodes_by_type('Decl')

        for decl_node in decl_nodes:
            has_pub = False
            var_decl = None

            # Check siblings for pub keyword
            if decl_node.prev_sibling and decl_node.prev_sibling.type == 'pub':
                has_pub = True

            # Find VarDecl child
            for child in decl_node.children:
                if child.type == 'VarDecl':
                    var_decl = child
                    break

            if not var_decl:
                continue

            # Look for ContainerDecl of the right type
            container_decl = None
            var_name = None

            for var_child in var_decl.children:
                if var_child.type == 'IDENTIFIER':
                    var_name = self._get_node_text(var_child)
                elif var_child.type == 'ContainerDecl':
                    container_decl = var_child

            if not container_decl or not var_name:
                continue

            # Check if this is the right container type
            is_correct_type = False
            for cont_child in container_decl.children:
                if cont_child.type == container_type:
                    is_correct_type = True
                    break

            if not is_correct_type:
                continue

            # Extract fields/values
            members = []
            for cont_child in container_decl.children:
                if cont_child.type == 'ContainerDeclAuto':
                    # Extract container members
                    for member in cont_child.children:
                        if member.type == 'ContainerField':
                            # Get field name
                            for field_child in member.children:
                                if field_child.type == 'IDENTIFIER':
                                    members.append(self._get_node_text(field_child))
                                    break

            container_info = {
                'line': decl_node.start_point[0] + 1,
                'name': var_name,
                'members': members,
            }

            if has_pub:
                container_info['visibility'] = 'pub'

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
