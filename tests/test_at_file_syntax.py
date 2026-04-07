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

    def test_at_file_check_exits_1_with_violations(self):
        """@file --check must exit 1 when any listed file has violations."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('import os\nimport os\n\ndef add(a, b):\n    return a + b\n')
            dirty_file = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f'{dirty_file}\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}', '--check')
            self.assertEqual(
                result.returncode, 1,
                f"Expected exit 1 (violations found), got {result.returncode}:\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
            self.assertNotIn('Traceback', result.stderr)
        finally:
            os.unlink(dirty_file)
            os.unlink(list_file)

    def test_at_file_check_exits_0_no_violations(self):
        """@file --check must exit 0 when no listed file has violations."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('def add(a, b):\n    return a + b\n')
            clean_file = f.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(f'{clean_file}\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}', '--check')
            self.assertEqual(
                result.returncode, 0,
                f"Expected exit 0 (no violations), got {result.returncode}:\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        finally:
            os.unlink(clean_file)
            os.unlink(list_file)

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


class TestAtFileBatchEquivalence(unittest.TestCase):
    """Tests for BACK-062: @file --batch produces same aggregated output as --stdin --batch."""

    def run_reveal(self, *args):
        """Run reveal command and return result."""
        cmd = [sys.executable, "-m", "reveal.main"] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        return result

    def test_at_file_batch_shows_batch_results_header(self):
        """@file --batch should produce BATCH CHECK RESULTS header."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('env://PATH\nenv://HOME\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}', '--batch')
            # Batch header must appear regardless of individual URI exit code
            self.assertIn('BATCH CHECK RESULTS', result.stdout)
        finally:
            os.unlink(list_file)

    def test_at_file_batch_aggregates_counts(self):
        """@file --batch should show Total URIs count across all items in file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('env://PATH\nenv://HOME\nenv://USER\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}', '--batch')
            # Batch header must appear regardless of individual URI success/failure
            self.assertIn('BATCH CHECK RESULTS', result.stdout)
            self.assertIn('Total URIs: 3', result.stdout)
        finally:
            os.unlink(list_file)

    def test_at_file_batch_summary_flag_works(self):
        """@file --batch --summary should show aggregated summary."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('env://PATH\nenv://HOME\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}', '--batch', '--summary')
            # Summary flag must produce BATCH CHECK RESULTS regardless of URI exit codes
            self.assertIn('BATCH CHECK RESULTS', result.stdout)
        finally:
            os.unlink(list_file)

    def test_at_file_batch_summary_suppresses_per_uri_lines(self):
        """BACK-060: --batch --summary must NOT emit one line per URI (header only)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('env://PATH\nenv://HOME\nenv://USER\nenv://SHELL\nenv://TERM\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}', '--batch', '--summary')
            self.assertIn('BATCH CHECK RESULTS', result.stdout)
            self.assertIn('Total URIs: 5', result.stdout)
            # Per-URI lines look like "✓ env://PATH: SUCCESS" — should be absent
            self.assertNotIn('env://PATH: ', result.stdout)
            self.assertNotIn('env://HOME: ', result.stdout)
        finally:
            os.unlink(list_file)

    def test_at_file_batch_without_summary_shows_per_uri_lines(self):
        """Without --summary, each URI gets its own output line."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write('env://PATH\nenv://HOME\n')
            list_file = f.name

        try:
            result = self.run_reveal(f'@{list_file}', '--batch')
            self.assertIn('BATCH CHECK RESULTS', result.stdout)
            # Per-URI lines must appear when --summary is NOT used
            self.assertIn('env://', result.stdout)
        finally:
            os.unlink(list_file)


class TestRenderBatchTextOutput:
    """BACK-060: _render_batch_text_output summary_only parameter unit tests."""

    def _make_results(self, n: int) -> list:
        return [
            {'uri': f'env://VAR{i}', 'scheme': 'env', 'status': 'success'}
            for i in range(n)
        ]

    def test_summary_only_suppresses_uri_lines(self, capsys):
        from reveal.cli.handlers import _render_batch_text_output
        results = self._make_results(5)
        by_scheme = {'env': results}
        stats = {'total': 5, 'successful': 5, 'warnings': 0, 'failures': 0}
        _render_batch_text_output(stats, 'pass', by_scheme, results, summary_only=True)
        out = capsys.readouterr().out
        assert 'BATCH CHECK RESULTS' in out
        assert 'Total URIs: 5' in out
        assert 'env://VAR0' not in out

    def test_summary_only_false_shows_uri_lines(self, capsys):
        from reveal.cli.handlers import _render_batch_text_output
        results = self._make_results(3)
        by_scheme = {'env': results}
        stats = {'total': 3, 'successful': 3, 'warnings': 0, 'failures': 0}
        _render_batch_text_output(stats, 'pass', by_scheme, results, summary_only=False)
        out = capsys.readouterr().out
        assert 'BATCH CHECK RESULTS' in out
        assert 'env://VAR0' in out

    def test_summary_only_json_drops_results_key(self, capsys):
        import json
        import sys
        from argparse import Namespace
        from unittest.mock import patch
        from reveal.cli.handlers import _render_batch_results
        results = [
            {'uri': f'env://VAR{i}', 'scheme': 'env', 'status': 'success', 'data': {}}
            for i in range(10)
        ]
        args = Namespace(format='json', summary=True, only_failures=False)
        with patch('sys.exit'):
            _render_batch_results(results, args)
        out = capsys.readouterr().out
        data = json.loads(out)
        assert 'results' not in data
        assert data['total'] == 10


if __name__ == '__main__':
    unittest.main()
