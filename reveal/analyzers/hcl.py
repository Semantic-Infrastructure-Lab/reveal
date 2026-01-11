"""HCL (HashiCorp Configuration Language) analyzer using tree-sitter."""
from typing import Dict, List, Any
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.tf', '.tfvars', '.hcl', name='HCL', icon='🏗️')
class HCLAnalyzer(TreeSitterAnalyzer):
    """HCL/Terraform language analyzer.

    Supports Terraform (.tf), Terraform variables (.tfvars),
    and generic HCL (.hcl) configuration files.
    """
    language = 'hcl'

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
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

        # Remove empty categories
        return {k: v for k, v in structure.items() if v}

    def _extract_blocks(self, block_type: str) -> List[Dict[str, Any]]:
        """Extract blocks of a specific type (resource, variable, output, etc.)."""
        blocks = []

        # Find all blocks in the file
        all_blocks = self._find_nodes_by_type('block')

        for block_node in all_blocks:
            # Get block identifier (type)
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

            # Only process blocks of the requested type
            if block_identifier != block_type:
                continue

            # Build block name/description based on type
            if block_type in ['resource', 'data']:
                # resource "aws_instance" "web" or data "aws_ami" "ubuntu"
                if len(labels) >= 2:
                    name = f"{labels[0]}.{labels[1]}"
                elif len(labels) >= 1:
                    name = labels[0]
                else:
                    name = block_type
            elif block_type in ['variable', 'output', 'module', 'provider']:
                # variable "region" or output "instance_id"
                if len(labels) >= 1:
                    name = labels[0]
                else:
                    name = block_type
            elif block_type == 'locals':
                # locals { ... }
                name = 'locals'
            else:
                name = block_type

            # Extract key attributes from block body
            attributes = self._extract_block_attributes(block_node)

            block_info = {
                'line': block_node.start_point[0] + 1,
                'name': name,
            }

            # Add type-specific info
            if block_type == 'variable' and 'type' in attributes:
                block_info['type'] = attributes['type']
            if block_type == 'variable' and 'default' in attributes:
                block_info['default'] = attributes['default']
            if block_type == 'output' and 'value' in attributes:
                block_info['value'] = attributes['value']
            if block_type == 'module' and 'source' in attributes:
                block_info['source'] = attributes['source']

            blocks.append(block_info)

        return blocks

    def _extract_block_attributes(self, block_node) -> Dict[str, str]:
        """Extract key-value attributes from a block's body."""
        attributes = {}

        # Find the body node
        for child in block_node.children:
            if child.type == 'body':
                # Look for attribute nodes in the body
                for body_child in child.children:
                    if body_child.type == 'attribute':
                        key = None
                        value = None

                        for attr_child in body_child.children:
                            if attr_child.type == 'identifier' and key is None:
                                key = self._get_node_text(attr_child)
                            elif attr_child.type in ['string_lit', 'number_lit', 'bool_lit']:
                                value = self._get_node_text(attr_child)
                                # Clean up string quotes
                                if value and value.startswith('"') and value.endswith('"'):
                                    value = value[1:-1]
                            elif attr_child.type == 'expression':
                                # For complex expressions, just get the text
                                value = self._get_node_text(attr_child)

                        if key:
                            attributes[key] = value or ''

        return attributes
