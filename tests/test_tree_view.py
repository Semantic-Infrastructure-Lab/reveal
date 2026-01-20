"""Tests for directory tree view."""

import unittest
import tempfile
import os
import shutil
from reveal.tree_view import (
    show_directory_tree,
    _count_entries,
    _get_file_info,
    _walk_directory
)
from reveal.utils import format_size
from reveal.display.filtering import PathFilter
from pathlib import Path


class TestTreeView(unittest.TestCase):
    """Test directory tree view functionality."""

    def setUp(self):
        """Create a temp directory structure for testing."""
        self.temp_dir = tempfile.mkdtemp()

        # Create a directory structure:
        # temp_dir/
        #   file1.py (10 lines)
        #   file2.txt
        #   .hidden
        #   subdir1/
        #     nested.py
        #   subdir2/
        #     deep/
        #       deeper.py

        # Files in root
        with open(os.path.join(self.temp_dir, 'file1.py'), 'w') as f:
            f.write('\n'.join([f'line{i}' for i in range(10)]))

        with open(os.path.join(self.temp_dir, 'file2.txt'), 'w') as f:
            f.write('Hello world')

        with open(os.path.join(self.temp_dir, '.hidden'), 'w') as f:
            f.write('hidden file')

        # Subdirectories
        os.makedirs(os.path.join(self.temp_dir, 'subdir1'))
        with open(os.path.join(self.temp_dir, 'subdir1', 'nested.py'), 'w') as f:
            f.write('# nested file\n')

        os.makedirs(os.path.join(self.temp_dir, 'subdir2', 'deep'))
        with open(os.path.join(self.temp_dir, 'subdir2', 'deep', 'deeper.py'), 'w') as f:
            f.write('# deep file\n')

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir)

    def test_basic_tree(self):
        """Test basic tree output."""
        result = show_directory_tree(self.temp_dir)

        # Should contain directory name
        self.assertIn(os.path.basename(self.temp_dir), result)

        # Should contain files
        self.assertIn('file1.py', result)
        self.assertIn('file2.txt', result)

        # Should contain subdirs
        self.assertIn('subdir1', result)
        self.assertIn('subdir2', result)

    def test_hidden_files_excluded_by_default(self):
        """Test that hidden files are excluded by default."""
        result = show_directory_tree(self.temp_dir)

        self.assertNotIn('.hidden', result)

    def test_hidden_files_included_when_requested(self):
        """Test that hidden files can be shown."""
        result = show_directory_tree(self.temp_dir, show_hidden=True)

        self.assertIn('.hidden', result)

    def test_depth_limit(self):
        """Test depth limiting."""
        # With depth=1, should not show nested files
        result = show_directory_tree(self.temp_dir, depth=1)

        self.assertIn('subdir1', result)
        self.assertNotIn('nested.py', result)

        # With depth=2, should show first level nested
        result = show_directory_tree(self.temp_dir, depth=2)
        self.assertIn('nested.py', result)

    def test_deep_nesting(self):
        """Test that deep nesting respects depth."""
        # Default depth=3 should show deeper.py
        result = show_directory_tree(self.temp_dir, depth=3)
        self.assertIn('deeper.py', result)

        # Depth=2 should not
        result = show_directory_tree(self.temp_dir, depth=2)
        self.assertNotIn('deeper.py', result)

    def test_tree_characters(self):
        """Test tree formatting characters."""
        result = show_directory_tree(self.temp_dir)

        # Should use tree characters
        self.assertTrue('├──' in result or '└──' in result)

    def test_not_a_directory(self):
        """Test error for non-directory path."""
        file_path = os.path.join(self.temp_dir, 'file1.py')
        result = show_directory_tree(file_path)

        self.assertIn('Error', result)
        self.assertIn('not a directory', result)

    def test_usage_hint(self):
        """Test that usage hint is included."""
        result = show_directory_tree(self.temp_dir)

        self.assertIn('Usage:', result)

    def test_fast_mode(self):
        """Test fast mode skips line counting."""
        result_normal = show_directory_tree(self.temp_dir, fast=False)
        result_fast = show_directory_tree(self.temp_dir, fast=True)

        # Fast mode should show file sizes instead of line counts
        # Both should work without errors
        self.assertIn('file1.py', result_fast)

    def test_max_entries_limit(self):
        """Test max_entries limiting."""
        # Create many files
        many_dir = os.path.join(self.temp_dir, 'many')
        os.makedirs(many_dir)
        for i in range(50):
            with open(os.path.join(many_dir, f'file{i}.txt'), 'w') as f:
                f.write('x')

        result = show_directory_tree(many_dir, max_entries=10)

        # Should indicate truncation
        self.assertIn('more entries', result)

    def test_dir_limit_snips_per_directory(self):
        """Test dir_limit snips directories individually while continuing with siblings."""
        # Create structure with multiple directories
        dir1 = os.path.join(self.temp_dir, 'dir1')
        dir2 = os.path.join(self.temp_dir, 'dir2')
        os.makedirs(dir1)
        os.makedirs(dir2)

        # Put many files in dir1
        for i in range(20):
            with open(os.path.join(dir1, f'file{i:02d}.txt'), 'w') as f:
                f.write('x')

        # Put few files in dir2
        for i in range(3):
            with open(os.path.join(dir2, f'other{i}.txt'), 'w') as f:
                f.write('x')

        result = show_directory_tree(self.temp_dir, dir_limit=5, fast=True)

        # Should snip dir1 after 5 entries
        self.assertIn('[snipped', result)
        # dir2 should still be fully shown (has only 3 files)
        self.assertIn('dir2/', result)
        self.assertIn('other0.txt', result)
        self.assertIn('other1.txt', result)
        self.assertIn('other2.txt', result)


