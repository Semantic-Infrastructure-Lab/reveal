"""PHP analyzer using tree-sitter."""

from typing import Any, Dict, List, Optional

from ..core import node_children as _children
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.php', name='PHP', icon='🐘')
class PhpAnalyzer(TreeSitterAnalyzer):
    """Analyze PHP source files.

    Extracts classes, functions, namespaces automatically using tree-sitter.
    """
    language = 'php'

    # ── Interfaces (BACK-403 pt 2) ──────────────────────────────────────────
    # PHP's 'interface_declaration' was previously invisible to get_structure()
    # (not in CLASS_NODE_TYPES), and class/interface bases fell through to the
    # base class's TS-shaped dispatch (which looks for 'class_heritage'/
    # 'extends_type_clause' — neither exists in PHP's grammar), so bases always
    # returned []. Both gaps closed here with PHP's real grammar shapes
    # (verified via `reveal file.php --show-ast`): a class's 'extends' is a
    # 'base_clause' child and its 'implements' is a separate
    # 'class_interface_clause' child; an interface's 'extends' is a 'base_clause'
    # child. Each wraps comma-separated 'name'/'qualified_name' nodes. Abstract
    # classes carry a distinct 'abstract_modifier' node child (not a grouped
    # modifiers node like Java, nor a per-keyword 'modifier' like C#).

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        interfaces = self._extract_interface_declarations()
        if interfaces:
            if head or tail or range:
                interfaces = self._apply_semantic_slice(interfaces, head, tail, range)
            structure['interfaces'] = interfaces
        return structure

    def _extract_class_bases(self, node) -> List[str]:
        node_type = node.kind()
        if node_type == 'class_declaration':
            # extends (base_clause) + implements (class_interface_clause)
            bases = self._extract_php_clause_names(node, 'base_clause')
            bases.extend(self._extract_php_clause_names(node, 'class_interface_clause'))
            return bases
        if node_type == 'interface_declaration':
            # interface Derived extends Base, Other — extends is a base_clause
            return self._extract_php_clause_names(node, 'base_clause')
        return super()._extract_class_bases(node)

    def _is_abstract_class_node(self, node) -> bool:
        # abstract class Base { ... } — 'abstract' parses to its own
        # 'abstract_modifier' node child (distinct node kind, not a token).
        for child in _children(node):
            if child.kind() == 'abstract_modifier':
                return True
        return False

    def _extract_php_clause_names(self, node, clause_kind: str) -> List[str]:
        # Both 'base_clause' and 'class_interface_clause' hold comma-separated
        # 'name' (unqualified) or 'qualified_name' (namespaced, e.g. App\Shape)
        # type references alongside the 'extends'/'implements' keyword token.
        names: List[str] = []
        for child in _children(node):
            if child.kind() != clause_kind:
                continue
            for item in _children(child):
                if item.kind() in ('name', 'qualified_name'):
                    text = self._get_node_text(item).strip()
                    if text:
                        names.append(text)
        return names
