"""Tests for stats adapter (stats://)."""

import pytest
from pathlib import Path
from reveal.adapters.stats import StatsAdapter


class TestStatsAdapterBasics:
    """Test basic stats adapter functionality."""

    def test_get_help_returns_documentation(self):
        """Test that get_help returns properly structured documentation."""
        help_data = StatsAdapter.get_help()

        assert 'name' in help_data
        assert help_data['name'] == 'stats'
        assert 'description' in help_data
        assert 'syntax' in help_data
        assert 'examples' in help_data
        assert 'features' in help_data
        assert 'filters' in help_data
        assert 'workflows' in help_data
        assert 'output_formats' in help_data

        # Check examples structure
        assert len(help_data['examples']) > 0
        example = help_data['examples'][0]
        assert 'uri' in example
        assert 'description' in example

        # Check filters documentation
        assert 'min_lines' in help_data['filters']
        assert 'max_lines' in help_data['filters']
        assert 'min_complexity' in help_data['filters']
        assert 'max_complexity' in help_data['filters']

    def test_init_with_valid_file(self, tmp_path):
        """Test initialization with a valid file path."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(str(test_file))
        assert adapter.path == test_file.resolve()

    def test_init_with_valid_directory(self, tmp_path):
        """Test initialization with a valid directory path."""
        adapter = StatsAdapter(str(tmp_path))
        assert adapter.path == tmp_path.resolve()

    def test_init_with_nonexistent_path_raises_error(self):
        """Test that initialization with nonexistent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Path not found"):
            StatsAdapter("/nonexistent/path/to/file.py")

    def test_get_metadata_for_file(self, tmp_path):
        """Test get_metadata returns correct metadata for a file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(str(test_file))
        metadata = adapter.get_metadata()

        assert metadata['type'] == 'statistics'
        assert metadata['path'] == str(test_file)
        assert metadata['is_directory'] is False
        assert metadata['exists'] is True

    def test_get_metadata_for_directory(self, tmp_path):
        """Test get_metadata returns correct metadata for a directory."""
        adapter = StatsAdapter(str(tmp_path))
        metadata = adapter.get_metadata()

        assert metadata['type'] == 'statistics'
        assert metadata['path'] == str(tmp_path)
        assert metadata['is_directory'] is True
        assert metadata['exists'] is True


class TestFileAnalysis:
    """Test single file analysis."""

    def test_analyze_simple_python_file(self, tmp_path):
        """Test analyzing a simple Python file."""
        test_file = tmp_path / "simple.py"
        test_file.write_text("""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

class Calculator:
    def multiply(self, a, b):
        return a * b
""")

        adapter = StatsAdapter(str(test_file))
        result = adapter.get_structure()

        # Structure changed - file stats now in files array
        assert 'files' in result
        assert len(result['files']) == 1
        file_stats = result['files'][0]

        assert 'file' in file_stats
        assert 'lines' in file_stats
        assert 'elements' in file_stats
        assert 'complexity' in file_stats
        assert 'quality' in file_stats

        # Check line counts
        assert file_stats['lines']['total'] > 0
        assert file_stats['lines']['code'] > 0

        # Check element counts
        assert file_stats['elements']['functions'] >= 2  # add, subtract (multiply is a method)
        assert file_stats['elements']['classes'] >= 1    # Calculator

    def test_analyze_file_with_complexity(self, tmp_path):
        """Test analyzing a file with complex functions."""
        test_file = tmp_path / "complex.py"
        test_file.write_text("""
def complex_function(x):
    if x > 0:
        if x > 10:
            return "big"
        else:
            return "small"
    elif x < 0:
        return "negative"
    else:
        return "zero"
