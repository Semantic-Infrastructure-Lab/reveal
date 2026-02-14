"""Comprehensive tests for xlsx adapter."""

import pytest
from pathlib import Path
from reveal.adapters.xlsx import XlsxAdapter, XlsxRenderer
from io import StringIO
import sys


# Test data paths
TEST_DATA_DIR = Path(__file__).parent / "test_data"
SAMPLE_XLSX = Path.home() / "Downloads" / "QA Items.xlsx"  # Real test file


class TestXlsxAdapterInit:
    """Tests for adapter initialization and URI parsing."""

    def test_init_requires_uri(self):
        """Test adapter initialization requires URI."""
        with pytest.raises(TypeError):
            XlsxAdapter()

    def test_init_with_valid_uri(self):
        """Test adapter initialization with valid URI."""
        if SAMPLE_XLSX.exists():
            uri = f"xlsx://{SAMPLE_XLSX}"
            adapter = XlsxAdapter(uri)
            assert adapter.file_path == SAMPLE_XLSX
            assert adapter.query_params == {}

    def test_init_with_query_params(self):
        """Test adapter initialization with query parameters."""
        if SAMPLE_XLSX.exists():
            uri = f"xlsx://{SAMPLE_XLSX}?sheet=0&limit=10"
            adapter = XlsxAdapter(uri)
            assert adapter.query_params.get('sheet') == '0'
            assert adapter.query_params.get('limit') == '10'

    def test_init_with_file_not_found(self):
        """Test adapter initialization with non-existent file."""
        uri = "xlsx:///nonexistent/file.xlsx"
        with pytest.raises(ValueError, match="Invalid file path"):
            XlsxAdapter(uri)

    def test_init_with_non_xlsx_file(self):
        """Test adapter initialization with non-Excel file."""
        # Create a temporary non-xlsx file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            temp_path = f.name

        try:
            uri = f"xlsx://{temp_path}"
            with pytest.raises(ValueError, match="Invalid Excel format"):
                XlsxAdapter(uri)
        finally:
            import os
            os.unlink(temp_path)

    def test_parse_multiple_query_params(self):
        """Test parsing multiple query parameters."""
        if SAMPLE_XLSX.exists():
            uri = f"xlsx://{SAMPLE_XLSX}?sheet=Sales&range=A1:C10&limit=50&format=csv"
            adapter = XlsxAdapter(uri)
            assert adapter.query_params.get('sheet') == 'Sales'
            assert adapter.query_params.get('range') == 'A1:C10'
            assert adapter.query_params.get('limit') == '50'
            assert adapter.query_params.get('format') == 'csv'


class TestXlsxAdapterSchema:
    """Tests for adapter schema."""

    def test_get_schema_returns_dict(self):
        """Test that get_schema returns a dictionary."""
        schema = XlsxAdapter.get_schema()
        assert isinstance(schema, dict)

    def test_schema_has_required_fields(self):
        """Test that schema contains required fields."""
        schema = XlsxAdapter.get_schema()
        assert schema['adapter'] == 'xlsx'
        assert 'description' in schema
        assert 'uri_syntax' in schema
        assert 'query_params' in schema

    def test_schema_query_params(self):
        """Test that schema documents query parameters."""
        schema = XlsxAdapter.get_schema()
        params = schema['query_params']
        assert 'sheet' in params
        assert 'range' in params
        assert 'limit' in params
        assert 'format' in params

    def test_schema_has_examples(self):
        """Test that schema includes example queries."""
        schema = XlsxAdapter.get_schema()
        assert 'example_queries' in schema
        assert len(schema['example_queries']) > 0

        # Verify each example has required fields
        for example in schema['example_queries']:
            assert 'uri' in example
            assert 'description' in example
            assert 'output_type' in example


class TestXlsxAdapterHelp:
    """Tests for adapter help system."""

    def test_get_help_returns_dict(self):
        """Test that get_help returns a dictionary."""
        help_doc = XlsxAdapter.get_help()
        assert isinstance(help_doc, dict)

    def test_help_has_required_fields(self):
        """Test that help contains required fields."""
        help_doc = XlsxAdapter.get_help()
        assert help_doc['name'] == 'xlsx'
        assert 'description' in help_doc
        assert 'syntax' in help_doc
        assert 'examples' in help_doc
        assert 'features' in help_doc

    def test_help_has_workflows(self):
        """Test that help includes workflow examples."""
        help_doc = XlsxAdapter.get_help()
        assert 'workflows' in help_doc
        assert len(help_doc['workflows']) > 0

    def test_help_output_formats(self):
        """Test that help documents output formats."""
        help_doc = XlsxAdapter.get_help()
        assert 'output_formats' in help_doc
        assert 'csv' in help_doc['output_formats']


