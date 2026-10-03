"""C file analyzer - tree-sitter based."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.c', '.h', name='C', icon='🔧')
class CAnalyzer(TreeSitterAnalyzer):
    """C file analyzer.

    Full C support with automatic extraction:
    - Functions
    - Structs
    - Includes
    - Element extraction
    """
    language = 'c'

    # enum and union definitions were in no category: invisible to the outline and to
    # `reveal f.c Color` (BACK-1648). A bare `enum Color c;` mention is not one (BACK-1627).
    DECLARATION_CATEGORIES = {
        'enums': ('enum_specifier',),
        'unions': ('union_specifier',),
    }
