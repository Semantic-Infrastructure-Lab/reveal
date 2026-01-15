"""YAML and JSON file analyzers - migrated to tree-sitter.

Previous implementation: 114 lines with regex patterns and json.loads()
Current implementation: 167 lines using tree-sitter AST extraction

Benefits:
- Handles complex YAML/JSON syntax automatically (nested structures, arrays, etc.)
- More robust parsing (no regex, AST-based extraction)
- Consistent tree-sitter approach for both formats
"""

from typing import Dict, List, Any, Optional
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.yaml', '.yml', name='YAML', icon='')
class YamlAnalyzer(TreeSitterAnalyzer):
    """YAML file analyzer using tree-sitter for robust parsing.

    Extracts top-level keys from YAML documents.
    """

    language = 'yaml'

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract YAML top-level keys using tree-sitter."""
        if not self.tree:
            return {}

        keys = []

        # Find the document node
        for node in self.tree.root_node.children:
            if node.type == 'document':
                # Look for block_mapping with top-level pairs
                for child in node.children:
                    if child.type == 'block_node':
                        # Find block_mapping
                        for mapping_child in child.children:
                            if mapping_child.type == 'block_mapping':
                                # Extract top-level keys
                                for pair in mapping_child.children:
                                    if pair.type == 'block_mapping_pair':
                                        key_node = pair.child_by_field_name('key')
                                        if key_node:
                                            key_name = self.content[key_node.start_byte:key_node.end_byte]
                                            keys.append({
                                                'line': pair.start_point[0] + 1,
                                                'name': key_name,
                                            })

        return {'keys': keys} if keys else {}

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a YAML key and its value using tree-sitter.

        Args:
            element_type: 'key'
            name: Key name to find

        Returns:
            Dict with key content and line range
        """
        if not self.tree:
            return super().extract_element(element_type, name)

        # Find the matching key
        for node in self.tree.root_node.children:
            if node.type == 'document':
                for child in node.children:
                    if child.type == 'block_node':
                        for mapping_child in child.children:
                            if mapping_child.type == 'block_mapping':
                                for pair in mapping_child.children:
                                    if pair.type == 'block_mapping_pair':
                                        key_node = pair.child_by_field_name('key')
                                        if key_node:
                                            key_name = self.content[key_node.start_byte:key_node.end_byte]
                                            if key_name == name:
                                                start_line = pair.start_point[0] + 1
                                                end_line = pair.end_point[0] + 1
                                                source = '\n'.join(self.lines[start_line-1:end_line])

                                                return {
                                                    'name': name,
                                                    'line_start': start_line,
                                                    'line_end': end_line,
                                                    'source': source,
                                                }

        # Fall back to grep-based search
        return super().extract_element(element_type, name)


@register('.json', name='JSON', icon='')
class JsonAnalyzer(TreeSitterAnalyzer):
    """JSON file analyzer using tree-sitter for robust parsing.

    Extracts top-level keys from JSON objects.
    """

    language = 'json'

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract JSON top-level keys using tree-sitter."""
        if not self.tree:
            return {}

        keys = []

        # Find the root object
        for node in self.tree.root_node.children:
            if node.type == 'object':
                # Extract all top-level pairs
                for child in node.children:
                    if child.type == 'pair':
                        key_node = child.child_by_field_name('key')
                        if key_node:
                            # Get key text and strip quotes
                            key_text = self.content[key_node.start_byte:key_node.end_byte]
                            key_name = key_text.strip('"')
                            keys.append({
                                'line': child.start_point[0] + 1,
                                'name': key_name,
                            })

        return {'keys': keys} if keys else {}

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a JSON key and its value using tree-sitter.

        Args:
            element_type: 'key'
            name: Key name to find

        Returns:
            Dict with key content and line range
        """
        if not self.tree:
            return super().extract_element(element_type, name)

        # Find the root object and search for matching key
        for node in self.tree.root_node.children:
            if node.type == 'object':
                for child in node.children:
                    if child.type == 'pair':
                        key_node = child.child_by_field_name('key')
                        if key_node:
                            key_text = self.content[key_node.start_byte:key_node.end_byte]
                            key_name = key_text.strip('"')
                            if key_name == name:
                                start_line = child.start_point[0] + 1
                                end_line = child.end_point[0] + 1
                                source = '\n'.join(self.lines[start_line-1:end_line])

                                return {
                                    'name': name,
                                    'line_start': start_line,
                                    'line_end': end_line,
                                    'source': source,
                                }

        # Fall back to grep-based search
        return super().extract_element(element_type, name)
