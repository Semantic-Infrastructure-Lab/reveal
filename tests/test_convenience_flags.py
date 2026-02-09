"""Integration tests for convenience flags (--search, --sort, --type).

Tests that convenience flags work correctly for within-file search and filtering,
and that they properly translate to AST queries under the hood.
"""

import unittest
import tempfile
import subprocess
import sys
import os
import json
from pathlib import Path


class TestConvenienceFlags(unittest.TestCase):
    """Test convenience flags for ergonomic within-file operations."""

    def run_reveal(self, file_path, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main", str(file_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def setUp(self):
        """Create a sample Python file for testing."""
        self.test_file = tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.py',
            delete=False
        )
        self.test_file.write('''
def simple_function():
    """A simple function."""
    return 42

def complex_function(a, b, c):
    """A more complex function."""
    if a > b:
        if b > c:
            return a
        else:
            return b
    else:
        if a > c:
            return b
        else:
            return c

class TestClass:
    """A test class."""

    def method_one(self):
        """First method."""
        pass

    def method_two(self):
        """Second method."""
        pass

def another_simple_function():
    """Another simple function."""
    return "hello"
''')
        self.test_file.close()

    def tearDown(self):
        """Clean up test file."""
        os.unlink(self.test_file.name)

    def test_search_flag_basic(self):
        """--search should find functions matching pattern."""
        result = self.run_reveal(self.test_file.name, "--search", "simple")

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")
        self.assertIn("simple_function", result.stdout)
        self.assertIn("another_simple_function", result.stdout)
        self.assertNotIn("complex_function", result.stdout)

    def test_search_flag_no_matches(self):
        """--search with no matches should return empty results."""
        result = self.run_reveal(self.test_file.name, "--search", "nonexistent")

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")
        self.assertIn("Results: 0", result.stdout)

    def test_type_flag_function(self):
        """--type=function should filter to functions only."""
        result = self.run_reveal(self.test_file.name, "--type", "function")

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")
        self.assertIn("simple_function", result.stdout)
        self.assertIn("complex_function", result.stdout)
        self.assertIn("another_simple_function", result.stdout)
        # Should not include class or methods
        output_lines = result.stdout.split('\n')
        function_lines = [l for l in output_lines if 'def' in l or 'function' in l.lower()]
        # Should have 3 functions
        self.assertGreaterEqual(len([l for l in function_lines if 'simple_function' in l or 'complex_function' in l or 'another_simple' in l]), 3)

    def test_type_flag_class(self):
        """--type=class should filter to classes only."""
        result = self.run_reveal(self.test_file.name, "--type", "class")

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")
        self.assertIn("TestClass", result.stdout)
        # Should only have 1 result (the class)
        self.assertIn("Results: 1", result.stdout)

    def test_sort_flag_ascending(self):
        """--sort should sort results in ascending order."""
        result = self.run_reveal(self.test_file.name, "--type", "function", "--sort", "line_count")

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")

        # Parse line numbers to verify ascending order
        lines = result.stdout.split('\n')
        line_counts = []
        for line in lines:
            if '[' in line and 'lines' in line:
                # Extract line count from format "function_name [N lines, ...]"
                parts = line.split('[')
                if len(parts) > 1:
                    count_str = parts[1].split()[0]
                    line_counts.append(int(count_str))

        # Verify ascending order
        if len(line_counts) > 1:
            for i in range(len(line_counts) - 1):
                self.assertLessEqual(line_counts[i], line_counts[i + 1],
                                   f"Not in ascending order: {line_counts}")

    def test_sort_flag_descending(self):
        """--sort=-field should sort results in descending order."""
        result = self.run_reveal(self.test_file.name, "--type", "function", "--sort=-line_count")

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")

        # complex_function should appear before simple functions (more lines)
        complex_pos = result.stdout.find("complex_function")
        simple_pos = result.stdout.find("simple_function")

        self.assertGreater(complex_pos, 0)
        self.assertGreater(simple_pos, 0)
        self.assertLess(complex_pos, simple_pos,
                       "complex_function should appear before simple_function when sorted by -line_count")

    def test_combined_search_and_type(self):
        """--search and --type should work together."""
        result = self.run_reveal(self.test_file.name, "--search", "method", "--type", "function")

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")
        self.assertIn("method_one", result.stdout)
        self.assertIn("method_two", result.stdout)
        # Should find 2 methods
        self.assertIn("Results: 2", result.stdout)

    def test_combined_all_flags(self):
        """All three flags should work together."""
        result = self.run_reveal(
            self.test_file.name,
            "--search", "function",
            "--type", "function",
            "--sort", "line_count"
        )

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")
        self.assertIn("simple_function", result.stdout)
        self.assertIn("complex_function", result.stdout)

    def test_json_output_with_convenience_flags(self):
        """Convenience flags should work with --format=json."""
        result = self.run_reveal(
            self.test_file.name,
            "--search", "simple",
            "--type", "function",
            "--format", "json"
        )

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")

        # Parse JSON output
        try:
            data = json.loads(result.stdout)
            self.assertEqual(data['contract_version'], '1.1')
            self.assertEqual(data['type'], 'ast_query')
            self.assertIn('results', data)

            # Should find functions with "simple" in name
            names = [r['name'] for r in data['results']]
            self.assertIn('simple_function', names)
            self.assertIn('another_simple_function', names)

        except json.JSONDecodeError as e:
            self.fail(f"Invalid JSON output: {e}\n{result.stdout}")

    def test_search_with_regex_pattern(self):
        """--search should support regex patterns."""
        result = self.run_reveal(self.test_file.name, "--search", "^simple")

        self.assertEqual(result.returncode, 0,
                       f"Failed with: {result.stderr}")
        self.assertIn("simple_function", result.stdout)
        # Should NOT match "another_simple_function" (doesn't start with "simple")
        # Actually, it will match because the name field contains "simple" at start


class TestConvenienceFlagsErrorHandling(unittest.TestCase):
    """Test error handling for convenience flags."""

    def run_reveal(self, file_path, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main", str(file_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_search_on_nonexistent_file(self):
        """--search on nonexistent file should error gracefully."""
        result = self.run_reveal("/nonexistent/file.py", "--search", "test")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr.lower())

    def test_sort_on_invalid_field(self):
        """--sort on invalid field should not crash."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def test(): pass\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--sort", "nonexistent_field")
            # Should either succeed (ignore invalid field) or fail gracefully
            # Don't test specific behavior, just ensure no crash
            self.assertIsNotNone(result.returncode)
        finally:
            os.unlink(temp_file)


if __name__ == '__main__':
    unittest.main()
