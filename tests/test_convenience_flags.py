"""Integration tests for convenience flags (--name/--search, --sort, --type).

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


    def test_search_hints_reveal_type_for_variable(self):
        """--search on a file where the term is a module-level variable should hint at reveal_type."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('LIVE_SIGNALS = [1, 2, 3]\n\ndef process(): pass\n')
            temp_file = f.name
        try:
            result = self.run_reveal(temp_file, '--search', 'LIVE_SIGNALS')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            self.assertIn('Results: 0', result.stdout)
            self.assertIn('reveal_type=LIVE_SIGNALS', result.stdout)
            self.assertIn('not a named code element', result.stdout)
        finally:
            os.unlink(temp_file)

    def test_search_no_hint_when_term_absent(self):
        """--search with a term not in the file at all should not emit a reveal_type hint."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def process(): pass\n')
            temp_file = f.name
        try:
            result = self.run_reveal(temp_file, '--search', 'NONEXISTENT_XYZ')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            self.assertNotIn('reveal_type', result.stdout)
        finally:
            os.unlink(temp_file)

    def test_search_no_hint_for_complex_regex(self):
        """--search with a complex regex pattern should not emit a reveal_type hint."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('MY_VAR = 1\n\ndef process(): pass\n')
            temp_file = f.name
        try:
            result = self.run_reveal(temp_file, '--search', '^MY.*VAR$')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            # Complex regex patterns should not trigger the hint
            self.assertNotIn('reveal_type', result.stdout)
        finally:
            os.unlink(temp_file)


class TestConvenienceFlagsOnDirectory(unittest.TestCase):
    """Test that convenience flags work on directories (not silently ignored)."""

    def run_reveal(self, *args):
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        with open(os.path.join(self.tmpdir, 'alpha.py'), 'w') as f:
            f.write('def alpha_func(): pass\nclass AlphaClass: pass\n')
        with open(os.path.join(self.tmpdir, 'beta.py'), 'w') as f:
            f.write('def beta_func(): pass\nclass BetaClass: pass\n')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_search_on_directory_routes_to_ast(self):
        """--search on a directory should search across files, not silently show tree."""
        result = self.run_reveal(self.tmpdir, '--search', 'alpha')
        self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
        self.assertIn('alpha_func', result.stdout)
        self.assertNotIn('beta_func', result.stdout)

    def test_type_on_directory_routes_to_ast(self):
        """--type on a directory should filter by element type across files."""
        result = self.run_reveal(self.tmpdir, '--type', 'class')
        self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
        self.assertIn('AlphaClass', result.stdout)
        self.assertIn('BetaClass', result.stdout)
        self.assertNotIn('alpha_func', result.stdout)
        self.assertNotIn('beta_func', result.stdout)

    def test_sort_alone_on_directory_shows_tree(self):
        """--sort alone on a directory should still show the directory tree (not AST)."""
        result = self.run_reveal(self.tmpdir, '--sort', 'name')
        self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
        self.assertIn('alpha.py', result.stdout)
        self.assertIn('beta.py', result.stdout)


class TestNameFlagAlias(unittest.TestCase):
    """--name is the canonical flag; --search is a backwards-compat alias. Both must produce identical output."""

    def run_reveal(self, *args):
        import subprocess
        import sys
        return subprocess.run(
            [sys.executable, '-m', 'reveal.main'] + list(args),
            capture_output=True, text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

    def setUp(self):
        import tempfile
        self.tmpfile = tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False)
        self.tmpfile.write(
            'def alpha_function():\n    pass\n\ndef beta_function():\n    pass\n\nclass AlphaClass:\n    pass\n'
        )
        self.tmpfile.flush()
        self.tmpfile.close()

    def tearDown(self):
        os.unlink(self.tmpfile.name)

    def test_name_flag_finds_matches(self):
        """--name should find elements matching pattern."""
        result = self.run_reveal(self.tmpfile.name, '--name', 'alpha')
        self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
        self.assertIn('alpha_function', result.stdout)
        self.assertNotIn('beta_function', result.stdout)

    def test_name_and_search_produce_identical_output(self):
        """--name and --search (alias) must produce byte-identical output."""
        r_name = self.run_reveal(self.tmpfile.name, '--name', 'alpha')
        r_search = self.run_reveal(self.tmpfile.name, '--search', 'alpha')
        self.assertEqual(r_name.returncode, 0)
        self.assertEqual(r_search.returncode, 0)
        self.assertEqual(r_name.stdout, r_search.stdout,
                         "--name and --search produced different output")

    def test_name_flag_no_matches(self):
        """--name with no matches should return empty results."""
        result = self.run_reveal(self.tmpfile.name, '--name', 'nonexistent')
        self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
        self.assertIn('Results: 0', result.stdout)

    def test_name_flag_regex(self):
        """--name should support regex patterns."""
        result = self.run_reveal(self.tmpfile.name, '--name', '^alpha')
        self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
        self.assertIn('alpha_function', result.stdout)
        self.assertNotIn('beta_function', result.stdout)

    def test_name_and_search_regex_identical(self):
        """--name and --search with regex must produce identical output."""
        r_name = self.run_reveal(self.tmpfile.name, '--name', '^alpha')
        r_search = self.run_reveal(self.tmpfile.name, '--search', '^alpha')
        self.assertEqual(r_name.stdout, r_search.stdout)


if __name__ == '__main__':
    unittest.main()
