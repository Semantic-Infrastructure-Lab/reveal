"""Tests for D001: Duplicate function detection rule."""

import unittest
from reveal.rules.duplicates.D001 import D001


class TestD001Basic(unittest.TestCase):
    """Basic tests for D001 duplicate detection."""

    def setUp(self):
        self.rule = D001()

    def test_no_structure_returns_empty(self):
        """No structure should return empty list."""
        result = self.rule.check("test.py", None, "")
        self.assertEqual(result, [])

    def test_no_functions_returns_empty(self):
        """Structure without functions returns empty."""
        result = self.rule.check("test.py", {"classes": []}, "content")
        self.assertEqual(result, [])

    def test_single_function_returns_empty(self):
        """Single function cannot have duplicates."""
        structure = {
            "functions": [{"name": "foo", "line": 1, "line_end": 3}]
        }
        content = "def foo():\n    return 1\n"
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(result, [])

    def test_detects_exact_duplicate(self):
        """Two identical functions should be detected."""
        content = """def foo():
    x = 1
    y = 2
    return x + y

def bar():
    x = 1
    y = 2
    return x + y
"""
        structure = {
            "functions": [
                {"name": "foo", "line": 1, "line_end": 4},
                {"name": "bar", "line": 6, "line_end": 9},
            ]
        }
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(len(result), 1)
        self.assertIn("bar", result[0].message)
        self.assertIn("foo", result[0].message)

    def test_different_functions_no_detection(self):
        """Different functions should not be flagged."""
        content = """def foo():
    return 1

def bar():
    return 2
"""
        structure = {
            "functions": [
                {"name": "foo", "line": 1, "line_end": 2},
                {"name": "bar", "line": 4, "line_end": 5},
            ]
        }
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(result, [])


class TestD001Normalization(unittest.TestCase):
    """Tests for code normalization."""

    def setUp(self):
        self.rule = D001()

    def test_normalize_removes_python_comments(self):
        """Should remove # comments."""
        code = "x = 1  # set x\ny = 2  # set y"
        normalized = self.rule._normalize(code)
        self.assertNotIn("#", normalized)

    def test_normalize_removes_c_style_comments(self):
        """Should remove // comments."""
        code = "x = 1; // set x\ny = 2; // set y"
        normalized = self.rule._normalize(code)
        self.assertNotIn("//", normalized)

    def test_normalize_removes_multiline_comments(self):
        """Should remove /* */ comments."""
        code = "x = 1; /* this is\na comment */ y = 2;"
        normalized = self.rule._normalize(code)
        self.assertNotIn("/*", normalized)
        self.assertNotIn("*/", normalized)

    def test_normalize_removes_docstrings(self):
        """Should remove Python docstrings."""
        code = '"""This is a docstring"""\nx = 1'
        normalized = self.rule._normalize(code)
        self.assertNotIn('"""', normalized)

    def test_normalize_removes_single_quote_docstrings(self):
        """Should remove single-quote docstrings."""
        code = "'''This is a docstring'''\nx = 1"
        normalized = self.rule._normalize(code)
        self.assertNotIn("'''", normalized)

    def test_normalize_collapses_whitespace(self):
        """Should collapse multiple spaces."""
        code = "x    =    1"
        normalized = self.rule._normalize(code)
        self.assertNotIn("    ", normalized)

    def test_normalize_removes_empty_lines(self):
        """Should remove empty lines."""
        code = "x = 1\n\n\ny = 2"
        normalized = self.rule._normalize(code)
        self.assertEqual(normalized.count("\n"), 1)


