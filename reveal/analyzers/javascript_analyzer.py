"""
JavaScript/JSX file analyzer using tree-sitter.

Extracts:
- Functions (regular, arrow, async)
- Classes
- Imports/Exports
- Variables (const, let, var)
"""

from typing import Dict, Any, List
from .treesitter_base import TreeSitterAnalyzer, TREE_SITTER_AVAILABLE
from ..registry import register


@register(['.js', '.jsx', '.mjs', '.cjs'], name='JavaScript', icon='📜')
class JavaScriptAnalyzer(TreeSitterAnalyzer):
    """
    Analyzer for JavaScript source files.

    Features:
    - Functions (declarations, expressions, arrow functions)
    - Classes and methods
    - Import/export statements
    - Variable declarations

    All positions are exact (tree-sitter preserves source locations).
    """

    language_name = 'javascript'

    def __init__(self, lines: List[str], **kwargs):
        """Initialize JavaScript analyzer."""
        self.node_type_map = {
            'function': 'function_declaration',
            'class': 'class_declaration',
            'import': 'import_statement',
        }
        super().__init__(lines, **kwargs)

    def extract_custom(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract JavaScript-specific items."""
        return {
            'arrow_functions': self._extract_arrow_functions(),
            'function_expressions': self._extract_function_expressions(),
            'exports': self._extract_exports(),
            'variables': self._extract_variables(),
        }

    def _extract_arrow_functions(self) -> List[Dict[str, Any]]:
        """Extract arrow function expressions."""
        if not self.tree:
            return []

        arrow_funcs = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'arrow_function':
                # Try to get the variable name it's assigned to
                parent = node.parent
                name = '<arrow>'

                if parent and parent.type == 'variable_declarator':
                    name_node = parent.child_by_field_name('name')
                    if name_node:
                        name = name_node.text.decode('utf-8')

                line = node.start_point[0] + 1
                if self.in_focus_range(line):
                    arrow_funcs.append({
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
        return arrow_funcs

    def _extract_function_expressions(self) -> List[Dict[str, Any]]:
        """Extract function expressions (const fn = function() {})."""
        if not self.tree:
            return []

        func_exprs = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'function' and node.parent:
                parent = node.parent
                if parent.type == 'variable_declarator':
                    name_node = parent.child_by_field_name('name')
                    if name_node:
                        line = node.start_point[0] + 1
                        if self.in_focus_range(line):
                            func_exprs.append({
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
        return func_exprs

    def _extract_exports(self) -> List[Dict[str, Any]]:
        """Extract export statements."""
        if not self.tree:
            return []

        exports = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            if node.type == 'export_statement':
                # Get exported name or use full statement text
                name = node.text.decode('utf-8').strip()
                if len(name) > 60:
                    name = name[:57] + "..."

                line = node.start_point[0] + 1
                if self.in_focus_range(line):
                    exports.append({
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
        return exports

    def _extract_variables(self) -> List[Dict[str, Any]]:
        """Extract top-level variable declarations."""
        if not self.tree:
            return []

        variables = []
        cursor = self.tree.walk()

        def visit(cursor):
            node = cursor.node

            # Only get top-level variables
            if node.type == 'variable_declaration' and node.parent.type == 'program':
                for child in node.children:
                    if child.type == 'variable_declarator':
                        name_node = child.child_by_field_name('name')
                        if name_node:
                            line = child.start_point[0] + 1
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

    def format_structure(self, structure: Dict[str, Any]) -> List[str]:
        """
        Custom formatting for JavaScript structure output.

        Groups items logically:
        1. Imports/Exports
        2. Classes
        3. Functions (declarations, expressions, arrow)
        4. Variables
        """
        if not TREE_SITTER_AVAILABLE or 'error' in structure:
            return None

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

        # Exports
        exports = structure.get('exports', [])
        if exports:
            lines.append(f"\nExports ({len(exports)}):")
            for item in exports[:10]:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")
            if len(exports) > 10:
                lines.append(f"  ... and {len(exports) - 10} more")

        # Classes
        classes = structure.get('classes', [])
        if classes:
            lines.append(f"\nClasses ({len(classes)}):")
            for item in classes:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  class {item['name']}")

        # Functions
        functions = structure.get('functions', [])
        arrow_functions = structure.get('arrow_functions', [])
        func_expressions = structure.get('function_expressions', [])

        func_count = len(functions) + len(arrow_functions) + len(func_expressions)
        if func_count > 0:
            lines.append(f"\nFunctions ({func_count}):")

            if functions:
                lines.append(f"  Declarations ({len(functions)}):")
                for item in functions:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  function {item['name']}()")

            if arrow_functions:
                lines.append(f"  Arrow Functions ({len(arrow_functions)}):")
                for item in arrow_functions:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']} =>")

            if func_expressions:
                lines.append(f"  Expressions ({len(func_expressions)}):")
                for item in func_expressions:
                    loc = self.format_location(item['line'])
                    lines.append(f"    {loc:28}  {item['name']}")

        # Variables
        variables = structure.get('variables', [])
        if variables:
            lines.append(f"\nVariables ({len(variables)}):")
            for item in variables[:15]:
                loc = self.format_location(item['line'])
                lines.append(f"  {loc:30}  {item['name']}")
            if len(variables) > 15:
                lines.append(f"  ... and {len(variables) - 15} more")

        return lines if lines else None