@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="Test file not available")
class TestXlsxAdapterWorkbookOverview:
    """Tests for workbook overview functionality."""

    def test_get_structure_returns_workbook(self):
        """Test that get_structure returns workbook overview."""
        uri = f"xlsx://{SAMPLE_XLSX}"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert result['type'] == 'xlsx_workbook'
        assert 'sheets' in result
        assert len(result['sheets']) > 0

    def test_workbook_has_sheet_metadata(self):
        """Test that workbook includes sheet metadata."""
        uri = f"xlsx://{SAMPLE_XLSX}"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        # Check first sheet has metadata
        sheet = result['sheets'][0]
        assert 'name' in sheet
        assert 'rows' in sheet
        assert 'cols' in sheet

    def test_workbook_includes_file_path(self):
        """Test that workbook result includes file path."""
        uri = f"xlsx://{SAMPLE_XLSX}"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert 'file' in result


@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="Test file not available")
class TestXlsxAdapterSheetExtraction:
    """Tests for sheet extraction functionality."""

    def test_extract_sheet_by_index(self):
        """Test extracting sheet by 0-based index."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert result['type'] == 'xlsx_sheet'
        assert 'sheet_name' in result
        assert 'rows' in result
        assert len(result['rows']) > 0

    def test_extract_sheet_by_name(self):
        """Test extracting sheet by name."""
        # Use known sheet name from QA Items.xlsx
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=J13"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert result['type'] == 'xlsx_sheet'
        assert 'J13' in result['sheet_name']
        assert 'rows' in result

    def test_extract_nonexistent_sheet(self):
        """Test extracting non-existent sheet raises error."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=NonExistentSheet"
        adapter = XlsxAdapter(uri)

        # Should raise ValueError for non-existent sheet
        with pytest.raises(ValueError, match="Sheet not found"):
            adapter.get_structure()

    def test_sheet_has_row_count(self):
        """Test that sheet result includes row count."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert 'rows_count' in result
        assert result['rows_count'] > 0

    def test_sheet_has_col_count(self):
        """Test that sheet result includes column count."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert 'cols_count' in result
        assert result['cols_count'] > 0


@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="Test file not available")
class TestXlsxAdapterCellRanges:
    """Tests for cell range extraction (A1 notation)."""

    def test_extract_cell_range(self):
        """Test extracting specific cell range."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=J13&range=A1:C5"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert result['type'] == 'xlsx_sheet'
        rows = result['rows']
        assert len(rows) == 5  # A1:C5 is 5 rows
        # Check that rows have at most 3 columns (some might have fewer due to empty cells)
        assert all(len(row) <= 3 for row in rows)
        # Check that at least one row has data in all 3 columns
        assert any(len(row) == 3 for row in rows)

    def test_column_letter_parsing(self):
        """Test that A1 notation columns are parsed correctly."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0&range=B2:D10"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        rows = result['rows']
        # Should have rows from 2 to 10 (9 rows) and columns B,C,D (3 cols)
        # But actual count depends on sheet content
        assert len(rows) <= 9
        assert all(len(row) <= 3 for row in rows if row)

    def test_single_cell_range(self):
        """Test extracting single cell."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0&range=A1:A1"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        rows = result['rows']
        assert len(rows) == 1
        assert len(rows[0]) >= 1


@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="Test file not available")
class TestXlsxAdapterRowLimiting:
    """Tests for row limiting functionality."""

    def test_limit_rows(self):
        """Test limiting number of rows returned."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0&limit=5"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        rows = result['rows']
        assert len(rows) == 5

    def test_limit_with_range(self):
        """Test limit combined with cell range."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0&range=A1:D100&limit=10"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        rows = result['rows']
        # Should be limited to 10 even if range specifies 100
        assert len(rows) == 10

    def test_limit_larger_than_sheet(self):
        """Test limit larger than actual sheet size."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=J13&limit=1000"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        # Should return all rows (sheet has ~63 rows)
        rows = result['rows']
        assert len(rows) <= 1000


