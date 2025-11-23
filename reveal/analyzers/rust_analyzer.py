"""
Rust file analyzer using tree-sitter.

Demonstrates how easy it is to add language support using TreeSitterAnalyzer.
This entire analyzer is ~100 lines including docs and formatting!

Extracts:
- Functions (fn)
- Structs
- Enums
- Traits
- Impls (trait implementations)
- Use statements (imports)
- Mods (module declarations)
"""

from typing import Dict, Any, List
from .treesitter_base import TreeSitterAnalyzer, TREE_SITTER_AVAILABLE
from ..registry import register


@register(['.rs'], name='Rust', icon='🦀')
class RustAnalyzer(TreeSitterAnalyzer):
    """
    Analyzer for Rust source files.

    Features:
    - Functions, structs, enums, traits with line numbers
    - Impl blocks (trait implementations)
    - Module structure
    - Use statements (imports)
    - Macro definitions

    All positions are exact (tree-sitter preserves source locations).
    """

    # Set language for tree-sitter
    language_name = 'rust'

    def __init__(self, lines: List[str], **kwargs):
        """Initialize Rust analyzer."""
        # Map reveal's generic names to Rust's tree-sitter node types
        self.node_type_map = {
            'function': 'function_item',
            'struct': 'struct_item',
            'class': 'struct_item',  # Rust uses structs, not classes
            'import': 'use_declaration',
        }
        super().__init__(lines, **kwargs)

    def extract_custom(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract Rust-specific items."""
        return {
            'enums': self._extract_nodes('enum_item', name_field='name'),
            'traits': self._extract_nodes('trait_item', name_field='name'),
            'impls': self._extract_impl_blocks(),
            'mods': self._extract_nodes('mod_item', name_field='name'),
            'macros': self._extract_nodes('macro_definition', name_field='name'),
        }

    def _extract_impl_blocks(self) -> List[Dict[str, Any]]:
        """
        Extract impl blocks with special handling.

        Rust impl blocks look like:
        - impl Foo { ... }           (inherent impl)
        - impl Trait for Foo { ... } (trait impl)
        """
        if not self.tree:
            return []

        impls = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'impl_item':
                # Try to get type being implemented
                type_node = node.child_by_field_name('type')
                trait_node = node.child_by_field_name('trait')

                if trait_node and type_node:
                    # impl Trait for Type
                    trait_name = trait_node.text.decode('utf-8')
                    type_name = type_node.text.decode('utf-8')
                    name = f"{trait_name} for {type_name}"
                elif type_node:
                    # impl Type
                    type_name = type_node.text.decode('utf-8')
                    name = type_name
                else:
                    name = "<impl>"

                line = node.start_point[0] + 1
                if self.in_focus_range(line):
                    impls.append({
                        'name': name,
                        'line': line
                    })

            # Recurse
            if cursor.goto_first_child():
                visit(cursor)
                while cursor.goto_next_sibling():
                    visit(cursor)
                cursor.goto_parent()

        visit(cursor)
        return impls

    def format_structure(self, structure: Dict[str, Any]) -> List[str]:
        """
        Custom formatting for Rust structure output.

        Groups items logically:
        1. Module/Crate info
        2. Imports (use statements)
        3. Types (structs, enums, traits)
        4. Implementations
        5. Functions
        6. Macros
        """
        if not TREE_SITTER_AVAILABLE or 'error' in structure:
            return None  # Use default formatting

        lines = []

        # Use statements
        imports = structure.get('imports', [])
        if imports:
            lines.append(f"\nUse statements ({len(imports)}):")
            for item in imports[:10]:  # Limit display
                loc = self.format_location(item['line'])
                # Shorten long imports
                name = item['name']
                if len(name) > 60:
                    name = name[:57] + "..."
                lines.append(f"  {loc:30}  {name}")
            if len(imports) > 10:
                lines.append(f"  ... and {len(imports) - 10} more")

        # Types section
        structs = structure.get('structs', [])
        enums = structure.get('enums', [])
        traits = structure.get('traits', [])

        type_count = len(structs) + len(enums) + len(traits)
        if type_count > 0:
            lines.append(f"\nTypes ({type_count}):")

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

            if traits:
                lines.append(f"  Traits ({len(traits)}):")
                for item in traits:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

        # Implementations
        impls = structure.get('impls', [])
        if impls:
            lines.append(f"\nImplementations ({len(impls)}):")
            for item in impls:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  impl {item['name']}")

        # Functions
        functions = structure.get('functions', [])
        if functions:
            lines.append(f"\nFunctions ({len(functions)}):")
            for item in functions:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  fn {item['name']}()")

        # Modules
        mods = structure.get('mods', [])
        if mods:
            lines.append(f"\nModules ({len(mods)}):")
            for item in mods:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  mod {item['name']}")

        # Macros
        macros = structure.get('macros', [])
        if macros:
            lines.append(f"\nMacros ({len(macros)}):")
            for item in macros:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}!")

        return lines if lines else None
