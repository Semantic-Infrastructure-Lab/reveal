"""Integration tests for CLI flags across file types.

Tests that all CLI flags (--outline, --head, --tail) work with all file types
without causing TypeError. This prevents LSP violations where analyzers
don't accept the parameters that the CLI layer passes.
"""

import unittest
import tempfile
import subprocess
import sys
import os
from pathlib import Path


class TestCLIFlagsIntegration(unittest.TestCase):
    """Test CLI flags work with different file types."""

    def run_reveal(self, file_path, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main", str(file_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        return result

    def test_json_with_outline(self):
        """JSON files should accept --outline flag without error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"name": "test", "version": "1.0"}')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
            self.assertIn("name", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_yaml_with_outline(self):
        """YAML files should accept --outline flag without error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('name: test\nversion: 1.0\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
            self.assertIn("name", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_json_with_head(self):
        """JSON files should accept --head flag without error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"a": 1, "b": 2, "c": 3, "d": 4}')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--head", "2")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)

    def test_yaml_with_tail(self):
        """YAML files should accept --tail flag without error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write('a: 1\nb: 2\nc: 3\nd: 4\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--tail", "2")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)

    def test_toml_with_outline(self):
        """TOML files should accept --outline flag."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write('[database]\nhost = "localhost"\n[cache]\nenabled = true\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)

    def test_dockerfile_with_head(self):
        """Dockerfile should accept --head flag."""
        # Create Dockerfile with proper name (no extension)
        temp_dir = tempfile.mkdtemp()
        temp_file = Path(temp_dir) / 'Dockerfile'
        temp_file.write_text('FROM python:3.9\nRUN pip install requests\nCOPY . /app\n')

        try:
            result = self.run_reveal(temp_file, "--head", "2")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            temp_file.unlink()
            Path(temp_dir).rmdir()

    def test_python_with_outline(self):
        """Python files should work with --outline (baseline test)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class Foo:\n    def bar(self): pass\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
            self.assertIn("Foo", result.stdout)
        finally:
            os.unlink(temp_file)

    def test_markdown_with_outline(self):
        """Markdown files should work with --outline."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write('# Title\n## Section\n### Subsection\n')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)


class TestCLIFlagsCombinations(unittest.TestCase):
    """Test multiple flags combined."""

    def run_reveal(self, file_path, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main", str(file_path)] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        return result

    def test_json_outline_and_format(self):
        """Test multiple flags together."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"name": "test"}')
            temp_file = f.name

        try:
            result = self.run_reveal(temp_file, "--outline", "--format", "json")
            self.assertEqual(result.returncode, 0,
                           f"Failed with: {result.stderr}")
        finally:
            os.unlink(temp_file)


if __name__ == '__main__':
    unittest.main()
