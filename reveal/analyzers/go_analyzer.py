"""
Go file analyzer using tree-sitter.

Extracts:
- Functions
- Structs
- Interfaces
- Methods
- Imports
"""

from typing import Dict, Any, List
from .treesitter_base import TreeSitterAnalyzer, TREE_SITTER_AVAILABLE
from ..registry import register


@register(['.go'], name='Go', icon='🐹')
class GoAnalyzer(TreeSitterAnalyzer):
    """
    Analyzer for Go source files.

    Features:
    - Functions, methods, structs, interfaces
    - Package and import statements
    - Type definitions

    All positions are exact (tree-sitter preserves source locations).
    """

    language_name = 'go'

    def __init__(self, lines: List[str], **kwargs):
        """Initialize Go analyzer."""
        self.node_type_map = {
            'function': 'function_declaration',
            'import': 'import_declaration',
        }
        super().__init__(lines, **kwargs)

    def extract_custom(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract Go-specific items."""
        return {
            'methods': self._extract_nodes('method_declaration', name_field='name'),
            'interfaces': self._extract_interfaces(),
            'structs': self._extract_structs(),
            'types': self._extract_types(),
        }

    def _extract_structs(self) -> List[Dict[str, Any]]:
        """Extract struct declarations."""
        if not self.tree:
            return []

        structs = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'type_spec':
                # Check if this type_spec contains a struct_type
                for child in node.children:
                    if child.type == 'struct_type':
                        # Get the name from type_identifier
                        name_node = node.child_by_field_name('name')
                        if name_node:
                            line = node.start_point[0] + 1
                            if self.in_focus_range(line):
                                structs.append({
                                    'name': name_node.text.decode('utf-8'),
                                    'line': line
                                })
                        break

            # Recurse
            if cursor.goto_first_child():
                visit(cursor)
                while cursor.goto_next_sibling():
                    visit(cursor)
                cursor.goto_parent()

        visit(cursor)
        return structs

    def _extract_interfaces(self) -> List[Dict[str, Any]]:
        """Extract interface declarations."""
        if not self.tree:
            return []

        interfaces = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'type_spec':
                # Check if this type_spec contains an interface_type
                for child in node.children:
                    if child.type == 'interface_type':
                        name_node = node.child_by_field_name('name')
                        if name_node:
                            line = node.start_point[0] + 1
                            if self.in_focus_range(line):
                                interfaces.append({
                                    'name': name_node.text.decode('utf-8'),
                                    'line': line
                                })
                        break

            # Recurse
            if cursor.goto_first_child():
                visit(cursor)
                while cursor.goto_next_sibling():
                    visit(cursor)
                cursor.goto_parent()

        visit(cursor)
        return interfaces

    def _extract_types(self) -> List[Dict[str, Any]]:
        """Extract type declarations (excluding interfaces and structs)."""
        if not self.tree:
            return []

        types = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'type_spec':
                # Check that it's not a struct or interface (handled separately)
                has_struct_or_interface = False
                for child in node.children:
                    if child.type in ('interface_type', 'struct_type'):
                        has_struct_or_interface = True
                        break

                if not has_struct_or_interface:
                    name_node = node.child_by_field_name('name')
                    if name_node:
                        line = node.start_point[0] + 1
                        if self.in_focus_range(line):
                            types.append({
                                'name': name_node.text.decode('utf-8'),
                                'line': line
                            })

            # Recurse
            if cursor.goto_first_child():
                visit(cursor)
                while cursor.goto_next_sibling():
                    visit(cursor)
                cursor.goto_parent()

        visit(cursor)
        return types

    def format_structure(self, structure: Dict[str, Any]) -> List[str]:
        """
        Custom formatting for Go structure output.

        Groups items logically:
        1. Package/Imports
        2. Types (structs, interfaces)
        3. Functions
        4. Methods
        """
        if not TREE_SITTER_AVAILABLE or 'error' in structure:
            return None  # Use default formatting

        lines = []

        # Imports
        imports = structure.get('imports', [])
        if imports:
            lines.append(f"\nImports ({len(imports)}):")
            for item in imports[:10]:
                loc = self.format_location(item['line'])
                name = item['name']
                if len(name) > 60:
                    name = name[:57] + "..."
                lines.append(f"  {loc:30}  {name}")
            if len(imports) > 10:
                lines.append(f"  ... and {len(imports) - 10} more")

        # Types section
        types = structure.get('types', [])
        structs = structure.get('structs', [])
        interfaces = structure.get('interfaces', [])

        type_count = len(types) + len(structs) + len(interfaces)
        if type_count > 0:
            lines.append(f"\nTypes ({type_count}):")

            if structs:
                lines.append(f"  Structs ({len(structs)}):")
                for item in structs:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

            if interfaces:
                lines.append(f"  Interfaces ({len(interfaces)}):")
                for item in interfaces:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

            if types:
                lines.append(f"  Other Types ({len(types)}):")
                for item in types:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

        # Functions
        functions = structure.get('functions', [])
        if functions:
            lines.append(f"\nFunctions ({len(functions)}):")
            for item in functions:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  func {item['name']}()")

        # Methods
        methods = structure.get('methods', [])
        if methods:
            lines.append(f"\nMethods ({len(methods)}):")
            for item in methods:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  func {item['name']}()")

        return lines if lines else None
