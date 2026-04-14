"""Bash/Shell script analyzer - tree-sitter based."""

from typing import Optional, List, Dict, Any
from ..registry import register
from ..treesitter import TreeSitterAnalyzer

_MAX_VALUE_LEN = 60


@register('.sh', name='Shell Script', icon='')
@register('.bash', name='Bash Script', icon='')
class BashAnalyzer(TreeSitterAnalyzer):
    """Bash/Shell script analyzer.

    Full shell script support via tree-sitter!
    Extracts:
    - Function definitions
    - Top-level variable assignments
    - Command invocations

    Cross-platform compatible:
    - Analyzes bash scripts on any OS (Windows/Linux/macOS)
    - Does NOT execute scripts, only parses syntax
    - Useful for DevOps/deployment script exploration
    - Works with WSL, Git Bash, and native Unix shells

    Note: This analyzes bash script SYNTAX, regardless of the host OS.
    """
    language = 'bash'

    def _get_node_name(self, node) -> Optional[str]:
        """Get the name of a bash node (function/variable/etc).

        Bash tree-sitter uses 'word' for names, not 'identifier'.
        This is called by _extract_functions() and other extraction methods.
        """
        # Look for 'word' child (bash uses this instead of 'identifier')
        for child in node.children:
            if child.type == 'word':
                return self._get_node_text(child)

        # Fallback to parent implementation (checks for 'identifier' or 'name')
        return super()._get_node_name(node)

    def _extract_bash_variables(self) -> List[Dict[str, Any]]:
        """Extract top-level variable assignments (direct children of program node).

        Only captures script-level config vars, not vars inside functions/loops/if blocks.
        """
        if not self.tree:
            return []

        variables = []
        for child in self.tree.root_node.children:
            if child.type != 'variable_assignment':
                continue
            name_node = child.child_by_field_name('name')
            value_node = child.child_by_field_name('value')
            if not name_node:
                continue
            name = self._get_node_text(name_node)
            value = self._get_node_text(value_node) if value_node else ''
            if len(value) > _MAX_VALUE_LEN:
                value = value[:_MAX_VALUE_LEN - 3] + '...'
            variables.append({
                'line': child.start_point[0] + 1,
                'name': name,
                'signature': f' = {value}' if value else '',
            })
        return variables

    def get_structure(self, head=None, tail=None, range=None, **kwargs) -> Dict[str, Any]:
        """Extract bash structure: functions + top-level variable assignments."""
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)

        variables = self._extract_bash_variables()
        if variables:
            if head or tail or range:
                variables = self._apply_semantic_slice(variables, head, tail, range)
            if variables:
                structure['variables'] = variables

        return structure
