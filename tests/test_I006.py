"""Tests for I006: Import inside function body detector."""

import unittest
from reveal.rules.imports.I006 import I006


def _imp(content, line):
    return {'content': content, 'line': line}


def _func(name, start, end):
    return {'name': name, 'line': start, 'line_end': end}


class TestI006Basic(unittest.TestCase):
    """Guard-rail / early-exit tests."""

    def setUp(self):
        self.rule = I006()

    def test_no_structure_returns_empty(self):
        self.assertEqual(self.rule.check("f.py", None, ""), [])

    def test_empty_structure_returns_empty(self):
        self.assertEqual(self.rule.check("f.py", {}, ""), [])

    def test_no_imports_returns_empty(self):
        structure = {"functions": [_func("foo", 1, 10)]}
        self.assertEqual(self.rule.check("f.py", structure, ""), [])

    def test_no_functions_returns_empty(self):
        structure = {"imports": [_imp("import os", 5)]}
        self.assertEqual(self.rule.check("f.py", structure, ""), [])

    def test_top_level_import_not_flagged(self):
        structure = {
            "imports": [_imp("import os", 1)],
            "functions": [_func("process", 3, 10)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(result, [])


class TestI006Detection(unittest.TestCase):
    """Core detection: imports inside function bodies."""

    def setUp(self):
        self.rule = I006()

    def test_import_inside_function_detected(self):
        structure = {
            "imports": [_imp("import json", 5)],
            "functions": [_func("process", 3, 10)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].line, 5)
        self.assertIn("process", result[0].message)

    def test_rule_code_is_I006(self):
        structure = {
            "imports": [_imp("import os", 2)],
            "functions": [_func("run", 1, 5)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(result[0].rule_code, "I006")

    def test_file_path_propagated(self):
        structure = {
            "imports": [_imp("import os", 2)],
            "functions": [_func("run", 1, 5)],
        }
        result = self.rule.check("pkg/mod.py", structure, "")
        self.assertEqual(result[0].file_path, "pkg/mod.py")

    def test_two_imports_inside_same_function(self):
        structure = {
            "imports": [
                _imp("import os", 3),
                _imp("import sys", 4),
            ],
            "functions": [_func("run", 1, 10)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 2)

    def test_import_at_function_boundary_start(self):
        """Import on the function's first line is inside it."""
        structure = {
            "imports": [_imp("import os", 1)],
            "functions": [_func("run", 1, 5)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 1)

    def test_import_at_function_boundary_end(self):
        """Import on the function's last line is inside it."""
        structure = {
            "imports": [_imp("import os", 5)],
            "functions": [_func("run", 1, 5)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 1)

    def test_import_just_outside_function_not_flagged(self):
        structure = {
            "imports": [_imp("import os", 11)],
            "functions": [_func("run", 1, 10)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(result, [])

    def test_multiple_functions_assigns_to_correct_one(self):
        structure = {
            "imports": [
                _imp("import os", 5),   # inside alpha (1-10)
                _imp("import sys", 15), # inside beta (11-20)
            ],
            "functions": [
                _func("alpha", 1, 10),
                _func("beta", 11, 20),
            ],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 2)
        msgs = {r.message for r in result}
        self.assertTrue(any("alpha" in m for m in msgs))
        self.assertTrue(any("beta" in m for m in msgs))

    def test_context_field_is_import_content(self):
        structure = {
            "imports": [_imp("import json", 5)],
            "functions": [_func("run", 1, 10)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertIn("import json", result[0].context)


class TestI006Exceptions(unittest.TestCase):
    """Imports that should be silently skipped."""

    def setUp(self):
        self.rule = I006()

    def test_future_import_skipped(self):
        structure = {
            "imports": [_imp("from __future__ import annotations", 2)],
            "functions": [_func("run", 1, 10)],
        }
        self.assertEqual(self.rule.check("f.py", structure, ""), [])

    def test_noqa_skipped(self):
        # line 2 = "    import os  # noqa"
        structure = {
            "imports": [_imp("import os", 2)],
            "functions": [_func("run", 1, 10)],
        }
        content = "def run():\n    import os  # noqa\n"
        self.assertEqual(self.rule.check("f.py", structure, content), [])

    def test_noqa_I006_skipped(self):
        # line 2 = "    import os  # noqa: I006"
        structure = {
            "imports": [_imp("import os", 2)],
            "functions": [_func("run", 1, 10)],
        }
        content = "def run():\n    import os  # noqa: I006\n"
        self.assertEqual(self.rule.check("f.py", structure, content), [])

    def test_noqa_only_in_content_field_not_seen_without_source(self):
        """Analyzer strips comments from content; without source lines noqa is invisible."""
        structure = {
            "imports": [_imp("import os", 2)],
            "functions": [_func("run", 1, 10)],
        }
        # No content passed — rule falls back to import_content (no comment) → should flag
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 1)

    def test_type_checking_in_import_skipped(self):
        structure = {
            "imports": [_imp("if TYPE_CHECKING: import Foo", 2)],
            "functions": [_func("run", 1, 10)],
        }
        self.assertEqual(self.rule.check("f.py", structure, ""), [])

    def test_lazy_function_name_skipped(self):
        structure = {
            "imports": [_imp("from heavy import Widget", 3)],
            "functions": [_func("_lazy_import_widget", 1, 10)],
        }
        self.assertEqual(self.rule.check("f.py", structure, ""), [])

    def test_import_in_function_name_skipped(self):
        structure = {
            "imports": [_imp("import re", 3)],
            "functions": [_func("_get_import_module", 1, 10)],
        }
        self.assertEqual(self.rule.check("f.py", structure, ""), [])

    def test_type_checking_in_function_name_skipped(self):
        structure = {
            "imports": [_imp("import Foo", 3)],
            "functions": [_func("_type_checking_imports", 1, 10)],
        }
        self.assertEqual(self.rule.check("f.py", structure, ""), [])

    def test_regular_function_not_excepted(self):
        """A non-matching function name should still produce a detection."""
        structure = {
            "imports": [_imp("import os", 3)],
            "functions": [_func("process_data", 1, 10)],
        }
        result = self.rule.check("f.py", structure, "")
        self.assertEqual(len(result), 1)


class TestI006BuildFunctionRanges(unittest.TestCase):
    """Unit tests for _build_function_ranges."""

    def setUp(self):
        self.rule = I006()

    def test_valid_function(self):
        functions = [_func("foo", 1, 10)]
        ranges = self.rule._build_function_ranges(functions)
        self.assertEqual(ranges, [(1, 10, "foo")])

    def test_inverted_range_excluded(self):
        """start > end should be dropped."""
        functions = [{'name': 'bad', 'line': 10, 'line_end': 5}]
        ranges = self.rule._build_function_ranges(functions)
        self.assertEqual(ranges, [])

    def test_missing_line_end_excluded(self):
        functions = [{'name': 'bad', 'line': 1}]
        ranges = self.rule._build_function_ranges(functions)
        self.assertEqual(ranges, [])

    def test_multiple_functions(self):
        functions = [_func("a", 1, 5), _func("b", 10, 20)]
        ranges = self.rule._build_function_ranges(functions)
        self.assertEqual(len(ranges), 2)


class TestI006FindEnclosingFunction(unittest.TestCase):
    """Unit tests for _find_enclosing_function."""

    def setUp(self):
        self.rule = I006()

    def test_import_inside_only_function(self):
        ranges = [(1, 10, "foo")]
        result = self.rule._find_enclosing_function(5, ranges)
        self.assertEqual(result, (1, 10, "foo"))

    def test_import_outside_returns_none(self):
        ranges = [(1, 10, "foo")]
        result = self.rule._find_enclosing_function(20, ranges)
        self.assertIsNone(result)

    def test_nested_functions_returns_innermost(self):
        """Inner function (smaller span) wins."""
        ranges = [
            (1, 50, "outer"),   # span 49
            (10, 20, "inner"),  # span 10 — innermost
        ]
        result = self.rule._find_enclosing_function(15, ranges)
        self.assertEqual(result[2], "inner")

    def test_boundary_inclusive(self):
        ranges = [(5, 15, "fn")]
        self.assertIsNotNone(self.rule._find_enclosing_function(5, ranges))
        self.assertIsNotNone(self.rule._find_enclosing_function(15, ranges))
        self.assertIsNone(self.rule._find_enclosing_function(4, ranges))
        self.assertIsNone(self.rule._find_enclosing_function(16, ranges))


class TestI006IsException(unittest.TestCase):
    """Unit tests for _is_exception."""

    def setUp(self):
        self.rule = I006()

    def test_future_import(self):
        self.assertTrue(self.rule._is_exception("from __future__ import annotations", "run"))

    def test_noqa_comment(self):
        self.assertTrue(self.rule._is_exception("import os  # noqa", "run"))

    def test_type_checking_in_content(self):
        self.assertTrue(self.rule._is_exception("TYPE_CHECKING import Foo", "run"))

    def test_lazy_in_func_name(self):
        self.assertTrue(self.rule._is_exception("import os", "_lazy_load"))

    def test_import_in_func_name(self):
        self.assertTrue(self.rule._is_exception("import os", "_get_import"))

    def test_type_checking_in_func_name(self):
        self.assertTrue(self.rule._is_exception("import Foo", "type_checking_block"))

    def test_normal_case_not_excepted(self):
        self.assertFalse(self.rule._is_exception("import os", "process"))

    def test_case_insensitive_lazy(self):
        self.assertTrue(self.rule._is_exception("import os", "LAZY_LOAD"))

    def test_case_insensitive_future(self):
        self.assertTrue(self.rule._is_exception("from __FUTURE__ import X", "run"))


if __name__ == '__main__':
    unittest.main()
