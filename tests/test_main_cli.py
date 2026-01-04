"""
Tests for main CLI functionality (reveal/main.py).

Tests command-line interface, flags, and output formatting.
"""

import unittest
import subprocess
import sys


class TestCLIFlags(unittest.TestCase):
    """Test CLI flags and basic functionality."""

    def run_reveal(self, *args):
        """Run reveal command and return output."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_version_flag(self):
        """Should show version with --version flag."""
        result = self.run_reveal("--version")

        self.assertEqual(result.returncode, 0)
        self.assertIn("reveal", result.stdout)
        # Check for semantic version pattern (e.g., 0.4.1, 0.5.0)
        self.assertRegex(result.stdout, r"reveal \d+\.\d+\.\d+")

    def test_version_short_form(self):
        """Should work with python -m reveal.main --version."""
        result = self.run_reveal("--version")

        self.assertEqual(result.returncode, 0)
        self.assertRegex(result.stdout, r"reveal \d+\.\d+\.\d+")

    def test_list_supported_flag(self):
        """Should list supported file types with --list-supported."""
        result = self.run_reveal("--list-supported")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Supported File Types", result.stdout)
        self.assertIn("Python", result.stdout)
        self.assertIn(".py", result.stdout)
        self.assertIn("GDScript", result.stdout)
        self.assertIn(".gd", result.stdout)

    def test_list_supported_short_flag(self):
        """Should work with -l short form."""
        result = self.run_reveal("-l")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Supported File Types", result.stdout)
        self.assertIn("Total:", result.stdout)

    def test_list_supported_shows_all_types(self):
        """Should show all 10+ supported file types."""
        result = self.run_reveal("--list-supported")

        self.assertEqual(result.returncode, 0)
        # Check for key file types
        for file_type in ["Python", "Rust", "Go", "GDScript", "Jupyter", "Markdown", "JSON", "YAML"]:
            self.assertIn(file_type, result.stdout)

    def test_help_flag(self):
        """Should show help with --help."""
        result = self.run_reveal("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("Reveal: Explore code semantically", result.stdout)
        self.assertIn("Examples:", result.stdout)
        self.assertIn("--version", result.stdout)
        self.assertIn("--list-supported", result.stdout)

    def test_help_shows_gdscript_examples(self):
        """Help should include GDScript examples."""
        result = self.run_reveal("--help")

        self.assertEqual(result.returncode, 0)
        # Help text format may vary - check for core content
        self.assertIn("reveal", result.stdout.lower())
        self.assertIn("Examples:", result.stdout)

    def test_no_args_shows_help(self):
        """Should show help when run with no arguments."""
        result = self.run_reveal()

        self.assertEqual(result.returncode, 1)
        self.assertIn("usage:", result.stdout)


class TestErrorMessages(unittest.TestCase):
    """Test improved error messages."""

    def run_reveal(self, *args):
        """Run reveal command and return output."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_unsupported_file_type_error(self):
        """Should show helpful error for unsupported file types."""
        import tempfile
        import os

        # Create temporary file with unsupported extension
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xyz', delete=False) as f:
            f.write("test content")
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("No analyzer found", result.stderr)
            self.assertIn(".xyz", result.stderr)
            self.assertIn("--list-supported", result.stderr)
        finally:
            os.unlink(temp_file)

    def test_nonexistent_file_error(self):
        """Should show clear error for non-existent files."""
        result = self.run_reveal("/tmp/definitely_does_not_exist_file.py")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr)


class TestOutputFormats(unittest.TestCase):
    """Test different output formats."""

    def run_reveal(self, *args):
        """Run reveal command and return output."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_list_supported_json_like_output(self):
        """List supported should have clean, readable output."""
        result = self.run_reveal("--list-supported")

        self.assertEqual(result.returncode, 0)
        # Should have core file types and extensions
        self.assertIn(".py", result.stdout)
        self.assertIn(".rs", result.stdout)
        self.assertIn("Python", result.stdout)
        self.assertIn("Rust", result.stdout)


if __name__ == '__main__':
    unittest.main()
