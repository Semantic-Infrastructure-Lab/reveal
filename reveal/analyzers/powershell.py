"""PowerShell script analyzer - tree-sitter based."""

from typing import Optional, List
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.ps1', name='PowerShell', icon='⚡')
@register('.psm1', name='PowerShell Module', icon='⚡')
@register('.psd1', name='PowerShell Data', icon='⚡')
class PowerShellAnalyzer(TreeSitterAnalyzer):
    """PowerShell script analyzer.

    Full PowerShell support via tree-sitter!
    Extracts:
    - Function definitions (function, filter, workflow)
    - Parameter blocks
    - Variable assignments
    - Cmdlet invocations
    - Classes (PowerShell 5.0+)

    Modern Windows automation:
    - Azure DevOps pipelines
    - Windows Server management
    - Active Directory administration
    - Desktop automation
    - Cloud infrastructure (AWS, Azure, GCP)

    Cross-platform compatible:
    - Analyzes PowerShell syntax on any OS (Windows/Linux/macOS)
    - Supports PowerShell Core (cross-platform)
    - Does NOT execute scripts, only parses syntax
    - Useful for DevOps/infrastructure script exploration

    Note: This analyzes PowerShell script SYNTAX, regardless of the host OS.
    """
    language = 'powershell'

    def _get_function_node_types(self) -> List[str]:
        """Get PowerShell-specific function node types.

        PowerShell has multiple function-like constructs:
        - function: Standard function definition
        - filter: Pipeline filter function
        - workflow: Workflow definition (PowerShell Workflow)
        """
        return [
            'function_statement',    # PowerShell function
            'filter_statement',      # PowerShell filter
            'workflow_statement',    # PowerShell workflow
        ]

    def _get_node_name(self, node) -> Optional[str]:
        """Get the name of a PowerShell node (function/class/etc).

        PowerShell tree-sitter uses 'function_name' or 'command_name' for names.
        This is called by _extract_functions() and other extraction methods.
        """
        # Look for 'function_name' child (PowerShell functions)
        for child in node.children:
            if child.type == 'function_name' or child.type == 'command_name':
                return self._get_node_text(child)

        # Look for 'identifier' or 'name' (generic fallback)
        for child in node.children:
            if child.type in ('identifier', 'name'):
                return self._get_node_text(child)

        # Fallback to parent implementation
        return super()._get_node_name(node)

    def _get_signature(self, node) -> str:
        """Get function signature for PowerShell.

        PowerShell functions have several forms:
        - function Name { ... }              -> no signature params
        - function Name { param($x) ... }    -> params in body
        - function Name($x, $y) { ... }      -> params after name

        The base implementation returns the full first line when no parens found,
        which causes name duplication. We handle the PowerShell-specific syntax.
        """
        # Look for script_block_expression or param_block in children
        for child in node.children:
            # Check for inline parameters: function Name($x, $y)
            if child.type == 'script_block_expression':
                text = self._get_node_text(child).strip()
                if text.startswith('('):
                    # Extract just the params part
                    paren_end = text.find(')')
                    if paren_end > 0:
                        return text[:paren_end + 1]

        # Look for param block inside script_block
        for child in node.children:
            if child.type == 'script_block':
                block_text = self._get_node_text(child)
                # Check for param(...) at start of block
                if 'param(' in block_text.lower():
                    # Find the param block
                    param_start = block_text.lower().find('param(')
                    if param_start >= 0:
                        # Find matching closing paren
                        depth = 0
                        for i, c in enumerate(block_text[param_start:]):
                            if c == '(':
                                depth += 1
                            elif c == ')':
                                depth -= 1
                                if depth == 0:
                                    param_block = block_text[param_start:param_start + i + 1]
                                    # Add leading space since formatter does name+signature
                                    return ' ' + param_block
                        break

        # No parameters found - return empty (don't return name again)
        return ''

    def _extract_structs(self) -> List[dict]:
        """Extract PowerShell classes (structs in PowerShell 5.0+).

        PowerShell 5.0 introduced class definitions that work similar to C# classes.
        """
        structs = []

        # PowerShell class nodes
        class_types = [
            'class_statement',  # PowerShell 5.0+ class
        ]

        for class_type in class_types:
            nodes = self._find_nodes_by_type(class_type)
            for node in nodes:
                name = self._get_node_name(node)
                if name:
                    structs.append({
                        'name': name,
                        'line': node.start_point[0] + 1,
                        'type': 'class',
                    })

        return structs
