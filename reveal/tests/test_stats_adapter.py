"""
Tests for reveal/adapters/stats.py

Tests the StatsAdapter class for codebase statistics and hotspot detection.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from reveal.adapters.stats import StatsAdapter


class TestStatsAdapter(unittest.TestCase):
    """Test the StatsAdapter class."""

    def setUp(self):
        """Set up test fixtures with temporary directory."""
        self.test_dir = Path(tempfile.mkdtemp())
        self._create_test_files()

    def tearDown(self):
        """Clean up temporary directory."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _create_test_files(self):
        """Create test Python files with known characteristics."""

        # Simple file: small, low complexity
        simple_file = self.test_dir / "simple.py"
        simple_file.write_text("""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

class Calculator:
    def multiply(self, a, b):
        return a * b
""")

        # Complex file: high complexity, long function
        complex_file = self.test_dir / "complex.py"
        complex_file.write_text("""
def process_data(data):
    # This function has high cyclomatic complexity
    if data is None:
        return None

    result = []
    for item in data:
        if item > 0:
            if item % 2 == 0:
                result.append(item * 2)
            else:
                result.append(item * 3)
        elif item < 0:
            if item % 2 == 0:
                result.append(item / 2)
            else:
                result.append(item / 3)
        else:
            result.append(0)

    return result

def very_long_function():
    # This function is >100 lines to trigger quality issues
    x = 1
    y = 2
    z = 3
""" + "\n    # More code here" * 100 + "\n    return x + y + z\n")

        # Empty file
        empty_file = self.test_dir / "empty.py"
        empty_file.write_text("")

        # Subdirectory with file
        subdir = self.test_dir / "submodule"
        subdir.mkdir()
        sub_file = subdir / "utils.py"
        sub_file.write_text("""
def helper():
    pass

def another_helper():
    pass
""")

    def test_init_with_valid_path(self):
        """Test adapter initialization with valid path."""
        adapter = StatsAdapter(str(self.test_dir))
        self.assertTrue(adapter.path.exists())
        self.assertTrue(adapter.path.is_dir())

    def test_init_with_file_path(self):
        """Test adapter initialization with file path."""
        file_path = self.test_dir / "simple.py"
        adapter = StatsAdapter(str(file_path))
        self.assertTrue(adapter.path.exists())
        self.assertTrue(adapter.path.is_file())

    def test_init_with_nonexistent_path(self):
        """Test adapter initialization with nonexistent path."""
        with self.assertRaises(FileNotFoundError):
            StatsAdapter("/nonexistent/path")

    def test_get_help(self):
        """Test get_help returns proper documentation."""
        help_dict = StatsAdapter.get_help()

        # Required fields
        self.assertIn('name', help_dict)
        self.assertEqual(help_dict['name'], 'stats')
        self.assertIn('description', help_dict)
        self.assertIn('syntax', help_dict)

        # Recommended fields
        self.assertIn('examples', help_dict)
        self.assertIn('features', help_dict)
        self.assertIn('workflows', help_dict)
        self.assertIn('notes', help_dict)

        # Check examples are well-formed
        self.assertGreater(len(help_dict['examples']), 0)
        for example in help_dict['examples']:
            self.assertIn('uri', example)
            self.assertIn('description', example)

    def test_analyze_simple_file(self):
        """Test analyzing a simple Python file."""
        file_path = self.test_dir / "simple.py"
        adapter = StatsAdapter(str(file_path))
        stats = adapter.get_structure()

        # Check structure
        self.assertIn('file', stats)
        self.assertIn('lines', stats)
        self.assertIn('elements', stats)
        self.assertIn('complexity', stats)
        self.assertIn('quality', stats)

        # Check line counts
        self.assertGreater(stats['lines']['total'], 0)
        self.assertGreaterEqual(stats['lines']['code'], 0)

        # Check element counts
        # Note: Depending on analyzer, may count methods separately or as functions
        self.assertGreaterEqual(stats['elements']['functions'], 2)  # at least add, subtract
        self.assertGreaterEqual(stats['elements']['classes'], 1)   # Calculator

        # Check quality score (should be high for simple file)
        self.assertGreater(stats['quality']['score'], 70)

    def test_analyze_complex_file(self):
        """Test analyzing a complex Python file."""
        file_path = self.test_dir / "complex.py"
        adapter = StatsAdapter(str(file_path))
        stats = adapter.get_structure()

        # Should have long function issue (very_long_function has >100 lines)
        self.assertGreater(stats['quality']['long_functions'], 0)

        # Should have lower quality score due to long function
        self.assertLess(stats['quality']['score'], 80)

        # Check issues are populated
        self.assertIn('issues', stats)
        self.assertGreater(len(stats['issues']['long_functions']), 0)

    def test_analyze_directory(self):
        """Test analyzing a directory."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure()

        # Check summary structure
        self.assertIn('summary', result)
        self.assertIn('files', result)

        summary = result['summary']
        self.assertIn('total_files', summary)
        self.assertIn('total_lines', summary)
        self.assertIn('total_functions', summary)
        self.assertIn('total_classes', summary)
        self.assertIn('avg_complexity', summary)
        self.assertIn('avg_quality_score', summary)

        # Should find at least 3 files (simple, complex, utils in subdir)
        # empty.py might not be counted if it has no structure
        self.assertGreaterEqual(summary['total_files'], 3)

        # Should have some functions and classes
        self.assertGreater(summary['total_functions'], 0)
        self.assertGreater(summary['total_classes'], 0)

        # Files should be detailed
        self.assertGreater(len(result['files']), 0)

    def test_hotspots_identification(self):
        """Test hotspot identification."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure(hotspots=True)

        # Should have hotspots key
        self.assertIn('hotspots', result)
        hotspots = result['hotspots']

        # Should be a list
        self.assertIsInstance(hotspots, list)

        # If we have hotspots, check structure
        if len(hotspots) > 0:
            hotspot = hotspots[0]
            self.assertIn('file', hotspot)
            self.assertIn('hotspot_score', hotspot)
            self.assertIn('quality_score', hotspot)
            self.assertIn('issues', hotspot)
            self.assertIn('details', hotspot)

            # complex.py should be in hotspots due to long function
            hotspot_files = [h['file'] for h in hotspots]
            self.assertTrue(any('complex.py' in f for f in hotspot_files))

    def test_filter_min_lines(self):
        """Test filtering by minimum lines."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure(min_lines=50)

        # Should only include files with 50+ lines
        for file_stat in result['files']:
            self.assertGreaterEqual(file_stat['lines']['total'], 50)

        # complex.py should be included (>100 lines)
        files = [f['file'] for f in result['files']]
        self.assertTrue(any('complex.py' in f for f in files))

    def test_filter_max_lines(self):
        """Test filtering by maximum lines."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure(max_lines=20)

        # Should only include files with <=20 lines
        for file_stat in result['files']:
            self.assertLessEqual(file_stat['lines']['total'], 20)

        # complex.py should NOT be included
        files = [f['file'] for f in result['files']]
        self.assertFalse(any('complex.py' in f for f in files))

    def test_filter_min_complexity(self):
        """Test filtering by minimum complexity."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure(min_complexity=5.0)

        # Should only include files with avg complexity >= 5
        for file_stat in result['files']:
            self.assertGreaterEqual(file_stat['complexity']['average'], 5.0)

    def test_filter_max_complexity(self):
        """Test filtering by maximum complexity."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure(max_complexity=5.0)

        # Should only include files with avg complexity <= 5
        for file_stat in result['files']:
            self.assertLessEqual(file_stat['complexity']['average'], 5.0)

    def test_filter_min_functions(self):
        """Test filtering by minimum function count."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure(min_functions=2)

        # Should only include files with 2+ functions
        for file_stat in result['files']:
            self.assertGreaterEqual(file_stat['elements']['functions'], 2)

    def test_get_element(self):
        """Test getting stats for a specific file."""
        adapter = StatsAdapter(str(self.test_dir))
        stats = adapter.get_element("simple.py")

        self.assertIsNotNone(stats)
        self.assertIn('file', stats)
        self.assertIn('elements', stats)

        # Should have at least 2 functions (may include methods)
        self.assertGreaterEqual(stats['elements']['functions'], 2)

    def test_get_element_nonexistent(self):
        """Test getting stats for nonexistent file."""
        adapter = StatsAdapter(str(self.test_dir))
        stats = adapter.get_element("nonexistent.py")

        self.assertIsNone(stats)

    def test_get_metadata(self):
        """Test getting metadata."""
        adapter = StatsAdapter(str(self.test_dir))
        metadata = adapter.get_metadata()

        self.assertIn('type', metadata)
        self.assertEqual(metadata['type'], 'statistics')
        self.assertIn('path', metadata)
        self.assertIn('is_directory', metadata)
        self.assertIn('exists', metadata)

        self.assertTrue(metadata['is_directory'])
        self.assertTrue(metadata['exists'])

    def test_quality_score_calculation(self):
        """Test quality score calculation logic."""
        adapter = StatsAdapter(str(self.test_dir))

        # Test perfect score (low complexity, short functions, no issues)
        score = adapter._calculate_quality_score(
            avg_complexity=5.0,
            avg_func_length=20.0,
            long_func_count=0,
            deep_nesting_count=0,
            total_functions=10
        )
        self.assertEqual(score, 100.0)

        # Test penalized score (high complexity)
        score = adapter._calculate_quality_score(
            avg_complexity=20.0,
            avg_func_length=20.0,
            long_func_count=0,
            deep_nesting_count=0,
            total_functions=10
        )
        self.assertLess(score, 100.0)

        # Test penalized score (long functions)
        score = adapter._calculate_quality_score(
            avg_complexity=5.0,
            avg_func_length=100.0,
            long_func_count=5,
            deep_nesting_count=0,
            total_functions=10
        )
        self.assertLess(score, 70.0)

        # Score should never go below 0
        score = adapter._calculate_quality_score(
            avg_complexity=100.0,
            avg_func_length=500.0,
            long_func_count=10,
            deep_nesting_count=10,
            total_functions=10
        )
        self.assertGreaterEqual(score, 0.0)

    def test_complexity_estimation(self):
        """Test complexity estimation algorithm."""
        adapter = StatsAdapter(str(self.test_dir / "simple.py"))

        content = """
