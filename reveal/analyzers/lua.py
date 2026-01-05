"""Lua analyzer using tree-sitter."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.lua', name='Lua', icon='🌙')
class LuaAnalyzer(TreeSitterAnalyzer):
    """Analyze Lua source files.

    Extracts functions automatically using tree-sitter.
    """
    language = 'lua'
