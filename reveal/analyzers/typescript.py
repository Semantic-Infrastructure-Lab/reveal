"""TypeScript file analyzer - tree-sitter based."""

from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.ts', name='TypeScript', icon='')
@register('.tsx', name='TypeScript React', icon='')
class TypeScriptAnalyzer(TreeSitterAnalyzer):
    """TypeScript file analyzer.

    Full TypeScript support via tree-sitter!
    Extracts:
    - Import/export statements (ES6 modules)
    - Function declarations
    - Class definitions
    - Interfaces
    - Type definitions
    - Arrow functions

    Supports both .ts and .tsx (React) files.
    Works on all platforms (Windows, Linux, macOS).
    """
    language = 'typescript'
