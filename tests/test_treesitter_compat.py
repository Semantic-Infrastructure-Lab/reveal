"""Tests for reveal.core.treesitter_compat helpers.

These helpers paper over the tree-sitter 0.x → 1.x API break (1.x removed
node.children, node.prev_sibling, node.next_sibling, and made every property
into a method). The helpers are imported by ~26 files in the codebase, so
their behavior is a shared contract.
"""

import unittest

import tree_sitter_language_pack as ts

from reveal.core import (
    node_children,
    node_prev_sibling,
    node_next_sibling,
    tree_root,
    ts_parse,
)
from reveal.core.treesitter_compat import _zero_arg

import pytest

# BACK-1149: guards cross-version/cross-platform compatibility behavior
pytestmark = pytest.mark.compat


def _parse(code: str, lang: str = 'python'):
    parser = ts.get_parser(lang)
    tree = ts_parse(parser, code)
    return tree_root(tree)


class TestNodeChildren(unittest.TestCase):
    def test_returns_list(self):
        root = _parse('x = 1')
        self.assertIsInstance(node_children(root), list)

    def test_count_matches_child_count(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        children = node_children(root)
        self.assertEqual(len(children), _zero_arg(root, 'child_count'))

    def test_order_matches_indexed_access(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        children = node_children(root)
        for i, c in enumerate(children):
            self.assertEqual(_zero_arg(c, 'kind'), _zero_arg(root.child(i), 'kind'))
            self.assertEqual(_zero_arg(c, 'start_byte'), _zero_arg(root.child(i), 'start_byte'))

    def test_empty_for_leaf(self):
        # A leaf-ish node (an identifier inside an assignment)
        root = _parse('x = 1')
        # Walk down to find a leaf
        node = root
        while _zero_arg(node, 'child_count') > 0:
            node = node.child(0)
        self.assertEqual(node_children(node), [])

    def test_iteration_safe(self):
        # Should be iterable multiple times (it's a real list, not a generator)
        root = _parse('x = 1\ny = 2')
        children = node_children(root)
        kinds_first = [_zero_arg(c, 'kind') for c in children]
        kinds_second = [_zero_arg(c, 'kind') for c in children]
        self.assertEqual(kinds_first, kinds_second)


class TestPrevSibling(unittest.TestCase):
    def test_first_child_returns_none(self):
        root = _parse('x = 1\ny = 2')
        first = root.child(0)
        self.assertIsNone(node_prev_sibling(first))

    def test_middle_child_returns_previous(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        # Three top-level expression_statements
        self.assertGreaterEqual(_zero_arg(root, 'child_count'), 3)
        second = root.child(1)
        prev = node_prev_sibling(second)
        self.assertIsNotNone(prev)
        self.assertEqual(_zero_arg(prev, 'start_byte'), _zero_arg(root.child(0), 'start_byte'))

    def test_root_node_returns_none(self):
        root = _parse('x = 1')
        # The root has no parent; node_prev_sibling must not crash
        self.assertIsNone(node_prev_sibling(root))

    def test_works_for_inner_nodes(self):
        # Inside `def f(a, b):` the parameters should have siblings
        root = _parse('def f(a, b):\n    pass\n')
        # Walk to find the parameters node
        def find_kind(node, target):
            if _zero_arg(node, 'kind') == target:
                return node
            for i in range(_zero_arg(node, 'child_count')):
                found = find_kind(node.child(i), target)
                if found is not None:
                    return found
            return None

        params = find_kind(root, 'parameters')
        self.assertIsNotNone(params)
        # parameters has children: '(', 'a', ',', 'b', ')'
        # 'b' should have a previous sibling (',')
        named_kids = [params.child(i) for i in range(_zero_arg(params, 'child_count'))]
        b_node = next(
            (
                c
                for c in named_kids
                if _zero_arg(c, 'kind') == 'identifier'
                and _zero_arg(c, 'start_byte') > _zero_arg(named_kids[0], 'start_byte') + 1
            ),
            None,
        )
        if b_node is not None:
            prev = node_prev_sibling(b_node)
            self.assertIsNotNone(prev)


class TestNextSibling(unittest.TestCase):
    def test_last_child_returns_none(self):
        root = _parse('x = 1')
        # Find the last top-level child
        last = root.child(_zero_arg(root, 'child_count') - 1)
        self.assertIsNone(node_next_sibling(last))

    def test_middle_child_returns_following(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        self.assertGreaterEqual(_zero_arg(root, 'child_count'), 3)
        first = root.child(0)
        nxt = node_next_sibling(first)
        self.assertIsNotNone(nxt)
        self.assertEqual(_zero_arg(nxt, 'start_byte'), _zero_arg(root.child(1), 'start_byte'))

    def test_root_node_returns_none(self):
        root = _parse('x = 1')
        self.assertIsNone(node_next_sibling(root))


class TestRoundTripWithCheckpoints(unittest.TestCase):
    """Sanity: prev(next(x)) and next(prev(x)) recover the same start_byte."""

    def test_next_then_prev(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        mid = root.child(1)
        nxt = node_next_sibling(mid)
        if nxt is not None:
            back = node_prev_sibling(nxt)
            self.assertIsNotNone(back)
            self.assertEqual(_zero_arg(back, 'start_byte'), _zero_arg(mid, 'start_byte'))

    def test_prev_then_next(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        mid = root.child(1)
        prv = node_prev_sibling(mid)
        if prv is not None:
            forward = node_next_sibling(prv)
            self.assertIsNotNone(forward)
            self.assertEqual(_zero_arg(forward, 'start_byte'), _zero_arg(mid, 'start_byte'))


class TestTreeRoot(unittest.TestCase):
    """tree_root() must work across the 1.12.5 root_node method→property change.

    tree-sitter-language-pack <1.12.5 exposes `Tree.root_node` as a bound
    method; 1.12.5+ exposes it as a property (BACK-573/BACK-574).
    """

    class _MethodStyleTree:
        """Simulates <1.12.5: root_node is callable."""

        def __init__(self, node):
            self._node = node

        def root_node(self):
            return self._node

    class _PropertyStyleTree:
        """Simulates >=1.12.5: root_node is a plain attribute."""

        def __init__(self, node):
            self.root_node = node

    def test_real_installed_tree(self):
        # Whatever calling convention the currently-installed pin uses,
        # tree_root() must resolve to the real root node either way.
        tree = ts.get_parser('python').parse('x = 1')
        root = tree_root(tree)
        self.assertEqual(_zero_arg(root, 'kind'), 'module')

    def test_method_style_root_node(self):
        sentinel = object()
        tree = self._MethodStyleTree(sentinel)
        self.assertIs(tree_root(tree), sentinel)

    def test_property_style_root_node(self):
        sentinel = object()
        tree = self._PropertyStyleTree(sentinel)
        self.assertIs(tree_root(tree), sentinel)


class TestZeroArgKindFallback(unittest.TestCase):
    """_zero_arg(x, 'kind') must resolve under both API eras.

    Unlike every other zero-arg accessor this module wraps, `kind` isn't a
    same-name method->property flip: the >=1.12.5 core `tree_sitter.Node`
    has no `.kind` attribute at all, only `.type` (same semantic value,
    different name) -- confirmed live in isolated venvs
    (torrential-breeze-0821) across tree-sitter 0.23.0 through 0.26.0.
    """

    class _MethodStyleNode:
        """Simulates <1.12.5 vendored Node: kind() is callable, no .type."""

        def kind(self):
            return 'module'

    class _CoreBindingNode:
        """Simulates >=1.12.5 core Node: no .kind, .type is the real value."""

        type = 'module'

    def test_method_style_kind(self):
        self.assertEqual(_zero_arg(self._MethodStyleNode(), 'kind'), 'module')

    def test_core_binding_falls_back_to_type(self):
        self.assertEqual(_zero_arg(self._CoreBindingNode(), 'kind'), 'module')

    def test_real_installed_node(self):
        # Whatever calling convention the currently-installed pin uses,
        # _zero_arg(node, 'kind') must resolve to the real node kind.
        tree = ts_parse(ts.get_parser('python'), 'x = 1')
        root = tree_root(tree)
        self.assertEqual(_zero_arg(root, 'kind'), 'module')

    def test_other_missing_attribute_still_raises(self):
        # The 'kind'->'type' fallback must not swallow every AttributeError
        # -- only the specific 'kind' case gets the fallback.
        with self.assertRaises(AttributeError):
            _zero_arg(self._MethodStyleNode(), 'nonexistent_accessor')


class TestZeroArgPositionFallback(unittest.TestCase):
    """_zero_arg(x, 'start_position'/'end_position') must resolve under both
    API eras (BACK-1158).

    Same root cause as `kind`/`type` (torrential-breeze-0821 root-cause
    note): Rust's `tree_sitter::Node` names these `.start_position()`/
    `.end_position()`; the >=1.12.5 core `tree_sitter.Node` binding has
    never used those names, only `.start_point`/`.end_point` (same
    semantic value, different name).
    """

    class _MethodStyleNode:
        """Simulates <1.12.5 vendored Node: *_position() callable, no *_point."""

        def start_position(self):
            return (0, 0)

        def end_position(self):
            return (0, 5)

    class _CoreBindingNode:
        """Simulates >=1.12.5 core Node: no *_position, *_point is the real value."""

        start_point = (0, 0)
        end_point = (0, 5)

    def test_method_style_start_position(self):
        self.assertEqual(_zero_arg(self._MethodStyleNode(), 'start_position'), (0, 0))

    def test_method_style_end_position(self):
        self.assertEqual(_zero_arg(self._MethodStyleNode(), 'end_position'), (0, 5))

    def test_core_binding_falls_back_to_start_point(self):
        self.assertEqual(_zero_arg(self._CoreBindingNode(), 'start_position'), (0, 0))

    def test_core_binding_falls_back_to_end_point(self):
        self.assertEqual(_zero_arg(self._CoreBindingNode(), 'end_position'), (0, 5))

    def test_real_installed_node(self):
        tree = ts_parse(ts.get_parser('python'), 'x = 1')
        root = tree_root(tree)
        # The vendored (<1.12.5) Point isn't a plain tuple -- compare via
        # .row/.column, present on both eras' Point type.
        start = _zero_arg(root, 'start_position')
        end = _zero_arg(root, 'end_position')
        self.assertEqual((start.row, start.column), (0, 0))
        self.assertEqual((end.row, end.column), (0, 5))

    def test_other_missing_attribute_still_raises(self):
        with self.assertRaises(AttributeError):
            _zero_arg(self._MethodStyleNode(), 'nonexistent_accessor')


class TestTsParse(unittest.TestCase):
    """ts_parse() must work across the 1.12.5 str→bytes change in Parser.parse()."""

    class _StrOnlyParser:
        """Simulates <1.12.5: parse() requires str, rejects bytes."""

        def parse(self, source):
            if not isinstance(source, str):
                raise TypeError("argument 'source': not an instance of 'str'")
            return ('parsed-str', source)

    class _BytesOnlyParser:
        """Simulates >=1.12.5: parse() requires bytes, rejects str."""

        def parse(self, source):
            if not isinstance(source, bytes):
                raise TypeError('source must be a bytestring or a callable, not str')
            return ('parsed-bytes', source)

    def test_real_installed_parser(self):
        parser = ts.get_parser('python')
        tree = ts_parse(parser, 'x = 1')
        self.assertEqual(_zero_arg(tree_root(tree), 'kind'), 'module')

    def test_str_only_parser_gets_str(self):
        result = ts_parse(self._StrOnlyParser(), 'hello')
        self.assertEqual(result, ('parsed-str', 'hello'))

    def test_bytes_only_parser_falls_back_to_bytes(self):
        result = ts_parse(self._BytesOnlyParser(), 'hello')
        self.assertEqual(result, ('parsed-bytes', b'hello'))


if __name__ == '__main__':
    unittest.main()
