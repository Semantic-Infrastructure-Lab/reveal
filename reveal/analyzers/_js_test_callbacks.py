"""Jest/Vitest/Jasmine `describe`/`it`/`test` callback extraction.

Shared by JavaScript and TypeScript analyzers (BACK-662): the logic was
originally TypeScript-only (`typescript.py`, BACK-334/BACK-530) because that's
where it was first needed, but the grammar shape — a call expression whose
last argument is a function/arrow-function literal — is identical in plain
JS. Without this, a `.js`/`.jsx` Jest spec file structurally reads as "one
3-line function": `describe()`/`it()` blocks are call expressions, not
declarations, so the generic tree-sitter function extraction (which only
finds declarations) never sees them at all — not merely unaddressable, but
invisible to `get_structure()`/`--outline` entirely.
"""

from typing import Any, Dict, List
from ..core import node_children as _children

TEST_FRAMEWORK_CALLEE_NAMES = frozenset({
    'describe', 'it', 'test',
    'beforeEach', 'afterEach', 'beforeAll', 'afterAll',
    'fdescribe', 'fit', 'xdescribe', 'xit', 'xtest',
})


class JSTestCallbackMixin:
    """Mix into any JS-family `TreeSitterAnalyzer` subclass for test-block support."""

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
            if callee_name not in TEST_FRAMEWORK_CALLEE_NAMES:
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
