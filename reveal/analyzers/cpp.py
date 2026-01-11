"""C++ file analyzer - tree-sitter based."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.cpp', '.cc', '.cxx', '.hpp', '.hh', '.h++', name='C++', icon='⚙️')
class CppAnalyzer(TreeSitterAnalyzer):
    """C++ file analyzer.

    Full C++ support with automatic extraction:
    - Functions
    - Classes
    - Structs
    - Namespaces
    - Templates
    - Includes
    - Element extraction
    """
    language = 'cpp'
