"""PHP analyzer using tree-sitter."""

from typing import List, Optional

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
    # Interface extraction itself (BACK-1003) is now handled generically and
    # cached in TreeSitterAnalyzer._get_or_build_structure().

    def _extract_class_bases(self, node) -> List[str]:
        node_type = node.kind()
        if node_type in ('class_declaration', 'anonymous_class'):
            # extends (base_clause) + implements (class_interface_clause).
            # BACK-801 (PHP recall oracle): 'anonymous_class' (`new class(...)
            # extends Foo implements Bar { ... }`) shares the exact same
            # base_clause/class_interface_clause heritage shape as a named
            # class_declaration (confirmed via direct tree-sitter parse), but
            # was falling through to the TS-shaped base implementation (which
            # looks for 'class_heritage'/'extends_type_clause' — neither
            # exists in PHP's grammar) and always returned []. Confirmed live
            # on samples/php (WordPress): 4 files use
            # `new class(...) extends WP_HTML_Tag_Processor { ... }` /
            # `extends WP_HTML_Processor { ... }` — both real, in-corpus
            # base classes — and all 4 anonymous classes silently reported
            # zero bases (invisible to `contracts`' implementer
            # classification and to the base class's own `implementations`
            # list) before this fix.
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

    # ── Callee naming (BACK-915 slice 4) ──────────────────────────────────────

    def _callee_name_php_method(self, call_node) -> Optional[str]:
        # PHP: $obj->method() — member_call_expression children are:
        #   receiver (->|?->) name arguments
        receiver_text = None
        method_name = None
        seen_arrow = False
        for child in _children(call_node):
            if child.kind() in ('->', '?->'):
                seen_arrow = True
                continue
            if child.kind() == 'arguments':
                break
            if not seen_arrow:
                receiver_text = self._get_node_text(child)
            else:
                method_name = self._get_node_text(child)
        if method_name:
            return f"{receiver_text}->{method_name}" if receiver_text else method_name
        return None

    def _callee_name_php_scoped_call(self, call_node) -> Optional[str]:
        # PHP: self::method() / parent::method() / static::method() /
        # Class::method() — scoped_call_expression's 'scope' field is
        # either a 'relative_scope' node (self/parent/static keyword) or a
        # plain 'name' node (a class constant), and 'name' is the method
        # being called (BACK-736).
        scope_node = call_node.child_by_field_name('scope')
        name_node = call_node.child_by_field_name('name')
        if name_node is None:
            return None
        name_text = self._get_node_text(name_node)
        if scope_node is None:
            return name_text
        return f"{self._get_node_text(scope_node)}::{name_text}"

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
