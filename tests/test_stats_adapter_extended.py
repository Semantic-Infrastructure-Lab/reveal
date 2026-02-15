"""Extended test coverage for reveal.adapters.stats.adapter module.

Targets remaining uncovered exception handlers:
- Line 247-249: parse_query_filters exception fallback
- Line 302-303: sorting TypeError/KeyError fallback
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from reveal.adapters.stats.adapter import StatsAdapter


class TestStatsAdapterExceptionHandling:
    """Test exception handling in StatsAdapter."""

    def test_query_filter_parsing_exception_fallback(self):
        """parse_query_filters exception should fall back to empty filters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal test directory
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("print('hello')\n")

            # Mock parse_query_filters to raise exception
            with patch('reveal.adapters.stats.adapter.parse_query_filters') as mock_parse:
                mock_parse.side_effect = ValueError("Invalid filter syntax")

                # Should not raise exception - should fall back to empty filters
                adapter = StatsAdapter(tmpdir, query_string="lines>5")
                assert adapter.query_filters == []

    def test_sorting_type_error_fallback(self):
        """Sorting TypeError should fall back to unsorted list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            test_file1 = Path(tmpdir) / "test1.py"
            test_file1.write_text("def foo():\n    pass\n")

            test_file2 = Path(tmpdir) / "test2.py"
            test_file2.write_text("def bar():\n    pass\n")

            # Request sorting by a field that doesn't exist or causes TypeError
            adapter = StatsAdapter(tmpdir, query_string="sort=nonexistent_field")

            # Should not raise exception
            result = adapter.get_structure()
            assert 'files' in result

    def test_sorting_key_error_fallback(self):
        """Sorting KeyError should fall back to unsorted list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_file = Path(tmpdir) / "test.py"
            test_file.write_text("def foo():\n    pass\n")

            # Mock field_value to raise KeyError
            with patch('reveal.adapters.stats.adapter.field_value') as mock_field:
                mock_field.side_effect = KeyError("Field not found")

                adapter = StatsAdapter(tmpdir, query_string="sort=lines")

                # Should not raise exception
                result = adapter.get_structure()
                assert 'files' in result
