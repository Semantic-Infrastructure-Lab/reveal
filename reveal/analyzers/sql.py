"""SQL analyzer using tree-sitter."""

from typing import Dict, List, Any, Optional
from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.sql', name='SQL', icon='🗄️')
class SQLAnalyzer(TreeSitterAnalyzer):
    """Analyze SQL files.

    Extracts CREATE statements (tables, functions, procedures, views)
    using tree-sitter with SQL-specific node types.
    """
    language = 'sql'

    def _find_identifier_child(self, node) -> Optional[str]:
        """Find the first identifier child's text."""
        for child in node.children:
            if child.type == 'identifier':
                return self._get_node_text(child)
        return None

    def _node_to_function_dict(self, node, name: str) -> Dict[str, Any]:
        """Convert a tree-sitter node to a function dict."""
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1
        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'signature': '(...)',
            'line_count': line_end - line_start + 1,
            'depth': 0,
            'complexity': 1,
            'decorators': [],
        }

    def _node_to_class_dict(self, node, name: str) -> Dict[str, Any]:
        """Convert a tree-sitter node to a class/table dict."""
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1
        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'decorators': [],
        }

    def _extract_functions(self) -> List[Dict[str, Any]]:
        """Extract SQL functions and procedures."""
        functions = []
        func_types = ('create_function_statement', 'create_procedure_statement')

        for func_type in func_types:
            for node in self._find_nodes_by_type(func_type):
                name = self._get_node_name(node) or self._find_identifier_child(node)
                if name:
                    functions.append(self._node_to_function_dict(node, name))

        return functions

    def _extract_classes(self) -> List[Dict[str, Any]]:
        """Extract SQL tables, views as 'classes'."""
        tables = []
        table_types = ('create_table_statement', 'create_view_statement')

        for table_type in table_types:
            for node in self._find_nodes_by_type(table_type):
                name = self._find_identifier_child(node)
                if name:
                    tables.append(self._node_to_class_dict(node, name))

        return tables
