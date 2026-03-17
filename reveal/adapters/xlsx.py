"""Xlsx adapter for xlsx:// URIs - Excel spreadsheet analysis and extraction."""

import sys
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from .base import ResourceAdapter, register_adapter, register_renderer
from ..analyzers.office.openxml import XlsxAnalyzer
from ..utils.query import parse_query_params
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
        from ..utils import safe_json_dumps

        # Check for format preference in result (from ?format=csv query param)
        preferred_format = result.get('preferred_format', format)

        if preferred_format == 'json':
            print(safe_json_dumps(result))
            return

        # Dispatch by result type
        result_type = result.get('type')
        if result_type == 'xlsx_sheet':
            XlsxRenderer._render_sheet_data(result, preferred_format)
        elif result_type == 'xlsx_search':
            XlsxRenderer._render_search_results(result, preferred_format)
        elif result_type == 'xlsx_powerpivot':
            XlsxRenderer._render_powerpivot(result, preferred_format)
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

        banner = result.get('powerpivot_banner')
        if banner:
            model_path = banner.get('model_path', '')
            table_names = banner.get('table_names', [])
            print(f"\n\u26a1 Power Pivot model detected ({model_path})")
            if table_names:
                names_str = ', '.join(table_names[:8])
                if len(table_names) > 8:
                    names_str += f', ... ({len(table_names)} total)'
                print(f"   Tables: {names_str}")
            print(f"   Run with ?powerpivot=schema to explore the full model")

    @staticmethod
    def _render_sheet_data(result: dict, format: str) -> None:
        """Render sheet data as table or CSV."""
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
    def _render_search_results(result: dict, format: str) -> None:
        """Render cross-sheet search results."""
        if format == 'json':
            from ..utils import safe_json_dumps
            print(safe_json_dumps(result))
            return

        pattern = result.get('pattern', '')
        total = result.get('total_matches', 0)
        sheets_count = result.get('sheets_with_matches', 0)
        sheet_results = result.get('sheet_results', [])

        if total == 0:
            print(f'No matches for "{pattern}"')
            return

        noun = 'match' if total == 1 else 'matches'
        sheet_noun = 'sheet' if sheets_count == 1 else 'sheets'
        print(f'{total} {noun} for "{pattern}" across {sheets_count} {sheet_noun}:\n')

        for sr in sheet_results:
            sheet_name = sr['sheet_name']
            matches = sr['matches']
            print(f'  [{sheet_name}] — {len(matches)} match{"es" if len(matches) != 1 else ""}')
            for m in matches:
                row_num = m['row_num']
                cells = m['cells']
                row_str = ' | '.join(str(c) if c is not None else '' for c in cells)
                print(f'    row {row_num:>4}:  {row_str}')
            print()

    @staticmethod
    def _render_powerpivot(result: dict, format: str) -> None:
        """Render Power Pivot model output for all ?powerpivot= modes."""
        from ..utils import safe_json_dumps

        if format == 'json':
            print(safe_json_dumps(result))
            return

        file_path = result.get('file', result.get('source', 'Unknown'))
        filename = Path(file_path).name
        mode = result.get('mode', 'schema')

        if not result.get('has_model'):
            print(f"No Power Pivot model found in {filename}")
            return

        xmla_available = result.get('xmla_available', False)
        tables = result.get('tables', [])
        measures = result.get('measures', [])
        message = result.get('message')

        if mode in ('measures', 'dax') and not xmla_available:
            print(f"Power Pivot Model: {filename}\n")
            if message:
                print(message)
            else:
                print("DAX measures not available — XMLA schema absent (modern Power BI export).")
                print("Install reveal-cli[powerpivot] for full extraction.")
            return

        if mode == 'tables':
            print(f"Power Pivot Model: {filename}\n")
            print(f"Tables ({len(tables)}):")
            for t in tables:
                col_count = len(t.get('columns', []))
                if col_count:
                    print(f"  {t['name']} ({col_count} columns)")
                else:
                    print(f"  {t['name']}")
            if not xmla_available:
                print("\n(Column counts not available — XMLA schema absent)")

        elif mode == 'schema':
            print(f"Power Pivot Model: {filename}\n")
            print(f"Tables ({len(tables)}):")
            for t in tables:
                cols = t.get('columns', [])
                if cols:
                    cols_preview = ', '.join(cols[:6])
                    if len(cols) > 6:
                        cols_preview += f', ... ({len(cols)} total)'
                    print(f"  {t['name']} ({len(cols)} columns)")
                    print(f"    {cols_preview}")
                else:
                    print(f"  {t['name']}")
            if measures:
                print(f"\nMeasures ({len(measures)}):")
                max_name = max(len(m['name']) for m in measures)
                for m in measures:
                    print(f"  [{m['name']:<{max_name}}]  {m['table']}")
            if not xmla_available:
                print("\n(Schema limited — XMLA absent; table names from pivotCache only)")

        elif mode == 'measures':
            print(f"Power Pivot Measures: {filename}\n")
            if not measures:
                print("No measures found.")
                return
            max_name = max(len(m['name']) for m in measures)
            for m in measures:
                print(f"  [{m['name']:<{max_name}}]  {m['table']}")

        elif mode == 'dax':
            print(f"Power Pivot Measures: {filename}\n")
            if not measures:
                print("No measures found.")
                return
            max_name = max(len(m['name']) for m in measures)
            for m in measures:
                print(f"[{m['name']:<{max_name}}]  = {m['expr']}")

        elif mode == 'relationships':
            relationships = result.get('relationships', [])
            print(f"Power Pivot Relationships: {filename}\n")
            if not relationships:
                if not xmla_available:
                    print("Relationships not available — XMLA schema absent.")
                else:
                    print("No relationships found.")
                return
            # Group by from-table for readable output
            from collections import defaultdict
            by_table: dict = defaultdict(list)
            for r in relationships:
                by_table[r['from']['table']].append(r)
            for tname in sorted(by_table):
                rels = by_table[tname]
                print(f"  {tname}")
                for r in rels:
                    fc = ', '.join(r['from']['columns']) or '?'
                    tc = ', '.join(r['to']['columns']) or '?'
                    tt = r['to']['table']
                    fm = r['from']['multiplicity']
                    tm = r['to']['multiplicity']
                    print(f"    [{fc}] ({fm})  ->  {tt}[{tc}] ({tm})")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific xlsx element (same as structure for sheets)."""
        XlsxRenderer.render_structure(result, format)

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error accessing Excel file: {error}", file=sys.stderr)


_SCHEMA_QUERY_PARAMS = {
    'sheet': {'type': 'string|integer', 'description': 'Sheet to extract (name or 0-based index)', 'examples': ['sheet=Sales', 'sheet=0']},
    'range': {'type': 'string', 'description': 'Cell range in A1 notation (e.g., A1:C10)', 'examples': ['range=A1:C10', 'range=B5:D20']},
    'search': {'type': 'string', 'description': 'Search for text across all sheets', 'examples': ['search=revenue', 'search=total']},
    'format': {'type': 'string', 'description': 'Output format (text, json, csv)', 'examples': ['format=csv', 'format=json']},
    'limit': {'type': 'integer', 'description': 'Maximum number of rows to return', 'examples': ['limit=100', 'limit=50']},
    'formulas': {'type': 'boolean', 'description': 'Show formulas instead of values', 'examples': ['formulas=true']},
    'powerpivot': {'type': 'string', 'description': 'Extract Power Pivot model (tables|schema|measures|dax)', 'examples': ['powerpivot=schema', 'powerpivot=dax', 'powerpivot=tables', 'powerpivot=measures']},
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'xlsx_workbook',
        'description': 'Workbook overview with sheet list',
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'xlsx_workbook'},
            'file': {'type': 'string'}, 'sheets': {'type': 'array'},
        }},
    },
    {
        'type': 'xlsx_sheet',
        'description': 'Sheet data with rows and columns',
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'xlsx_sheet'},
            'sheet_name': {'type': 'string'}, 'rows': {'type': 'array'},
            'dimension': {'type': 'string'},
        }},
    },
    {
        'type': 'xlsx_search',
        'description': 'Cross-sheet search results with matching rows grouped by sheet',
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'xlsx_search'},
            'query': {'type': 'string'}, 'total_matches': {'type': 'integer'},
            'sheets': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'sheet_name': {'type': 'string'}, 'matches': {'type': 'array'},
            }}},
        }},
    },
    {
        'type': 'xlsx_powerpivot',
        'description': 'Power Pivot data model: tables, columns, DAX measures',
        'schema': {'type': 'object', 'properties': {
            'type': {'type': 'string', 'const': 'xlsx_powerpivot'},
            'has_model': {'type': 'boolean'},
            'xmla_available': {'type': 'boolean'},
            'model_path': {'type': 'string'},
            'tables': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'name': {'type': 'string'}, 'columns': {'type': 'array'},
            }}},
            'measures': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'name': {'type': 'string'}, 'table': {'type': 'string'}, 'expr': {'type': 'string'},
            }}},
        }},
    },
]

_SCHEMA_NOTES = [
    'Pure stdlib implementation — no extra dependencies required',
    'Sheet can be specified by name or 0-based integer index (sheet=0 for first sheet)',
    '?range=A1:C10 uses standard A1 notation; omit to get the entire sheet',
    '?search=term is case-insensitive and searches all sheets simultaneously',
    '?formulas=true shows raw formulas instead of computed cell values',
    '?format=csv exports the sheet as CSV — pipe to other tools or save to file',
    '?powerpivot=schema shows Power Pivot tables and columns (Excel 2010/2013 XMLA format)',
    '?powerpivot=dax shows DAX measure expressions (requires Excel 2010/2013 XMLA; modern Power BI exports not supported without reveal-cli[powerpivot])',
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'xlsx:///path/to/file.xlsx', 'description': 'List all sheets in workbook', 'output_type': 'xlsx_workbook'},
    {'uri': 'xlsx:///path/to/file.xlsx?sheet=0', 'description': 'Extract first sheet', 'output_type': 'xlsx_sheet'},
    {'uri': 'xlsx:///path/to/file.xlsx?sheet=Sales&range=A1:C10', 'description': 'Extract cell range from specific sheet', 'output_type': 'xlsx_sheet'},
    {'uri': 'xlsx:///path/to/file.xlsx?sheet=Sales&format=csv', 'description': 'Export sheet as CSV', 'output_type': 'xlsx_sheet'},
    {'uri': 'xlsx:///path/to/file.xlsx?search=revenue', 'description': 'Search all sheets for matching rows (case-insensitive)', 'output_type': 'xlsx_search'},
    {'uri': 'xlsx:///path/to/file.xlsx?search=error&limit=20', 'description': 'Cross-sheet search with result limit', 'output_type': 'xlsx_search'},
    {'uri': 'xlsx:///path/to/file.xlsx?powerpivot=tables', 'description': 'List Power Pivot tables with column counts', 'output_type': 'xlsx_powerpivot'},
    {'uri': 'xlsx:///path/to/file.xlsx?powerpivot=schema', 'description': 'Show Power Pivot tables with all column names', 'output_type': 'xlsx_powerpivot'},
    {'uri': 'xlsx:///path/to/file.xlsx?powerpivot=dax', 'description': 'Show DAX measure expressions', 'output_type': 'xlsx_powerpivot'},
]


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
            'query_params': _SCHEMA_QUERY_PARAMS,
            'elements': {},
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'notes': _SCHEMA_NOTES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
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
            self.query_params = parse_query_params(query_part)
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

    def _init_analyzer(self) -> None:
        """Initialize XlsxAnalyzer for the file."""
        if self.file_path:
            self.analyzer = XlsxAnalyzer(str(self.file_path))

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        """Get workbook structure or sheet data based on query params.

        Returns:
            Dict containing workbook overview or sheet data
        """
        if not self.analyzer:
            raise ValueError("No file loaded")

        # Check for powerpivot parameter
        powerpivot_param = self.query_params.get('powerpivot')
        if powerpivot_param is not None:
            return self._get_powerpivot(powerpivot_param)

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

        # Power Pivot banner: detect model and show table names
        banner = self._build_powerpivot_banner()
        if banner:
            result_data['powerpivot_banner'] = banner

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
        """Search for pattern across all sheets (case-insensitive).

        Args:
            pattern: Search text

        Returns:
            Dict with search results grouped by sheet
        """
        if self.analyzer is None:
            raise ValueError("Analyzer not initialized")

        matches = self.analyzer.search_all_sheets(pattern)

        # Apply limit if specified
        limit_param = self.query_params.get('limit')
        if limit_param:
            try:
                matches = matches[:int(limit_param)]
            except ValueError:
                pass

        # Group by sheet
        sheets_seen: Dict[str, List[Dict[str, Any]]] = {}
        for m in matches:
            sname = m['sheet_name']
            sheets_seen.setdefault(sname, []).append(m)

        sheet_results = [
            {'sheet_name': sname, 'matches': rows}
            for sname, rows in sheets_seen.items()
        ]

        result_data = {
            'pattern': pattern,
            'total_matches': len(matches),
            'sheets_with_matches': len(sheet_results),
            'sheet_results': sheet_results,
        }

        return ResultBuilder.create(
            result_type='xlsx_search',
            source=self.file_path or Path('unknown'),
            data=result_data
        )

    # -------------------------------------------------------------------------
    # Power Pivot helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _local(tag: str) -> str:
        """Strip XML namespace from an ElementTree tag."""
        return tag.split('}')[-1] if '}' in tag else tag

    def _detect_powerpivot(self, zf: zipfile.ZipFile) -> Optional[str]:
        """Return the model data path if this workbook contains a Power Pivot model.

        Returns a real zip path for embedded models, or the sentinel 'xl/pivotCache/'
        for external SSAS/OLAP workbooks that have pivot caches with OLAP hierarchies.
        """
        names = set(zf.namelist())
        if 'xl/model/item.data' in names:
            return 'xl/model/item.data'
        if 'xl/customData/item1.data' in names:
            return 'xl/customData/item1.data'
        # External SSAS/OLAP: no embedded model, but pivotCaches reference a cube.
        # Detect by checking for cacheHierarchy elements (OLAP-only attribute).
        for name in names:
            if not re.match(r'xl/pivotCache/pivotCacheDefinition\d+\.xml$', name):
                continue
            try:
                root = ET.fromstring(zf.read(name))
                for el in root.iter():
                    if self._local(el.tag) == 'cacheHierarchies':
                        return 'xl/pivotCache/'
            except Exception:
                pass
        return None

    def _find_xmla_item(self, zf: zipfile.ZipFile) -> Optional[str]:
        """Return the customXml item path containing Gemini SSAS XMLA metadata, or None."""
        for name in zf.namelist():
            if not re.match(r'customXml/item\d+\.xml$', name):
                continue
            try:
                raw = zf.read(name)
                if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):  # UTF-16 BOM
                    text = raw.decode('utf-16', errors='replace')
                    if 'MetadataRecoveryInformation' in text:
                        return name
            except Exception:
                pass
        return None

    def _parse_xmla(self, zf: zipfile.ZipFile, item_path: str) -> Dict[str, Any]:
        """Parse SSAS XMLA item — extract tables, columns, and DAX measures.

        The item is a UTF-16 XML file with the XMLA wrapped in a CDATA section
        inside a <Gemini><CustomContent><![CDATA[...]]></CustomContent></Gemini>
        envelope.  We parse the outer doc first, then the inner XMLA.
        """
        raw = zf.read(item_path)
        text = raw.decode('utf-16', errors='replace')
        outer = ET.fromstring(text)
        # Unwrap CDATA from <CustomContent> element (if present)
        cc = next((e for e in outer.iter() if self._local(e.tag) == 'CustomContent'), None)
        if cc is not None and cc.text:
            root = ET.fromstring(cc.text)
        else:
            root = outer

        local = self._local

        # Collect tables from Dimension elements that have Attributes children.
        # The XMLA has both full definitions and lightweight MeasureGroup refs;
        # keep whichever has the most columns per name.
        tables: Dict[str, List[str]] = {}
        for dim in root.iter():
            if local(dim.tag) != 'Dimension':
                continue
            attrs_elem = next((c for c in dim if local(c.tag) == 'Attributes'), None)
            if attrs_elem is None:
                continue
            name = next((c.text for c in dim if local(c.tag) == 'Name'), None) or \
                   next((c.text for c in dim if local(c.tag) == 'ID'), None)
            if not name:
                continue
            cols: List[str] = []
            for attr in attrs_elem:
                if local(attr.tag) != 'Attribute':
                    continue
                attr_type = next((c.text for c in attr if local(c.tag) == 'Type'), None)
                if attr_type == 'RowNumber':
                    continue
                col_name = next((c.text for c in attr if local(c.tag) == 'Name'), None) or \
                           next((c.text for c in attr if local(c.tag) == 'ID'), None)
                if col_name:
                    cols.append(col_name)
            if name not in tables or len(cols) > len(tables[name]):
                tables[name] = cols

        # Extract DAX measures from MdxScript Command/Text elements.
        measure_pattern = re.compile(
            r"CREATE\s+MEASURE\s+(?:\[[^\]]+\]\.)?'?([^'\[\r\n]+?)'?\[([^\]]+)\]\s*=\s*(.+?)(?=\s*;|\s*CREATE\s+MEASURE|\s*$)",
            re.IGNORECASE | re.DOTALL,
        )
        measures = []
        for cmd in root.iter():
            if local(cmd.tag) != 'Text':
                continue
            content = cmd.text or ''
            if 'CREATE MEASURE' not in content.upper():
                continue
            for m in measure_pattern.finditer(content):
                measures.append({
                    'table': m.group(1).strip(),
                    'name': m.group(2).strip(),
                    'expr': m.group(3).strip().rstrip(';').strip(),
                })

        # Build dim ID -> name map for relationship resolution.
        dim_id_to_name: Dict[str, str] = {}
        for dim in root.iter():
            if local(dim.tag) != 'Dimension':
                continue
            did = next((c.text for c in dim if local(c.tag) == 'ID'), None)
            dname = next((c.text for c in dim if local(c.tag) == 'Name'), None)
            if did and dname:
                dim_id_to_name[did] = dname

        # Extract relationships from Relationship elements.
        relationships = []
        for rel in root.iter():
            if local(rel.tag) != 'Relationship':
                continue
            from_end = next((c for c in rel if local(c.tag) == 'FromRelationshipEnd'), None)
            to_end = next((c for c in rel if local(c.tag) == 'ToRelationshipEnd'), None)
            if from_end is None or to_end is None:
                continue

            def _parse_end(end: ET.Element) -> Dict[str, Any]:
                did = next((c.text for c in end if local(c.tag) == 'DimensionID'), None) or ''
                mult = next((c.text for c in end if local(c.tag) == 'Multiplicity'), None) or 'Unknown'
                tname = dim_id_to_name.get(did, did)
                attrs_el = next((c for c in end if local(c.tag) == 'Attributes'), None)
                cols: List[str] = []
                if attrs_el is not None:
                    for attr in attrs_el:
                        aid = next((c.text for c in attr if local(c.tag) == 'AttributeID'), None)
                        if aid:
                            cols.append(aid)
                return {'table': tname, 'columns': cols, 'multiplicity': mult}

            relationships.append({
                'from': _parse_end(from_end),
                'to': _parse_end(to_end),
            })

        return {
            'has_model': True,
            'xmla_available': True,
            'tables': [{'name': k, 'columns': v} for k, v in tables.items()],
            'measures': measures,
            'relationships': relationships,
        }

    def _parse_pivot_cache(self, zf: zipfile.ZipFile) -> Dict[str, Any]:
        """Fallback: extract table names from pivotCacheDefinition files."""
        table_names: Set[str] = set()
        for name in zf.namelist():
            if not re.match(r'xl/pivotCache/pivotCacheDefinition\d+\.xml$', name):
                continue
            try:
                root = ET.fromstring(zf.read(name))
                for h in root.iter():
                    if self._local(h.tag) == 'cacheHierarchy':
                        m = re.match(r'\[([^\]]+)\]', h.get('uniqueName', ''))
                        if m and m.group(1) != 'Measures':
                            table_names.add(m.group(1))
            except Exception:
                pass
        return {
            'has_model': True,
            'xmla_available': False,
            'tables': [{'name': t, 'columns': []} for t in sorted(table_names)],
            'measures': [],
            'relationships': [],
        }

    def _build_powerpivot_banner(self) -> Optional[Dict[str, Any]]:
        """Return banner dict for workbook overview, or None if no model detected."""
        if not self.file_path:
            return None
        try:
            with zipfile.ZipFile(self.file_path) as zf:
                model_path = self._detect_powerpivot(zf)
                if model_path is None:
                    return None
                xmla_item = self._find_xmla_item(zf)
                if xmla_item:
                    data = self._parse_xmla(zf, xmla_item)
                    table_names = [t['name'] for t in data['tables']]
                else:
                    data = self._parse_pivot_cache(zf)
                    table_names = [t['name'] for t in data['tables']]
                return {'model_path': model_path, 'table_names': table_names}
        except Exception:
            return None

    def _get_powerpivot(self, mode: str) -> Dict[str, Any]:
        """Extract Power Pivot model for a ?powerpivot=<mode> request."""
        valid_modes = ('tables', 'schema', 'measures', 'dax', 'relationships')
        if mode not in valid_modes:
            mode = 'schema'

        if not self.file_path:
            return ResultBuilder.create_error(
                result_type='xlsx_powerpivot',
                source=Path('unknown'),
                error="No file loaded",
            )

        try:
            with zipfile.ZipFile(self.file_path) as zf:
                model_path = self._detect_powerpivot(zf)
                if model_path is None:
                    return ResultBuilder.create(
                        result_type='xlsx_powerpivot',
                        source=self.file_path,
                        data={'file': str(self.file_path), 'has_model': False, 'mode': mode},
                    )

                xmla_item = self._find_xmla_item(zf)
                if xmla_item:
                    data = self._parse_xmla(zf, xmla_item)
                else:
                    data = self._parse_pivot_cache(zf)
                    if mode in ('measures', 'dax'):
                        data['message'] = (
                            'DAX measures not available — XMLA schema absent (modern Power BI export). '
                            'Install reveal-cli[powerpivot] for full extraction.'
                        )

                data['file'] = str(self.file_path)
                data['model_path'] = model_path
                data['mode'] = mode

                return ResultBuilder.create(
                    result_type='xlsx_powerpivot',
                    source=self.file_path,
                    data=data,
                )
        except Exception as e:
            return ResultBuilder.create_error(
                result_type='xlsx_powerpivot',
                source=self.file_path,
                error=str(e),
            )

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
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