@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="Test file not available")
class TestXlsxAdapterFormatParameter:
    """Tests for format query parameter."""

    def test_format_csv_parameter(self):
        """Test that format=csv is stored in result."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0&format=csv"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert result.get('preferred_format') == 'csv'

    def test_format_json_parameter(self):
        """Test that format=json is stored in result."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0&format=json"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert result.get('preferred_format') == 'json'

    def test_no_format_parameter(self):
        """Test that no format parameter doesn't add preferred_format."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        # Should not have preferred_format
        assert 'preferred_format' not in result or result.get('preferred_format') is None


class TestXlsxRenderer:
    """Tests for renderer methods."""

    def test_render_workbook_text(self, capsys):
        """Test rendering workbook in text format."""
        result = {
            'type': 'xlsx_workbook',
            'file': '/path/to/test.xlsx',
            'sheets': [
                {'name': 'Sheet1', 'dimension': 'A1:D10', 'rows': 10, 'cols': 4},
                {'name': 'Sheet2', 'dimension': 'A1:C5', 'rows': 5, 'cols': 3},
            ]
        }
        XlsxRenderer.render_structure(result, 'text')
        captured = capsys.readouterr()

        assert 'test.xlsx' in captured.out
        assert 'Sheet1' in captured.out
        assert 'Sheet2' in captured.out
        assert '10 rows' in captured.out

    def test_render_sheet_text(self, capsys):
        """Test rendering sheet data in text format."""
        result = {
            'type': 'xlsx_sheet',
            'sheet_name': 'Sales',
            'dimension': 'A1:C5',
            'rows_count': 5,
            'cols_count': 3,
            'rows': [
                ['Name', 'Price', 'Qty'],
                ['Item1', '10', '5'],
                ['Item2', '20', '3'],
            ]
        }
        XlsxRenderer.render_structure(result, 'text')
        captured = capsys.readouterr()

        assert 'Sales' in captured.out
        assert 'Name' in captured.out
        assert 'Item1' in captured.out

    def test_render_sheet_csv(self, capsys):
        """Test rendering sheet data in CSV format."""
        result = {
            'type': 'xlsx_sheet',
            'sheet_name': 'Sales',
            'rows': [
                ['Name', 'Price', 'Qty'],
                ['Item1', '10', '5'],
                ['Item2', '20', '3'],
            ],
            'preferred_format': 'csv'
        }
        XlsxRenderer.render_structure(result, 'text')  # format ignored, uses preferred
        captured = capsys.readouterr()

        # Should be CSV format
        assert 'Name,Price,Qty' in captured.out
        assert 'Item1,10,5' in captured.out

    def test_render_csv_with_commas(self, capsys):
        """Test CSV rendering with commas in data."""
        result = {
            'type': 'xlsx_sheet',
            'sheet_name': 'Test',
            'rows': [
                ['Name', 'Description'],
                ['Item', 'Value with, comma'],
            ],
            'preferred_format': 'csv'
        }
        XlsxRenderer.render_structure(result, 'text')
        captured = capsys.readouterr()

        # Comma should be properly escaped
        assert '"Value with, comma"' in captured.out

    def test_render_json(self, capsys):
        """Test JSON format rendering."""
        result = {
            'type': 'xlsx_sheet',
            'sheet_name': 'Test',
            'rows': [['A', 'B']],
        }
        XlsxRenderer.render_structure(result, 'json')
        captured = capsys.readouterr()

        assert '{' in captured.out
        assert '"type"' in captured.out

    def test_render_preferred_format_overrides(self, capsys):
        """Test that preferred_format in result overrides CLI format."""
        result = {
            'type': 'xlsx_sheet',
            'sheet_name': 'Test',
            'rows': [['A', 'B']],
            'preferred_format': 'csv'
        }
        # Pass 'text' as format, but preferred_format should override
        XlsxRenderer.render_structure(result, 'text')
        captured = capsys.readouterr()

        # Should be CSV (comma-separated), not table format
        assert 'A,B' in captured.out


@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="Test file not available")
class TestXlsxAdapterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_query_string(self):
        """Test URI with empty query string."""
        uri = f"xlsx://{SAMPLE_XLSX}?"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        # Should return workbook overview
        assert result['type'] == 'xlsx_workbook'

    def test_invalid_limit_value(self):
        """Test with non-numeric limit value."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=0&limit=invalid"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        # Should handle gracefully (ignore limit)
        assert result is not None

    def test_sheet_name_case_insensitive(self):
        """Test sheet name matching is case insensitive."""
        uri = f"xlsx://{SAMPLE_XLSX}?sheet=j13"  # lowercase
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        # Should still find J13 sheet
        assert result['type'] == 'xlsx_sheet'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
