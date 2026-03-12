"""TOML file analyzer - migrated to tree-sitter.

Previous implementation: 114 lines with regex patterns for sections and key-value pairs
Current implementation: 144 lines using tree-sitter AST extraction

Benefits:
- Handles complex TOML syntax automatically (dotted keys, inline tables, etc.)
- More robust parsing (no manual line-by-line processing, no regex)
- Cleaner core logic (AST-based instead of regex matching)
"""

from typing import Dict, List, Any, Optional
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.toml', name='TOML', icon='')
class TomlAnalyzer(TreeSitterAnalyzer):
    """TOML file analyzer using tree-sitter for robust parsing.

    Extracts sections ([section], [[array]]) and top-level key-value pairs.
    """

    language = 'toml'

    def _process_toml_pair_node(self, node, keys: list) -> None:
        """Extract a top-level key-value pair node into the keys list."""
        if node.children and node.children[0].type in ['bare_key', 'dotted_key', 'quoted_key']:
            key_node = node.children[0]
            keys.append({
                'line_start': node.start_point[0] + 1,
                'name': self.content[key_node.start_byte:key_node.end_byte],
            })

    def _process_toml_table_node(self, node, outline: bool, sections: list) -> None:
        """Extract a table/table_array node into the sections list."""
        section_name = self._extract_table_name(node)
        section_info: Dict[str, Any] = {
            'line_start': node.start_point[0] + 1,
            'name': section_name,
        }
        if outline:
            section_info['level'] = section_name.count('.') + 1
        sections.append(section_info)

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, outline: bool = False, **kwargs) -> Dict[str, Any]:
        """Extract TOML sections and top-level keys using tree-sitter."""
        if not self.tree:
            return {}

        sections: list = []
        keys: list = []

        for node in self.tree.root_node.children:
            if node.type == 'pair':
                self._process_toml_pair_node(node, keys)
            elif node.type in ('table', 'table_array_element'):
                self._process_toml_table_node(node, outline, sections)

        result = {}
        if sections:
            result['sections'] = sections
        if keys:
            result['keys'] = keys

        if not result:
            return {}
        return {
            'contract_version': '1.0',
            'type': 'toml_structure',
            'source': str(self.path),
            'source_type': 'file',
            **result,
        }

    def _extract_table_name(self, node) -> str:
        """Extract section name from table node."""
        # Find the key node between [ and ]
        for child in node.children:
            if child.type in ['bare_key', 'dotted_key', 'quoted_key']:
                return self.content[child.start_byte:child.end_byte]
        return ''

    def _find_section_end_line(self, node) -> int:
        """Return end line for a section node (stops at next table or EOF)."""
        end_line = node.end_point[0] + 1
        for sibling in self.tree.root_node.children:
            if sibling.start_point[0] <= node.start_point[0]:
                continue
            if sibling.type in ['table', 'table_array_element']:
                return sibling.start_point[0]
            if sibling.type == 'pair':
                end_line = max(end_line, sibling.end_point[0] + 1)
        return end_line

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a TOML section by name."""
        if not self.tree:
            return super().extract_element(element_type, name)
        for node in self.tree.root_node.children:
            if node.type not in ['table', 'table_array_element']:
                continue
            if self._extract_table_name(node) != name:
                continue
            start_line = node.start_point[0] + 1
            end_line = self._find_section_end_line(node)
            source = '\n'.join(self.lines[start_line - 1:end_line])
            return {'name': name, 'line_start': start_line, 'line_end': end_line, 'source': source}
        return super().extract_element(element_type, name)
