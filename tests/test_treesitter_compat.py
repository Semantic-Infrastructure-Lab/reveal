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
)


def _parse(code: str, lang: str = 'python'):
    parser = ts.get_parser(lang)
    tree = parser.parse(code)
    return tree.root_node()


class TestNodeChildren(unittest.TestCase):
    def test_returns_list(self):
        root = _parse('x = 1')
        self.assertIsInstance(node_children(root), list)

    def test_count_matches_child_count(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        children = node_children(root)
        self.assertEqual(len(children), root.child_count())

    def test_order_matches_indexed_access(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        children = node_children(root)
        for i, c in enumerate(children):
            self.assertEqual(c.kind(), root.child(i).kind())
            self.assertEqual(c.start_byte(), root.child(i).start_byte())

    def test_empty_for_leaf(self):
        # A leaf-ish node (an identifier inside an assignment)
        root = _parse('x = 1')
        # Walk down to find a leaf
        node = root
        while node.child_count() > 0:
            node = node.child(0)
        self.assertEqual(node_children(node), [])

    def test_iteration_safe(self):
        # Should be iterable multiple times (it's a real list, not a generator)
        root = _parse('x = 1\ny = 2')
        children = node_children(root)
        kinds_first = [c.kind() for c in children]
        kinds_second = [c.kind() for c in children]
        self.assertEqual(kinds_first, kinds_second)


class TestPrevSibling(unittest.TestCase):
    def test_first_child_returns_none(self):
        root = _parse('x = 1\ny = 2')
        first = root.child(0)
        self.assertIsNone(node_prev_sibling(first))

    def test_middle_child_returns_previous(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        # Three top-level expression_statements
        self.assertGreaterEqual(root.child_count(), 3)
        second = root.child(1)
        prev = node_prev_sibling(second)
        self.assertIsNotNone(prev)
        self.assertEqual(prev.start_byte(), root.child(0).start_byte())

    def test_root_node_returns_none(self):
        root = _parse('x = 1')
        # The root has no parent; node_prev_sibling must not crash
        self.assertIsNone(node_prev_sibling(root))

    def test_works_for_inner_nodes(self):
        # Inside `def f(a, b):` the parameters should have siblings
        root = _parse('def f(a, b):\n    pass\n')
        # Walk to find the parameters node
        def find_kind(node, target):
            if node.kind() == target:
                return node
            for i in range(node.child_count()):
                found = find_kind(node.child(i), target)
                if found is not None:
                    return found
            return None

        params = find_kind(root, 'parameters')
        self.assertIsNotNone(params)
        # parameters has children: '(', 'a', ',', 'b', ')'
        # 'b' should have a previous sibling (',')
        named_kids = [params.child(i) for i in range(params.child_count())]
        b_node = next((c for c in named_kids if c.kind() == 'identifier' and c.start_byte() > named_kids[0].start_byte() + 1), None)
        if b_node is not None:
            prev = node_prev_sibling(b_node)
            self.assertIsNotNone(prev)


class TestNextSibling(unittest.TestCase):
    def test_last_child_returns_none(self):
        root = _parse('x = 1')
        # Find the last top-level child
        last = root.child(root.child_count() - 1)
        self.assertIsNone(node_next_sibling(last))

    def test_middle_child_returns_following(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        self.assertGreaterEqual(root.child_count(), 3)
        first = root.child(0)
        nxt = node_next_sibling(first)
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.start_byte(), root.child(1).start_byte())

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
            self.assertEqual(back.start_byte(), mid.start_byte())

    def test_prev_then_next(self):
        root = _parse('x = 1\ny = 2\nz = 3')
        mid = root.child(1)
        prv = node_prev_sibling(mid)
        if prv is not None:
            forward = node_next_sibling(prv)
            self.assertIsNotNone(forward)
            self.assertEqual(forward.start_byte(), mid.start_byte())


if __name__ == '__main__':
    unittest.main()
