"""Swift analyzer using tree-sitter."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.swift', name='Swift', icon='🦅')
class SwiftAnalyzer(TreeSitterAnalyzer):
    """Analyze Swift source files.

    Extracts classes, functions, protocols, structs automatically using tree-sitter.
    Supports iOS, macOS, and Swift-based applications.
    """
    language = 'swift'