class TestD001ExtractFunctionBody(unittest.TestCase):
    """Tests for function body extraction."""

    def setUp(self):
        self.rule = D001()

    def test_extract_basic_body(self):
        """Should extract function body."""
        content = "def foo():\n    return 1\n    return 2\n"
        func = {"name": "foo", "line": 1, "line_end": 3}
        body = self.rule._extract_function_body(func, content)
        self.assertIn("return 1", body)
        self.assertIn("return 2", body)

    def test_extract_with_zero_line(self):
        """Zero line should return empty."""
        func = {"name": "foo", "line": 0, "line_end": 3}
        body = self.rule._extract_function_body(func, "content")
        self.assertEqual(body, "")

    def test_extract_with_zero_end_line(self):
        """Zero end line should return empty."""
        func = {"name": "foo", "line": 1, "line_end": 0}
        body = self.rule._extract_function_body(func, "content")
        self.assertEqual(body, "")

    def test_extract_out_of_bounds(self):
        """Line beyond content should return empty."""
        func = {"name": "foo", "line": 100, "line_end": 105}
        body = self.rule._extract_function_body(func, "short\ncontent\n")
        self.assertEqual(body, "")

    def test_extract_empty_body(self):
        """Empty body range returns empty."""
        content = "def foo():\n    pass\n"
        func = {"name": "foo", "line": 2, "line_end": 1}  # Invalid range
        body = self.rule._extract_function_body(func, content)
        self.assertEqual(body, "")


class TestD001MultipleDuplicates(unittest.TestCase):
    """Tests for multiple duplicate scenarios."""

    def setUp(self):
        self.rule = D001()

    def test_three_identical_functions(self):
        """Three identical functions should generate 2 detections."""
        content = """def foo():
    x = 1
    y = 2
    return x + y

def bar():
    x = 1
    y = 2
    return x + y

def baz():
    x = 1
    y = 2
    return x + y
"""
        structure = {
            "functions": [
                {"name": "foo", "line": 1, "line_end": 4},
                {"name": "bar", "line": 6, "line_end": 9},
                {"name": "baz", "line": 11, "line_end": 14},
            ]
        }
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(len(result), 2)

    def test_two_pairs_of_duplicates(self):
        """Two separate pairs of duplicates."""
        content = """def foo():
    result = calculate(1)
    return result

def bar():
    result = calculate(1)
    return result

def baz():
    result = calculate(2)
    return result

def qux():
    result = calculate(2)
    return result
"""
        structure = {
            "functions": [
                {"name": "foo", "line": 1, "line_end": 3},
                {"name": "bar", "line": 5, "line_end": 7},
                {"name": "baz", "line": 9, "line_end": 11},
                {"name": "qux", "line": 13, "line_end": 15},
            ]
        }
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(len(result), 2)


class TestD001EdgeCases(unittest.TestCase):
    """Edge case tests for D001."""

    def setUp(self):
        self.rule = D001()

    def test_trivial_functions_ignored(self):
        """Very short functions (< 10 chars) should be ignored."""
        content = """def a():
    x

def b():
    x
"""
        structure = {
            "functions": [
                {"name": "a", "line": 1, "line_end": 2},
                {"name": "b", "line": 4, "line_end": 5},
            ]
        }
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(result, [])

    def test_detection_message_format(self):
        """Detection should have proper message format."""
        content = """def original():
    x = 1
    y = 2
    return x + y

def duplicate():
    x = 1
    y = 2
    return x + y
"""
        structure = {
            "functions": [
                {"name": "original", "line": 1, "line_end": 4},
                {"name": "duplicate", "line": 6, "line_end": 9},
            ]
        }
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(len(result), 1)
        detection = result[0]
        self.assertEqual(detection.rule_code, "D001")
        self.assertIn("duplicate", detection.message)
        self.assertIn("original", detection.message)
        self.assertIn("Refactor", detection.suggestion)

    def test_missing_function_name(self):
        """Functions without names should use <unknown>."""
        content = """def ():
    return 42

def ():
    return 42
"""
        structure = {
            "functions": [
                {"line": 1, "line_end": 2},  # No name
                {"line": 4, "line_end": 5},  # No name
            ]
        }
        result = self.rule.check("test.py", structure, content)
        if result:  # If detected
            self.assertIn("<unknown>", result[0].message)


class TestD001RuleMetadata(unittest.TestCase):
    """Tests for rule metadata."""

    def test_rule_code(self):
        """Rule should have correct code."""
        rule = D001()
        self.assertEqual(rule.code, "D001")

    def test_rule_message(self):
        """Rule should have a message."""
        rule = D001()
        self.assertIsNotNone(rule.message)

    def test_rule_version(self):
        """Rule should have a version."""
        rule = D001()
        self.assertEqual(rule.version, "1.0.0")


if __name__ == "__main__":
    unittest.main()
