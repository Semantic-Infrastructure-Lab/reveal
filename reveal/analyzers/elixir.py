"""Elixir file analyzer."""

from typing import Any, Dict

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.ex', name='Elixir', icon='')
class ElixirAnalyzer(TreeSitterAnalyzer):
    """Elixir file analyzer.

    Full Elixir support via tree-sitter!

    Automatically extracts:
    - Functions/methods
    - Classes/structs
    - Imports/modules
    - Comments and docstrings

    NOTE: This assumes tree-sitter-elixir is available.
    Install it with: pip install tree-sitter-elixir

    If tree-sitter grammar doesn't exist, you'll need to:
    1. Create a custom FileAnalyzer subclass instead
    2. Implement get_structure() manually
    3. See reveal/base.py for FileAnalyzer base class
    """
    language = 'elixir'

    def get_structure(self, head=None, tail=None, range=None, **kwargs) -> Dict[str, Any]:
        """Extract Elixir code structure with output contract fields."""
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        return {
            'contract_version': '1.0',
            'type': 'elixir_structure',
            'source': str(self.path),
            'source_type': 'file',
            **structure,
        }
