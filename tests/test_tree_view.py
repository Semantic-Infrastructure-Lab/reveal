"""Tests for directory tree view."""

import unittest
import tempfile
import os
import shutil
import pytest

from reveal.tree_view import (
    show_directory_tree,
    show_directory_tree_json,
    show_file_list,
    show_file_list_json,
    _count_entries,
    _count_entries_with_suppressed,
    _format_suppressed_footer,
    _get_file_info,
    _walk_directory
)
from reveal.utils import format_size
from reveal.display.filtering import PathFilter
from pathlib import Path

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


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

    def test_dir_limit_truncation_hints_dir_limit_flag(self):
        """BACK-864: when dir_limit (not max_entries) causes truncation, the
        final hint must mention --dir-limit 0 — --max-entries 0 alone won't
        expand a directory still capped by dir_limit."""
        many_dir = os.path.join(self.temp_dir, 'many')
        os.makedirs(many_dir)
        for i in range(80):
            with open(os.path.join(many_dir, f'file{i:03d}.txt'), 'w') as f:
                f.write('x')

        # max_entries left high so dir_limit (default 50) is the only thing that fires
        result = show_directory_tree(many_dir, fast=True, dir_limit=50, max_entries=1000)

        self.assertIn('--dir-limit 0', result)
        self.assertNotIn('--max-entries 0', result)

    def test_max_entries_truncation_hints_max_entries_flag(self):
        """When only max_entries causes truncation, the hint should mention
        --max-entries 0 and not a spurious --dir-limit 0."""
        many_dir = os.path.join(self.temp_dir, 'many')
        os.makedirs(many_dir)
        for i in range(80):
            with open(os.path.join(many_dir, f'file{i:03d}.txt'), 'w') as f:
                f.write('x')

        result = show_directory_tree(many_dir, fast=True, dir_limit=0, max_entries=10)

        self.assertIn('--max-entries 0', result)
        self.assertNotIn('--dir-limit 0', result)


