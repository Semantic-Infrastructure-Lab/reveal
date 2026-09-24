"""SQL analyzer using tree-sitter."""

from typing import Dict, List, Any, Optional
from ..reveal_types import StructureItem
from ..registry import register
from ..treesitter import TreeSitterAnalyzer
from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg


@register('.sql', name='SQL', icon='🗄️')
class SQLAnalyzer(TreeSitterAnalyzer):
    """Analyze SQL files.

    Extracts CREATE statements (tables, functions, procedures, views)
    using tree-sitter with SQL-specific node types.
    """
    language = 'sql'

    def _find_identifier_child(self, node) -> Optional[str]:
        """The created object's name, schema-qualified as written.

        The grammar nests it in an `object_reference` (`public` `.` `users`);
        its FIRST identifier is the schema, which named every object in a
        pg_dump file `public` (BACK-1413).
        """
        direct = next((c for c in _children(node) if _zero_arg(c, 'kind') == 'identifier'), None)
        if direct:
            return self._get_node_text(direct)
        for child in _children(node):
            if _zero_arg(child, 'kind') != 'object_reference':
                continue
            parts = [self._get_node_text(gc) for gc in _children(child)
                     if _zero_arg(gc, 'kind') == 'identifier']
            if parts:
                return '.'.join(parts)
        return None

    def _node_to_function_dict(self, node, name: str) -> StructureItem:
        """Convert a tree-sitter node to a function dict."""
        line_start = _zero_arg(node, 'start_position').row + 1
        line_end = _zero_arg(node, 'end_position').row + 1
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

    def _node_to_class_dict(self, node, name: str) -> StructureItem:
        """Convert a tree-sitter node to a class/table dict."""
        line_start = _zero_arg(node, 'start_position').row + 1
        line_end = _zero_arg(node, 'end_position').row + 1
        return {
            'line': line_start,
            'line_end': line_end,
            'name': name,
            'decorators': [],
        }

    def _extract_functions(self) -> List[StructureItem]:
        """Extract SQL functions and procedures."""
        functions = []
        # New grammar uses create_function, create_procedure (no _statement suffix)
        func_types = ('create_function', 'create_procedure',
                     'create_function_statement', 'create_procedure_statement')

        for func_type in func_types:
            for node in self._find_nodes_by_type(func_type):
                name = self._find_identifier_child(node) or self._get_node_name(node)
                if name:
                    functions.append(self._node_to_function_dict(node, name))

        return functions

    def _extract_classes(self) -> List[StructureItem]:
        """Extract SQL tables, views as 'classes'."""
        tables = []
        # New grammar uses create_table, create_view (no _statement suffix)
        table_types = ('create_table', 'create_view',
                      'create_table_statement', 'create_view_statement')

        for table_type in table_types:
            for node in self._find_nodes_by_type(table_type):
                name = self._find_identifier_child(node)
                if name:
                    tables.append(self._node_to_class_dict(node, name))

        return tables
