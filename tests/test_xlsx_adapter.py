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


class TestXlsxAdapterCrossSheetSearch:
    """Tests for cross-sheet search functionality (BACK-003)."""

    @pytest.fixture
    def multi_sheet_xlsx(self, tmp_path):
        """Create a multi-sheet xlsx file for testing."""
        openpyxl = pytest.importorskip("openpyxl", reason="openpyxl not installed (pip install reveal-cli[xlsx])")
        wb = openpyxl.Workbook()

        # Sheet 1: Customers
        ws1 = wb.active
        ws1.title = "Customers"
        ws1.append(["ID", "Name", "Email"])
        ws1.append([1, "Alice Smith", "alice@example.com"])
        ws1.append([2, "Bob Jones", "bob@example.com"])
        ws1.append([3, "Charlie Brown", "charlie@example.com"])

        # Sheet 2: Orders
        ws2 = wb.create_sheet("Orders")
        ws2.append(["OrderID", "CustomerID", "Product", "Amount"])
        ws2.append([101, 1, "Widget", 29.99])
        ws2.append([102, 2, "Gadget", 49.99])
        ws2.append([103, 1, "Widget Pro", 79.99])

        # Sheet 3: Products
        ws3 = wb.create_sheet("Products")
        ws3.append(["SKU", "Name", "Price"])
        ws3.append(["W001", "Widget", 29.99])
        ws3.append(["G001", "Gadget", 49.99])
        ws3.append(["WP001", "Widget Pro", 79.99])

        path = tmp_path / "test_multi.xlsx"
        wb.save(path)
        return path

    def test_search_returns_search_type(self, multi_sheet_xlsx):
        """search=X returns xlsx_search result type."""
        uri = f"xlsx://{multi_sheet_xlsx}?search=Widget"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        assert result['type'] == 'xlsx_search'

    def test_search_finds_matches_across_sheets(self, multi_sheet_xlsx):
        """search=X scans all sheets and finds matches."""
        uri = f"xlsx://{multi_sheet_xlsx}?search=Widget"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()

        assert result['total_matches'] > 0
        # Widget appears in Orders and Products sheets
        sheet_names = [sr['sheet_name'] for sr in result['sheet_results']]
        assert 'Orders' in sheet_names
        assert 'Products' in sheet_names

    def test_search_case_insensitive(self, multi_sheet_xlsx):
        """search is case-insensitive."""
        uri_lower = f"xlsx://{multi_sheet_xlsx}?search=widget"
        uri_upper = f"xlsx://{multi_sheet_xlsx}?search=WIDGET"
        adapter_lower = XlsxAdapter(uri_lower)
        adapter_upper = XlsxAdapter(uri_upper)
        result_lower = adapter_lower.get_structure()
        result_upper = adapter_upper.get_structure()
        assert result_lower['total_matches'] == result_upper['total_matches']

    def test_search_no_matches(self, multi_sheet_xlsx):
        """search returns zero matches for absent term."""
        uri = f"xlsx://{multi_sheet_xlsx}?search=ZZZNOMATCH"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        assert result['total_matches'] == 0
        assert result['sheets_with_matches'] == 0
        assert result['sheet_results'] == []

    def test_search_groups_by_sheet(self, multi_sheet_xlsx):
        """search results are grouped by sheet."""
        uri = f"xlsx://{multi_sheet_xlsx}?search=Widget"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        for sr in result['sheet_results']:
            assert 'sheet_name' in sr
            assert 'matches' in sr
            assert isinstance(sr['matches'], list)

    def test_search_includes_row_number(self, multi_sheet_xlsx):
        """Each match includes the 1-based row number."""
        uri = f"xlsx://{multi_sheet_xlsx}?search=Alice"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        assert result['total_matches'] >= 1
        match = result['sheet_results'][0]['matches'][0]
        assert 'row_num' in match
        assert isinstance(match['row_num'], int)
        assert match['row_num'] >= 1

    def test_search_includes_cells(self, multi_sheet_xlsx):
        """Each match includes the full row cells."""
        uri = f"xlsx://{multi_sheet_xlsx}?search=Alice"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        match = result['sheet_results'][0]['matches'][0]
        assert 'cells' in match
        assert isinstance(match['cells'], list)
        assert any('Alice' in str(c) for c in match['cells'])

    def test_search_limit_respected(self, multi_sheet_xlsx):
        """?limit=N caps total search results."""
        uri = f"xlsx://{multi_sheet_xlsx}?search=Widget&limit=1"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        assert result['total_matches'] == 1

    def test_search_includes_pattern_in_result(self, multi_sheet_xlsx):
        """Result always echoes the search pattern."""
        uri = f"xlsx://{multi_sheet_xlsx}?search=Gadget"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        assert result['pattern'] == 'Gadget'


