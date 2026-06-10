"""JavaScript file analyzer - tree-sitter based."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.js', name='JavaScript', icon='')
@register('.jsx', name='JavaScript React', icon='')
@register('.mjs', name='JavaScript Module', icon='')
@register('.cjs', name='JavaScript CommonJS', icon='')
class JavaScriptAnalyzer(TreeSitterAnalyzer):
    """JavaScript file analyzer.

    Full JavaScript support via tree-sitter!
    Extracts:
    - Import/export statements
    - Function declarations
    - Class definitions
    - Arrow functions
    - Object methods

    Works on all platforms (Windows, Linux, macOS).
    """
    language = 'javascript'
