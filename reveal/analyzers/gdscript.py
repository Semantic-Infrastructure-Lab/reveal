"""GDScript file analyzer - for Godot game engine scripts.

Migrated from regex-based parsing to tree-sitter for robust AST extraction.
Tree-sitter handles nested blocks, comments, and edge cases correctly.

Previous implementation: 197 lines of regex patterns
Current implementation: 15 lines using TreeSitterAnalyzer
"""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.gd', name='GDScript', icon='')
class GDScriptAnalyzer(TreeSitterAnalyzer):
    """GDScript file analyzer for Godot Engine.

    Extracts classes, functions, signals, and variables using tree-sitter.
    Full GDScript support in 3 lines - tree-sitter handles all parsing!
    """
    language = 'gdscript'
