"""Tests for C905: Nesting depth too high rule."""

import unittest
from reveal.rules.complexity.C905 import C905
from reveal.rules.base import Severity


class TestC905Basic(unittest.TestCase):
    """Basic tests for C905 nesting depth detection."""

    def setUp(self):
        self.rule = C905()

    def test_no_structure_returns_empty(self):
        """No structure should return empty list."""
        result = self.rule.check("test.py", None, "")
        self.assertEqual(result, [])

    def test_no_functions_returns_empty(self):
        """Structure without functions returns empty."""
        result = self.rule.check("test.py", {"classes": []}, "content")
        self.assertEqual(result, [])

    def test_low_depth_no_detection(self):
        """Functions with low depth should not be flagged."""
        structure = {
            "functions": [
                {"name": "foo", "line": 1, "depth": 2},
                {"name": "bar", "line": 10, "depth": 3},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(result, [])

    def test_high_depth_detected(self):
        """Functions with depth > MAX_DEPTH should be flagged."""
        structure = {
            "functions": [
                {"name": "deeply_nested", "line": 5, "depth": 6},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].rule_code, "C905")
        self.assertIn("deeply_nested", result[0].message)
        self.assertIn("6", result[0].message)

    def test_exact_threshold_no_detection(self):
        """Functions at exactly MAX_DEPTH should not be flagged."""
        structure = {
            "functions": [
                {"name": "at_threshold", "line": 1, "depth": C905.MAX_DEPTH},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(result, [])

    def test_one_over_threshold_detected(self):
        """Functions one over MAX_DEPTH should be flagged."""
        structure = {
            "functions": [
                {"name": "over_threshold", "line": 1, "depth": C905.MAX_DEPTH + 1},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(len(result), 1)


class TestC905ZeroDepth(unittest.TestCase):
    """Tests for zero depth handling."""

    def setUp(self):
        self.rule = C905()

    def test_zero_depth_skipped(self):
        """Functions with depth 0 should be skipped."""
        structure = {
            "functions": [
                {"name": "no_depth", "line": 1, "depth": 0},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(result, [])

    def test_missing_depth_skipped(self):
        """Functions without depth field should be skipped."""
        structure = {
            "functions": [
                {"name": "no_depth_field", "line": 1},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(result, [])


class TestC905Multiple(unittest.TestCase):
    """Tests for multiple function handling."""

    def setUp(self):
        self.rule = C905()

    def test_multiple_deep_functions(self):
        """Multiple deep functions should all be detected."""
        structure = {
            "functions": [
                {"name": "deep1", "line": 1, "depth": 6},
                {"name": "deep2", "line": 20, "depth": 7},
                {"name": "deep3", "line": 40, "depth": 8},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(len(result), 3)

    def test_mixed_depths(self):
        """Should only flag functions over threshold."""
        structure = {
            "functions": [
                {"name": "shallow", "line": 1, "depth": 2},
                {"name": "medium", "line": 10, "depth": 4},
                {"name": "deep", "line": 20, "depth": 6},
                {"name": "very_deep", "line": 30, "depth": 10},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(len(result), 2)
        names = [d.context for d in result]
        self.assertTrue(any("deep" in n for n in names))
        self.assertTrue(any("very_deep" in n for n in names))


class TestC905Detection(unittest.TestCase):
    """Tests for detection details."""

    def setUp(self):
        self.rule = C905()

    def test_detection_has_suggestion(self):
        """Detection should have helpful suggestion."""
        structure = {
            "functions": [
                {"name": "nested_func", "line": 10, "depth": 7},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(len(result), 1)
        self.assertIn("early returns", result[0].suggestion)
        self.assertIn("helper functions", result[0].suggestion)

    def test_detection_has_context(self):
        """Detection should have context with function name."""
        structure = {
            "functions": [
                {"name": "complex_func", "line": 5, "depth": 8},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(len(result), 1)
        self.assertIn("complex_func", result[0].context)

    def test_detection_severity(self):
        """Detection should have MEDIUM severity."""
        structure = {
            "functions": [
                {"name": "func", "line": 1, "depth": 6},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(result[0].severity, Severity.MEDIUM)

    def test_detection_line_number(self):
        """Detection should report correct line number."""
        structure = {
            "functions": [
                {"name": "func", "line": 42, "depth": 6},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(result[0].line, 42)

    def test_unknown_function_name(self):
        """Functions without name should use <unknown>."""
        structure = {
            "functions": [
                {"line": 1, "depth": 6},
            ]
        }
        result = self.rule.check("test.py", structure, "content")
        self.assertEqual(len(result), 1)
        self.assertIn("<unknown>", result[0].message)


class TestC905RuleMetadata(unittest.TestCase):
    """Tests for rule metadata."""

    def test_rule_code(self):
        """Rule should have correct code."""
        rule = C905()
        self.assertEqual(rule.code, "C905")

    def test_max_depth_constant(self):
        """MAX_DEPTH should be reasonable."""
        rule = C905()
        self.assertEqual(rule.MAX_DEPTH, 4)

    def test_rule_version(self):
        """Rule should have a version."""
        rule = C905()
        self.assertEqual(rule.version, "1.0.0")


if __name__ == "__main__":
    unittest.main()
