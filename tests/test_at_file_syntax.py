"""Tests for @file syntax feature (Issue #17).

Tests reading URIs/paths from a file using @filename syntax:
    reveal @domains.txt --check
"""

import unittest
import tempfile
import subprocess
import sys
import os
from pathlib import Path


class TestAtFileSyntax(unittest.TestCase):
    """Test @file syntax for reading URIs from files."""

    def run_reveal(self, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_at_file_with_paths(self):
        """@file should process file paths from file."""
        # Create temp files to analyze
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    pass\n')
            py_file = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"name": "test"}')
            json_file = f.name

        # Create file list
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f'{py_file}\n{json_file}\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            # Should process both files
            self.assertIn('hello', result.stdout)
            self.assertIn('name', result.stdout)
        finally:
            os.unlink(py_file)
            os.unlink(json_file)
            os.unlink(list_file)

    def test_at_file_with_comments(self):
        """@file should skip comment lines (starting with #)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    pass\n')
            py_file = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f'# This is a comment\n{py_file}\n# Another comment\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            self.assertIn('hello', result.stdout)
        finally:
            os.unlink(py_file)
            os.unlink(list_file)

    def test_at_file_with_blank_lines(self):
        """@file should skip blank lines."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    pass\n')
            py_file = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f'\n\n{py_file}\n\n\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            self.assertIn('hello', result.stdout)
        finally:
            os.unlink(py_file)
            os.unlink(list_file)

    def test_at_file_not_found(self):
        """@file should error on missing file."""
        result = self.run_reveal('@/nonexistent/file.txt')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('File not found', result.stderr)

    def test_at_file_empty(self):
        """@file should error on empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('')  # Empty file
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No URIs found', result.stderr)
        finally:
            os.unlink(list_file)

    def test_at_file_with_only_comments(self):
        """@file with only comments should error."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('# Comment 1\n# Comment 2\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('No URIs found', result.stderr)
        finally:
            os.unlink(list_file)

    def test_at_file_with_missing_path(self):
        """@file should warn on missing files in list and continue."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    pass\n')
            py_file = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f'/nonexistent/file.py\n{py_file}\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}')
            # Should succeed (exits 0) despite missing file
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            # Should warn about missing file
            self.assertIn('not found', result.stderr)
            # Should process the valid file
            self.assertIn('hello', result.stdout)
        finally:
            os.unlink(py_file)
            os.unlink(list_file)

    def test_at_file_with_uris(self):
        """@file should handle URI syntax (env://)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('env://PATH\nenv://HOME\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            # Should show env var info
            # PATH or HOME should be in output (actual values)
        finally:
            os.unlink(list_file)

    def test_at_file_directory_warning(self):
        """@file should warn on directory paths and skip them."""
        temp_dir = tempfile.mkdtemp()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    pass\n')
            py_file = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f'{temp_dir}\n{py_file}\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            # Should warn about directory
            self.assertIn('directory', result.stderr)
            # Should process the file
            self.assertIn('hello', result.stdout)
        finally:
            os.unlink(py_file)
            os.unlink(list_file)
            os.rmdir(temp_dir)


class TestAtFileWithFlags(unittest.TestCase):
    """Test @file syntax combined with CLI flags."""

    def run_reveal(self, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        return result

    def test_at_file_with_json_format(self):
        """@file should work with --format=json."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def hello():\n    pass\n')
            py_file = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f'{py_file}\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}', '--format=json')
            self.assertEqual(result.returncode, 0, f"Failed with: {result.stderr}")
            # Output should be valid JSON structure
            import json
            # May have multiple JSON objects for multiple files
            self.assertIn('"hello"', result.stdout)
        finally:
            os.unlink(py_file)
            os.unlink(list_file)


if __name__ == '__main__':
    unittest.main()
