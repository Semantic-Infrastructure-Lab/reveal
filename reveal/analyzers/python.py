"""Python file analyzer - tree-sitter based."""

from typing import List, Optional

from ..core import node_children as _children
from ..core.treesitter_compat import _zero_arg
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.py', name='Python', icon='')
class PythonAnalyzer(TreeSitterAnalyzer):
    """Python file analyzer.

    Gets structure + extraction for FREE from TreeSitterAnalyzer!
    """
    language = 'python'

    def _extract_class_bases(self, node) -> List[str]:
        if _zero_arg(node, 'kind') != 'class_definition':
            return super()._extract_class_bases(node)
        # class Foo(ABC, abc.Meta, metaclass=ABCMeta): ...
        for child in _children(node):
            if _zero_arg(child, 'kind') != 'argument_list':
                continue
            bases = []
            for item in _children(child):
                if _zero_arg(item, 'kind') in ('identifier', 'attribute'):
                    text = self._get_node_text(item).strip()
                    if text:
                        bases.append(text)
                elif _zero_arg(item, 'kind') == 'subscript':
                    # BACK-781: class Foo(Protocol[T]) — take the base name
                    # before the subscript, dropping the type parameter.
                    base = self._extract_subscript_base(item)
                    if base:
                        bases.append(base)
                elif _zero_arg(item, 'kind') == 'keyword_argument':
                    # BACK-782: class Foo(metaclass=ABCMeta) — surface the
                    # metaclass value as a base so _is_abc's tail-match on
                    # bases sees it, same as an explicit ABC/ABCMeta base.
                    base = self._extract_metaclass_base(item)
                    if base:
                        bases.append(base)
            return bases
        return []

    def _extract_metaclass_base(self, keyword_arg_node) -> Optional[str]:
        kids = _children(keyword_arg_node)
        if len(kids) < 3:
            return None
        name_node, value_node = kids[0], kids[-1]
        if self._get_node_text(name_node).strip() != 'metaclass':
            return None
        if _zero_arg(value_node, 'kind') in ('identifier', 'attribute'):
            return self._get_node_text(value_node).strip() or None
        return None

    def _extract_subscript_base(self, subscript_node) -> Optional[str]:
        for gchild in _children(subscript_node):
            if _zero_arg(gchild, 'kind') in ('identifier', 'attribute'):
                text = self._get_node_text(gchild).strip()
                if text:
                    return text
        return None
