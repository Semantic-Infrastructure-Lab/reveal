"""HCL (HashiCorp Configuration Language) analyzer using tree-sitter."""
from typing import Dict, List, Any, Optional, Tuple
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.tf', '.tfvars', '.hcl', name='HCL', icon='🏗️')
class HCLAnalyzer(TreeSitterAnalyzer):
    """HCL/Terraform language analyzer.

    Supports Terraform (.tf), Terraform variables (.tfvars),
    and generic HCL (.hcl) configuration files.
    """
    language = 'hcl'

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract HCL/Terraform structure."""
        if not self.tree:
            return {}

        structure = {}

        # Extract Terraform/HCL elements
        structure['resources'] = self._extract_blocks('resource')
        structure['data'] = self._extract_blocks('data')
        structure['variables'] = self._extract_blocks('variable')
        structure['outputs'] = self._extract_blocks('output')
        structure['locals'] = self._extract_blocks('locals')
        structure['modules'] = self._extract_blocks('module')
        structure['providers'] = self._extract_blocks('provider')

        # Apply semantic slicing to each category
        if head or tail or range:
            for category in structure:
                structure[category] = self._apply_semantic_slice(
                    structure[category], head, tail, range
                )

        # Remove empty categories and add output contract fields
        return {
            'contract_version': '1.0',
            'type': 'hcl_structure',
            'source': str(self.path),
            'source_type': 'file',
            **{k: v for k, v in structure.items() if v},
        }

    def _extract_blocks(self, block_type: str) -> List[Dict[str, Any]]:
        """Extract blocks of a specific type (resource, variable, output, etc.)."""
        blocks = []
        all_blocks = self._find_nodes_by_type('block')

        for block_node in all_blocks:
            block_identifier, labels = self._parse_block_header(block_node)

            # Only process blocks of the requested type
            if block_identifier != block_type:
                continue

            # Build block info
            name = self._build_block_name(block_type, labels)
            attributes = self._extract_block_attributes(block_node)

            block_info = {
                'line': block_node.start_point[0] + 1,
                'name': name,
            }

            # Add type-specific attributes
            self._add_type_specific_info(block_info, block_type, attributes)

            blocks.append(block_info)

        return blocks

    def _parse_block_header(self, block_node: Any) -> Tuple[Optional[str], List[str]]:
        """Parse block identifier and labels from block node.

        Args:
            block_node: HCL block node

        Returns:
            Tuple of (identifier, labels_list)
        """
        block_identifier = None
        labels = []

        for i, child in enumerate(block_node.children):
            if child.type == 'identifier' and i == 0:
                block_identifier = self._get_node_text(child)
            elif child.type == 'string_lit':
                # Remove quotes from string literals
                label_text = self._get_node_text(child)
                if label_text.startswith('"') and label_text.endswith('"'):
                    label_text = label_text[1:-1]
                labels.append(label_text)

        return block_identifier, labels

    def _build_block_name(self, block_type: str, labels: List[str]) -> str:
        """Build block name based on type and labels.

        Args:
            block_type: Block type (resource, variable, etc.)
            labels: List of block labels

        Returns:
            Block name string
        """
        if block_type in ['resource', 'data']:
            # resource "aws_instance" "web" -> "aws_instance.web"
            if len(labels) >= 2:
                return f"{labels[0]}.{labels[1]}"
            elif len(labels) >= 1:
                return labels[0]
            return block_type

        elif block_type in ['variable', 'output', 'module', 'provider']:
            # variable "region" -> "region"
            return labels[0] if labels else block_type

        elif block_type == 'locals':
            return 'locals'

        return block_type

    def _add_type_specific_info(self, block_info: Dict[str, Any], block_type: str, attributes: Dict[str, Any]) -> None:
        """Add type-specific attributes to block info.

        Args:
            block_info: Block info dict to modify
            block_type: Block type
            attributes: Extracted attributes from block
        """
        if block_type == 'variable':
            if 'type' in attributes:
                block_info['type'] = attributes['type']
            if 'default' in attributes:
                block_info['default'] = attributes['default']

        elif block_type == 'output':
            if 'value' in attributes:
                block_info['value'] = attributes['value']

        elif block_type == 'module':
            if 'source' in attributes:
                block_info['source'] = attributes['source']

    def _parse_attribute_node(self, attr_node: Any) -> Tuple[Optional[str], Optional[str]]:
        """Parse key and value from a single HCL attribute node."""
        key = None
        value = None
        for attr_child in attr_node.children:
            if attr_child.type == 'identifier' and key is None:
                key = self._get_node_text(attr_child)
            elif attr_child.type in ['string_lit', 'number_lit', 'bool_lit']:
                value = self._get_node_text(attr_child)
                if value and value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
            elif attr_child.type == 'expression':
                value = self._get_node_text(attr_child)
        return key, value

    def _extract_block_attributes(self, block_node) -> Dict[str, str]:
        """Extract key-value attributes from a block's body."""
        attributes = {}
        for child in block_node.children:
            if child.type == 'body':
                for body_child in child.children:
                    if body_child.type == 'attribute':
                        key, value = self._parse_attribute_node(body_child)
                        if key:
                            attributes[key] = value or ''
        return attributes
