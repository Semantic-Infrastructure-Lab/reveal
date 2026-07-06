"""Regression test for TreeSitterAnalyzer._complexity_depth_and_calls.

BACK-489: `_build_function_dict` used to call `calculate_complexity_and_depth`
and `_extract_calls_in_function` as two independent full subtree walks per
function. Profiling a real 11K-file TypeScript repo showed this pair
dominates `reveal architecture`'s cost for large repos even after fixing the
double-parse-per-file bug (node_children: 94M calls, 88s self time). Merged
into one traversal (`_complexity_depth_and_calls`) to halve node visits.

This pins the equivalence: the merged walk must return exactly the same
(complexity, depth, calls) as calling the two original functions back to
back, for real code with nesting, decisions, and calls — not just simple
cases, since the original bug-class here would be an off-by-one in which
node's kind drives the depth increment during the merge.
"""

import tempfile
import unittest
from pathlib import Path

from reveal.complexity import calculate_complexity_and_depth
from reveal.analyzers.python import PythonAnalyzer


def _first_function_node(analyzer):
    for node in analyzer._find_nodes_by_type('function_definition'):
        return node
    raise AssertionError("no function_definition node found")


class TestComplexityDepthAndCallsMerge(unittest.TestCase):

    def _assert_matches_originals(self, code: str):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sample.py"
            path.write_text(code)
            analyzer = PythonAnalyzer(str(path))
            node = _first_function_node(analyzer)

            old_complexity, old_depth = calculate_complexity_and_depth(node)
            old_calls = analyzer._extract_calls_in_function(node)

            new_complexity, new_depth, new_calls = analyzer._complexity_depth_and_calls(node)

            self.assertEqual(new_complexity, old_complexity)
            self.assertEqual(new_depth, old_depth)
            self.assertEqual(new_calls, old_calls)

    def test_simple_function_no_branches(self):
        self._assert_matches_originals("def f():\n    return 1\n")

    def test_deeply_nested_conditionals(self):
        self._assert_matches_originals(
            "def outer():\n"
            "    if a:\n"
            "        if b:\n"
            "            for x in y:\n"
            "                while z:\n"
            "                    if c and d:\n"
            "                        foo()\n"
            "    return bar()\n"
        )

    def test_nested_function_definitions(self):
        """BACK-490: a nested function def is a leaf for the outer walk — the
        outer function's complexity/depth/calls must NOT include the inner
        function's contributions (that used to double-count: outer() got the
        same complexity as inner() purely from re-walking its body). The
        inner function keeps its own full walk via its own top-level entry."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sample.py"
            path.write_text(
                "def outer():\n"
                "    def inner():\n"
                "        if a:\n"
                "            baz()\n"
                "        return 1\n"
                "    return inner() + qux()\n"
            )
            analyzer = PythonAnalyzer(str(path))
            nodes = list(analyzer._find_nodes_by_type('function_definition'))
            by_name = {analyzer._get_node_name(n): n for n in nodes}

            outer_complexity, outer_depth, outer_calls = analyzer._complexity_depth_and_calls(by_name['outer'])
            self.assertEqual(outer_complexity, 1)
            self.assertEqual(outer_depth, 0)
            self.assertEqual(outer_calls, ['inner', 'qux'])

            inner_complexity, inner_depth, inner_calls = analyzer._complexity_depth_and_calls(by_name['inner'])
            self.assertEqual(inner_complexity, 2)
            self.assertEqual(inner_calls, ['baz'])

    def test_repeated_and_nested_calls(self):
        self._assert_matches_originals(
            "def f():\n"
            "    foo(bar())\n"
            "    foo(baz())\n"
            "    return foo(bar())\n"
        )


if __name__ == '__main__':
    unittest.main()
