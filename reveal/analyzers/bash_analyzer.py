"""
Bash/Shell script analyzer using tree-sitter.

Extracts:
- Functions
- Variables
- Exported variables
- Source/include statements
"""

from typing import Dict, Any, List
from .treesitter_base import TreeSitterAnalyzer, TREE_SITTER_AVAILABLE
from ..registry import register


@register(['.sh', '.bash', '.zsh'], name='Bash', icon='🐚')
class BashAnalyzer(TreeSitterAnalyzer):
    """
    Analyzer for Bash/Shell script files.

    Features:
    - Function definitions
    - Variable assignments
    - Exported variables
    - Source statements

    All positions are exact (tree-sitter preserves source locations).
    """

    language_name = 'bash'

    def __init__(self, lines: List[str], **kwargs):
        """Initialize Bash analyzer."""
        self.node_type_map = {
            'function': 'function_definition',
        }
        super().__init__(lines, **kwargs)

    def extract_custom(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract Bash-specific items."""
        return {
            'variables': self._extract_variables(),
            'exports': self._extract_exports(),
            'sources': self._extract_sources(),
        }

    def _extract_variables(self) -> List[Dict[str, Any]]:
        """Extract variable assignments."""
        if not self.tree:
            return []

        variables = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'variable_assignment':
                # Get variable name
                name_node = node.child_by_field_name('name')
                if name_node:
                    line = node.start_point[0] + 1
                    if self.in_focus_range(line):
                        variables.append({
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
        return variables

    def _extract_exports(self) -> List[Dict[str, Any]]:
        """Extract export statements."""
        if not self.tree:
            return []

        exports = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'declaration_command':
                # Check if it's an export
                for child in node.children:
                    if child.type == 'variable_assignment':
                        name_node = child.child_by_field_name('name')
                        if name_node:
                            line = node.start_point[0] + 1
                            if self.in_focus_range(line):
                                exports.append({
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
        return exports

    def _extract_sources(self) -> List[Dict[str, Any]]:
        """Extract source/. statements."""
        if not self.tree:
            return []

        sources = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            # Look for source command or . command
            if node.type == 'command':
                command_name = node.child_by_field_name('name')
                if command_name:
                    cmd_text = command_name.text.decode('utf-8')
                    if cmd_text in ('source', '.'):
                        # Get the sourced file
                        full_text = node.text.decode('utf-8').strip()
                        line = node.start_point[0] + 1
                        if self.in_focus_range(line):
                            sources.append({
                                'name': full_text,
                                'line': line
                            })

            # Recurse
            if cursor.goto_first_child():
                visit(cursor)
                while cursor.goto_next_sibling():
                    visit(cursor)
                cursor.goto_parent()

        visit(cursor)
        return sources

    def format_structure(self, structure: Dict[str, Any]) -> List[str]:
        """
        Custom formatting for Bash structure output.

        Groups items logically:
        1. Source statements
        2. Functions
        3. Exported variables
        4. Variables
        """
        if not TREE_SITTER_AVAILABLE or 'error' in structure:
            return None

        lines = []

        # Sources
        sources = structure.get('sources', [])
        if sources:
            lines.append(f"\nSource statements ({len(sources)}):")
            for item in sources[:10]:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")
            if len(sources) > 10:
                lines.append(f"  ... and {len(sources) - 10} more")

        # Functions
        functions = structure.get('functions', [])
        if functions:
            lines.append(f"\nFunctions ({len(functions)}):")
            for item in functions:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}()")

        # Exports
        exports = structure.get('exports', [])
        if exports:
            lines.append(f"\nExported variables ({len(exports)}):")
            for item in exports[:15]:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")
            if len(exports) > 15:
                lines.append(f"  ... and {len(exports) - 15} more")

        # Variables
        variables = structure.get('variables', [])
        if variables:
            lines.append(f"\nVariables ({len(variables)}):")
            for item in variables[:20]:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")
            if len(variables) > 20:
                lines.append(f"  ... and {len(variables) - 20} more")

        return lines if lines else None