class TestDirectoryTreeJson(unittest.TestCase):
    """BACK-975: --format json was silently ignored on a plain directory
    listing, always returning ASCII tree text. show_directory_tree_json /
    show_file_list_json are the JSON counterparts wired up to fix that."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        with open(os.path.join(self.temp_dir, 'file1.py'), 'w') as f:
            f.write('\n'.join([f'line{i}' for i in range(10)]))
        with open(os.path.join(self.temp_dir, '.hidden'), 'w') as f:
            f.write('hidden file')
        os.makedirs(os.path.join(self.temp_dir, 'subdir1'))
        with open(os.path.join(self.temp_dir, 'subdir1', 'nested.py'), 'w') as f:
            f.write('# nested file\n')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_returns_dict_not_string(self):
        result = show_directory_tree_json(self.temp_dir)
        self.assertIsInstance(result, dict)

    def test_json_serializable(self):
        import json
        result = show_directory_tree_json(self.temp_dir)
        json.dumps(result)  # must not raise

    def test_contains_files_and_dirs(self):
        result = show_directory_tree_json(self.temp_dir)
        names = {e['name']: e for e in result['entries']}
        self.assertIn('file1.py', names)
        self.assertEqual(names['file1.py']['type'], 'file')
        self.assertIn('subdir1', names)
        self.assertEqual(names['subdir1']['type'], 'dir')
        child_names = {c['name'] for c in names['subdir1']['children']}
        self.assertIn('nested.py', child_names)

    def test_hidden_files_excluded_by_default(self):
        result = show_directory_tree_json(self.temp_dir)
        names = {e['name'] for e in result['entries']}
        self.assertNotIn('.hidden', names)

    def test_hidden_files_included_when_requested(self):
        result = show_directory_tree_json(self.temp_dir, show_hidden=True)
        names = {e['name'] for e in result['entries']}
        self.assertIn('.hidden', names)

    def test_not_a_directory_returns_error_dict(self):
        file_path = os.path.join(self.temp_dir, 'file1.py')
        result = show_directory_tree_json(file_path)
        self.assertIn('error', result)

    def test_file_list_json_returns_dict(self):
        result = show_file_list_json(self.temp_dir)
        self.assertIsInstance(result, dict)
        paths = {e['path'] for e in result['entries']}
        self.assertIn('file1.py', paths)
        self.assertIn(str(Path('subdir1') / 'nested.py'), paths)

    def test_file_list_json_serializable(self):
        import json
        result = show_file_list_json(self.temp_dir)
        json.dumps(result)  # must not raise


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


class TestSuppressedEntriesFooter(unittest.TestCase):
    """BACK-1224: directory tree must not silently hide gitignored entries."""

    def setUp(self):
        """Create a repo-like temp directory: a .gitignore hiding a whole source tree,
        isolated from any default-noise-pattern name (__pycache__ etc.) so gitignore-only
        assertions don't have to account for noise filtering too."""
        self.temp_dir = tempfile.mkdtemp()

        with open(os.path.join(self.temp_dir, '.gitignore'), 'w') as f:
            f.write('vendored/\n')
        with open(os.path.join(self.temp_dir, 'README.md'), 'w') as f:
            f.write('x')

        os.makedirs(os.path.join(self.temp_dir, 'vendored'))
        with open(os.path.join(self.temp_dir, 'vendored', 'lib.py'), 'w') as f:
            f.write('x')

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_count_with_suppressed_tallies_gitignore(self):
        """A gitignored directory is counted as one suppressed entry, by cause."""
        path = Path(self.temp_dir)
        path_filter = PathFilter(root_path=path, respect_gitignore=True, include_defaults=False)
        count, suppressed = _count_entries_with_suppressed(
            path, depth=3, show_hidden=False, path_filter=path_filter)

        # README.md kept; .gitignore is dotfile-hidden by default
        self.assertEqual(count, 1)
        self.assertEqual(suppressed['gitignore'], 1)  # vendored/

    def test_count_with_suppressed_tallies_noise(self):
        """Default noise patterns (e.g. __pycache__) are tallied separately from gitignore."""
        noise_dir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(noise_dir, '__pycache__'))
            with open(os.path.join(noise_dir, '__pycache__', 'x.pyc'), 'w') as f:
                f.write('x')
            with open(os.path.join(noise_dir, '.gitignore'), 'w') as f:
                f.write('vendored/\n')
            os.makedirs(os.path.join(noise_dir, 'vendored'))

            path = Path(noise_dir)
            path_filter = PathFilter(root_path=path, respect_gitignore=True, include_defaults=True)
            _, suppressed = _count_entries_with_suppressed(
                path, depth=3, show_hidden=False, path_filter=path_filter)

            self.assertEqual(suppressed['gitignore'], 1)   # vendored/
            self.assertEqual(suppressed['noise'], 1)        # __pycache__/
        finally:
            shutil.rmtree(noise_dir)

    def test_suppressed_directory_not_recursed_into(self):
        """A suppressed dir counts as 1 entry, not 1 + its contents (cheap by design)."""
        path = Path(self.temp_dir)
        path_filter = PathFilter(root_path=path, respect_gitignore=True, include_defaults=False)
        _, suppressed = _count_entries_with_suppressed(
            path, depth=3, show_hidden=False, path_filter=path_filter)

        # vendored/lib.py must not add a second gitignore tally
        self.assertEqual(suppressed['gitignore'], 1)

    def test_show_directory_tree_reports_gitignore_footer(self):
        """The rendered tree names the hidden count and how to reveal it."""
        output = show_directory_tree(self.temp_dir, depth=3, respect_gitignore=True)

        self.assertIn('entries hidden by .gitignore', output)
        self.assertIn('--no-gitignore', output)

    def test_show_directory_tree_no_footer_when_nothing_suppressed(self):
        """A plain directory with nothing gitignored/noise/excluded reports no footer."""
        clean_dir = tempfile.mkdtemp()
        try:
            with open(os.path.join(clean_dir, 'plain.txt'), 'w') as f:
                f.write('x')
            output = show_directory_tree(clean_dir, depth=3)
            self.assertNotIn('entries hidden', output)
        finally:
            shutil.rmtree(clean_dir)

    def test_show_directory_tree_json_includes_suppressed_count(self):
        """MCP/agent JSON consumers get the same attribution as the text footer."""
        result = show_directory_tree_json(self.temp_dir, depth=3, respect_gitignore=True)

        self.assertIn('suppressed_count', result)
        self.assertEqual(result['suppressed_count']['gitignore'], 1)
        self.assertGreaterEqual(result['suppressed_count']['total'], 1)

    def test_format_suppressed_footer_single_cause(self):
        from collections import Counter
        footer = _format_suppressed_footer(Counter({'gitignore': 4}))
        self.assertEqual(footer, '... 4 entries hidden by .gitignore (use --no-gitignore to show)')

    def test_format_suppressed_footer_multi_cause(self):
        from collections import Counter
        footer = _format_suppressed_footer(Counter({'gitignore': 4, 'exclude': 2}))
        self.assertTrue(footer.startswith('... 6 entries hidden ('))
        self.assertIn('4 by .gitignore (use --no-gitignore to show)', footer)
        self.assertIn('2 by --exclude', footer)

    def test_format_suppressed_footer_empty(self):
        from collections import Counter
        self.assertIsNone(_format_suppressed_footer(Counter()))


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