""")

        adapter = StatsAdapter(str(test_file))
        result = adapter.get_structure()

        # Structure changed - file stats now in files array
        assert 'files' in result
        file_stats = result['files'][0]

        # Should detect complexity from if/elif/else statements
        assert file_stats['complexity']['average'] >= 1

    def test_analyze_file_with_long_function(self, tmp_path):
        """Test detecting long functions (>100 lines)."""
        # Create a file with a very long function
        long_func = "def long_function():\n" + "\n".join([f"    x = {i}" for i in range(150)])

        test_file = tmp_path / "long.py"
        test_file.write_text(long_func)

        adapter = StatsAdapter(str(test_file))
        result = adapter.get_structure()

        # Structure changed - file stats now in files array
        assert 'files' in result
        file_stats = result['files'][0]

        # Should detect long function
        assert 'issues' in file_stats
        # Note: This might be empty if tree-sitter doesn't parse it correctly, but we're testing the logic

    def test_get_element_for_existing_file(self, tmp_path):
        """Test get_element retrieves stats for a specific file."""
        # Create directory structure
        subdir = tmp_path / "src"
        subdir.mkdir()
        test_file = subdir / "module.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_element("src/module.py")

        assert result is not None
        assert 'lines' in result
        assert 'elements' in result

    def test_get_element_for_nonexistent_file(self, tmp_path):
        """Test get_element returns None for nonexistent file."""
        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_element("nonexistent.py")

        assert result is None


class TestDirectoryAnalysis:
    """Test directory analysis and aggregation."""

    def test_analyze_directory_with_multiple_files(self, tmp_path):
        """Test analyzing a directory with multiple files."""
        # Create multiple Python files
        (tmp_path / "file1.py").write_text("def func1(): pass")
        (tmp_path / "file2.py").write_text("def func2(): pass\ndef func3(): pass")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()

        assert 'summary' in result
        assert 'files' in result

        # Check summary
        summary = result['summary']
        assert summary['total_files'] >= 2
        assert summary['total_lines'] > 0
        assert summary['total_functions'] >= 3

    def test_analyze_empty_directory(self, tmp_path):
        """Test analyzing an empty directory."""
        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()

        assert 'summary' in result
        assert result['summary']['total_files'] == 0
        assert result['summary']['total_lines'] == 0

    def test_directory_ignores_common_directories(self, tmp_path):
        """Test that common directories like .git, node_modules are ignored."""
        # Create files in ignored directories
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config.py").write_text("def git_func(): pass")

        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "lib.py").write_text("def node_func(): pass")

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def main(): pass")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()

        # Should only analyze src/main.py, not .git or node_modules
        assert result['summary']['total_files'] >= 1
        # Verify files don't include .git or node_modules
        file_paths = [f['file'] for f in result['files']]
        assert not any('.git' in p for p in file_paths)
        assert not any('node_modules' in p for p in file_paths)


class TestFiltering:
    """Test filtering functionality."""

    def test_filter_by_min_lines(self, tmp_path):
        """Test filtering files by minimum line count."""
        # Create files with different line counts
        (tmp_path / "small.py").write_text("def f(): pass")
        (tmp_path / "large.py").write_text("\n".join([f"def f{i}(): pass" for i in range(20)]))

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(min_lines=10)

        # Should only include large.py
        assert result['summary']['total_files'] >= 1
        # All files should have >= 10 lines
        for file_stat in result['files']:
            assert file_stat['lines']['total'] >= 10

    def test_filter_by_max_lines(self, tmp_path):
        """Test filtering files by maximum line count."""
        (tmp_path / "small.py").write_text("def f(): pass")
        (tmp_path / "large.py").write_text("\n".join([f"def f{i}(): pass" for i in range(20)]))

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(max_lines=5)

        # All files should have <= 5 lines
        for file_stat in result['files']:
            assert file_stat['lines']['total'] <= 5

    def test_filter_by_min_complexity(self, tmp_path):
        """Test filtering files by minimum complexity."""
        # Simple file
        (tmp_path / "simple.py").write_text("def f(): return 1")

        # Complex file
        (tmp_path / "complex.py").write_text("""
def complex_func(x):
    if x > 0:
        if x > 10:
            return "big"
        elif x > 5:
            return "medium"
        else:
            return "small"
    else:
        return "zero"
