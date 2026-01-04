"""Tests for reveal complexity rules (C902)."""

import unittest
import tempfile
import os
from reveal.rules.complexity.C902 import C902
from reveal.rules.base import Severity


class TestC902FunctionTooLong(unittest.TestCase):
    """Test C902: Function too long detector."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.rule = C902()

    def tearDown(self):
        """Clean up temp files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_temp_file(self, content: str, name: str = "test.py") -> str:
        """Helper: Create temp file with given content."""
        path = os.path.join(self.temp_dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    # ==================== Tests for function length thresholds ====================

    def test_short_function_ok(self):
        """Test that short functions (< 50 lines) are not flagged."""
        structure = {
            'functions': [
                {'name': 'short_func', 'line': 1, 'line_count': 30}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 0)

    def test_medium_function_warning(self):
        """Test that medium functions (51-100 lines) trigger MEDIUM severity."""
        structure = {
            'functions': [
                {'name': 'medium_func', 'line': 1, 'line_count': 75}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'C902')
        self.assertEqual(detections[0].severity, Severity.MEDIUM)
        self.assertIn('75 lines', detections[0].message)
        self.assertIn('medium_func', detections[0].message)
        self.assertIn('consider refactoring', detections[0].message.lower())

    def test_large_function_error(self):
        """Test that large functions (> 100 lines) trigger HIGH severity."""
        structure = {
            'functions': [
                {'name': 'god_function', 'line': 1, 'line_count': 250}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].rule_code, 'C902')
        self.assertEqual(detections[0].severity, Severity.HIGH)
        self.assertIn('250 lines', detections[0].message)
        self.assertIn('god_function', detections[0].message)
        self.assertIn('max: 100', detections[0].message)

    def test_exactly_at_warn_threshold(self):
        """Test edge case: exactly at warn threshold (51 lines)."""
        structure = {
            'functions': [
                {'name': 'func_at_threshold', 'line': 1, 'line_count': 51}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].severity, Severity.MEDIUM)

    def test_exactly_at_error_threshold(self):
        """Test edge case: exactly at error threshold (101 lines)."""
        structure = {
            'functions': [
                {'name': 'func_at_error', 'line': 1, 'line_count': 101}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].severity, Severity.HIGH)

    def test_just_below_warn_threshold(self):
        """Test edge case: just below warn threshold (50 lines)."""
        structure = {
            'functions': [
                {'name': 'func_below', 'line': 1, 'line_count': 50}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 0)

    def test_just_below_error_threshold(self):
        """Test edge case: just below error threshold (100 lines)."""
        structure = {
            'functions': [
                {'name': 'func_below_error', 'line': 1, 'line_count': 100}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].severity, Severity.MEDIUM)  # Still medium

    # ==================== Tests for multiple functions ====================

    def test_multiple_functions_mixed(self):
        """Test multiple functions with different lengths."""
        structure = {
            'functions': [
                {'name': 'short_func', 'line': 1, 'line_count': 20},
                {'name': 'medium_func', 'line': 25, 'line_count': 60},
                {'name': 'long_func', 'line': 90, 'line_count': 150},
                {'name': 'another_short', 'line': 250, 'line_count': 15},
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        # Should detect medium_func (MEDIUM) and long_func (HIGH)
        self.assertEqual(len(detections), 2)

        # Sort by line to ensure consistent order
        detections = sorted(detections, key=lambda d: d.line)

        # First detection: medium_func
        self.assertEqual(detections[0].line, 25)
        self.assertIn('medium_func', detections[0].message)
        self.assertEqual(detections[0].severity, Severity.MEDIUM)

        # Second detection: long_func
        self.assertEqual(detections[1].line, 90)
        self.assertIn('long_func', detections[1].message)
        self.assertEqual(detections[1].severity, Severity.HIGH)

    def test_all_short_functions(self):
        """Test file with all short functions."""
        structure = {
            'functions': [
                {'name': 'func1', 'line': 1, 'line_count': 10},
                {'name': 'func2', 'line': 15, 'line_count': 20},
                {'name': 'func3', 'line': 40, 'line_count': 30},
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 0)

    def test_all_long_functions(self):
        """Test file with all long functions."""
        structure = {
            'functions': [
                {'name': 'god_func_1', 'line': 1, 'line_count': 200},
                {'name': 'god_func_2', 'line': 210, 'line_count': 150},
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 2)
        # Both should be HIGH severity
        self.assertTrue(all(d.severity == Severity.HIGH for d in detections))

    # ==================== Tests for edge cases ====================

    def test_no_structure_provided(self):
        """Test that missing structure returns empty list."""
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, None, "# content")
        self.assertEqual(len(detections), 0)

    def test_empty_structure(self):
        """Test that empty structure returns empty list."""
        structure = {}
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 0)

    def test_no_functions_in_structure(self):
        """Test structure with no functions key."""
        structure = {'classes': [], 'imports': []}
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 0)

    def test_empty_functions_list(self):
        """Test structure with empty functions list."""
        structure = {'functions': []}
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 0)

    def test_function_with_zero_line_count(self):
        """Test function with line_count=0 is skipped."""
        structure = {
            'functions': [
                {'name': 'func_zero', 'line': 1, 'line_count': 0}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 0)

    def test_function_missing_line_count(self):
        """Test function without line_count key is skipped."""
        structure = {
            'functions': [
                {'name': 'func_no_count', 'line': 1}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 0)

    def test_function_missing_name(self):
        """Test function without name shows '<unknown>'."""
        structure = {
            'functions': [
                {'line': 1, 'line_count': 120}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        self.assertIn('<unknown>', detections[0].message)

    def test_function_missing_line(self):
        """Test function without line number defaults to 0."""
        structure = {
            'functions': [
                {'name': 'func_no_line', 'line_count': 120}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].line, 0)

    # ==================== Tests for messages and suggestions ====================

    def test_medium_suggestion_content(self):
        """Test that MEDIUM severity has appropriate suggestion."""
        structure = {
            'functions': [
                {'name': 'medium_func', 'line': 1, 'line_count': 75}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        suggestion = detections[0].suggestion
        self.assertIn('getting large', suggestion.lower())
        self.assertIn('refactoring', suggestion.lower())
        self.assertIn('100', suggestion)  # Mentions error threshold

    def test_high_suggestion_content(self):
        """Test that HIGH severity has appropriate suggestion."""
        structure = {
            'functions': [
                {'name': 'god_func', 'line': 1, 'line_count': 250}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        suggestion = detections[0].suggestion
        self.assertIn('break', suggestion.lower())
        self.assertIn('250-line', suggestion)
        self.assertIn('god function', suggestion.lower())
        self.assertIn('llm cost', suggestion.lower())
        self.assertIn('tokens', suggestion.lower())

    def test_llm_token_cost_estimate(self):
        """Test that HIGH severity includes LLM token cost estimate."""
        structure = {
            'functions': [
                {'name': 'huge_func', 'line': 1, 'line_count': 200}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        # Should estimate ~200 * 15 = 3000 tokens
        self.assertIn('3000 tokens', detections[0].suggestion)

    def test_context_includes_function_name_and_count(self):
        """Test that context field includes function name and line count."""
        structure = {
            'functions': [
                {'name': 'my_func', 'line': 1, 'line_count': 75}
            ]
        }
        path = self.create_temp_file("# content")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)
        context = detections[0].context
        self.assertIn('my_func', context)
        self.assertIn('75 lines', context)

    # ==================== Tests for rule metadata ====================

    def test_rule_code(self):
        """Test rule code is C902."""
        self.assertEqual(self.rule.code, 'C902')

    def test_rule_message(self):
        """Test rule message."""
        self.assertEqual(self.rule.message, 'Function is too long')

    def test_rule_category(self):
        """Test rule category is complexity."""
        self.assertEqual(self.rule.category.value, 'C')

    def test_rule_severity(self):
        """Test base rule severity is MEDIUM."""
        self.assertEqual(self.rule.severity, Severity.MEDIUM)

    def test_file_patterns_universal(self):
        """Test that C902 applies to all file types."""
        self.assertEqual(self.rule.file_patterns, ['*'])

    def test_thresholds_are_correct(self):
        """Test threshold constants."""
        self.assertEqual(self.rule.THRESHOLD_WARN, 50)
        self.assertEqual(self.rule.THRESHOLD_ERROR, 100)

    # ==================== Tests for various file types ====================

    def test_works_on_python_file(self):
        """Test C902 works on Python files."""
        structure = {
            'functions': [
                {'name': 'long_python_func', 'line': 1, 'line_count': 120}
            ]
        }
        path = self.create_temp_file("# Python content", "test.py")
        detections = self.rule.check(path, structure, "# content")
        self.assertEqual(len(detections), 1)

    def test_works_on_javascript_file(self):
        """Test C902 works on JavaScript files."""
        structure = {
            'functions': [
                {'name': 'longJsFunc', 'line': 1, 'line_count': 150}
            ]
        }
        path = self.create_temp_file("// JavaScript content", "test.js")
        detections = self.rule.check(path, structure, "// content")
        self.assertEqual(len(detections), 1)

    def test_works_on_any_structured_file(self):
        """Test C902 works on any file with structure."""
        structure = {
            'functions': [
                {'name': 'long_func', 'line': 1, 'line_count': 110}
            ]
        }
        path = self.create_temp_file("content", "test.xyz")
        detections = self.rule.check(path, structure, "content")
        self.assertEqual(len(detections), 1)


if __name__ == '__main__':
    unittest.main()