class TestXlsxSearchRenderer:
    """Tests for the search result renderer (BACK-003)."""

    def _capture(self, result, format='text'):
        old = sys.stdout
        sys.stdout = buf = StringIO()
        try:
            XlsxRenderer.render_structure(result, format=format)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def _make_result(self, pattern='test', total=2, sheet_results=None):
        if sheet_results is None:
            sheet_results = [
                {
                    'sheet_name': 'Sheet1',
                    'matches': [
                        {'row_num': 3, 'cells': ['foo', 'test value', 'bar']},
                        {'row_num': 7, 'cells': ['alpha', 'test again', 'beta']},
                    ],
                }
            ]
        return {
            'type': 'xlsx_search',
            'pattern': pattern,
            'total_matches': total,
            'sheets_with_matches': len(sheet_results),
            'sheet_results': sheet_results,
        }

    def test_render_shows_match_count(self):
        output = self._capture(self._make_result())
        assert '2 matches' in output
        assert '"test"' in output

    def test_render_shows_sheet_name(self):
        output = self._capture(self._make_result())
        assert 'Sheet1' in output

    def test_render_shows_row_numbers(self):
        output = self._capture(self._make_result())
        assert 'row' in output
        assert '3' in output
        assert '7' in output

    def test_render_shows_cell_values(self):
        output = self._capture(self._make_result())
        assert 'test value' in output

    def test_render_no_matches(self):
        result = self._make_result(total=0, sheet_results=[])
        result['total_matches'] = 0
        output = self._capture(result)
        assert 'No matches' in output

    def test_render_json_format(self):
        import json
        result = self._make_result()
        output = self._capture(result, format='json')
        parsed = json.loads(output)
        assert parsed['type'] == 'xlsx_search'
        assert parsed['pattern'] == 'test'


@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="Test file not available")
class TestXlsxCrossSheetSearchIntegration:
    """Integration tests against the real QA Items.xlsx file."""

    def test_search_returns_xlsx_search_type(self):
        uri = f"xlsx://{SAMPLE_XLSX}?search=2018"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        assert result['type'] == 'xlsx_search'

    def test_search_spans_multiple_sheets(self):
        uri = f"xlsx://{SAMPLE_XLSX}?search=2018"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        assert result['sheets_with_matches'] > 1

    def test_search_no_match(self):
        uri = f"xlsx://{SAMPLE_XLSX}?search=ZZZNEVEREXISTSZZZ"
        adapter = XlsxAdapter(uri)
        result = adapter.get_structure()
        assert result['total_matches'] == 0


# ---------------------------------------------------------------------------
# Power Pivot test infrastructure
# ---------------------------------------------------------------------------

POWERPIVOT_2013 = Path("/tmp/powerpivot-samples/Excel2013/PowerPivotTutorialSample.xlsx")
POWERPIVOT_2010 = Path("/tmp/powerpivot-samples/Excel2010/PowerPivotTutorialSample.xlsx")
POWERPIVOT_MODERN = Path("/tmp/powerpivot-samples/RetailAnalysis-no-PV.xlsx")