class TestCountEntries(unittest.TestCase):
    """Test entry counting helper."""

    def setUp(self):
        """Create a temp directory structure."""
        self.temp_dir = tempfile.mkdtemp()

        # Create structure
        with open(os.path.join(self.temp_dir, 'file1.txt'), 'w') as f:
            f.write('x')
        with open(os.path.join(self.temp_dir, '.hidden'), 'w') as f:
            f.write('x')

        os.makedirs(os.path.join(self.temp_dir, 'sub'))
        with open(os.path.join(self.temp_dir, 'sub', 'nested.txt'), 'w') as f:
            f.write('x')

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def test_count_entries(self):
        """Test entry counting."""
        path = Path(self.temp_dir)
        path_filter = PathFilter(root_path=path, respect_gitignore=False, include_defaults=False)
        count = _count_entries(path, depth=3, show_hidden=False, path_filter=path_filter)

        # file1.txt + sub/ + nested.txt = 3
        self.assertEqual(count, 3)

    def test_count_with_hidden(self):
        """Test counting includes hidden when requested."""
        path = Path(self.temp_dir)
        path_filter = PathFilter(root_path=path, respect_gitignore=False, include_defaults=False)
        count = _count_entries(path, depth=3, show_hidden=True, path_filter=path_filter)

        # file1.txt + .hidden + sub/ + nested.txt = 4
        self.assertEqual(count, 4)

    def test_count_depth_zero(self):
        """Test depth=0 returns 0."""
        path = Path(self.temp_dir)
        path_filter = PathFilter(root_path=path, respect_gitignore=False, include_defaults=False)
        count = _count_entries(path, depth=0, show_hidden=False, path_filter=path_filter)

        self.assertEqual(count, 0)


class TestFormatSize(unittest.TestCase):
    """Test file size formatting."""

    def test_bytes(self):
        """Test byte-range sizes."""
        self.assertEqual(format_size(0), '0.0 B')
        self.assertEqual(format_size(100), '100.0 B')
        self.assertEqual(format_size(1023), '1023.0 B')

    def test_kilobytes(self):
        """Test KB range sizes."""
        self.assertEqual(format_size(1024), '1.0 KB')
        self.assertEqual(format_size(2048), '2.0 KB')

    def test_megabytes(self):
        """Test MB range sizes."""
        self.assertEqual(format_size(1024 * 1024), '1.0 MB')
        self.assertEqual(format_size(5 * 1024 * 1024), '5.0 MB')

    def test_gigabytes(self):
        """Test GB range sizes."""
        self.assertEqual(format_size(1024 * 1024 * 1024), '1.0 GB')

    def test_terabytes(self):
        """Test TB range sizes."""
        result = format_size(1024 * 1024 * 1024 * 1024)
        self.assertIn('TB', result)


class TestGetFileInfo(unittest.TestCase):
    """Test file info extraction."""

    def setUp(self):
        """Create temp files for testing."""
        self.temp_dir = tempfile.mkdtemp()

        # Create a Python file
        self.py_file = os.path.join(self.temp_dir, 'test.py')
        with open(self.py_file, 'w') as f:
            f.write('# Test\ndef foo():\n    pass\n')

        # Create a text file
        self.txt_file = os.path.join(self.temp_dir, 'test.txt')
        with open(self.txt_file, 'w') as f:
            f.write('Hello world')

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def test_python_file_info(self):
        """Test info extraction for Python file."""
        result = _get_file_info(Path(self.py_file), fast=False)

        self.assertIn('test.py', result)
        # Should have line count
        self.assertIn('lines', result)

    def test_fast_mode_shows_size(self):
        """Test fast mode shows size instead of lines."""
        result = _get_file_info(Path(self.py_file), fast=True)

        self.assertIn('test.py', result)
        # Should have size unit
        self.assertTrue('B' in result or 'KB' in result)


class TestWalkDirectory(unittest.TestCase):
    """Test directory walking helper."""

    def setUp(self):
        """Create temp directory structure."""
        self.temp_dir = tempfile.mkdtemp()

        with open(os.path.join(self.temp_dir, 'a.txt'), 'w') as f:
            f.write('a')
        with open(os.path.join(self.temp_dir, 'b.txt'), 'w') as f:
            f.write('b')

        os.makedirs(os.path.join(self.temp_dir, 'dir1'))
        with open(os.path.join(self.temp_dir, 'dir1', 'c.txt'), 'w') as f:
            f.write('c')

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def test_walk_builds_lines(self):
        """Test that walking builds line list."""
        lines = []
        context = {'count': 0, 'max_entries': 100, 'truncated': 0}
        _walk_directory(Path(self.temp_dir), lines, depth=2, context=context)

        # Should have entries
        self.assertGreater(len(lines), 0)

    def test_walk_respects_max_entries(self):
        """Test that walking respects entry limit."""
        lines = []
        context = {'count': 0, 'max_entries': 2, 'truncated': 0}
        _walk_directory(Path(self.temp_dir), lines, depth=2, context=context)

        # Should have limited entries
        self.assertEqual(context['count'], 2)
        self.assertGreater(context['truncated'], 0)

    def test_directories_come_first(self):
        """Test that directories are sorted before files."""
        lines = []
        context = {'count': 0, 'max_entries': 100, 'truncated': 0}
        _walk_directory(Path(self.temp_dir), lines, depth=1, context=context)

        # Find positions
        dir_pos = None
        file_pos = None
        for i, line in enumerate(lines):
            if 'dir1/' in line and dir_pos is None:
                dir_pos = i
            if 'a.txt' in line and file_pos is None:
                file_pos = i

        # Directory should come before files
        if dir_pos is not None and file_pos is not None:
            self.assertLess(dir_pos, file_pos)


if __name__ == '__main__':
    unittest.main()