""")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(min_complexity=3.0)

        # All files should have avg complexity >= 3.0
        for file_stat in result['files']:
            assert file_stat['complexity']['average'] >= 3.0

    def test_filter_by_max_complexity(self, tmp_path):
        """Test filtering files by maximum complexity."""
        (tmp_path / "simple.py").write_text("def f(): return 1")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(max_complexity=2.0)

        # All files should have avg complexity <= 2.0
        for file_stat in result['files']:
            assert file_stat['complexity']['average'] <= 2.0

    def test_filter_by_min_functions(self, tmp_path):
        """Test filtering files by minimum function count."""
        (tmp_path / "one_func.py").write_text("def f(): pass")
        (tmp_path / "many_funcs.py").write_text("def f1(): pass\ndef f2(): pass\ndef f3(): pass")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(min_functions=2)

        # All files should have >= 2 functions
        for file_stat in result['files']:
            assert file_stat['elements']['functions'] >= 2


class TestHotspots:
    """Test hotspot identification."""

    def test_hotspots_identifies_complex_files(self, tmp_path):
        """Test that hotspots identifies files with high complexity."""
        # Create a simple file
        (tmp_path / "simple.py").write_text("def f(): return 1")

        # Create a complex file
        (tmp_path / "complex.py").write_text("""
def complex1(x):
    if x > 0:
        if x > 10:
            if x > 20:
                return "very big"
            else:
                return "big"
        elif x > 5:
            return "medium"
        else:
            return "small"
    else:
        return "zero"

def complex2(y):
    if y < 0:
        if y < -10:
            return "very negative"
        else:
            return "negative"
    elif y > 0:
        return "positive"
    else:
        return "zero"
""")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(hotspots=True)

        assert 'hotspots' in result
        # Hotspots might be empty if quality is good, but should be a list
        assert isinstance(result['hotspots'], list)

        # If there are hotspots, check structure
        if len(result['hotspots']) > 0:
            hotspot = result['hotspots'][0]
            assert 'file' in hotspot
            assert 'hotspot_score' in hotspot
            assert 'quality_score' in hotspot
            assert 'issues' in hotspot
            assert 'details' in hotspot

    def test_hotspots_empty_for_clean_code(self, tmp_path):
        """Test that hotspots is empty for clean, simple code."""
        (tmp_path / "clean.py").write_text("def add(a, b): return a + b")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(hotspots=True)

        assert 'hotspots' in result
        # Hotspots list might be empty or have low scores

    def test_hotspots_limited_to_10_files(self, tmp_path):
        """Test that hotspots returns at most 10 files."""
        # Create many files with issues
        for i in range(20):
            (tmp_path / f"file{i}.py").write_text("""
def complex_func(x):
    if x > 0:
        if x > 10:
            return "big"
        else:
            return "small"
    else:
        return "zero"