def _make_minimal_xlsx(tmp_path, extra_files=None):
    """Create a minimal valid xlsx zip file.  extra_files = {name: bytes}."""
    import zipfile
    p = tmp_path / "test.xlsx"
    with zipfile.ZipFile(p, 'w') as zf:
        zf.writestr('[Content_Types].xml', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>'
        ))
        zf.writestr('_rels/.rels', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ))
        zf.writestr('xl/workbook.xml', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
            '</workbook>'
        ))
        zf.writestr('xl/_rels/workbook.xml.rels', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>'
        ))
        zf.writestr('xl/worksheets/sheet1.xml', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData/></worksheet>'
        ))
        for name, content in (extra_files or {}).items():
            if isinstance(content, str):
                zf.writestr(name, content)
            else:
                zf.writestr(name, content)
    return p


def _make_xmla_item_bytes(tables, measures=None):
    """Build a minimal UTF-16 XMLA item blob with the Gemini CDATA wrapper."""
    dims_xml = ''
    for tname, cols in tables.items():
        attrs_xml = '<Attribute><ID>RowNumber</ID><Name>RowNumber</Name><Type>RowNumber</Type></Attribute>'
        for col in cols:
            attrs_xml += f'<Attribute><ID>{col}</ID><Name>{col}</Name></Attribute>'
        dims_xml += (
            f'<Dimension><ID>{tname}</ID><Name>{tname}</Name>'
            f'<Attributes>{attrs_xml}</Attributes></Dimension>'
        )

    mdx_text = ''
    for tname, mname, expr in (measures or []):
        mdx_text += f"CREATE MEASURE [Sandbox].'{tname}'[{mname}]={expr};"

    inner_xml = (
        '<?xml version="1.0" encoding="utf-16"?>'
        '<Create AllowOverwrite="true" xmlns="http://schemas.microsoft.com/analysisservices/2003/engine">'
        '<ObjectDefinition><Database>'
        f'<Dimensions>{dims_xml}</Dimensions>'
        f'<MdxScripts><MdxScript><Commands><Command><Text>{mdx_text}</Text></Command></Commands></MdxScript></MdxScripts>'
        '</Database></ObjectDefinition></Create>'
    )
    outer_xml = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Gemini xmlns="http://gemini/pivotcustomization/http://gemini/workbookcustomization/MetadataRecoveryInformation">'
        f'<CustomContent><![CDATA[{inner_xml}]]></CustomContent>'
        '</Gemini>'
    )
    return outer_xml.encode('utf-16')


def _make_pivot_cache_bytes(table_names):
    """Build a minimal pivotCacheDefinition with cacheHierarchy elements."""
    hierarchies = ''.join(
        f'<cacheHierarchy uniqueName="[{t}].[Col].[Col]"/>' for t in table_names
    ) + '<cacheHierarchy uniqueName="[Measures].[Total]"/>'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<pivotCacheDefinition xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<cacheHierarchies count="{len(table_names) + 1}">{hierarchies}</cacheHierarchies>'
        '</pivotCacheDefinition>'
    ).encode('utf-8')


class TestPowerPivotDetection:
    """Unit tests for _detect_powerpivot (model path detection)."""

    def test_detects_excel_2013_model_path(self, tmp_path):
        import zipfile
        p = _make_minimal_xlsx(tmp_path, {'xl/model/item.data': b''})
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            assert adapter._detect_powerpivot(zf) == 'xl/model/item.data'

    def test_detects_excel_2010_model_path(self, tmp_path):
        import zipfile
        p = _make_minimal_xlsx(tmp_path, {'xl/customData/item1.data': b''})
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            assert adapter._detect_powerpivot(zf) == 'xl/customData/item1.data'

    def test_prefers_2013_path_when_both_present(self, tmp_path):
        import zipfile
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'xl/customData/item1.data': b'',
        })
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            assert adapter._detect_powerpivot(zf) == 'xl/model/item.data'

    def test_returns_none_for_plain_xlsx(self, tmp_path):
        import zipfile
        p = _make_minimal_xlsx(tmp_path)
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            assert adapter._detect_powerpivot(zf) is None


