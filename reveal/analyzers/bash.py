"""Bash/Shell script analyzer - tree-sitter based."""

from typing import Optional
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.sh', name='Shell Script', icon='')
@register('.bash', name='Bash Script', icon='')
class BashAnalyzer(TreeSitterAnalyzer):
    """Bash/Shell script analyzer.

    Full shell script support via tree-sitter!
    Extracts:
    - Function definitions
    - Variable assignments
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