def simple():
    return 1

def complex_func():
    if x:
        if y:
            for i in range(10):
                while z:
                    try:
                        if a and b or c:
                            pass
                    except:
                        pass
"""

        # Simple function (no branches)
        func_simple = {'line': 2, 'end_line': 3}
        complexity = adapter._estimate_complexity(func_simple, content)
        self.assertIsNotNone(complexity)
        self.assertEqual(complexity, 1)

        # Complex function (multiple branches)
        func_complex = {'line': 5, 'end_line': 14}
        complexity = adapter._estimate_complexity(func_complex, content)
        self.assertIsNotNone(complexity)
        self.assertGreater(complexity, 10)

    def test_find_analyzable_files(self):
        """Test finding analyzable files in directory."""
        adapter = StatsAdapter(str(self.test_dir))
        files = adapter._find_analyzable_files(self.test_dir)

        # Should find Python files
        self.assertGreater(len(files), 0)

        # Should not include hidden directories
        file_paths = [str(f) for f in files]
        self.assertFalse(any('.git' in p for p in file_paths))
        self.assertFalse(any('__pycache__' in p for p in file_paths))

    def test_empty_directory(self):
        """Test analyzing empty directory."""
        empty_dir = self.test_dir / "empty_subdir"
        empty_dir.mkdir()

        adapter = StatsAdapter(str(empty_dir))
        result = adapter.get_structure()

        # Should return structure with zeros
        self.assertEqual(result['summary']['total_files'], 0)
        self.assertEqual(result['summary']['total_lines'], 0)

    def test_combined_filters(self):
        """Test using multiple filters together."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure(
            min_lines=10,
            max_complexity=10.0,
            min_functions=1
        )

        # Should only include files matching ALL filters
        for file_stat in result['files']:
            self.assertGreaterEqual(file_stat['lines']['total'], 10)
            self.assertLessEqual(file_stat['complexity']['average'], 10.0)
            self.assertGreaterEqual(file_stat['elements']['functions'], 1)

    def test_hotspots_limit_to_10(self):
        """Test that hotspots are limited to top 10."""
        # Create many files to test limit
        for i in range(15):
            file_path = self.test_dir / f"file_{i}.py"
            file_path.write_text(f"""
def func_{i}():
    # Long function to create hotspot
""" + "\n    pass" * 200)

        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure(hotspots=True)

        # Should have at most 10 hotspots
        self.assertLessEqual(len(result['hotspots']), 10)

    def test_relative_file_paths(self):
        """Test that file paths are relative to base directory."""
        adapter = StatsAdapter(str(self.test_dir))
        result = adapter.get_structure()

        # All file paths should be relative
        for file_stat in result['files']:
            self.assertFalse(file_stat['file'].startswith('/'))
            self.assertNotIn(str(self.test_dir), file_stat['file'])


if __name__ == '__main__':
    unittest.main()
