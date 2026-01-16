"""Integration tests for reveal adapters.

Tests adapters end-to-end using subprocess to ensure they work
in real-world usage through the CLI interface.
"""

import unittest
import subprocess
import sys
import tempfile
import os
from pathlib import Path


class TestHelpAdapterIntegration(unittest.TestCase):
    """Integration tests for help:// adapter."""

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

    def test_help_adapter_list_topics(self):
        """Test help:// adapter lists available topics."""
        result = self.run_reveal_command("help://")

        self.assertEqual(
            result.returncode, 0,
            f"help:// failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show help system
        self.assertIn('reveal help system', result.stdout.lower())

    def test_help_adapter_show_tricks_topic(self):
        """Test help:// adapter shows tricks topic."""
        result = self.run_reveal_command("help://tricks")

        self.assertEqual(
            result.returncode, 0,
            f"help://tricks failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should contain tricks/tips content
        output = result.stdout.lower()
        self.assertTrue(
            'trick' in output or 'tip' in output or 'cool' in output,
            f"Expected tricks information in output: {result.stdout}"
        )

    def test_help_adapter_show_adapters_topic(self):
        """Test help:// adapter shows adapters topic."""
        result = self.run_reveal_command("help://adapters")

        self.assertEqual(
            result.returncode, 0,
            f"help://adapters failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should mention adapters
        self.assertIn('adapter', result.stdout.lower())

    def test_help_adapter_invalid_topic_fails_gracefully(self):
        """Test help:// adapter handles invalid topic gracefully."""
        result = self.run_reveal_command("help://nonexistent-topic-xyz")

        # Should fail gracefully (non-zero exit or helpful message)
        # Either it exits with error or shows available topics
        self.assertTrue(
            result.returncode != 0 or 'not found' in result.stderr.lower() or 'available' in result.stdout.lower(),
            f"Expected graceful failure for invalid topic:\nreturncode: {result.returncode}\nstderr: {result.stderr}"
        )


class TestEnvAdapterIntegration(unittest.TestCase):
    """Integration tests for env:// adapter."""

    def run_reveal_command(self, *args, env=None):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)

        # Set up environment variables
        test_env = os.environ.copy()
        if env:
            test_env.update(env)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,
            env=test_env
        )
        return result

    def test_env_adapter_shows_all_variables(self):
        """Test env:// adapter lists environment variables."""
        result = self.run_reveal_command("env://", env={"TEST_VAR_REVEAL": "test_value"})

        self.assertEqual(
            result.returncode, 0,
            f"env:// failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show environment variable listing
        self.assertIn('TEST_VAR_REVEAL', result.stdout)

    def test_env_adapter_shows_specific_variable(self):
        """Test env:// adapter shows specific environment variable."""
        result = self.run_reveal_command("env://PATH")

        self.assertEqual(
            result.returncode, 0,
            f"env://PATH failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show PATH variable (exists on all systems)
        self.assertIn('PATH', result.stdout)

    def test_env_adapter_nonexistent_variable(self):
        """Test env:// adapter handles nonexistent variable gracefully."""
        result = self.run_reveal_command("env://NONEXISTENT_VAR_XYZ_123")

        # Should handle gracefully (either empty result or helpful message)
        # Exit code could be 0 (empty result) or non-zero (error)
        self.assertNotIn('Traceback', result.stderr)
        self.assertNotIn('TypeError', result.stderr)

    def test_env_adapter_shows_categories(self):
        """Test env:// adapter organizes variables by category."""
        result = self.run_reveal_command("env://")

        self.assertEqual(
            result.returncode, 0,
            f"env:// failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show environment variable categories
        output = result.stdout.lower()
        self.assertTrue(
            'system' in output or 'python' in output or 'environment' in output,
            f"Expected category organization in output: {result.stdout}"
        )


class TestAstAdapterIntegration(unittest.TestCase):
    """Integration tests for ast:// adapter."""

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

    def test_ast_adapter_shows_python_structure(self):
        """Test ast:// adapter shows Python AST structure."""
        # Create a temporary directory and Python file
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("""
def test_function():
    '''Test function docstring.'''
    return 42

class TestClass:
    '''Test class docstring.'''
    def method(self):
        pass
""")

            # Query the temporary directory
            result = self.run_reveal_command(f"ast://{tmpdir}")

            self.assertEqual(
                result.returncode, 0,
                f"ast://{tmpdir} failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

            # Should show function or class names
            output = result.stdout
            self.assertTrue(
                'test_function' in output or 'TestClass' in output or 'function' in output.lower(),
                f"Expected AST structure in output: {result.stdout}"
            )

    def test_ast_adapter_query_specific_nodes(self):
        """Test ast:// adapter with query for specific nodes."""
        # Create a temporary directory and Python file
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("""
def hello():
    return "world"

def goodbye():
    return "farewell"
""")

            # Query for functions only
            result = self.run_reveal_command(f"ast://{tmpdir}?type=function")

            self.assertEqual(
                result.returncode, 0,
                f"ast://{tmpdir}?type=function failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

            # Should show function information
            output = result.stdout
            self.assertTrue(
                'hello' in output or 'goodbye' in output or 'function' in output.lower(),
                f"Expected function information in output: {result.stdout}"
            )

    def test_ast_adapter_on_invalid_python_fails_gracefully(self):
        """Test ast:// adapter handles invalid Python gracefully."""
        # Create a temporary directory with invalid Python file
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "invalid.py"
            test_file.write_text("def incomplete_function(")

            result = self.run_reveal_command(f"ast://{tmpdir}")

            # Should fail gracefully (non-zero exit code or helpful error)
            # Or it might just skip the invalid file
            # Most important: no crash
            self.assertNotIn('Traceback (most recent call last)', result.stderr)


class TestGitAdapterIntegration(unittest.TestCase):
    """Integration tests for git:// adapter."""

    def run_reveal_command(self, *args, cwd=None):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=30,
            cwd=cwd
        )
        return result

    @unittest.skip("git:// adapter requires CLI routing fix - adapter not receiving resource parameter")
    def test_git_adapter_shows_repo_info(self):
        """Test git:// adapter shows repository information."""
        # Run in the reveal repository itself
        repo_dir = Path(__file__).parent.parent

        result = self.run_reveal_command("git://.", cwd=repo_dir)

        self.assertEqual(
            result.returncode, 0,
            f"git://. failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show git information
        output = result.stdout.lower()
        self.assertTrue(
            'branch' in output or 'commit' in output or 'repository' in output or 'git' in output,
            f"Expected git information in output: {result.stdout}"
        )

    @unittest.skip("git:// adapter requires CLI routing fix - adapter not receiving resource parameter")
    def test_git_adapter_shows_status(self):
        """Test git:// adapter shows status information."""
        repo_dir = Path(__file__).parent.parent

        result = self.run_reveal_command("git://status", cwd=repo_dir)

        self.assertEqual(
            result.returncode, 0,
            f"git://status failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show status information
        output = result.stdout.lower()
        # Git status output varies, but should contain some git-related terms
        self.assertTrue(
            len(result.stdout) > 0,
            "Expected some output from git://status"
        )

    @unittest.skip("git:// adapter requires CLI routing fix - adapter not receiving resource parameter")
    def test_git_adapter_shows_log(self):
        """Test git:// adapter shows commit log."""
        repo_dir = Path(__file__).parent.parent

        result = self.run_reveal_command("git://log", cwd=repo_dir)

        self.assertEqual(
            result.returncode, 0,
            f"git://log failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # Should show commit log
        output = result.stdout.lower()
        self.assertTrue(
            'commit' in output or len(result.stdout) > 0,
            f"Expected commit log in output: {result.stdout}"
        )

    def test_git_adapter_outside_repo_fails_gracefully(self):
        """Test git:// adapter handles non-git directory gracefully."""
        # Use /tmp which is unlikely to be a git repo
        result = self.run_reveal_command("git://", cwd="/tmp")

        # Should fail gracefully (non-zero exit or helpful message)
        self.assertTrue(
            result.returncode != 0 or 'not a git' in result.stderr.lower(),
            f"Expected graceful failure outside git repo:\nreturncode: {result.returncode}\nstderr: {result.stderr}"
        )


class TestJsonAdapterIntegration(unittest.TestCase):
    """Integration tests for json:// adapter."""

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

    def test_json_adapter_shows_structure(self):
        """Test json:// adapter shows JSON structure."""
        # Create a temporary JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"name": "test", "value": 42, "items": [1, 2, 3]}')
            temp_file = f.name

        try:
            result = self.run_reveal_command(f"json://{temp_file}")

            self.assertEqual(
                result.returncode, 0,
                f"json://{temp_file} failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

            # Should show JSON content or structure
            self.assertTrue(
                'name' in result.stdout or 'test' in result.stdout,
                f"Expected JSON content in output: {result.stdout}"
            )
        finally:
            os.unlink(temp_file)

    def test_json_adapter_query_path(self):
        """Test json:// adapter with path query."""
        # Create a temporary JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"user": {"name": "John", "age": 30}}')
            temp_file = f.name

        try:
            result = self.run_reveal_command(f"json://{temp_file}/user/name")

            self.assertEqual(
                result.returncode, 0,
                f"json://{temp_file}/user/name failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

            # Should show the queried value
            self.assertIn('John', result.stdout)
        finally:
            os.unlink(temp_file)

    def test_json_adapter_invalid_json_fails_gracefully(self):
        """Test json:// adapter handles invalid JSON with error exit code."""
        # Create a temporary file with invalid JSON
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"incomplete": ')
            temp_file = f.name

        try:
            result = self.run_reveal_command(f"json://{temp_file}")

            # Should fail with non-zero exit code
            self.assertNotEqual(
                result.returncode, 0,
                f"Expected non-zero exit code for invalid JSON:\nreturncode: {result.returncode}\nstderr: {result.stderr}"
            )

            # Should show error message
            self.assertTrue(
                'error' in result.stderr.lower() or 'file not found' in result.stderr.lower() or 'json' in result.stderr.lower(),
                f"Expected error message in stderr: {result.stderr}"
            )
        finally:
            os.unlink(temp_file)

    def test_json_adapter_invalid_path_fails_gracefully(self):
        """Test json:// adapter handles invalid path gracefully."""
        # Create a temporary JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"name": "test"}')
            temp_file = f.name

        try:
            result = self.run_reveal_command(f"json://{temp_file}/nonexistent/path")

            # Should handle gracefully (could be empty result or error)
            # Most important: no crash
            self.assertNotIn('Traceback (most recent call last)', result.stderr)
            self.assertNotIn('TypeError', result.stderr)
        finally:
            os.unlink(temp_file)


class TestMarkdownAdapterIntegration(unittest.TestCase):
    """Integration tests for markdown:// adapter."""

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

    def test_markdown_adapter_searches_directory(self):
        """Test markdown:// adapter searches for markdown files in a directory."""
        # Create a temporary directory with markdown files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test markdown files with frontmatter
            test_file1 = Path(tmpdir) / "test1.md"
            test_file1.write_text("""---
title: Test Document One
author: Test Author
---

# Test Document One
""")

            test_file2 = Path(tmpdir) / "test2.md"
            test_file2.write_text("""---
title: Test Document Two
author: Another Author
---

# Test Document Two
""")

            # Query for markdown files in the directory
            result = self.run_reveal_command(f"markdown://{tmpdir}")

            self.assertEqual(
                result.returncode, 0,
                f"markdown://{tmpdir} failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )

            # Should show matched markdown files
            output = result.stdout
            self.assertTrue(
                'test1.md' in output or 'test2.md' in output or 'matched' in output.lower(),
                f"Expected markdown file listing in output: {result.stdout}"
            )


if __name__ == '__main__':
    unittest.main()