class TestXmlaItemDetection:
    """Unit tests for _find_xmla_item (XMLA CDATA item location)."""

    def test_finds_xmla_item(self, tmp_path):
        import zipfile
        xmla_bytes = _make_xmla_item_bytes({'MyTable': ['Col1', 'Col2']})
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'customXml/item1.xml': xmla_bytes,
        })
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            found = adapter._find_xmla_item(zf)
        assert found == 'customXml/item1.xml'

    def test_returns_none_when_no_xmla(self, tmp_path):
        import zipfile
        non_xmla = '<?xml version="1.0"?><root/>'.encode('utf-8')
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'customXml/item1.xml': non_xmla,
        })
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            assert adapter._find_xmla_item(zf) is None

    def test_ignores_non_customxml_items(self, tmp_path):
        import zipfile
        xmla_bytes = _make_xmla_item_bytes({'T': ['C']})
        # Put XMLA in a path that doesn't match customXml/itemN.xml
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'xl/metadata/item1.xml': xmla_bytes,
        })
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            assert adapter._find_xmla_item(zf) is None


class TestXmlaParsing:
    """Unit tests for _parse_xmla with synthetic XMLA content."""

    @pytest.fixture
    def adapter_with_model(self, tmp_path):
        tables = {
            'SalesTable': ['Region', 'Amount', 'Date'],
            'ProductTable': ['SKU', 'Name', 'Price'],
        }
        measures = [('SalesTable', 'TotalSales', "SUM('SalesTable'[Amount])")]
        xmla_bytes = _make_xmla_item_bytes(tables, measures)
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'customXml/item1.xml': xmla_bytes,
        })
        return XlsxAdapter(f"xlsx://{p}"), p

    def test_extracts_table_names(self, adapter_with_model, tmp_path):
        import zipfile
        adapter, p = adapter_with_model
        with zipfile.ZipFile(p) as zf:
            item = adapter._find_xmla_item(zf)
            data = adapter._parse_xmla(zf, item)
        table_names = {t['name'] for t in data['tables']}
        assert 'SalesTable' in table_names
        assert 'ProductTable' in table_names

    def test_extracts_column_names(self, adapter_with_model, tmp_path):
        import zipfile
        adapter, p = adapter_with_model
        with zipfile.ZipFile(p) as zf:
            item = adapter._find_xmla_item(zf)
            data = adapter._parse_xmla(zf, item)
        sales_cols = next(t['columns'] for t in data['tables'] if t['name'] == 'SalesTable')
        assert 'Region' in sales_cols
        assert 'Amount' in sales_cols
        assert 'Date' in sales_cols

    def test_excludes_rownumber_column(self, adapter_with_model, tmp_path):
        import zipfile
        adapter, p = adapter_with_model
        with zipfile.ZipFile(p) as zf:
            item = adapter._find_xmla_item(zf)
            data = adapter._parse_xmla(zf, item)
        all_cols = [c for t in data['tables'] for c in t['columns']]
        assert 'RowNumber' not in all_cols

    def test_extracts_measures(self, adapter_with_model, tmp_path):
        import zipfile
        adapter, p = adapter_with_model
        with zipfile.ZipFile(p) as zf:
            item = adapter._find_xmla_item(zf)
            data = adapter._parse_xmla(zf, item)
        assert len(data['measures']) == 1
        m = data['measures'][0]
        assert m['name'] == 'TotalSales'
        assert m['table'] == 'SalesTable'
        assert 'SUM' in m['expr']

    def test_xmla_available_flag(self, adapter_with_model, tmp_path):
        import zipfile
        adapter, p = adapter_with_model
        with zipfile.ZipFile(p) as zf:
            item = adapter._find_xmla_item(zf)
            data = adapter._parse_xmla(zf, item)
        assert data['xmla_available'] is True