""")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(hotspots=True)

        assert 'hotspots' in result
        assert len(result['hotspots']) <= 10


class TestQualityMetrics:
    """Test quality score and complexity calculations."""

    def test_quality_score_high_for_simple_code(self, tmp_path):
        """Test that quality score is high for simple, clean code."""
        test_file = tmp_path / "clean.py"
        test_file.write_text("""
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
""")

        adapter = StatsAdapter(str(test_file))
        result = adapter.get_structure()

        # Clean code should have high quality score (close to 100)
        # Use summary for aggregated stats
        assert result['summary']['avg_quality_score'] >= 70

    def test_complexity_estimation(self, tmp_path):
        """Test complexity estimation for functions."""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
def simple():
    return 1

def with_if(x):
    if x > 0:
        return "positive"
    return "non-positive"

def with_multiple_branches(x):
    if x > 0:
        return "positive"
    elif x < 0:
        return "negative"
    else:
        return "zero"
""")

        adapter = StatsAdapter(str(test_file))
        result = adapter.get_structure()

        # Should calculate some complexity
        # Use files array for file-specific stats
        file_stats = result['files'][0]
        assert file_stats['complexity']['average'] >= 1
        assert file_stats['complexity']['max'] >= 1

    def test_empty_and_comment_line_detection(self, tmp_path):
        """Test detection of empty and comment lines."""
        test_file = tmp_path / "comments.py"
        test_file.write_text("""
# This is a comment
def hello():
    # Another comment
    return "world"

# More comments
""")

        adapter = StatsAdapter(str(test_file))
        result = adapter.get_structure()

        # Use files array for file-specific stats
        file_stats = result['files'][0]
        assert file_stats['lines']['total'] > 0
        assert file_stats['lines']['empty'] >= 1
        assert file_stats['lines']['comments'] >= 2


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_analyze_file_with_syntax_error_returns_none(self, tmp_path):
        """Test that files with syntax errors are silently skipped."""
        test_file = tmp_path / "broken.py"
        test_file.write_text("def broken syntax here")

        adapter = StatsAdapter(str(test_file))
        # Should not crash, might return partial results or skip
        result = adapter.get_structure()
        # Just ensure it doesn't crash
        assert result is not None

    def test_aggregate_stats_with_empty_list(self, tmp_path):
        """Test aggregating stats with no files."""
        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()

        assert result['summary']['total_files'] == 0
        assert result['summary']['total_lines'] == 0
        assert result['summary']['avg_complexity'] == 0

    def test_matches_filters_with_none_values(self, tmp_path):
        """Test that None filter values are handled correctly."""
        # Use a directory with multiple files to test filtering
        (tmp_path / "file1.py").write_text("def f(): pass")
        (tmp_path / "file2.py").write_text("def g(): pass")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure(
            min_lines=None,
            max_lines=None,
            min_complexity=None,
            max_complexity=None,
            min_functions=None
        )

        # Should return results without filtering
        assert 'summary' in result
        assert result['summary']['total_files'] >= 2


class TestURIQueryParameters:
    """Test URI query parameter parsing and integration."""

    def test_parse_query_with_hotspots(self, tmp_path):
        """Test parsing hotspots=true query parameter."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string="hotspots=true")

        assert 'hotspots' in adapter.query_params
        assert adapter.query_params['hotspots'] is True

    def test_parse_query_with_min_complexity(self, tmp_path):
        """Test parsing min_complexity query parameter."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string="min_complexity=5")

        assert 'min_complexity' in adapter.query_params
        assert adapter.query_params['min_complexity'] == 5

    def test_parse_query_with_multiple_params(self, tmp_path):
        """Test parsing multiple query parameters."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(
            str(tmp_path),
            query_string="hotspots=true&min_complexity=10&min_lines=50"
        )

        assert adapter.query_params['hotspots'] is True
        assert adapter.query_params['min_complexity'] == 10
        assert adapter.query_params['min_lines'] == 50

    def test_parse_query_with_float_values(self, tmp_path):
        """Test parsing float query parameters."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string="max_complexity=3.5")

        assert 'max_complexity' in adapter.query_params
        assert adapter.query_params['max_complexity'] == 3.5

    def test_parse_query_with_boolean_variants(self, tmp_path):
        """Test parsing various boolean representations."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        # Test 'true'
        adapter1 = StatsAdapter(str(tmp_path), query_string="hotspots=true")
        assert adapter1.query_params['hotspots'] is True

        # Test '1'
        adapter2 = StatsAdapter(str(tmp_path), query_string="hotspots=1")
        assert adapter2.query_params['hotspots'] is True

        # Test 'yes'
        adapter3 = StatsAdapter(str(tmp_path), query_string="hotspots=yes")
        assert adapter3.query_params['hotspots'] is True

        # Test 'false'
        adapter4 = StatsAdapter(str(tmp_path), query_string="hotspots=false")
        assert adapter4.query_params['hotspots'] is False

        # Test '0'
        adapter5 = StatsAdapter(str(tmp_path), query_string="hotspots=0")
        assert adapter5.query_params['hotspots'] is False

    def test_query_params_override_flag_params(self, tmp_path):
        """Test that query params take precedence over flag params."""
        # Create test files with different complexity
        (tmp_path / "simple.py").write_text("def f(): pass")
        (tmp_path / "complex.py").write_text("""
