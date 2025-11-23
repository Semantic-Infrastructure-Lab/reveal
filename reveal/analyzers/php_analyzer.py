"""
PHP file analyzer using tree-sitter.

Extracts:
- Classes
- Functions
- Methods
- Traits
- Interfaces
- Namespaces
"""

from typing import Dict, Any, List
from .treesitter_base import TreeSitterAnalyzer, TREE_SITTER_AVAILABLE
from ..registry import register


@register(['.php'], name='PHP', icon='🐘')
class PHPAnalyzer(TreeSitterAnalyzer):
    """
    Analyzer for PHP source files.

    Features:
    - Classes, interfaces, traits
    - Functions and methods
    - Namespaces
    - Use statements

    All positions are exact (tree-sitter preserves source locations).
    """

    language_name = 'php'

    def __init__(self, lines: List[str], **kwargs):
        """Initialize PHP analyzer."""
        self.node_type_map = {
            'function': 'function_definition',
            'class': 'class_declaration',
            'import': 'namespace_use_declaration',
        }
        super().__init__(lines, **kwargs)

    def extract_custom(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract PHP-specific items."""
        return {
            'methods': self._extract_nodes('method_declaration', name_field='name'),
            'interfaces': self._extract_nodes('interface_declaration', name_field='name'),
            'traits': self._extract_nodes('trait_declaration', name_field='name'),
            'namespaces': self._extract_namespaces(),
        }

    def _extract_namespaces(self) -> List[Dict[str, Any]]:
        """Extract namespace declarations."""
        if not self.tree:
            return []

        namespaces = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'namespace_definition':
                # Get namespace name
                name_node = node.child_by_field_name('name')
                if name_node:
                    line = node.start_point[0] + 1
                    if self.in_focus_range(line):
                        namespaces.append({
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
        return namespaces

    def format_structure(self, structure: Dict[str, Any]) -> List[str]:
        """
        Custom formatting for PHP structure output.

        Groups items logically:
        1. Namespaces
        2. Use statements
        3. Types (classes, interfaces, traits)
        4. Functions
        5. Methods
        """
        if not TREE_SITTER_AVAILABLE or 'error' in structure:
            return None

        lines = []

        # Namespaces
        namespaces = structure.get('namespaces', [])
        if namespaces:
            lines.append(f"\nNamespaces ({len(namespaces)}):")
            for item in namespaces:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")

        # Use statements
        imports = structure.get('imports', [])
        if imports:
            lines.append(f"\nUse statements ({len(imports)}):")
            for item in imports[:10]:
                loc = self.format_location(item['line'])
                name = item['name']
                if len(name) > 60:
                    name = name[:57] + "..."
                lines.append(f"  {loc:30}  {name}")
            if len(imports) > 10:
                lines.append(f"  ... and {len(imports) - 10} more")

        # Types
        classes = structure.get('classes', [])
        interfaces = structure.get('interfaces', [])
        traits = structure.get('traits', [])

        type_count = len(classes) + len(interfaces) + len(traits)
        if type_count > 0:
            lines.append(f"\nTypes ({type_count}):")

            if classes:
                lines.append(f"  Classes ({len(classes)}):")
                for item in classes:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

            if interfaces:
                lines.append(f"  Interfaces ({len(interfaces)}):")
                for item in interfaces:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

            if traits:
                lines.append(f"  Traits ({len(traits)}):")
                for item in traits:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

        # Functions
        functions = structure.get('functions', [])
        if functions:
            lines.append(f"\nFunctions ({len(functions)}):")
            for item in functions:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  function {item['name']}()")

        # Methods
        methods = structure.get('methods', [])
        if methods:
            lines.append(f"\nMethods ({len(methods)}):")
            for item in methods[:20]:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}()")
            if len(methods) > 20:
                lines.append(f"  ... and {len(methods) - 20} more")

        return lines if lines else None