class TestPivotCacheFallback:
    """Unit tests for _parse_pivot_cache."""

    def test_extracts_table_names_from_pivot_cache(self, tmp_path):
        import zipfile
        tables = ['Sales', 'Products', 'Customers']
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'xl/pivotCache/pivotCacheDefinition1.xml': _make_pivot_cache_bytes(tables),
        })
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            data = adapter._parse_pivot_cache(zf)
        table_names = {t['name'] for t in data['tables']}
        assert 'Sales' in table_names
        assert 'Products' in table_names
        assert 'Customers' in table_names

    def test_excludes_measures_table(self, tmp_path):
        import zipfile
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'xl/pivotCache/pivotCacheDefinition1.xml': _make_pivot_cache_bytes(['MyTable']),
        })
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            data = adapter._parse_pivot_cache(zf)
        table_names = {t['name'] for t in data['tables']}
        assert 'Measures' not in table_names

    def test_returns_empty_measures(self, tmp_path):
        import zipfile
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'xl/pivotCache/pivotCacheDefinition1.xml': _make_pivot_cache_bytes(['T']),
        })
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            data = adapter._parse_pivot_cache(zf)
        assert data['measures'] == []
        assert data['xmla_available'] is False


class TestPowerPivotGetStructure:
    """Unit tests for the get_structure() powerpivot dispatch and result shapes."""

    @pytest.fixture
    def pp_adapter(self, tmp_path):
        tables = {'Orders': ['OrderID', 'Amount'], 'Customers': ['CustID', 'Name']}
        measures = [('Orders', 'TotalRevenue', "SUM('Orders'[Amount])")]
        xmla_bytes = _make_xmla_item_bytes(tables, measures)
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'customXml/item1.xml': xmla_bytes,
        })
        return XlsxAdapter(f"xlsx://{p}")

    def test_powerpivot_tables_returns_powerpivot_type(self, pp_adapter):
        pp_adapter.query_params['powerpivot'] = 'tables'
        result = pp_adapter.get_structure()
        assert result['type'] == 'xlsx_powerpivot'

    def test_powerpivot_schema_has_tables(self, pp_adapter):
        pp_adapter.query_params['powerpivot'] = 'schema'
        result = pp_adapter.get_structure()
        assert result['has_model'] is True
        assert len(result['tables']) == 2

    def test_powerpivot_dax_has_measures(self, pp_adapter):
        pp_adapter.query_params['powerpivot'] = 'dax'
        result = pp_adapter.get_structure()
        assert len(result['measures']) == 1
        assert result['measures'][0]['name'] == 'TotalRevenue'

    def test_workbook_overview_has_banner(self, pp_adapter):
        result = pp_adapter.get_structure()
        assert result['type'] == 'xlsx_workbook'
        assert 'powerpivot_banner' in result
        banner = result['powerpivot_banner']
        assert banner['model_path'] == 'xl/model/item.data'
        assert 'Orders' in banner['table_names']

    def test_plain_xlsx_has_no_banner(self, tmp_path):
        p = _make_minimal_xlsx(tmp_path)
        adapter = XlsxAdapter(f"xlsx://{p}")
        result = adapter.get_structure()
        assert result['type'] == 'xlsx_workbook'
        assert 'powerpivot_banner' not in result

    def test_no_model_returns_has_model_false(self, tmp_path):
        p = _make_minimal_xlsx(tmp_path)
        adapter = XlsxAdapter(f"xlsx://{p}")
        adapter.query_params['powerpivot'] = 'schema'
        result = adapter.get_structure()
        assert result['type'] == 'xlsx_powerpivot'
        assert result['has_model'] is False