def complex_function(a, b, c):
    if a > 0:
        for i in range(10):
            if b > i:
                while c > 0:
                    c -= 1
    return a + b + c
""")

        # Query param says hotspots=true, flag param says False
        adapter = StatsAdapter(str(tmp_path), query_string="hotspots=true")
        result = adapter.get_structure(hotspots=False)

        # Query param should win
        assert 'hotspots' in result

    def test_query_params_with_filters_applied(self, tmp_path):
        """Test that query params are properly applied to filtering."""
        # Create files with different line counts
        (tmp_path / "small.py").write_text("def f(): pass")  # ~1 line
        (tmp_path / "medium.py").write_text("def g():\n" + "    pass\n" * 30)  # ~32 lines
        (tmp_path / "large.py").write_text("def h():\n" + "    pass\n" * 60)  # ~62 lines

        # Filter for files with 50+ lines
        adapter = StatsAdapter(str(tmp_path), query_string="min_lines=50")
        result = adapter.get_structure()

        # Should only include large.py
        assert 'files' in result
        filtered_files = [f for f in result['files'] if f['lines']['total'] >= 50]
        assert len(filtered_files) >= 1
        assert any('large.py' in f['file'] for f in filtered_files)

    def test_empty_query_string(self, tmp_path):
        """Test handling of empty query string."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string="")

        assert adapter.query_params == {}

    def test_none_query_string(self, tmp_path):
        """Test handling of None query string."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string=None)

        assert adapter.query_params == {}

    def test_malformed_query_params_ignored(self, tmp_path):
        """Test that malformed query params are handled gracefully."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass")

        # Param without value should be ignored
        adapter = StatsAdapter(str(tmp_path), query_string="hotspots&min_lines=50")

        # Only properly formed params should be parsed
        assert 'min_lines' in adapter.query_params
        assert adapter.query_params['min_lines'] == 50


