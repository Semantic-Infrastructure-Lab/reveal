"""Xlsx adapter for xlsx:// URIs - Excel spreadsheet analysis and extraction."""

import sys
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from .base import ResourceAdapter, register_adapter, register_renderer
from ..analyzers.office.openxml import XlsxAnalyzer
from ..utils.results import ResultBuilder


class XlsxRenderer:
    """Renderer for xlsx adapter results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render xlsx structure overview.

        Args:
            result: Structure dict from XlsxAdapter.get_structure()
            format: Output format ('text', 'json', 'grep', 'csv')
        """
        from ..main import safe_json_dumps

        # Check for format preference in result (from ?format=csv query param)
        preferred_format = result.get('preferred_format', format)

        if preferred_format == 'json':
            print(safe_json_dumps(result))
            return

        # Check if this is a sheet data result or workbook overview
        if result.get('type') == 'xlsx_sheet':
            XlsxRenderer._render_sheet_data(result, preferred_format)
        else:
            XlsxRenderer._render_workbook(result, preferred_format)

    @staticmethod
    def _render_workbook(result: dict, format: str) -> None:
        """Render workbook overview."""
        file_path = result.get('file', result.get('source', 'Unknown'))
        print(f"File: {Path(file_path).name}\n")

        sheets = result.get('sheets', [])
        if not sheets:
            print("No sheets found")
            return

        print(f"Sheets ({len(sheets)}):")
        for i, sheet in enumerate(sheets, 1):
            name = sheet.get('name', f'Sheet{i}')
            dim = sheet.get('dimension', '')
            rows = sheet.get('rows', 0)
            cols = sheet.get('cols', 0)
            formulas = sheet.get('formulas', 0)

            dim_str = f" ({dim})" if dim else ""
            formula_str = f", {formulas} formulas" if formulas > 0 else ""
            print(f"  :{i:2}   {name}{dim_str} - {rows} rows, {cols} cols{formula_str}")

    @staticmethod
    def _render_sheet_data(result: dict, format: str) -> None:
        """Render sheet data as table or CSV."""
        sheet_name = result.get('sheet_name', 'Sheet')
        rows_data = result.get('rows', [])

        if format == 'csv':
            XlsxRenderer._render_csv(rows_data)
        else:
            XlsxRenderer._render_table(result, rows_data)

    @staticmethod
    def _render_csv(rows_data: List[List[Any]]) -> None:
        """Render as CSV format."""
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        for row in rows_data:
            writer.writerow(row)
        print(output.getvalue(), end='')

    @staticmethod
    def _render_table(result: dict, rows_data: List[List[Any]]) -> None:
        """Render as formatted table."""
        sheet_name = result.get('sheet_name', 'Sheet')
        dim = result.get('dimension', '')
        rows_count = result.get('rows_count', len(rows_data))
        cols_count = result.get('cols_count', 0)

        # Header
        print(f"Sheet: {sheet_name}", end='')
        if dim:
            print(f" ({dim})", end='')
        print(f"\nRows: {rows_count}, Cols: {cols_count}\n")

        # Data with line numbers
        for i, row in enumerate(rows_data, 1):
            row_str = ' | '.join(str(cell) if cell is not None else '' for cell in row)
            print(f"{i:6}  {row_str}")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific xlsx element (same as structure for sheets)."""
        XlsxRenderer.render_structure(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error accessing Excel file: {error}", file=sys.stderr)


@register_adapter('xlsx')
@register_renderer(XlsxRenderer)
class XlsxAdapter(ResourceAdapter):
    """Adapter for exploring Excel spreadsheets via xlsx:// URIs.

    Example URIs:
        xlsx:///path/to/file.xlsx                    # Workbook overview (all sheets)
        xlsx:///path/to/file.xlsx?sheet=0            # First sheet (by index)
        xlsx:///path/to/file.xlsx?sheet=Sales        # Sheet by name
        xlsx:///path/to/file.xlsx?sheet=Sales&range=A1:C10  # Cell range
        xlsx:///path/to/file.xlsx?search=revenue     # Search across sheets
        xlsx:///path/to/file.xlsx?sheet=Sales&format=csv  # Export as CSV
        xlsx:///path/to/file.xlsx?sheet=Sales&limit=50    # Limit rows
    """

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for xlsx:// adapter."""
        return {
            'adapter': 'xlsx',
            'description': 'Excel spreadsheet inspection and data extraction',
            'uri_syntax': 'xlsx:///path/to/file.xlsx[?query_params]',
            'query_params': {
                'sheet': {
                    'type': 'string|integer',
                    'description': 'Sheet to extract (name or 0-based index)',
                    'examples': ['sheet=Sales', 'sheet=0']
                },
                'range': {
                    'type': 'string',
                    'description': 'Cell range in A1 notation (e.g., A1:C10)',
                    'examples': ['range=A1:C10', 'range=B5:D20']
                },
                'search': {
                    'type': 'string',
                    'description': 'Search for text across all sheets',
                    'examples': ['search=revenue', 'search=total']
                },
                'format': {
                    'type': 'string',
                    'description': 'Output format (text, json, csv)',
                    'examples': ['format=csv', 'format=json']
                },
                'limit': {
                    'type': 'integer',
                    'description': 'Maximum number of rows to return',
                    'examples': ['limit=100', 'limit=50']
                },
                'formulas': {
                    'type': 'boolean',
                    'description': 'Show formulas instead of values',
                    'examples': ['formulas=true']
                }
            },
            'elements': {},  # Dynamic - sheets determined by file
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'xlsx_workbook',
                    'description': 'Workbook overview with sheet list',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'xlsx_workbook'},
                            'file': {'type': 'string'},
                            'sheets': {'type': 'array'}
                        }
                    }
                },
                {
                    'type': 'xlsx_sheet',
                    'description': 'Sheet data with rows and columns',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'xlsx_sheet'},
                            'sheet_name': {'type': 'string'},
                            'rows': {'type': 'array'},
                            'dimension': {'type': 'string'}
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'xlsx:///path/to/file.xlsx',
                    'description': 'List all sheets in workbook',
                    'output_type': 'xlsx_workbook'
                },
                {
                    'uri': 'xlsx:///path/to/file.xlsx?sheet=0',
                    'description': 'Extract first sheet',
                    'output_type': 'xlsx_sheet'
                },
                {
                    'uri': 'xlsx:///path/to/file.xlsx?sheet=Sales&range=A1:C10',
                    'description': 'Extract cell range from specific sheet',
                    'output_type': 'xlsx_sheet'
                },
                {
                    'uri': 'xlsx:///path/to/file.xlsx?sheet=Sales&format=csv',
                    'description': 'Export sheet as CSV',
                    'output_type': 'xlsx_sheet'
                }
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for xlsx:// adapter."""
        return {
            'name': 'xlsx',
            'description': 'Extract and analyze Excel spreadsheet data',
            'syntax': 'xlsx:///path/to/file.xlsx[?query_params]',
            'examples': [
                {
                    'uri': 'xlsx:///data/sales.xlsx',
                    'description': 'Show workbook overview with all sheets'
                },
                {
                    'uri': 'xlsx:///data/sales.xlsx?sheet=Q1',
                    'description': 'Extract "Q1" sheet data'
                },
                {
                    'uri': 'xlsx:///data/sales.xlsx?sheet=0',
                    'description': 'Extract first sheet (by index)'
                },
                {
                    'uri': 'xlsx:///data/sales.xlsx?sheet=Q1&range=A1:D10',
                    'description': 'Extract cell range A1:D10 from Q1 sheet'
                },
                {
                    'uri': 'xlsx:///data/sales.xlsx?sheet=Q1&limit=50',
                    'description': 'Extract first 50 rows from Q1 sheet'
                },
                {
                    'uri': 'xlsx:///data/sales.xlsx?sheet=Q1&format=csv',
                    'description': 'Export Q1 sheet as CSV'
                },
                {
                    'uri': 'xlsx:///data/sales.xlsx?search=revenue',
                    'description': 'Search for "revenue" across all sheets'
                }
            ],
            'features': [
                'Workbook overview with sheet list',
                'Sheet extraction by name or index',
                'Cell range extraction (A1 notation)',
                'CSV export',
                'Row limiting',
                'Cross-sheet search',
                'JSON and text output'
            ],
            'try_now': [
                "reveal xlsx:///path/to/file.xlsx",
                "reveal xlsx:///path/to/file.xlsx?sheet=0",
            ],
            'workflows': [
                {
                    'name': 'Extract Sheet Data',
                    'scenario': 'Export Excel sheet to CSV for processing',
                    'steps': [
                        "reveal xlsx:///data/sales.xlsx              # See all sheets",
                        "reveal xlsx:///data/sales.xlsx?sheet=Q1&format=csv > output.csv",
                    ],
                },
                {
                    'name': 'Quick Data Inspection',
                    'scenario': 'Preview large Excel file',
                    'steps': [
                        "reveal xlsx:///data/huge.xlsx              # List sheets",
                        "reveal xlsx:///data/huge.xlsx?sheet=Summary&limit=20  # Preview first 20 rows",
                    ],
                }
            ],
            'output_formats': ['text', 'json', 'csv'],
            'see_also': ['stats://', 'json://']
        }

    def __init__(self, connection_string: str):
        """Initialize xlsx adapter.

        Args:
            connection_string: xlsx:///path/to/file.xlsx?query_params
        """
        self.connection_string = connection_string
        self.file_path: Optional[Path] = None
        self.query_params: Dict[str, str] = {}
        self.analyzer: Optional[XlsxAnalyzer] = None

        self._parse_uri(connection_string)
        self._init_analyzer()

    def _parse_uri(self, uri: str) -> None:
        """Parse xlsx:// URI into file path and query parameters.

        Args:
            uri: xlsx:///path/to/file.xlsx?param=value

        Raises:
            ValueError: If URI format is invalid
        """
        if not uri:
            raise ValueError("xlsx:// URI required: xlsx:///path/to/file.xlsx")

        # Remove xlsx:// prefix
        if uri.startswith("xlsx://"):
            uri = uri[7:]

        # Split path and query string
        if '?' in uri:
            path_part, query_part = uri.split('?', 1)
            self.query_params = self._parse_query_string(query_part)
        else:
            path_part = uri
            self.query_params = {}

        # Handle absolute vs relative paths
        if path_part.startswith('/'):
            self.file_path = Path(path_part)
        else:
            self.file_path = Path.cwd() / path_part

        if not self.file_path.exists():
            raise ValueError(
                f"Invalid file path (file not found): {self.file_path}\n"
                f"Example: reveal xlsx:///path/to/existing/file.xlsx"
            )

        if not self.file_path.suffix.lower() in ('.xlsx', '.xlsm'):
            raise ValueError(
                f"Invalid Excel format: {self.file_path}\n"
                f"Supported formats: .xlsx, .xlsm\n"
                f"Example: reveal xlsx:///data/sales.xlsx"
            )

    def _parse_query_string(self, query: str) -> Dict[str, str]:
        """Parse query string into dict.

        Args:
            query: param1=value1&param2=value2

        Returns:
            Dict of query parameters
        """
        params = {}
        for part in query.split('&'):
            if '=' in part:
                key, value = part.split('=', 1)
                params[key] = value
            else:
                params[part] = 'true'
        return params

    def _init_analyzer(self) -> None:
        """Initialize XlsxAnalyzer for the file."""
        if self.file_path:
            self.analyzer = XlsxAnalyzer(str(self.file_path))

    def get_structure(self) -> Dict[str, Any]:
        """Get workbook structure or sheet data based on query params.

        Returns:
            Dict containing workbook overview or sheet data
        """
        if not self.analyzer:
            raise ValueError("No file loaded")

        # Check for sheet parameter - if present, extract sheet data
        sheet_param = self.query_params.get('sheet')
        if sheet_param is not None:
            return self._get_sheet_data(sheet_param)

        # Check for search parameter
        search_param = self.query_params.get('search')
        if search_param:
            return self._search_sheets(search_param)

        # Default: return workbook overview
        return self._get_workbook_overview()

    def _get_workbook_overview(self) -> Dict[str, Any]:
        """Get overview of all sheets in workbook."""
        if self.analyzer is None:
            return ResultBuilder.create_error(
                result_type='xlsx_workbook',
                source=self.file_path or Path('unknown'),
                error="Analyzer not initialized"
            )
        structure = self.analyzer.get_structure()
        sheets_data = structure.get('sheets', [])

        # Enhance with sheet metadata
        enhanced_sheets = []
        for sheet_info in sheets_data:
            # Parse the name to extract metadata
            name = sheet_info.get('name', '')
            # Name format: "Sheet Name (A1:Z100) - 100 rows, 26 cols, 5 formulas"
            match = re.match(r'([^(]+?)(?:\s*\(([^)]+)\))?\s*-\s*(\d+)\s*rows,\s*(\d+)\s*cols(?:,\s*(\d+)\s*formulas)?', name)

            if match:
                sheet_name = match.group(1).strip()
                dimension = match.group(2) or ''
                rows = int(match.group(3))
                cols = int(match.group(4))
                formulas = int(match.group(5)) if match.group(5) else 0

                enhanced_sheets.append({
                    'name': sheet_name,
                    'dimension': dimension,
                    'rows': rows,
                    'cols': cols,
                    'formulas': formulas,
                    'line': sheet_info.get('line')
                })
            else:
                # Fallback if parsing fails
                enhanced_sheets.append({
                    'name': name,
                    'line': sheet_info.get('line')
                })

        # Build result data
        result_data = {
            'file': str(self.file_path),
            'sheets': enhanced_sheets
        }

        # Add preferred format if specified in query params
        format_param = self.query_params.get('format')
        if format_param:
            result_data['preferred_format'] = format_param

        return ResultBuilder.create(
            result_type='xlsx_workbook',
            source=self.file_path or Path('unknown'),
            data=result_data
        )

    def _get_sheet_data(self, sheet_identifier: str) -> Dict[str, Any]:
        """Extract data from specific sheet.

        Args:
            sheet_identifier: Sheet name or index (0-based)

        Returns:
            Dict with sheet data
        """
        # Get sheet name
        sheet_name = self._resolve_sheet_name(sheet_identifier)
        if not sheet_name:
            raise ValueError(f"Sheet not found: {sheet_identifier}")

        # Extract sheet using analyzer
        if self.analyzer is None:
            raise ValueError("Analyzer not initialized")
        sheet_result = self.analyzer.extract_element('sheet', sheet_name)
        if not sheet_result:
            raise ValueError(f"Failed to extract sheet: {sheet_name}")

        # Parse the sheet data
        source_text = sheet_result.get('source', '')
        lines = source_text.split('\n') if source_text else []
        rows_data = self._parse_sheet_lines(lines)

        # Apply cell range if specified
        range_param = self.query_params.get('range')
        if range_param:
            rows_data = self._apply_cell_range(rows_data, range_param)

        # Apply row limit if specified
        limit_param = self.query_params.get('limit')
        if limit_param:
            try:
                limit = int(limit_param)
                rows_data = rows_data[:limit]
            except ValueError:
                pass  # Ignore invalid limit

        # Get sheet metadata
        sheet_info = self._get_sheet_info(sheet_name)

        # Build result data
        result_data = {
            'sheet_name': sheet_name,
            'rows': rows_data,
            'dimension': sheet_info.get('dimension', ''),
            'rows_count': sheet_info.get('rows', len(rows_data)),
            'cols_count': sheet_info.get('cols', len(rows_data[0]) if rows_data else 0)
        }

        # Add preferred format if specified in query params
        format_param = self.query_params.get('format')
        if format_param:
            result_data['preferred_format'] = format_param

        return ResultBuilder.create(
            result_type='xlsx_sheet',
            source=self.file_path or Path('unknown'),
            data=result_data
        )

    def _resolve_sheet_name(self, identifier: str) -> Optional[str]:
        """Resolve sheet identifier to sheet name.

        Args:
            identifier: Sheet name or index (e.g., "Sales" or "0")

        Returns:
            Sheet name, or None if not found
        """
        if self.analyzer is None:
            return None
        structure = self.analyzer.get_structure()
        sheets = structure.get('sheets', [])

        # Try as index first
        try:
            index = int(identifier)
            if 0 <= index < len(sheets):
                name = sheets[index].get('name', '')
                # Extract just the sheet name (before dimension)
                match = re.match(r'([^(]+)', name)
                return match.group(1).strip() if match else name
        except ValueError:
            pass

        # Try as name - case insensitive search
        identifier_lower = identifier.lower()
        for sheet in sheets:
            name = sheet.get('name', '')
            match = re.match(r'([^(]+)', name)
            if match:
                sheet_name = match.group(1).strip()
                if sheet_name.lower() == identifier_lower or identifier_lower in sheet_name.lower():
                    return sheet_name

        return None

    def _get_sheet_info(self, sheet_name: str) -> Dict[str, Any]:
        """Get metadata for a specific sheet.

        Args:
            sheet_name: Sheet name

        Returns:
            Dict with sheet metadata
        """
        if self.analyzer is None:
            return {'name': sheet_name}
        structure = self.analyzer.get_structure()
        sheets = structure.get('sheets', [])

        for sheet in sheets:
            name = sheet.get('name', '')
            if sheet_name in name:
                match = re.match(r'([^(]+?)(?:\s*\(([^)]+)\))?\s*-\s*(\d+)\s*rows,\s*(\d+)\s*cols', name)
                if match:
                    return {
                        'name': match.group(1).strip(),
                        'dimension': match.group(2) or '',
                        'rows': int(match.group(3)),
                        'cols': int(match.group(4))
                    }

        return {'name': sheet_name}

    def _parse_sheet_lines(self, lines: List[str]) -> List[List[Any]]:
        """Parse sheet lines into row data.

        Args:
            lines: List of text lines from sheet extraction

        Returns:
            List of rows (each row is a list of cell values)
        """
        rows = []
        for line in lines:
            # Skip header lines and empty lines
            line = line.strip()
            if not line or line.startswith('Sheet:') or line.startswith('Rows:'):
                continue

            # Remove line number prefix if present (e.g., "  1  data|data|data")
            line = re.sub(r'^\s*\d+\s+', '', line)

            # Split by pipe delimiter
            cells = [cell.strip() for cell in line.split('|')]
            rows.append(cells)

        return rows

    def _apply_cell_range(self, rows: List[List[Any]], cell_range: str) -> List[List[Any]]:
        """Apply cell range filter to rows.

        Args:
            rows: Full sheet data
            cell_range: A1 notation range (e.g., "A1:C10", "B5:D20")

        Returns:
            Filtered rows
        """
        # Parse A1 notation
        match = re.match(r'([A-Z]+)(\d+):([A-Z]+)(\d+)', cell_range, re.IGNORECASE)
        if not match:
            return rows  # Invalid range, return all rows

        start_col, start_row, end_col, end_row = match.groups()

        # Convert column letters to indices (A=0, B=1, etc.)
        start_col_idx = self._col_letter_to_index(start_col)
        end_col_idx = self._col_letter_to_index(end_col)
        start_row_idx = int(start_row) - 1  # 1-based to 0-based
        end_row_idx = int(end_row) - 1

        # Filter rows and columns
        filtered = []
        for i in range(start_row_idx, min(end_row_idx + 1, len(rows))):
            if i < len(rows):
                row = rows[i]
                filtered_row = row[start_col_idx:end_col_idx + 1]
                filtered.append(filtered_row)

        return filtered

    def _col_letter_to_index(self, col: str) -> int:
        """Convert column letter to 0-based index.

        Args:
            col: Column letter (e.g., "A", "B", "AA")

        Returns:
            0-based column index
        """
        index = 0
        for char in col.upper():
            index = index * 26 + (ord(char) - ord('A') + 1)
        return index - 1

    def _search_sheets(self, pattern: str) -> Dict[str, Any]:
        """Search for pattern across all sheets.

        Args:
            pattern: Search text

        Returns:
            Dict with search results
        """
        # TODO: Implement cross-sheet search
        raise NotImplementedError("Search functionality coming soon")

    def get_element(self, element_name: str) -> Optional[Dict[str, Any]]:
        """Get specific sheet by name.

        Args:
            element_name: Sheet name

        Returns:
            Dict with sheet data
        """
        # Set sheet parameter and get sheet data
        self.query_params['sheet'] = element_name
        return self._get_sheet_data(element_name)

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the Excel file.

        Returns:
            Dict with file metadata
        """
        if not self.analyzer:
            return {'type': 'xlsx'}

        return self.analyzer.get_metadata()