class TestPowerPivotRenderer:
    """Unit tests for XlsxRenderer._render_powerpivot output."""

    def _capture(self, result, format='text'):
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            XlsxRenderer.render_structure(result, format)
            return sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

    def _make_result(self, mode='schema', xmla=True, tables=None, measures=None):
        return {
            'type': 'xlsx_powerpivot',
            'file': '/tmp/test.xlsx',
            'has_model': True,
            'mode': mode,
            'xmla_available': xmla,
            'model_path': 'xl/model/item.data',
            'tables': tables or [
                {'name': 'SalesTable', 'columns': ['Region', 'Amount']},
                {'name': 'ProductTable', 'columns': ['SKU', 'Price']},
            ],
            'measures': measures or [
                {'name': 'TotalSales', 'table': 'SalesTable', 'expr': "SUM('SalesTable'[Amount])"},
            ],
        }

    def test_schema_shows_table_names(self):
        output = self._capture(self._make_result(mode='schema'))
        assert 'SalesTable' in output
        assert 'ProductTable' in output

    def test_schema_shows_column_names(self):
        output = self._capture(self._make_result(mode='schema'))
        assert 'Region' in output
        assert 'Amount' in output

    def test_schema_shows_measures(self):
        output = self._capture(self._make_result(mode='schema'))
        assert 'TotalSales' in output

    def test_tables_mode_shows_column_count(self):
        output = self._capture(self._make_result(mode='tables'))
        assert '2 columns' in output

    def test_dax_mode_shows_expression(self):
        output = self._capture(self._make_result(mode='dax'))
        assert 'SUM' in output
        assert 'TotalSales' in output

    def test_measures_mode_shows_table_name(self):
        output = self._capture(self._make_result(mode='measures'))
        assert 'SalesTable' in output

    def test_no_model_shows_message(self):
        result = {'type': 'xlsx_powerpivot', 'file': '/tmp/test.xlsx', 'has_model': False, 'mode': 'schema'}
        output = self._capture(result)
        assert 'No Power Pivot' in output

    def test_modern_file_dax_shows_install_hint(self):
        result = self._make_result(mode='dax', xmla=False, measures=[])
        output = self._capture(result)
        assert 'powerpivot' in output.lower() or 'XMLA' in output

    def test_json_format_returns_valid_json(self):
        import json
        result = self._make_result(mode='schema')
        output = self._capture(result, format='json')
        parsed = json.loads(output)
        assert parsed['type'] == 'xlsx_powerpivot'