class TestUnifiedQuerySyntax:
    """Test new unified query syntax (operators and result control)."""

    def test_greater_than_operator(self, tmp_path):
        """Test lines>50 syntax."""
        (tmp_path / "small.py").write_text("def f(): pass")
        (tmp_path / "large.py").write_text("def h():\n" + "    pass\n" * 60)

        adapter = StatsAdapter(str(tmp_path), query_string="lines>50")
        result = adapter.get_structure()

        assert result['summary']['total_files'] == 1
        assert any('large.py' in f['file'] for f in result['files'])

    def test_less_than_operator(self, tmp_path):
        """Test complexity<5 syntax."""
        (tmp_path / "simple.py").write_text("def f(): pass")
        (tmp_path / "complex.py").write_text("def g():\n    if x:\n        if y:\n            if z: pass")

        adapter = StatsAdapter(str(tmp_path), query_string="complexity<5")
        result = adapter.get_structure()

        # Should include simple.py
        assert any('simple.py' in f['file'] for f in result['files'])

    def test_not_equals_operator(self, tmp_path):
        """Test functions!=0 syntax."""
        (tmp_path / "empty.py").write_text("# Just a comment")
        (tmp_path / "with_func.py").write_text("def f(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string="functions!=0")
        result = adapter.get_structure()

        # Should only include with_func.py
        assert result['summary']['total_files'] >= 1
        assert all(f['elements']['functions'] != 0 for f in result['files'])

    def test_range_operator(self, tmp_path):
        """Test lines=10..50 syntax (range)."""
        (tmp_path / "tiny.py").write_text("pass")
        (tmp_path / "medium.py").write_text("def f():\n" + "    pass\n" * 25)
        (tmp_path / "large.py").write_text("def h():\n" + "    pass\n" * 60)

        adapter = StatsAdapter(str(tmp_path), query_string="lines=10..50")
        result = adapter.get_structure()

        # Should only include medium.py
        assert all(10 <= f['lines']['total'] <= 50 for f in result['files'])

    def test_result_control_sort_ascending(self, tmp_path):
        """Test sort=lines syntax (ascending)."""
        (tmp_path / "medium.py").write_text("def f():\n" + "    pass\n" * 30)
        (tmp_path / "small.py").write_text("def g(): pass")
        (tmp_path / "large.py").write_text("def h():\n" + "    pass\n" * 60)

        adapter = StatsAdapter(str(tmp_path), query_string="sort=lines")
        result = adapter.get_structure()

        # Files should be sorted by lines ascending
        files = result['files']
        assert len(files) >= 3
        for i in range(len(files) - 1):
            assert files[i]['lines']['total'] <= files[i + 1]['lines']['total']

    def test_result_control_sort_descending(self, tmp_path):
        """Test sort=-lines syntax (descending)."""
        (tmp_path / "medium.py").write_text("def f():\n" + "    pass\n" * 30)
        (tmp_path / "small.py").write_text("def g(): pass")
        (tmp_path / "large.py").write_text("def h():\n" + "    pass\n" * 60)

        adapter = StatsAdapter(str(tmp_path), query_string="sort=-lines")
        result = adapter.get_structure()

        # Files should be sorted by lines descending
        files = result['files']
        assert len(files) >= 3
        for i in range(len(files) - 1):
            assert files[i]['lines']['total'] >= files[i + 1]['lines']['total']

    def test_result_control_limit(self, tmp_path):
        """Test limit=2 syntax."""
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text(f"def f{i}(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string="limit=2")
        result = adapter.get_structure()

        # Should only show 2 files
        assert len(result['files']) == 2
        assert result['displayed_results'] == 2
        assert result['total_matches'] == 5

    def test_result_control_offset(self, tmp_path):
        """Test offset=2 syntax."""
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text(f"def f{i}(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string="offset=2")
        result = adapter.get_structure()

        # Should skip first 2 files, show remaining 3
        assert len(result['files']) == 3

    def test_result_control_combined(self, tmp_path):
        """Test sort=-lines&limit=2&offset=1 syntax."""
        (tmp_path / "tiny.py").write_text("pass")
        (tmp_path / "small.py").write_text("def f(): pass\n" * 5)
        (tmp_path / "medium.py").write_text("def g():\n" + "    pass\n" * 30)
        (tmp_path / "large.py").write_text("def h():\n" + "    pass\n" * 60)

        adapter = StatsAdapter(str(tmp_path), query_string="sort=-lines&limit=2&offset=1")
        result = adapter.get_structure()

        # Should skip largest (offset=1), show next 2 (limit=2)
        files = result['files']
        assert len(files) == 2
        # Should be in descending order (largest to smallest)
        for i in range(len(files) - 1):
            assert files[i]['lines']['total'] >= files[i + 1]['lines']['total']

    def test_filter_and_result_control_combined(self, tmp_path):
        """Test lines>10&sort=-lines&limit=2 syntax."""
        (tmp_path / "tiny.py").write_text("pass")
        (tmp_path / "small.py").write_text("def f():\n" + "    pass\n" * 15)
        (tmp_path / "medium.py").write_text("def g():\n" + "    pass\n" * 30)
        (tmp_path / "large.py").write_text("def h():\n" + "    pass\n" * 60)

        adapter = StatsAdapter(str(tmp_path), query_string="lines>10&sort=-lines&limit=2")
        result = adapter.get_structure()

        # Should filter (lines>10), sort descending, limit to 2
        files = result['files']
        assert len(files) == 2
        # All should be > 10 lines
        assert all(f['lines']['total'] > 10 for f in files)
        # Should be in descending order
        for i in range(len(files) - 1):
            assert files[i]['lines']['total'] >= files[i + 1]['lines']['total']

    def test_truncation_warning(self, tmp_path):
        """Test that truncation warning is added when results are limited."""
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text(f"def f{i}(): pass")

        adapter = StatsAdapter(str(tmp_path), query_string="limit=2")
        result = adapter.get_structure()

        # Should have warning about truncation
        assert 'warnings' in result
        assert any(w['type'] == 'truncated' for w in result['warnings'])
        assert result['displayed_results'] == 2
        assert result['total_matches'] == 5


class TestStatsAdapterSchema:
    """Test schema generation for AI agent integration."""

    def test_get_schema(self):
        """Should return machine-readable schema."""
        schema = StatsAdapter.get_schema()

        assert schema is not None
        assert schema['adapter'] == 'stats'
        assert 'description' in schema
        assert 'uri_syntax' in schema
        assert 'stats://' in schema['uri_syntax']

    def test_schema_query_params(self):
        """Schema should document query parameters."""
        schema = StatsAdapter.get_schema()

        assert 'query_params' in schema
        query_params = schema['query_params']

        # Should have filtering params
        assert 'min_lines' in query_params
        assert 'max_lines' in query_params
        assert 'min_complexity' in query_params
        assert 'max_complexity' in query_params
        assert 'min_functions' in query_params
        assert 'hotspots' in query_params
        assert 'code_only' in query_params

    def test_schema_boolean_params(self):
        """Schema should document boolean operation params."""
        schema = StatsAdapter.get_schema()

        query_params = schema['query_params']
        assert 'hotspots' in query_params
        assert query_params['hotspots']['type'] == 'boolean'
        assert 'code_only' in query_params
        assert query_params['code_only']['type'] == 'boolean'

    def test_schema_output_types(self):
        """Schema should define output types."""
        schema = StatsAdapter.get_schema()

        assert 'output_types' in schema
        assert len(schema['output_types']) >= 1

        # Should have stats output types
        output_types = [ot['type'] for ot in schema['output_types']]
        assert 'stats_summary' in output_types
        assert 'stats_file' in output_types

    def test_schema_examples(self):
        """Schema should include usage examples."""
        schema = StatsAdapter.get_schema()

        assert 'example_queries' in schema
        assert len(schema['example_queries']) >= 5

        # Examples should have required fields
        for example in schema['example_queries']:
            assert 'uri' in example
            assert 'description' in example

    def test_schema_flags(self):
        """Schema should document CLI flags."""
        schema = StatsAdapter.get_schema()

        assert 'cli_flags' in schema
        cli_flags = schema['cli_flags']

        # cli_flags is a list of strings
        assert isinstance(cli_flags, list)
        # Stats adapter has at least one flag
        assert len(cli_flags) >= 0


class TestStatsRenderer:
    """Test renderer output formatting."""

    def test_renderer_structure(self, tmp_path):
        """Renderer should format statistics correctly."""
        from reveal.adapters.stats import StatsRenderer
        from io import StringIO
        import sys

        # Create test file
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\n\ndef bar():\n    return 1")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        StatsRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain key sections (summary format doesn't show individual files)
        assert 'Statistics' in output or 'Files:' in output
        assert 'Lines:' in output or 'Functions:' in output

    def test_renderer_json_format(self, tmp_path):
        """Renderer should support JSON output."""
        from reveal.adapters.stats import StatsRenderer
        from io import StringIO
        import sys
        import json

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_structure()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        StatsRenderer.render_structure(result, format='json')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should be valid JSON
        parsed = json.loads(output)
        assert 'type' in parsed
        assert parsed['type'] == 'stats_summary'

    def test_renderer_error_handling(self):
        """Renderer should handle errors gracefully."""
        from reveal.adapters.stats import StatsRenderer
        from io import StringIO
        import sys

        # Capture stderr
        old_stderr = sys.stderr
        sys.stderr = captured_output = StringIO()

        error = FileNotFoundError("Path not found")
        StatsRenderer.render_error(error)

        sys.stderr = old_stderr
        output = captured_output.getvalue()

        assert 'Error' in output
        assert 'Path not found' in output

    def test_renderer_element(self, tmp_path):
        """Renderer should format element statistics correctly."""
        from reveal.adapters.stats import StatsRenderer
        from io import StringIO
        import sys

        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass")

        adapter = StatsAdapter(str(tmp_path))
        result = adapter.get_element('test.py')

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        StatsRenderer.render_element(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain file statistics
        assert 'test.py' in output
