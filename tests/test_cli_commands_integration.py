"""Integration tests for CLI commands.

Tests CLI commands end-to-end using subprocess to ensure they work
in real-world usage, not just when functions are called directly.
"""

import unittest
import subprocess
import sys
from pathlib import Path


class TestCLICommandsIntegration(unittest.TestCase):
    """Integration tests for reveal CLI commands."""

    def run_reveal_command(self, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30
        )
        return result

    def test_rules_command_works(self):
        """Test `reveal --rules` command doesn't crash.

        This is the specific bug we fixed: TypeError when file_patterns=None.
        """
        result = self.run_reveal_command("--rules")

        # Should exit successfully
        self.assertEqual(
            result.returncode, 0,
            f"reveal --rules failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show rule codes
        self.assertIn('B001', result.stdout)
        self.assertIn('I001', result.stdout)
        self.assertIn('Total:', result.stdout)

        # Should not have TypeError
        self.assertNotIn('TypeError', result.stderr)
        self.assertNotIn('can only join an iterable', result.stderr)

    def test_rules_command_shows_categories(self):
        """Test `reveal --rules` shows organized categories."""
        result = self.run_reveal_command("--rules")

        self.assertEqual(result.returncode, 0)

        # Should show category headers
        self.assertIn('B Rules', result.stdout)  # Bugs
        self.assertIn('I Rules', result.stdout)  # Imports
        self.assertIn('C Rules', result.stdout)  # Complexity

    def test_explain_rule_command_works(self):
        """Test `reveal --explain` command works."""
        result = self.run_reveal_command("--explain", "B001")

        self.assertEqual(
            result.returncode, 0,
            f"reveal --explain B001 failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should explain the rule
        self.assertIn('B001', result.stdout)

    def test_explain_nonexistent_rule_fails_gracefully(self):
        """Test `reveal --explain` with invalid code."""
        result = self.run_reveal_command("--explain", "X999")

        self.assertEqual(result.returncode, 1)
        # Error message goes to stderr
        self.assertIn('not found', result.stderr.lower())

    def test_languages_command_works(self):
        """Test `reveal --languages` command works."""
        result = self.run_reveal_command("--languages")

        self.assertEqual(
            result.returncode, 0,
            f"reveal --languages failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should list languages
        self.assertIn('python', result.stdout.lower())

    def test_list_schemas_command_works(self):
        """Test `reveal --list-schemas` command works."""
        result = self.run_reveal_command("--list-schemas")

        self.assertEqual(
            result.returncode, 0,
            f"reveal --list-schemas failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should list schemas
        self.assertIn('Built-in Schemas', result.stdout)

    def test_version_command_works(self):
        """Test `reveal --version` command works."""
        result = self.run_reveal_command("--version")

        self.assertEqual(
            result.returncode, 0,
            f"reveal --version failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show version number
        self.assertRegex(result.stdout, r'\d+\.\d+\.\d+')

    def test_help_command_works(self):
        """Test `reveal --help` command works."""
        result = self.run_reveal_command("--help")

        self.assertEqual(
            result.returncode, 0,
            f"reveal --help failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show usage information
        self.assertIn('usage:', result.stdout.lower())
        self.assertIn('reveal', result.stdout.lower())


class TestCLIWithFilesIntegration(unittest.TestCase):
    """Integration tests for reveal with actual files."""

    def run_reveal_on_file(self, file_path, *args):
        """Run reveal on a file and return result."""
        cmd = [sys.executable, "-m", "reveal.main", str(file_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30
        )
        return result

    def test_check_on_test_file_works(self):
        """Test `reveal <file> --check` works on test files."""
        # Use this test file itself
        test_file = Path(__file__)

        result = self.run_reveal_on_file(test_file, "--check")

        # Should exit successfully (even if it finds issues)
        self.assertIn(
            result.returncode, [0, 1],
            f"reveal --check failed with unexpected code {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should not crash with TypeError
        self.assertNotIn('TypeError', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_check_subcommand_exits_1_with_violations(self):
        """reveal check <file> must exit 1 when violations are found."""
        # This test file has known violations (duplicate imports inside test methods)
        test_file = Path(__file__)

        result = subprocess.run(
            [sys.executable, "-m", "reveal.main", "check", str(test_file)],
            capture_output=True, text=True, encoding='utf-8', timeout=30
        )

        self.assertEqual(
            result.returncode, 1,
            f"Expected exit 1 (violations found), got {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        self.assertNotIn('Traceback', result.stderr)

    def test_check_subcommand_exits_0_no_violations(self):
        """reveal check <file> must exit 0 when no violations are found."""
        import tempfile
        # Write a minimal clean Python file with no quality issues
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write('def add(a, b):\n    return a + b\n')
            clean_file = f.name

        try:
            result = subprocess.run(
                [sys.executable, "-m", "reveal.main", "check", clean_file],
                capture_output=True, text=True, encoding='utf-8', timeout=30
            )
            self.assertEqual(
                result.returncode, 0,
                f"Expected exit 0 (no violations), got {result.returncode}:\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        finally:
            import os
            os.unlink(clean_file)

    def test_stdin_check_exits_1_with_violations(self):
        """git diff --name-only | reveal --stdin --check must exit 1 when violations found."""
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            # Write a file with a known violation (duplicate import)
            f.write('import os\nimport os\n\ndef add(a, b):\n    return a + b\n')
            dirty_file = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "reveal.main", "--stdin", "--check"],
                input=dirty_file + '\n',
                capture_output=True, text=True, encoding='utf-8', timeout=30
            )
            self.assertEqual(
                result.returncode, 1,
                f"Expected exit 1 (violations found via stdin), got {result.returncode}:\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            self.assertNotIn('Traceback', result.stderr)
        finally:
            os.unlink(dirty_file)

    def test_stdin_check_exits_0_no_violations(self):
        """reveal --stdin --check must exit 0 when no violations found in any file."""
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
            f.write('def add(a, b):\n    return a + b\n')
            clean_file = f.name
        try:
            result = subprocess.run(
                [sys.executable, "-m", "reveal.main", "--stdin", "--check"],
                input=clean_file + '\n',
                capture_output=True, text=True, encoding='utf-8', timeout=30
            )
            self.assertEqual(
                result.returncode, 0,
                f"Expected exit 0 (no violations via stdin), got {result.returncode}:\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        finally:
            os.unlink(clean_file)

    def test_outline_on_test_file_works(self):
        """Test `reveal <file> --outline` works."""
        # Use this test file itself
        test_file = Path(__file__)

        result = self.run_reveal_on_file(test_file, "--outline")

        # Should exit successfully
        self.assertEqual(
            result.returncode, 0,
            f"reveal --outline failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show structure (test classes will be listed)
        self.assertIn('TestCLI', result.stdout)

    def test_outline_with_class_method_syntax(self):
        """reveal file.py ClassName.method_name --outline should work."""
        import tempfile
        import os
        code = (
            'class MyProcessor:\n'
            '    def run(self, items):\n'
            '        for item in items:\n'
            '            if item:\n'
            '                print(item)\n'
            '        return items\n'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        try:
            result = self.run_reveal_on_file(temp_file, 'MyProcessor.run', '--outline')
            self.assertEqual(
                result.returncode, 0,
                f'Class.method --outline failed:\nstdout: {result.stdout}\nstderr: {result.stderr}',
            )
            self.assertIn('run', result.stdout)
        finally:
            os.unlink(temp_file)

    def test_outline_with_class_method_not_found_shows_hint(self):
        """reveal file.py Class.bad_method --outline should show Class.method hint."""
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class Foo:\n    def bar(self): pass\n')
            temp_file = f.name
        try:
            result = self.run_reveal_on_file(temp_file, 'Foo.missing', '--outline')
            self.assertEqual(result.returncode, 1)
            self.assertIn('Class.method', result.stderr)
        finally:
            os.unlink(temp_file)

    def test_nav_dispatch_scope_with_line_ref(self):
        """reveal file.py :LINE --scope should print scope chain and exit 0."""
        import tempfile
        import os
        # Line 4 is inside `if` inside `for` — scope chain should show both blocks
        code = (
            'def process(items):\n'
            '    for item in items:\n'
            '        if item:\n'
            '            print(item)\n'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        try:
            result = self.run_reveal_on_file(temp_file, ':4', '--scope')
            self.assertEqual(
                result.returncode, 0,
                f'--scope with :LINE failed:\nstdout: {result.stdout}\nstderr: {result.stderr}',
            )
            self.assertIn('L4', result.stdout)
        finally:
            os.unlink(temp_file)

    def test_nav_dispatch_scope_without_element_exits_error(self):
        """reveal file.py --scope (no element) should exit 1 with a clear error."""
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def foo(): pass\n')
            temp_file = f.name
        try:
            result = self.run_reveal_on_file(temp_file, '--scope')
            self.assertEqual(result.returncode, 1)
            self.assertIn('--scope', result.stderr)
        finally:
            os.unlink(temp_file)

    def test_nav_dispatch_outline_with_element_is_control_flow(self):
        """reveal file.py myfunc --outline should produce nav control-flow output, not file-level tree."""
        import tempfile
        import os
        code = (
            'def process(items):\n'
            '    for item in items:\n'
            '        if item:\n'
            '            print(item)\n'
            '    return items\n'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            temp_file = f.name
        try:
            result = self.run_reveal_on_file(temp_file, 'process', '--outline')
            self.assertEqual(
                result.returncode, 0,
                f'element --outline failed:\nstdout: {result.stdout}\nstderr: {result.stderr}',
            )
            # Nav outline renders branch/loop keywords in uppercase, not just the function name
            self.assertIn('FOR', result.stdout)
            self.assertIn('IF', result.stdout)
        finally:
            os.unlink(temp_file)


class TestParseLineRange(unittest.TestCase):
    """Unit tests for _parse_line_range edge cases."""

    def setUp(self):
        from reveal.file_handler import _parse_line_range
        self.parse = _parse_line_range

    def test_valid_range(self):
        self.assertEqual(self.parse('10-20', 1, 100), (10, 20))

    def test_single_number_uses_default_end(self):
        self.assertEqual(self.parse('15', 1, 100), (15, 100))

    def test_negative_number_falls_back_to_defaults(self):
        # Negative numbers don't match \d+ regex → falls through to defaults
        self.assertEqual(self.parse('-5', 1, 100), (1, 100))

    def test_start_greater_than_end_returned_as_is(self):
        # _parse_line_range does not validate ordering — callers are responsible
        self.assertEqual(self.parse('50-10', 1, 100), (50, 10))

    def test_out_of_bounds_returned_as_is(self):
        # Values beyond function bounds are returned without clamping
        self.assertEqual(self.parse('1-9999', 10, 50), (1, 9999))

    def test_invalid_string_falls_back_to_defaults(self):
        self.assertEqual(self.parse('abc', 5, 20), (5, 20))

    def test_empty_string_falls_back_to_defaults(self):
        self.assertEqual(self.parse('', 5, 20), (5, 20))


if __name__ == '__main__':
    unittest.main()
