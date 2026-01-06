"""SQL analyzer using tree-sitter."""

from typing import Dict, List, Any
from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.sql', name='SQL', icon='🗄️')
class SQLAnalyzer(TreeSitterAnalyzer):
    """Analyze SQL files.

    Extracts CREATE statements (tables, functions, procedures, views)
    using tree-sitter with SQL-specific node types.
    """
    language = 'sql'

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract SQL functions and procedures."""
        functions = []

        # SQL function/procedure node types
        func_types = [
            'create_function_statement',
            'create_procedure_statement',
        ]

        for func_type in func_types:
            nodes = self._find_nodes_by_type(func_type)
            for node in nodes:
                name = self._get_node_name(node)
                if not name:
                    # Try to find identifier child
                    for child in node.children:
                        if child.type == 'identifier':
                            name = self._get_node_text(child)
                            break

                if name:
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    functions.append({
                        'line': line_start,
                        'line_end': line_end,
                        'name': name,
                        'signature': '(...)',
                        'line_count': line_end - line_start + 1,
                        'depth': 0,
                        'complexity': 1,
                        'decorators': [],
                    })

        return functions

    def _extract_classes(self) -> List[Dict[str, Any]]:
        """Extract SQL tables, views as 'classes'."""
        tables = []

        # SQL table/view node types
        table_types = [
            'create_table_statement',
            'create_view_statement',
        ]

        for table_type in table_types:
            nodes = self._find_nodes_by_type(table_type)
            for node in nodes:
                name = None
                # Find the table/view name (usually an identifier child)
                for child in node.children:
                    if child.type == 'identifier':
                        name = self._get_node_text(child)
                        break

                if name:
                    line_start = node.start_point[0] + 1
                    line_end = node.end_point[0] + 1
                    tables.append({
                        'line': line_start,
                        'line_end': line_end,
                        'name': name,
                        'decorators': [],
                    })

        return tables
