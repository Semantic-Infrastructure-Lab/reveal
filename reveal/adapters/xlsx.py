"""Xlsx adapter for xlsx:// URIs - Excel spreadsheet analysis and extraction."""

import sys
import re
import base64
import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from .base import ResourceAdapter, register_adapter, register_renderer
from ..analyzers.office.openxml import XlsxAnalyzer
from ..utils import safe_json_dumps
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
        elif result_type == 'xlsx_powerquery':
            XlsxRenderer._render_powerquery(result, preferred_format)
        elif result_type == 'xlsx_names':
            XlsxRenderer._render_named_ranges(result, preferred_format)
        elif result_type == 'xlsx_connections':
            XlsxRenderer._render_connections(result, preferred_format)
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
            if 'rows' in sheet:
                print(f"  :{i:2}   {name}{dim_str} - {rows} rows, {cols} cols{formula_str}")
            else:
                print(f"  :{i:2}   {name}")

        banner = result.get('powerpivot_banner')
        if banner:
            model_path = banner.get('model_path', '')
            if model_path:
                table_names = banner.get('table_names', [])
                print(f"\n\u26a1 Power Pivot model detected ({model_path})")
                if table_names:
                    names_str = ', '.join(table_names[:8])
                    if len(table_names) > 8:
                        names_str += f', ... ({len(table_names)} total)'
                    print(f"   Tables: {names_str}")
                print(f"   Run with ?powerpivot=schema to explore the full model")
            if banner.get('has_powerquery'):
                print(f"\n\U0001f4e6 Power Query detected — run with ?powerquery=list to explore queries")
            conn_count = banner.get('connection_count', 0)
            if conn_count:
                s = 's' if conn_count != 1 else ''
                print(f"\n\U0001f517 {conn_count} external connection{s} — run with ?connections=list")
            range_count = banner.get('named_range_count', 0)
            if range_count:
                s = 's' if range_count != 1 else ''
                print(f"\n\U0001f4ce {range_count} named range{s} — run with ?names=list")

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
    def _render_powerpivot_tables(filename: str, tables: list, xmla_available: bool) -> None:
        """Render ?powerpivot=tables output."""
        print(f"Power Pivot Model: {filename}\n")
        print(f"Tables ({len(tables)}):")
        for t in tables:
            col_count = len(t.get('columns', []))
            if col_count:
                print(f"  {t['name']} ({col_count} columns)")
            else:
                print(f"  {t['name']}")
        if not xmla_available:
            print("\n(Column counts not available — install pbixray for full schema)")

    @staticmethod
    def _render_powerpivot_schema(
        filename: str, tables: list, measures: list, xmla_available: bool
    ) -> None:
        """Render ?powerpivot=schema output."""
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
            print("\n(Schema limited — install pbixray for full columns and DAX)")

    @staticmethod
    def _render_powerpivot_measures(filename: str, measures: list) -> None:
        """Render ?powerpivot=measures output."""
        print(f"Power Pivot Measures: {filename}\n")
        if not measures:
            print("No measures found.")
            return
        max_name = max(len(m['name']) for m in measures)
        for m in measures:
            print(f"  [{m['name']:<{max_name}}]  {m['table']}")

    @staticmethod
    def _render_powerpivot_dax(filename: str, measures: list) -> None:
        """Render ?powerpivot=dax output."""
        print(f"Power Pivot Measures: {filename}\n")
        if not measures:
            print("No measures found.")
            return
        max_name = max(len(m['name']) for m in measures)
        for m in measures:
            print(f"[{m['name']:<{max_name}}]  = {m['expr']}")

    @staticmethod
    def _render_powerpivot_relationships(
        filename: str, relationships: list, xmla_available: bool
    ) -> None:
        """Render ?powerpivot=relationships output."""
        from collections import defaultdict
        print(f"Power Pivot Relationships: {filename}\n")
        if not relationships:
            if not xmla_available:
                print("Relationships not available — XMLA schema absent.")
            else:
                print("No relationships found.")
            return
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
    def _render_powerpivot(result: dict, format: str) -> None:
        """Render Power Pivot model output — dispatches to per-mode helpers."""

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

        pbixray_available = result.get('pbixray_available', False)
        if mode in ('measures', 'dax') and not xmla_available and not pbixray_available:
            print(f"Power Pivot Model: {filename}\n")
            if message:
                print(message)
            else:
                print("DAX measures not available — XMLA schema absent (modern Power BI export).")
                print("Install pbixray (pip install pbixray) for full extraction.")
            return

        has_full_schema = xmla_available or pbixray_available
        _mode_renderers = {
            'tables': lambda: XlsxRenderer._render_powerpivot_tables(filename, tables, has_full_schema),
            'schema': lambda: XlsxRenderer._render_powerpivot_schema(filename, tables, measures, has_full_schema),
            'measures': lambda: XlsxRenderer._render_powerpivot_measures(filename, measures),
            'dax': lambda: XlsxRenderer._render_powerpivot_dax(filename, measures),
            'relationships': lambda: XlsxRenderer._render_powerpivot_relationships(
                filename, result.get('relationships', []), has_full_schema
            ),
        }
        renderer = _mode_renderers.get(mode)
        if renderer:
            renderer()

    @staticmethod
    def _render_powerquery(result: dict, format: str) -> None:
        """Render Power Query M code output."""
        if format == 'json':
            print(safe_json_dumps(result))
            return

        file_path = result.get('file', result.get('source', 'Unknown'))
        filename = Path(file_path).name
        mode = result.get('mode', 'list')

        if not result.get('has_powerquery'):
            print(f"No Power Query found in {filename}")
            print("Power Query (Get & Transform) embeds M code in customXml/DataMashup.")
            return

        queries = result.get('queries', [])

        if mode == 'list':
            print(f"Power Query: {filename}\n")
            print(f"Queries ({len(queries)}):")
            for q in queries:
                expr = q.get('expression', '')
                lines = len(expr.splitlines())
                print(f"  {q['name']}  ({lines} lines)")
            print(f"\nRun with ?powerquery=show to see all M code")
            print(f"Run with ?powerquery=<name> to see a specific query")
        elif mode == 'show':
            print(f"Power Query: {filename}\n")
            for q in queries:
                print(f"// {q['name']}")
                print(q.get('expression', ''))
                print()
        else:
            # Specific query name lookup
            matches = [q for q in queries if q['name'].lower() == mode.lower()]
            if matches:
                q = matches[0]
                print(f"// {q['name']}")
                print(q.get('expression', ''))
            else:
                print(f"Query '{mode}' not found in {filename}")
                if queries:
                    print(f"Available: {', '.join(q['name'] for q in queries)}")

    @staticmethod
    def _render_named_ranges(result: dict, format: str) -> None:
        """Render named ranges (defined names) output."""
        if format == 'json':
            print(safe_json_dumps(result))
            return

        file_path = result.get('file', result.get('source', 'Unknown'))
        filename = Path(file_path).name
        ranges = result.get('ranges', [])

        if not ranges:
            print(f"No named ranges found in {filename}")
            return

        print(f"Named Ranges: {filename}\n")
        max_name = max((len(r['name']) for r in ranges), default=4)
        max_scope = max((len(r['scope']) for r in ranges), default=5)
        print(f"  {'Name':<{max_name}}  {'Scope':<{max_scope}}  Reference")
        print(f"  {'-' * max_name}  {'-' * max_scope}  ---------")
        for r in ranges:
            hidden = '  (hidden)' if r.get('hidden') else ''
            print(f"  {r['name']:<{max_name}}  {r['scope']:<{max_scope}}  {r['reference']}{hidden}")

    @staticmethod
    def _render_connections(result: dict, format: str) -> None:
        """Render external data connections output."""
        if format == 'json':
            print(safe_json_dumps(result))
            return

        file_path = result.get('file', result.get('source', 'Unknown'))
        filename = Path(file_path).name
        connections = result.get('connections', [])
        mode = result.get('mode', 'list')

        if not connections:
            print(f"No external connections found in {filename}")
            return

        print(f"External Connections: {filename}\n")

        if mode == 'show':
            for conn in connections:
                print(f"Connection: {conn['name']}")
                print(f"  Type:             {conn['type']}")
                if conn.get('connection_string'):
                    print(f"  Connection String: {conn['connection_string']}")
                if conn.get('command'):
                    cmd_type = f" ({conn['command_type']})" if conn.get('command_type') else ''
                    print(f"  Command{cmd_type}:       {conn['command']}")
                if conn.get('source_file'):
                    print(f"  Source File:       {conn['source_file']}")
                refresh = conn.get('refresh_on_load', False)
                print(f"  Refresh On Load:   {refresh}")
                print()
        else:
            print(f"Connections ({len(connections)}):")
            for conn in connections:
                name = conn.get('name', '')
                conn_type = conn.get('type', '')
                source = conn.get('connection_string') or conn.get('source_file') or ''
                if len(source) > 60:
                    source = source[:57] + '...'
                print(f"  {name}  [{conn_type}]  {source}")
            print(f"\nRun with ?connections=show for full connection strings and SQL")

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
    'powerquery': {'type': 'string', 'description': 'Extract Power Query M code (list|show|<name>)', 'examples': ['powerquery=list', 'powerquery=show', 'powerquery=SalesData']},
    'names': {'type': 'flag', 'description': 'List named ranges defined in the workbook', 'examples': ['names']},
    'connections': {'type': 'string', 'description': 'List external data connections (list or omit value)', 'examples': ['connections=list', 'connections']},
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
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?powerpivot=schema',
                    'description': 'Show Power Pivot data model tables and columns'
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?powerpivot=dax',
                    'description': 'Show all DAX measure expressions'
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?powerpivot=relationships',
                    'description': 'Show table relationship graph'
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?powerquery=list',
                    'description': 'List Power Query (M) queries embedded in the workbook'
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?powerquery=show',
                    'description': 'Show all Power Query M code'
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?powerquery=SalesData',
                    'description': 'Show M code for the "SalesData" query'
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?names=list',
                    'description': 'List all named ranges and defined names'
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?connections=list',
                    'description': 'List external data connections (ODBC, web, etc.)'
                },
                {
                    'uri': 'xlsx:///data/model.xlsx?connections=show',
                    'description': 'Show full connection strings and SQL commands'
                }
            ],
            'features': [
                'Workbook overview with sheet list',
                'Sheet extraction by name or index',
                'Cell range extraction (A1 notation)',
                'CSV export',
                'Row limiting',
                'Cross-sheet search',
                'Power Pivot data model (tables, columns, DAX measures, relationships)',
                'Power Query M code extraction (?powerquery=)',
                'Named ranges / defined names (?names=list)',
                'External data connections (?connections=)',
                'JSON and text output'
            ],
            'try_now': [
                "reveal xlsx:///path/to/file.xlsx",
                "reveal xlsx:///path/to/file.xlsx?sheet=0",
                "reveal xlsx:///path/to/file.xlsx?powerpivot=schema",
                "reveal xlsx:///path/to/file.xlsx?powerquery=list",
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
                },
                {
                    'name': 'Explore Power BI Export',
                    'scenario': 'Understand a Power BI xlsx export data model',
                    'steps': [
                        "reveal xlsx:///data/report.xlsx                    # Overview — see model detected",
                        "reveal xlsx:///data/report.xlsx?powerpivot=schema  # Tables + columns",
                        "reveal xlsx:///data/report.xlsx?powerpivot=dax     # DAX measures",
                        "reveal xlsx:///data/report.xlsx?powerquery=list    # Power Query ETL queries",
                    ],
                },
                {
                    'name': 'Audit Data Sources',
                    'scenario': 'Find where a workbook pulls its data from',
                    'steps': [
                        "reveal xlsx:///data/report.xlsx?connections=list   # External connections",
                        "reveal xlsx:///data/report.xlsx?connections=show   # Full connection strings + SQL",
                        "reveal xlsx:///data/report.xlsx?powerquery=list    # Power Query sources",
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

        # Check for powerquery parameter
        powerquery_param = self.query_params.get('powerquery')
        if powerquery_param is not None:
            return self._get_powerquery(powerquery_param if powerquery_param else 'list')

        # Check for names parameter (named ranges)
        if 'names' in self.query_params:
            return self._get_named_ranges()

        # Check for connections parameter
        connections_param = self.query_params.get('connections')
        if connections_param is not None:
            return self._get_connections(connections_param if connections_param else 'list')

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
            except Exception:  # noqa: BLE001 — defensive XML/zip parsing fallback
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
            except Exception:  # noqa: BLE001 — defensive XML/zip parsing fallback
                pass
        return None

    def _find_datamashup_item(self, zf: zipfile.ZipFile) -> Optional[str]:
        """Return the customXml item path containing a Power Query DataMashup blob, or None.

        DataMashup items may be UTF-8 or UTF-16 XML.  The reliable distinguisher
        from XMLA (also UTF-16) is the root element name — DataMashup vs Gemini.
        We check for 'DataMashup' in text and absence of XMLA-specific markers.
        """
        for name in zf.namelist():
            if not re.match(r'customXml/item\d+\.xml$', name):
                continue
            try:
                raw = zf.read(name)
                if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
                    text = raw.decode('utf-16', errors='replace')
                else:
                    text = raw.decode('utf-8', errors='replace')
                if 'DataMashup' in text and 'MetadataRecoveryInformation' not in text:
                    return name
            except Exception:  # noqa: BLE001 — defensive XML/zip parsing fallback
                pass
        return None

    def _parse_powerquery_stdlib(self, zf: zipfile.ZipFile, item_path: str) -> Dict[str, Any]:
        """Extract Power Query M code from a DataMashup blob using stdlib only.

        The DataMashup XML contains a base64-encoded binary.  The binary is a
        streaming ZIP (central directory may be empty) containing M formula
        files.  We scan for local file headers directly rather than relying on
        Python's ZipFile central-directory reader.
        """
        import struct
        import zlib as _zlib

        raw = zf.read(item_path)

        # Decode the XML (may be UTF-16 or UTF-8)
        if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
            text = raw.decode('utf-16', errors='replace')
        else:
            text = raw.decode('utf-8', errors='replace')

        # Extract base64 blob — the text content between > and < in the root
        m = re.search(r'>([A-Za-z0-9+/=\s]{100,})<', text)
        if not m:
            return {'has_powerquery': False, 'queries': []}

        blob_b64 = m.group(1).replace('\n', '').replace('\r', '').replace(' ', '')
        try:
            binary = base64.b64decode(blob_b64)
        except Exception:
            return {'has_powerquery': False, 'queries': []}

        # Scan local file headers (streaming ZIP — central directory may be empty)
        def _scan_local_headers(data: bytes) -> Dict[str, bytes]:
            files: Dict[str, bytes] = {}
            offset = 0
            while offset + 30 < len(data):
                if data[offset:offset + 4] != b'PK\x03\x04':
                    offset += 1
                    continue
                chunk = data[offset + 4:offset + 30]
                if len(chunk) < 26:
                    break
                _, flags, method = struct.unpack_from('<HHH', chunk, 0)
                comp_sz, uncomp_sz = struct.unpack_from('<II', chunk, 14)
                name_len, extra_len = struct.unpack_from('<HH', chunk, 22)
                fname = data[offset + 30:offset + 30 + name_len].decode('utf-8', 'replace')
                data_start = offset + 30 + name_len + extra_len
                raw_data = data[data_start:data_start + comp_sz]
                if method == 8 and comp_sz > 0:  # DEFLATE
                    try:
                        raw_data = _zlib.decompress(raw_data, -15)
                    except Exception:  # noqa: BLE001 — defensive XML/zip parsing fallback
                        pass
                files[fname] = raw_data
                offset = data_start + comp_sz
            return files

        inner_files = _scan_local_headers(binary)

        queries: List[Dict[str, str]] = []
        if 'Formulas/Section1.m' in inner_files:
            m_code = inner_files['Formulas/Section1.m'].decode('utf-8', errors='replace')
            queries = self._split_m_section(m_code)
        else:
            for fname, fdata in inner_files.items():
                if fname.lower().endswith('.m'):
                    code = fdata.decode('utf-8', errors='replace')
                    queries.append({'name': Path(fname).stem, 'expression': code})

        if not queries:
            return {'has_powerquery': False, 'queries': []}

        return {
            'has_powerquery': True,
            'query_count': len(queries),
            'queries': queries,
        }

    @staticmethod
    def _split_m_section(m_code: str) -> List[Dict[str, str]]:
        """Split Section1.m M code into individual named queries.

        Format::

            section Section1;
            shared #"Query Name" = let ... in ...;
            shared OtherQuery = ...;
        """
        pattern = re.compile(
            r'(?:^|\n)shared\s+(?:#"([^"]+)"|(\w[\w.]*))\s*=',
            re.MULTILINE,
        )
        matches = list(pattern.finditer(m_code))
        queries: List[Dict[str, str]] = []
        for i, match in enumerate(matches):
            name = match.group(1) or match.group(2)
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(m_code)
            expression = m_code[start:end].rstrip()
            if expression.endswith(';'):
                expression = expression[:-1].rstrip()
            queries.append({'name': name.strip(), 'expression': expression.strip()})
        return queries

    def _parse_pbixray(self) -> Optional[Dict[str, Any]]:
        """Tier 2: use pbixray to extract the schema from a modern VertiPaq model.

        Used when xl/model/item.data exists but no XMLA envelope is present
        (modern Power BI export format).  Returns None when pbixray is not
        installed or extraction fails, allowing Tier 3 fallback.
        """
        if not self.file_path:
            return None
        try:
            from pbixray import PBIXRay  # optional dependency

            px = PBIXRay(str(self.file_path))

            # Tables and columns from schema DataFrame
            tables: Dict[str, List[str]] = {}
            schema_df = px.schema
            if schema_df is not None and not schema_df.empty:
                for _, row in schema_df.iterrows():
                    tname = str(row.get('TableName', ''))
                    col = str(row.get('ColumnName', ''))
                    if tname and col:
                        tables.setdefault(tname, []).append(col)

            # Tables with no columns — px.tables is a numpy.ndarray of names
            tables_arr = px.tables
            if tables_arr is not None:
                for tname in tables_arr:
                    tname = str(tname)
                    if tname and tname not in tables:
                        tables[tname] = []

            # DAX measures
            measures: List[Dict[str, str]] = []
            measures_df = px.dax_measures
            if measures_df is not None and not measures_df.empty:
                for _, row in measures_df.iterrows():
                    measures.append({
                        'table': str(row.get('TableName', '')),
                        'name': str(row.get('Name', '')),
                        'expr': str(row.get('Expression', '')),
                    })

            # Relationships — normalise to XMLA from/to structure
            _card_map = {
                'OneToMany': ('1', 'n'), 'ManyToOne': ('n', '1'),
                'OneToOne': ('1', '1'), 'ManyToMany': ('n', 'n'),
            }
            relationships: List[Dict[str, Any]] = []
            rels_df = px.relationships
            if rels_df is not None and not rels_df.empty:
                for _, row in rels_df.iterrows():
                    card = str(row.get('Cardinality', ''))
                    from_mult, to_mult = _card_map.get(card, (card, card))
                    relationships.append({
                        'from': {
                            'table': str(row.get('FromTableName', '')),
                            'columns': [str(row.get('FromColumnName', ''))],
                            'multiplicity': from_mult,
                        },
                        'to': {
                            'table': str(row.get('ToTableName', '')),
                            'columns': [str(row.get('ToColumnName', ''))],
                            'multiplicity': to_mult,
                        },
                        'active': bool(row.get('IsActive', True)),
                        'cross_filter': str(row.get('CrossFilteringBehavior', '')),
                    })

            return {
                'has_model': True,
                'xmla_available': False,
                'pbixray_available': True,
                'tables': [{'name': k, 'columns': v} for k, v in tables.items()],
                'measures': measures,
                'relationships': relationships,
            }
        except ImportError:
            return None
        except Exception:
            return None

    @staticmethod
    def _xmla_decode_root(zf: zipfile.ZipFile, item_path: str) -> ET.Element:
        """UTF-16 decode + CDATA unwrap → parsed ET.Element root."""
        raw = zf.read(item_path)
        text = raw.decode('utf-16', errors='replace')
        outer = ET.fromstring(text)
        cc = next((e for e in outer.iter() if XlsxAdapter._local(e.tag) == 'CustomContent'), None)
        if cc is not None and cc.text:
            return ET.fromstring(cc.text)
        return outer

    @staticmethod
    def _parse_xmla_tables(root: ET.Element) -> Dict[str, List[str]]:
        """Extract table→columns mapping from XMLA root.

        The XMLA has both full Dimension definitions and lightweight MeasureGroup
        refs; keep whichever entry has the most columns per table name.
        """
        local = XlsxAdapter._local
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
        return tables

    @staticmethod
    def _parse_xmla_measures(root: ET.Element) -> List[Dict[str, str]]:
        """Extract DAX measures from MdxScript Command/Text elements."""
        local = XlsxAdapter._local
        measure_pattern = re.compile(
            r"CREATE\s+MEASURE\s+(?:\[[^\]]+\]\.)?'?([^'\[\r\n]+?)'?\[([^\]]+)\]\s*=\s*(.+?)(?=\s*;|\s*CREATE\s+MEASURE|\s*$)",
            re.IGNORECASE | re.DOTALL,
        )
        measures: List[Dict[str, str]] = []
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
        return measures

    @staticmethod
    def _parse_xmla_dim_id_map(root: ET.Element) -> Dict[str, str]:
        """Build dim ID → name map from XMLA root (used for relationship resolution)."""
        local = XlsxAdapter._local
        dim_id_to_name: Dict[str, str] = {}
        for dim in root.iter():
            if local(dim.tag) != 'Dimension':
                continue
            did = next((c.text for c in dim if local(c.tag) == 'ID'), None)
            dname = next((c.text for c in dim if local(c.tag) == 'Name'), None)
            if did and dname:
                dim_id_to_name[did] = dname
        return dim_id_to_name

    @staticmethod
    def _parse_xmla_end(end: ET.Element, dim_id_to_name: Dict[str, str]) -> Dict[str, Any]:
        """Parse a single relationship end (FromRelationshipEnd / ToRelationshipEnd)."""
        local = XlsxAdapter._local
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

    @staticmethod
    def _parse_xmla_relationships(
        root: ET.Element,
        dim_id_to_name: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """Extract relationship list from XMLA root."""
        local = XlsxAdapter._local
        relationships: List[Dict[str, Any]] = []
        for rel in root.iter():
            if local(rel.tag) != 'Relationship':
                continue
            from_end = next((c for c in rel if local(c.tag) == 'FromRelationshipEnd'), None)
            to_end = next((c for c in rel if local(c.tag) == 'ToRelationshipEnd'), None)
            if from_end is None or to_end is None:
                continue
            relationships.append({
                'from': XlsxAdapter._parse_xmla_end(from_end, dim_id_to_name),
                'to': XlsxAdapter._parse_xmla_end(to_end, dim_id_to_name),
            })
        return relationships

    def _parse_xmla(self, zf: zipfile.ZipFile, item_path: str) -> Dict[str, Any]:
        """Parse SSAS XMLA item — extract tables, columns, DAX measures, and relationships.

        The item is a UTF-16 XML file with the XMLA wrapped in a CDATA section
        inside a <Gemini><CustomContent><![CDATA[...]]></CustomContent></Gemini>
        envelope.  We parse the outer doc first, then the inner XMLA.
        """
        root = self._xmla_decode_root(zf, item_path)
        tables = self._parse_xmla_tables(root)
        measures = self._parse_xmla_measures(root)
        dim_id_to_name = self._parse_xmla_dim_id_map(root)
        relationships = self._parse_xmla_relationships(root, dim_id_to_name)
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
            except Exception:  # noqa: BLE001 — defensive XML/zip parsing fallback
                pass
        return {
            'has_model': True,
            'xmla_available': False,
            'tables': [{'name': t, 'columns': []} for t in sorted(table_names)],
            'measures': [],
            'relationships': [],
        }

    def _build_powerpivot_banner(self) -> Optional[Dict[str, Any]]:
        """Return banner dict for workbook overview with model and extras info.

        Returns None only if nothing interesting was found (no model, no Power
        Query, no connections, no named ranges).
        """
        if not self.file_path:
            return None
        try:
            with zipfile.ZipFile(self.file_path) as zf:
                names_set = set(zf.namelist())
                result: Dict[str, Any] = {}

                # Power Pivot model
                model_path = self._detect_powerpivot(zf)
                if model_path:
                    xmla_item = self._find_xmla_item(zf)
                    if xmla_item:
                        data = self._parse_xmla(zf, xmla_item)
                    else:
                        data = self._parse_pivot_cache(zf)
                    result['model_path'] = model_path
                    result['table_names'] = [t['name'] for t in data['tables']]

                # Power Query (DataMashup presence check — no full extraction)
                if self._find_datamashup_item(zf):
                    result['has_powerquery'] = True

                # External connections count
                if 'xl/connections.xml' in names_set:
                    try:
                        root = ET.fromstring(zf.read('xl/connections.xml'))
                        count = sum(1 for el in root.iter() if self._local(el.tag) == 'connection')
                        if count:
                            result['connection_count'] = count
                    except Exception:  # noqa: BLE001 — defensive XML/zip parsing fallback
                        pass

                # Named ranges count (from workbook.xml definedNames)
                if 'xl/workbook.xml' in names_set:
                    try:
                        root = ET.fromstring(zf.read('xl/workbook.xml'))
                        count = sum(1 for el in root.iter() if self._local(el.tag) == 'definedName')
                        if count:
                            result['named_range_count'] = count
                    except Exception:  # noqa: BLE001 — defensive XML/zip parsing fallback
                        pass

                return result if result else None
        except Exception:
            return None

    def _get_powerquery(self, mode: str) -> Dict[str, Any]:
        """Extract Power Query M code for a ?powerquery=<mode> request.

        Modes:
            list  — query names and line counts (default)
            show  — full M code for all queries
            <name> — M code for a specific named query
        """
        if not mode:
            mode = 'list'
        if not self.file_path:
            return ResultBuilder.create_error(
                result_type='xlsx_powerquery',
                source=Path('unknown'),
                error="No file loaded",
            )
        try:
            with zipfile.ZipFile(self.file_path) as zf:
                pq_item = self._find_datamashup_item(zf)
                if not pq_item:
                    return ResultBuilder.create(
                        result_type='xlsx_powerquery',
                        source=self.file_path,
                        data={
                            'file': str(self.file_path),
                            'mode': mode,
                            'has_powerquery': False,
                            'queries': [],
                        },
                    )
                data = self._parse_powerquery_stdlib(zf, pq_item)
                data['file'] = str(self.file_path)
                data['mode'] = mode
                return ResultBuilder.create(
                    result_type='xlsx_powerquery',
                    source=self.file_path,
                    data=data,
                )
        except Exception as e:
            return ResultBuilder.create_error(
                result_type='xlsx_powerquery',
                source=self.file_path,
                error=str(e),
            )

    def _get_named_ranges(self) -> Dict[str, Any]:
        """Extract named ranges (defined names) from the workbook.

        Reads xl/workbook.xml <definedNames> via raw ZIP/XML — no openpyxl
        needed.  Returns all names including Excel internals (_xlnm.*).
        """
        if not self.file_path:
            return ResultBuilder.create_error(
                result_type='xlsx_names',
                source=Path('unknown'),
                error="No file loaded",
            )
        try:
            with zipfile.ZipFile(self.file_path) as zf:
                if 'xl/workbook.xml' not in zf.namelist():
                    return ResultBuilder.create(
                        result_type='xlsx_names',
                        source=self.file_path,
                        data={'file': str(self.file_path), 'ranges': []},
                    )
                root = ET.fromstring(zf.read('xl/workbook.xml'))
                ranges: List[Dict[str, Any]] = []
                for el in root.iter():
                    if self._local(el.tag) != 'definedName':
                        continue
                    name = el.get('name', '')
                    if not name:
                        continue
                    local_id = el.get('localSheetId')
                    scope = 'global' if local_id is None else f'sheet:{local_id}'
                    ref = (el.text or '').strip()
                    hidden = el.get('hidden', '0') == '1'
                    ranges.append({
                        'name': name,
                        'scope': scope,
                        'reference': ref,
                        'hidden': hidden,
                    })
                return ResultBuilder.create(
                    result_type='xlsx_names',
                    source=self.file_path,
                    data={'file': str(self.file_path), 'ranges': ranges},
                )
        except Exception as e:
            return ResultBuilder.create_error(
                result_type='xlsx_names',
                source=self.file_path,
                error=str(e),
            )

    def _get_connections(self, mode: str = 'list') -> Dict[str, Any]:
        """Extract external data connections from xl/connections.xml.

        Modes:
            list — connection name, type, and source summary (default)
            show — full connection strings and SQL commands
        """
        if not self.file_path:
            return ResultBuilder.create_error(
                result_type='xlsx_connections',
                source=Path('unknown'),
                error="No file loaded",
            )
        _conn_types = {
            '1': 'ODBC', '2': 'OLE DB', '3': 'Web', '4': 'Text File',
            '5': 'ADO', '100': 'Power Query',
        }
        _cmd_types = {
            '1': 'table', '2': 'SQL', '3': 'cube',
            '4': 'statement', '5': 'file', '6': 'MDX',
        }
        try:
            with zipfile.ZipFile(self.file_path) as zf:
                if 'xl/connections.xml' not in zf.namelist():
                    return ResultBuilder.create(
                        result_type='xlsx_connections',
                        source=self.file_path,
                        data={'file': str(self.file_path), 'mode': mode, 'connections': []},
                    )
                root = ET.fromstring(zf.read('xl/connections.xml'))
                connections: List[Dict[str, Any]] = []
                for el in root.iter():
                    if self._local(el.tag) != 'connection':
                        continue
                    type_id = el.get('type', '')
                    cmd_type_id = el.get('commandType', '')
                    connections.append({
                        'name': el.get('name', ''),
                        'type': _conn_types.get(type_id, f'type-{type_id}'),
                        'connection_string': el.get('connectionString', ''),
                        'command': el.get('command', ''),
                        'command_type': _cmd_types.get(cmd_type_id, ''),
                        'source_file': el.get('sourceFile', ''),
                        'refresh_on_load': el.get('refreshOnLoad', '0') == '1',
                    })
                return ResultBuilder.create(
                    result_type='xlsx_connections',
                    source=self.file_path,
                    data={'file': str(self.file_path), 'mode': mode, 'connections': connections},
                )
        except Exception as e:
            return ResultBuilder.create_error(
                result_type='xlsx_connections',
                source=self.file_path,
                error=str(e),
            )

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
                    # Tier 1: full XMLA metadata (Excel 2010/2013)
                    data = self._parse_xmla(zf, xmla_item)
                else:
                    # Tier 2: try pbixray for modern files (Power BI export, no XMLA)
                    data = self._parse_pbixray()
                    if data is None:
                        # Tier 3: pivot cache fallback (table names only)
                        data = self._parse_pivot_cache(zf)
                        if mode in ('measures', 'dax'):
                            data['message'] = (
                                'DAX measures not available — XMLA schema absent (modern Power BI export). '
                                'Install pbixray (pip install pbixray) for full extraction.'
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
