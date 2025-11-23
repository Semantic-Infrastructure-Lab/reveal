"""
C# file analyzer using tree-sitter.

Extracts C# structure including:
- Namespaces
- Classes
- Interfaces
- Structs
- Enums
- Methods
- Properties
- Using statements (imports)

Demonstrates the power of tree-sitter for enterprise languages.
"""

from typing import Dict, Any, List
from .treesitter_base import TreeSitterAnalyzer, TREE_SITTER_AVAILABLE
from ..registry import register


@register(['.cs'], name='C#', icon='🔷')
class CSharpAnalyzer(TreeSitterAnalyzer):
    """
    Analyzer for C# source files.

    Features:
    - Full OOP structure (classes, interfaces, methods)
    - Namespace detection
    - Using statements
    - Properties and fields
    - Delegates and events

    All positions are exact (tree-sitter preserves source locations).
    """

    # Set language for tree-sitter
    language_name = 'c_sharp'

    def __init__(self, lines: List[str], **kwargs):
        """Initialize C# analyzer."""
        # Map reveal's generic names to C#'s tree-sitter node types
        self.node_type_map = {
            'function': 'method_declaration',
            'class': 'class_declaration',
            'import': 'using_directive',
        }
        super().__init__(lines, **kwargs)

    def extract_custom(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract C#-specific items."""
        return {
            'namespaces': self._extract_nodes('namespace_declaration', name_field='name'),
            'interfaces': self._extract_nodes('interface_declaration', name_field='name'),
            'structs': self._extract_nodes('struct_declaration', name_field='name'),
            'enums': self._extract_nodes('enum_declaration', name_field='name'),
            'properties': self._extract_nodes('property_declaration', name_field='name'),
            'delegates': self._extract_nodes('delegate_declaration', name_field='name'),
            'events': self._extract_nodes('event_declaration', name_field='name'),
        }

    def format_structure(self, structure: Dict[str, Any]) -> List[str]:
        """
        Custom formatting for C# structure output.

        Groups items logically:
        1. Namespaces
        2. Using statements
        3. Types (classes, interfaces, structs, enums)
        4. Members (methods, properties, events)
        """
        if not TREE_SITTER_AVAILABLE or 'error' in structure:
            return None  # Use default formatting

        lines = []

        # Namespaces
        namespaces = structure.get('namespaces', [])
        if namespaces:
            lines.append(f"\nNamespaces ({len(namespaces)}):")
            for item in namespaces:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")

        # Using statements
        imports = structure.get('imports', [])
        if imports:
            lines.append(f"\nUsing statements ({len(imports)}):")
            for item in imports[:10]:  # Limit display
                loc = self.format_location(item['line'])
                # Clean up "using System;" -> "System"
                name = item['name'].replace('using ', '').replace(';', '').strip()
                lines.append(f"  {loc:30}  {name}")
            if len(imports) > 10:
                lines.append(f"  ... and {len(imports) - 10} more")

        # Types section
        classes = structure.get('classes', [])
        interfaces = structure.get('interfaces', [])
        structs = structure.get('structs', [])
        enums = structure.get('enums', [])

        type_count = len(classes) + len(interfaces) + len(structs) + len(enums)
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

            if structs:
                lines.append(f"  Structs ({len(structs)}):")
                for item in structs:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

            if enums:
                lines.append(f"  Enums ({len(enums)}):")
                for item in enums:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

        # Methods
        methods = structure.get('functions', [])
        if methods:
            lines.append(f"\nMethods ({len(methods)}):")
            for item in methods[:20]:  # Limit display
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}()")
            if len(methods) > 20:
                lines.append(f"  ... and {len(methods) - 20} more")

        # Properties
        properties = structure.get('properties', [])
        if properties:
            lines.append(f"\nProperties ({len(properties)}):")
            for item in properties[:15]:  # Limit display
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")
            if len(properties) > 15:
                lines.append(f"  ... and {len(properties) - 15} more")

        # Events
        events = structure.get('events', [])
        if events:
            lines.append(f"\nEvents ({len(events)}):")
            for item in events:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")

        # Delegates
        delegates = structure.get('delegates', [])
        if delegates:
            lines.append(f"\nDelegates ({len(delegates)}):")
            for item in delegates:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")

        return lines if lines else None