@pytest.mark.skipif(not POWERPIVOT_2013.exists(), reason="Power Pivot sample files not in /tmp/powerpivot-samples/")
class TestPowerPivotIntegration2013:
    """Integration tests against the real Excel 2013 Contoso sample file."""

    def test_banner_shown_in_overview(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}")
        result = adapter.get_structure()
        assert result['type'] == 'xlsx_workbook'
        assert 'powerpivot_banner' in result

    def test_banner_has_9_tables(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}")
        result = adapter.get_structure()
        assert len(result['powerpivot_banner']['table_names']) == 9

    def test_schema_extracts_9_tables(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=schema")
        result = adapter.get_structure()
        assert result['has_model'] is True
        assert result['xmla_available'] is True
        assert len(result['tables']) == 9

    def test_schema_extracts_dimdatecol_columns(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=schema")
        result = adapter.get_structure()
        dim_date = next(t for t in result['tables'] if t['name'] == 'dbo_DimDate')
        assert len(dim_date['columns']) == 29

    def test_dax_extracts_3_measures(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=dax")
        result = adapter.get_structure()
        assert len(result['measures']) == 3

    def test_dax_measure_names(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=dax")
        result = adapter.get_structure()
        names = {m['name'] for m in result['measures']}
        assert 'Sum of TotalSales' in names

    def test_dax_expressions_have_sum(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=dax")
        result = adapter.get_structure()
        exprs = {m['expr'] for m in result['measures']}
        assert any('SUM' in e for e in exprs)

    def test_tables_mode(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=tables")
        result = adapter.get_structure()
        assert result['type'] == 'xlsx_powerpivot'
        assert len(result['tables']) == 9


@pytest.mark.skipif(not POWERPIVOT_2010.exists(), reason="Power Pivot sample files not in /tmp/powerpivot-samples/")
class TestPowerPivotIntegration2010:
    """Integration tests against the real Excel 2010 Contoso sample file."""

    def test_detects_2010_model_path(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2010}")
        result = adapter.get_structure()
        banner = result.get('powerpivot_banner', {})
        assert banner.get('model_path') == 'xl/customData/item1.data'

    def test_extracts_same_9_tables_as_2013(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2010}?powerpivot=schema")
        result = adapter.get_structure()
        assert len(result['tables']) == 9


@pytest.mark.skipif(not POWERPIVOT_MODERN.exists(), reason="Power Pivot sample files not in /tmp/powerpivot-samples/")
class TestPowerPivotIntegrationModern:
    """Integration tests against a modern Power BI xlsx file (no XMLA)."""

    def test_banner_present(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_MODERN}")
        result = adapter.get_structure()
        assert 'powerpivot_banner' in result

    def test_xmla_not_available(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_MODERN}?powerpivot=schema")
        result = adapter.get_structure()
        assert result['xmla_available'] is False

    def test_table_names_from_pivot_cache(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_MODERN}?powerpivot=tables")
        result = adapter.get_structure()
        assert len(result['tables']) > 0

    def test_dax_mode_shows_not_available(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_MODERN}?powerpivot=dax")
        result = adapter.get_structure()
        # Should not raise, should return gracefully
        assert result['type'] == 'xlsx_powerpivot'
        assert result['has_model'] is True


def _make_xmla_item_bytes_with_relationships(tables, measures=None, relationships=None):
    """Build a UTF-16 XMLA item blob including Relationship elements."""
    dims_xml = ''
    for tname, cols in tables.items():
        attrs_xml = '<Attribute><ID>RowNumber</ID><Name>RowNumber</Name><Type>RowNumber</Type></Attribute>'
        for col in cols:
            attrs_xml += f'<Attribute><ID>{col}</ID><Name>{col}</Name></Attribute>'
        dims_xml += (
            f'<Dimension><ID>{tname}</ID><Name>{tname}</Name>'
            f'<Attributes>{attrs_xml}</Attributes></Dimension>'
        )

    mdx_text = ''
    for tname, mname, expr in (measures or []):
        mdx_text += f"CREATE MEASURE [Sandbox].'{tname}'[{mname}]={expr};"

    rels_xml = ''
    for from_table, from_col, to_table, to_col in (relationships or []):
        rels_xml += (
            f'<Relationship><ID>R_{from_table}_{to_table}</ID>'
            f'<FromRelationshipEnd>'
            f'<DimensionID>{from_table}</DimensionID>'
            f'<Multiplicity>Many</Multiplicity>'
            f'<Attributes><Attribute><AttributeID>{from_col}</AttributeID></Attribute></Attributes>'
            f'</FromRelationshipEnd>'
            f'<ToRelationshipEnd>'
            f'<DimensionID>{to_table}</DimensionID>'
            f'<Multiplicity>One</Multiplicity>'
            f'<Attributes><Attribute><AttributeID>{to_col}</AttributeID></Attribute></Attributes>'
            f'</ToRelationshipEnd>'
            f'</Relationship>'
        )

    inner_xml = (
        '<?xml version="1.0" encoding="utf-16"?>'
        '<Create AllowOverwrite="true" xmlns="http://schemas.microsoft.com/analysisservices/2003/engine">'
        '<ObjectDefinition><Database>'
        f'<Dimensions>{dims_xml}</Dimensions>'
        f'<MdxScripts><MdxScript><Commands><Command><Text>{mdx_text}</Text></Command></Commands></MdxScript></MdxScripts>'
        f'<Relationships>{rels_xml}</Relationships>'
        '</Database></ObjectDefinition></Create>'
    )
    outer_xml = (
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<Gemini xmlns="http://gemini/pivotcustomization/http://gemini/workbookcustomization/MetadataRecoveryInformation">'
        f'<CustomContent><![CDATA[{inner_xml}]]></CustomContent>'
        '</Gemini>'
    )
    return outer_xml.encode('utf-16')


class TestPowerPivotRelationships:
    """Unit tests for ?powerpivot=relationships extraction and rendering."""

    @pytest.fixture
    def rel_adapter(self, tmp_path):
        tables = {
            'Orders': ['OrderID', 'CustomerID', 'Amount'],
            'Customers': ['CustID', 'Name'],
            'Calendar': ['DateKey', 'Year'],
        }
        relationships = [
            ('Orders', 'CustomerID', 'Customers', 'CustID'),
            ('Orders', 'OrderDate', 'Calendar', 'DateKey'),
        ]
        xmla_bytes = _make_xmla_item_bytes_with_relationships(tables, relationships=relationships)
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'customXml/item1.xml': xmla_bytes,
        })
        return XlsxAdapter(f"xlsx://{p}")

    def test_relationships_mode_returns_powerpivot_type(self, rel_adapter):
        rel_adapter.query_params['powerpivot'] = 'relationships'
        result = rel_adapter.get_structure()
        assert result['type'] == 'xlsx_powerpivot'

    def test_relationships_extracted_count(self, rel_adapter):
        rel_adapter.query_params['powerpivot'] = 'relationships'
        result = rel_adapter.get_structure()
        assert len(result['relationships']) == 2

    def test_relationship_from_fields(self, rel_adapter):
        rel_adapter.query_params['powerpivot'] = 'relationships'
        result = rel_adapter.get_structure()
        rel = next(r for r in result['relationships'] if r['from']['table'] == 'Orders'
                   and r['to']['table'] == 'Customers')
        assert rel['from']['columns'] == ['CustomerID']
        assert rel['from']['multiplicity'] == 'Many'

    def test_relationship_to_fields(self, rel_adapter):
        rel_adapter.query_params['powerpivot'] = 'relationships'
        result = rel_adapter.get_structure()
        rel = next(r for r in result['relationships'] if r['to']['table'] == 'Customers')
        assert rel['to']['columns'] == ['CustID']
        assert rel['to']['multiplicity'] == 'One'

    def test_schema_result_includes_relationships(self, rel_adapter):
        rel_adapter.query_params['powerpivot'] = 'schema'
        result = rel_adapter.get_structure()
        assert 'relationships' in result
        assert len(result['relationships']) == 2

    def test_pivot_cache_fallback_returns_empty_relationships(self, tmp_path):
        import zipfile
        cache_bytes = _make_pivot_cache_bytes(['Sales', 'Products'])
        p = _make_minimal_xlsx(tmp_path, {
            'xl/model/item.data': b'',
            'xl/pivotCache/pivotCacheDefinition1.xml': cache_bytes,
        })
        adapter = XlsxAdapter(f"xlsx://{p}")
        with zipfile.ZipFile(p) as zf:
            data = adapter._parse_pivot_cache(zf)
        assert data['relationships'] == []

    def test_renderer_relationships_mode(self, rel_adapter):
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            rel_adapter.query_params['powerpivot'] = 'relationships'
            result = rel_adapter.get_structure()
            XlsxRenderer.render_structure(result, 'text')
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        assert 'Orders' in output
        assert 'Customers' in output
        assert 'Many' in output
        assert 'One' in output

    def test_renderer_relationships_no_xmla(self):
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            result = {
                'type': 'xlsx_powerpivot', 'file': '/tmp/test.xlsx',
                'has_model': True, 'mode': 'relationships',
                'xmla_available': False, 'relationships': [],
            }
            XlsxRenderer.render_structure(result, 'text')
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout
        assert 'not available' in output.lower() or 'XMLA' in output


@pytest.mark.skipif(not POWERPIVOT_2013.exists(), reason="Power Pivot sample files not in /tmp/powerpivot-samples/")
class TestPowerPivotRelationshipsIntegration2013:
    """Integration tests for ?powerpivot=relationships against the Contoso 2013 sample."""

    def test_relationships_mode_returns_list(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=relationships")
        result = adapter.get_structure()
        assert isinstance(result['relationships'], list)

    def test_relationships_have_expected_fields(self):
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=relationships")
        result = adapter.get_structure()
        for rel in result['relationships']:
            assert 'from' in rel and 'to' in rel
            assert 'table' in rel['from'] and 'columns' in rel['from']
            assert 'multiplicity' in rel['from']

    def test_relationships_result_is_list(self):
        # Contoso tutorial has no explicit relationships defined; verify we return an empty list
        adapter = XlsxAdapter(f"xlsx://{POWERPIVOT_2013}?powerpivot=relationships")
        result = adapter.get_structure()
        assert result['relationships'] == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
