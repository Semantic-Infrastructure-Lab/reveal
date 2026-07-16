"""JavaScript file analyzer - tree-sitter based."""

from typing import Any, Dict, List
from ..registry import register
from ..treesitter import TreeSitterAnalyzer
from ._js_test_callbacks import JSTestCallbackMixin


@register('.js', name='JavaScript', icon='')
@register('.jsx', name='JavaScript React', icon='')
@register('.mjs', name='JavaScript Module', icon='')
@register('.cjs', name='JavaScript CommonJS', icon='')
class JavaScriptAnalyzer(JSTestCallbackMixin, TreeSitterAnalyzer):
    """JavaScript file analyzer.

    Full JavaScript support via tree-sitter!
    Extracts:
    - Import/export statements
    - Function declarations
    - Class definitions
    - Arrow functions
    - Object methods
    - Jest/Vitest/Jasmine describe()/it()/test() blocks (BACK-662) — see
      JSTestCallbackMixin.

    Works on all platforms (Windows, Linux, macOS).
    """
    language = 'javascript'

    def _extract_functions(self) -> List[Dict[str, Any]]:
        funcs = super()._extract_functions()
        funcs.extend(self._extract_test_callbacks())
        return funcs
