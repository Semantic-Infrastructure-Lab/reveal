"""TypeScript (.ts) and TypeScript React (.tsx) file analyzers."""

from typing import Any, Dict, List, Optional
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

    # ── Test callbacks ────────────────────────────────────────────────────
    # Arrow-function-as-const extraction (`const f = () => {}`) lives in the
    # shared TreeSitterAnalyzer base (treesitter.py) — it's a JS-family
    # grammar shape, not TypeScript-specific; see that class's
    # _extract_arrow_functions()/_find_named_arrow_function() docstrings.

    def _extract_functions(self) -> List[Dict[str, Any]]:
        funcs = super()._extract_functions()
        funcs.extend(self._extract_test_callbacks())
        return funcs

    def _iter_test_callbacks(self):
        """Yield ``(synthetic_name, callback_node)`` for every Jest/Vitest
        ``describe``/``test``/``it`` (etc.) call in the file.

        The single source of truth for the synthetic label, shared by
        :meth:`_extract_test_callbacks` (structure/``--outline``) and
        :meth:`_find_named_test_callback` (by-name ``reveal file <label>``
        resolution). BACK-530: these two paths previously synthesized — and
        would have had to keep re-synthesizing — the label independently; a
        lone enumerator makes the "outline lists it" and "by-name resolves
        it" answers identical by construction, so they cannot drift (the
        exact bug class BACK-530 closes — BACK-527 was another instance).
        """
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
            yield name, last_arg

    def _extract_test_callbacks(self) -> List[Dict[str, Any]]:
        """Extract Jest/Vitest describe/test/it callbacks as synthetic named functions.

        Attributes calls inside test-framework callbacks to named entries so
        calls:// can find callers that live inside test blocks (BACK-334).
        """
        return [
            self._build_function_dict(node, name, [])
            for name, node in self._iter_test_callbacks()
        ]

    def _find_named_test_callback(self, name: str):
        """Resolve a synthetic test-callback label (``describe(foo)``,
        ``test(does a thing)``, or a bare ``beforeEach``) back to its callback
        node, so ``reveal file '<label>'`` resolves exactly what ``--outline``
        lists (BACK-530). Wired into both by-name resolvers
        (``display.element._try_treesitter_extraction`` and
        ``file_handler._find_element_node``), mirroring
        ``_find_named_arrow_function``'s BACK-527 fix."""
        for cb_name, node in self._iter_test_callbacks():
            if cb_name == name:
                return node
        return None

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
