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
from ..core import node_children as _children


@register('.yaml', '.yml', name='YAML', icon='')
class YamlAnalyzer(TreeSitterAnalyzer):
    """YAML file analyzer using tree-sitter for robust parsing.

    Extracts top-level keys from YAML documents.
    """

    language = 'yaml'

    def _get_mapping_pairs(self, block_node) -> List[Any]:
        """Extract block_mapping_pair nodes from a block_node child."""
        pairs: List[Any] = []
        for mapping_child in _children(block_node):
            if mapping_child.kind() == 'block_mapping':
                pairs.extend(
                    p for p in _children(mapping_child)
                    if p.kind() == 'block_mapping_pair'
                )
        return pairs

    def _get_document_mapping_pairs(self, doc_node) -> List[Any]:
        """Return mapping pairs from a YAML document node."""
        pairs: List[Any] = []
        for child in _children(doc_node):
            if child.kind() == 'block_node':
                pairs.extend(self._get_mapping_pairs(child))
        return pairs

    def _find_yaml_pairs(self) -> List[Any]:
        """Find top-level block_mapping_pair nodes in the document.

        Returns:
            List of top-level block_mapping_pair nodes
        """
        if not self.tree:
            return []
        pairs: List[Any] = []
        for node in _children(self.tree.root_node()):
            if node.kind() == 'document':
                pairs.extend(self._get_document_mapping_pairs(node))
        return pairs

    def _extract_key_info(self, pair_node):
        """Extract key name from a block_mapping_pair node.

        Args:
            pair_node: A block_mapping_pair tree-sitter node

        Returns:
            Tuple of (key_name, key_node) or (None, None) if no key found
        """
        key_node = pair_node.child_by_field_name('key')
        if key_node:
            key_name = self._get_node_text(key_node)
            return key_name, key_node
        return None, None

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract YAML top-level keys using tree-sitter."""
        if not self.tree:
            return {}

        keys = []
        pairs = self._find_yaml_pairs()

        for pair in pairs:
            key_name, _ = self._extract_key_info(pair)
            if key_name:
                keys.append({
                    'line_start': pair.start_position().row + 1,
                    'name': key_name,
                })

        if not keys:
            return {}
        return {
            'contract_version': '1.0',
            'type': 'yaml_structure',
            'source': str(self.path),
            'source_type': 'file',
            'keys': keys,
        }

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

        pairs = self._find_yaml_pairs()

        for pair in pairs:
            key_name, _ = self._extract_key_info(pair)
            if key_name == name:
                start_line = pair.start_position().row + 1
                end_line = pair.end_position().row + 1
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

    def _find_json_pairs(self):
        """Find top-level pair nodes in the root JSON object.

        Returns:
            List of top-level pair nodes (JSON key-value pairs)
        """
        pairs: List[Any] = []
        # Only look for pairs that are direct children of the root object
        if not self.tree:
            return pairs
        for node in _children(self.tree.root_node()):
            if node.kind() == 'object':
                pairs.extend(c for c in _children(node) if c.kind() == 'pair')
        return pairs

    def _extract_key_info(self, pair_node):
        """Extract key name from a pair node.

        Args:
            pair_node: A pair tree-sitter node (JSON key-value pair)

        Returns:
            Tuple of (key_name, key_node) or (None, None) if no key found
        """
        key_node = pair_node.child_by_field_name('key')
        if key_node:
            key_name = self._get_node_text(key_node).strip('"')
            return key_name, key_node
        return None, None

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract JSON top-level keys using tree-sitter."""
        if not self.tree:
            return {}

        keys = []
        pairs = self._find_json_pairs()

        for pair in pairs:
            key_name, _ = self._extract_key_info(pair)
            if key_name:
                keys.append({
                    'line_start': pair.start_position().row + 1,
                    'name': key_name,
                })

        if not keys:
            return {}
        return {
            'contract_version': '1.0',
            'type': 'json_structure',
            'source': str(self.path),
            'source_type': 'file',
            'keys': keys,
        }

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

        pairs = self._find_json_pairs()

        for pair in pairs:
            key_name, _ = self._extract_key_info(pair)
            if key_name == name:
                start_line = pair.start_position().row + 1
                end_line = pair.end_position().row + 1
                source = '\n'.join(self.lines[start_line-1:end_line])

                return {
                    'name': name,
                    'line_start': start_line,
                    'line_end': end_line,
                    'source': source,
                }

        # Fall back to grep-based search
        return super().extract_element(element_type, name)