class TestSortAliases(unittest.TestCase):
    """Test that 'modified' is accepted as an alias for 'mtime' in sort_by."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Create files with distinct mtimes
        self.older = os.path.join(self.temp_dir, 'older.txt')
        self.newer = os.path.join(self.temp_dir, 'newer.txt')
        with open(self.older, 'w') as f:
            f.write('old')
        with open(self.newer, 'w') as f:
            f.write('new')
        # Ensure distinct mtimes
        os.utime(self.older, (1000000, 1000000))
        os.utime(self.newer, (2000000, 2000000))

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_show_file_list_sort_modified_alias(self):
        """'modified' should sort by mtime, same as 'mtime'."""
        result_mtime = show_file_list(self.temp_dir, sort_by='mtime', sort_desc=True)
        result_modified = show_file_list(self.temp_dir, sort_by='modified', sort_desc=True)
        self.assertEqual(result_mtime, result_modified)

    def test_show_file_list_sort_modified_newest_first(self):
        """sort_by='modified' desc puts newest file first."""
        result = show_file_list(self.temp_dir, sort_by='modified', sort_desc=True)
        lines = [l for l in result.strip().splitlines() if l]
        self.assertIn('newer.txt', lines[0])
        self.assertIn('older.txt', lines[1])

    def test_show_directory_tree_sort_modified_alias(self):
        """'modified' as sort key for directory tree doesn't crash and produces output."""
        result_mtime = show_directory_tree(self.temp_dir, sort_by='mtime')
        result_modified = show_directory_tree(self.temp_dir, sort_by='modified')
        self.assertEqual(result_mtime, result_modified)


# ---------------------------------------------------------------------------
# MEM-08: _collect_matching_files is a generator; show_file_list uses heapq
# ---------------------------------------------------------------------------

class TestCollectMatchingFilesGenerator(unittest.TestCase):
    """MEM-08: _collect_matching_files must be a generator, not return a list."""

    def test_returns_generator(self):
        """_collect_matching_files must yield, not return a list."""
        import types
        from reveal.tree_view import _collect_matching_files
        from reveal.display.filtering import PathFilter

        with tempfile.TemporaryDirectory() as d:
            Path(os.path.join(d, 'a.txt')).write_text('x')
            pf = PathFilter(root_path=Path(d), respect_gitignore=False,
                            exclude_patterns=None, include_defaults=False)
            result = _collect_matching_files(Path(d), show_hidden=False, path_filter=pf, exts=None)
        self.assertIsInstance(result, types.GeneratorType,
                              "_collect_matching_files must be a generator (use yield, not return list)")

    def test_generator_yields_correct_tuples(self):
        """Yielded items must be (Path, stat_result) tuples."""
        import stat
        from reveal.tree_view import _collect_matching_files
        from reveal.display.filtering import PathFilter

        with tempfile.TemporaryDirectory() as d:
            fpath = Path(os.path.join(d, 'sample.txt'))
            fpath.write_text('hello')
            pf = PathFilter(root_path=Path(d), respect_gitignore=False,
                            exclude_patterns=None, include_defaults=False)
            items = list(_collect_matching_files(Path(d), show_hidden=False, path_filter=pf, exts=None))

        self.assertEqual(len(items), 1)
        path, st = items[0]
        self.assertIsInstance(path, Path)
        self.assertTrue(hasattr(st, 'st_mtime'))

    def test_heapq_bounds_memory_for_mtime_sort(self):
        """show_file_list with mtime sort must never hold more than _MAX_FILE_LIST entries."""
        # Create more files than _MAX_FILE_LIST (500) to confirm truncation
        _MAX = 500
        with tempfile.TemporaryDirectory() as d:
            for i in range(_MAX + 50):
                Path(os.path.join(d, f'f{i:04d}.txt')).write_text(str(i))
            result = show_file_list(d)
            lines = [l for l in result.strip().splitlines() if l and not l.startswith('...')]
        self.assertLessEqual(len(lines), _MAX,
                             f"show_file_list returned {len(lines)} lines, expected <= {_MAX}")

    def test_sort_ascending_mtime_still_correct(self):
        """sort_desc=False (oldest first) must still return files in ascending mtime order."""
        with tempfile.TemporaryDirectory() as d:
            older = Path(os.path.join(d, 'older.txt'))
            newer = Path(os.path.join(d, 'newer.txt'))
            older.write_text('old')
            newer.write_text('new')
            os.utime(str(older), (1000000, 1000000))
            os.utime(str(newer), (2000000, 2000000))
            result = show_file_list(d, sort_by='mtime', sort_desc=False)
            lines = [l for l in result.strip().splitlines() if l]
        self.assertIn('older.txt', lines[0])
        self.assertIn('newer.txt', lines[1])

    def test_sort_by_name_still_works(self):
        """Name sort falls back to full list path — must still produce correct output."""
        with tempfile.TemporaryDirectory() as d:
            for name in ('charlie.txt', 'alpha.txt', 'beta.txt'):
                Path(os.path.join(d, name)).write_text(name)
            result = show_file_list(d, sort_by='name', sort_desc=False)
            lines = [l for l in result.strip().splitlines() if l]
        names_in_order = [l.split()[-1] for l in lines]
        self.assertEqual(names_in_order, ['alpha.txt', 'beta.txt', 'charlie.txt'])


if __name__ == '__main__':
    unittest.main()
