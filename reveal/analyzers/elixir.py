"""Elixir file analyzer."""

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

    # Optional: Override these for custom behavior
    # def get_structure(self) -> Dict[str, Any]:
    #     structure = super().get_structure()
    #     # Add custom processing here
    #     return structure
