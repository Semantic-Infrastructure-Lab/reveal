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


if __name__ == '__main__':
    unittest.main()
