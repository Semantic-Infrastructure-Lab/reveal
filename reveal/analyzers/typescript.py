"""TypeScript (.ts) and TypeScript React (.tsx) file analyzers."""

from typing import Any, Dict, List, Optional, Tuple
from ..core import node_children as _children
from ..registry import register
from ..treesitter import TreeSitterAnalyzer

_TEST_FRAMEWORK_CALLEE_NAMES = frozenset({
    'describe', 'it', 'test',
    'beforeEach', 'afterEach', 'beforeAll', 'afterAll',
    'fdescribe', 'fit', 'xdescribe', 'xit', 'xtest',
})


class _TypeScriptBase(TreeSitterAnalyzer):
    """Shared extraction for TypeScript (.ts) and TypeScript React (.tsx)."""

    # ── Arrow functions & test callbacks ─────────────────────────────────────

    def _extract_functions(self) -> List[Dict[str, Any]]:
        funcs = super()._extract_functions()
        funcs.extend(self._extract_arrow_functions())
        funcs.extend(self._extract_test_callbacks())
        return funcs

    def _is_module_scope_decl(self, lexical_decl_node) -> bool:
        parent = lexical_decl_node.parent()
        if parent is None:
            return False
        if parent.kind() == 'program':
            return True
        if parent.kind() == 'export_statement':
            gp = parent.parent()
            return gp is not None and gp.kind() == 'program'
        return False

    def _arrow_or_fn_value(self, variable_declarator_node) -> Tuple[Optional[Any], Optional[Any]]:
        """Return (name_node, value_node) for a variable_declarator, or (None, None)."""
        name_node = value_node = None
        for ch in _children(variable_declarator_node):
            if ch.kind() == 'identifier' and name_node is None:
                name_node = ch
            elif ch.kind() in ('arrow_function', 'function_expression'):
                value_node = ch
        return name_node, value_node

    def _extract_arrow_functions(self) -> List[Dict[str, Any]]:
        """Extract module-scope arrow/function-expression declarations (const X = () => {})."""
        funcs = []
        for decl_node in self._find_nodes_by_type('lexical_declaration'):
            if not self._is_module_scope_decl(decl_node):
                continue
            for child in _children(decl_node):
                if child.kind() != 'variable_declarator':
                    continue
                name_node, value_node = self._arrow_or_fn_value(child)
                if name_node and value_node:
                    funcs.append(self._build_function_dict(
                        value_node, self._get_node_text(name_node), []
                    ))
        return funcs

    def _extract_test_callbacks(self) -> List[Dict[str, Any]]:
        """Extract Jest/Vitest describe/test/it callbacks as synthetic named functions.

        Attributes calls inside test-framework callbacks to named entries so
        calls:// can find callers that live inside test blocks (BACK-334).
        """
        funcs = []
        for call_node in self._find_nodes_by_type('call_expression'):
            callee_name = self._get_callee_name(call_node)
            if callee_name not in _TEST_FRAMEWORK_CALLEE_NAMES:
                continue
            args_nodes = [ch for ch in _children(call_node) if ch.kind() == 'arguments']
            if not args_nodes:
                continue
            arg_children = [
                ch for ch in _children(args_nodes[0])
                if ch.kind() not in (',', '(', ')')
            ]
            if not arg_children:
                continue
            last_arg = arg_children[-1]
            if last_arg.kind() not in ('arrow_function', 'function_expression', 'function'):
                continue
            # Optional string label as first arg (absent for beforeEach/afterEach etc.)
            test_name = None
            if len(arg_children) >= 2 and arg_children[0].kind() in ('string', 'template_string'):
                raw = self._get_node_text(arg_children[0])
                test_name = raw.strip('"\'`')
            name = f"{callee_name}({test_name})" if test_name else callee_name
            funcs.append(self._build_function_dict(last_arg, name, []))
        return funcs

    # ── TypeScript type declarations ──────────────────────────────────────────

    def _extract_ts_types(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract interface, type alias, and enum declarations."""
        interfaces: List[Dict[str, Any]] = []
        types: List[Dict[str, Any]] = []
        enums: List[Dict[str, Any]] = []

        for node_type, bucket in (
            ('interface_declaration', interfaces),
            ('type_alias_declaration', types),
            ('enum_declaration', enums),
        ):
            for node in self._find_nodes_by_type(node_type):
                name = self._get_node_name(node)
                if not name:
                    continue
                line_start = node.start_position().row + 1
                line_end = node.end_position().row + 1
                entry: Dict[str, Any] = {
                    'line': line_start,
                    'line_end': line_end,
                    'name': name,
                    'line_count': line_end - line_start + 1,
                    'decorators': [],
                    'bases': self._extract_class_bases(node),
                }
                bucket.append(entry)

        return {'interfaces': interfaces, 'types': types, 'enums': enums}

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        structure = super().get_structure(head=head, tail=tail, range=range, **kwargs)
        for key, items in self._extract_ts_types().items():
            if items:
                if head or tail or range:
                    items = self._apply_semantic_slice(items, head, tail, range)
                structure[key] = items
        return structure


@register('.ts', name='TypeScript', icon='')
class TypeScriptAnalyzer(_TypeScriptBase):
    """TypeScript (.ts) file analyzer."""
    language = 'typescript'


@register('.tsx', name='TypeScript React', icon='')
class TSXAnalyzer(_TypeScriptBase):
    """TypeScript React (.tsx) file analyzer — uses JSX-aware tree-sitter grammar."""
    language = 'tsx'
