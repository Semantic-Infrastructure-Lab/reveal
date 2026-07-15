"""C++ file analyzer - tree-sitter based."""

from typing import List

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
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

    # ── Class bases (BACK-645) ──────────────────────────────────────────────
    # `class Foo final : public Bar, private ns::Baz { ... }` previously fell
    # through to the base class's Python/TS-shaped _extract_class_bases
    # dispatch (neither 'argument_list' nor 'class_heritage' exist in C++'s
    # grammar), silently returning []. Real shape (verified via
    # `reveal file.cpp --show-ast`): a 'base_class_clause' child wrapping
    # 'type_identifier' (unqualified) or 'qualified_identifier' (namespaced,
    # e.g. 'ns::Bar') entries, interleaved with 'access_specifier' tokens
    # (public/private/protected) that are skipped here — bases are recorded
    # regardless of access level, matching every other language's behavior.

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') != 'class_specifier':
            return super()._extract_class_bases(node)
        for child in _children(node):
            if _zero_arg(child, 'kind') == 'base_class_clause':
                bases = []
                for item in _children(child):
                    if _zero_arg(item, 'kind') in ('type_identifier', 'qualified_identifier'):
                        text = self._get_node_text(item).strip()
                        if text:
                            bases.append(text)
                return bases
        return []
