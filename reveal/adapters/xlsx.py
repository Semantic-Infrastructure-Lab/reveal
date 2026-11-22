"""Xlsx adapter for xlsx:// URIs - Excel spreadsheet analysis and extraction."""

import logging
import re
import base64
import binascii
import csv
import io
import struct
import zipfile
import xml.etree.ElementTree as ET
import zlib as _zlib
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, Any, Optional, List, Set, Tuple, Type
from .base import ResourceAdapter, register_adapter, register_renderer
from ..analyzers.office.openxml import XlsxAnalyzer
from ..utils import print_json_result
from ..utils.query import parse_query_params
from ..utils.query_binding import bind_declared_params, switch_value
from ..utils.query_parser import (
    CliBinding, LegacySpelling, ParamSpec, ParamValueError, QueryParams, ResourceSpec, legacy_check, param_schema,
    peek_query_items, whole_number,
)
from ..utils.path_utils import failure_records, to_posix
from ..errors import RequestValidationError
from ..utils.results import (
    AnalysisCompleteness, ExecutionFacts, FailureCause, ResultBuilder, note_truncation, outcome_of, result_execution_facts,
)
from ..utils.warning_render import render_meta_warnings
from reveal.reveal_types import CONTRACT_VERSION, WarningEntry
from reveal.utils.lines import split_lines
from reveal.utils.match_terms import term_label

logger = logging.getLogger(__name__)

# Rows the sheet view shows when ?limit= is not set; ?format=csv exports every row (BACK-1608).
DEFAULT_SHEET_ROWS = 100

# What opening the archive and reading its XML can raise beyond one part's errors: a member
# stored with a compression zipfile cannot decode (NotImplementedError) or an LZMA member
# that is damaged (lzma.LZMAError, which zipfile lets through; bz2 raises OSError).
_DECOMPRESS_ERRORS: Tuple[Type[Exception], ...]
try:
    from lzma import LZMAError as _LZMAError
    _DECOMPRESS_ERRORS = (_LZMAError,)
except ImportError:  # a Python built without liblzma: zipfile itself cannot read LZMA members
    _DECOMPRESS_ERRORS = ()

# What reading one part of the workbook zip can raise: a corrupt or truncated member
# (BadZipFile, zlib.error, EOFError), malformed XML (ParseError), an encrypted or
# unsupported-compression member (RuntimeError, NotImplementedError), a damaged LZMA member
# and I/O (OSError). The part-level handlers lacked LZMAError, so a damaged LZMA member
# crashed them instead of reading as part_unreadable (BACK-1853); NotImplementedError is a
# RuntimeError subclass and is listed so that is visible.
# Anything else is a bug in this module and propagates (BACK-1614, BACK-1059).
_PART_ERRORS: Tuple[Type[Exception], ...] = (
    zipfile.BadZipFile, _zlib.error, EOFError, ET.ParseError, RuntimeError, NotImplementedError,
    OSError,
) + _DECOMPRESS_ERRORS
# Opening the archive raises the same set; the whole-view handlers keep their own name.
_ARCHIVE_ERRORS: Tuple[Type[Exception], ...] = _PART_ERRORS
# The DataMashup blob is base64 around a streaming zip that is walked with struct.unpack_from.
_POWERQUERY_ERRORS: Tuple[Type[Exception], ...] = _ARCHIVE_ERRORS + (binascii.Error, struct.error)

# The view each answer selector picks, with its result type: _get_structure dispatches on it and the router expects
# its type (BACK-2325). No selector is the workbook overview; two are an invalid request (role='operation').
_VIEWS: Tuple[Tuple[str, str], ...] = (
    ('powerpivot', 'xlsx_powerpivot'), ('powerquery', 'xlsx_powerquery'), ('names', 'xlsx_names'),
    ('connections', 'xlsx_connections'), ('sheet', 'xlsx_sheet'), ('match', 'xlsx_search'),
)
_WORKBOOK = 'xlsx_workbook'

# The warnings that mean an answer is missing a part it is built from (D6 exit 3). The overview's
# Power Pivot banner is optional decoration, so its unreadable part is disclosed but not required.
_REQUIRED_PARTS: Dict[str, frozenset] = {
    'xlsx_workbook': XlsxAnalyzer.REQUIRED_STRUCTURE_WARNINGS,
    'xlsx_search': frozenset({'sheets_unsearched'}),
    'xlsx_powerpivot': frozenset({'part_unreadable'}),
    'xlsx_powerquery': frozenset({'part_unreadable'}),
}


def _result_type(params: Any) -> str:
    """The answer a request (bound, prepared or a plain mapping) selects, under any spelling of its selector; prediction
    never raises: a request the binder rejects names no other answer."""
    given = dict(peek_query_items(params))
    for key, result_type in _VIEWS:
        if any(given.get(word) not in (None, False) for word in _SPEC[key].spellings):
            return result_type
    return _WORKBOOK


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
            print_json_result(result)
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
        if preferred_format != 'csv':
            render_meta_warnings(result)

    @staticmethod
    def _render_workbook(result: dict, format: str) -> None:
        """Render workbook overview."""
        file_path = result.get('file', result.get('source', 'Unknown'))
        print(f"File: {Path(file_path).name}\n")

        sheets = result.get('sheets', [])
        if not sheets:
            print("No sheets found")
            return

        # Numbered as ?sheet= counts them, from 0 (BACK-1608: listed from 1, so ?sheet=1
        # opened the sheet shown as 2).
        print(f"Sheets ({len(sheets)}) -- open one with --sheet NAME or --sheet INDEX:")
        for i, sheet in enumerate(sheets):
            name = sheet.get('name', f'Sheet{i + 1}')
            dim = sheet.get('dimension', '')
            rows = sheet.get('rows', 0)
            cols = sheet.get('cols', 0)
            formulas = sheet.get('formulas', 0)

            dim_str = f" ({dim})" if dim else ""
            formula_str = f", {formulas} formulas" if formulas > 0 else ""
            if 'rows' in sheet:
                print(f"  [{i}]  {name}{dim_str} - {rows} rows, {cols} cols{formula_str}")
            else:
                print(f"  [{i}]  {name}")

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
                print("   Run with --powerpivot schema to explore the full model")
            if banner.get('has_powerquery'):
                print("\n\U0001f4e6 Power Query detected — run with --powerquery list to explore queries")
            conn_count = banner.get('connection_count', 0)
            if conn_count:
                s = 's' if conn_count != 1 else ''
                print(f"\n\U0001f517 {conn_count} external connection{s} — run with --connections list")
            range_count = banner.get('named_range_count', 0)
            if range_count:
                s = 's' if range_count != 1 else ''
                print(f"\n\U0001f4ce {range_count} named range{s} — run with --names list")

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

        # Rows by Excel's own row number: a ?range= starts at its first row (BACK-2213)
        for i, row in enumerate(rows_data, result.get('first_row', 1)):
            row_str = ' | '.join(str(cell) if cell is not None else '' for cell in row)
            print(f"{i:6}  {row_str}")

    @staticmethod
    def _render_search_results(result: dict, format: str) -> None:
        """Render cross-sheet search results."""
        if format == 'json':
            print_json_result(result)
            return

        pattern = term_label(result.get('pattern'))  # one term as typed; several joined by AND
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
            print("\n(Column counts not available — install reveal-cli[powerpivot] for full schema)")

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
            print("\n(Schema limited — install reveal-cli[powerpivot] for full columns and DAX)")

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
            print_json_result(result)
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
                print('Install pbixray (pip install "reveal-cli[powerpivot]") for full extraction.')
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
            print_json_result(result)
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
                lines = len(split_lines(expr))
                print(f"  {q['name']}  ({lines} lines)")
            print("\nRun with --powerquery show to see all M code")
            print("Run with --powerquery NAME to see a specific query")
        elif mode == 'show':
            print(f"Power Query: {filename}\n")
            for q in queries:
                print(f"// {q['name']}")
                print(q.get('expression', ''))
                print()
        else:
            # One query by name: the adapter kept only it (a name that matches nothing exits 2).
            for q in queries:
                print(f"// {q['name']}")
                print(q.get('expression', ''))

    @staticmethod
    def _render_named_ranges(result: dict, format: str) -> None:
        """Render named ranges (defined names) output."""
        if format == 'json':
            print_json_result(result)
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
            print_json_result(result)
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
            print("\nRun with --connections show for full connection strings and SQL")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific xlsx element (same as structure for sheets)."""
        XlsxRenderer.render_structure(result, format)


def _text_value(name: str, example: str) -> Callable[[Any], str]:
    """A value that names something (a sheet, a range, a search term): a bare or blank key names
    nothing. A bare ``?search`` crashed on ``True.lower()`` (exit 3, BACK-2525)."""
    def convert(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ParamValueError(f'{name} needs a value: {example}')
        return value
    return convert


_match_term = _text_value('match', '--match TEXT')


def _match_terms(value: Any) -> List[str]:
    """Match terms: one string, or every repeat of a repeated match (COMMAND_MODEL "Conflicting values"), each a
    nonblank string; a row matches when it holds every term."""
    return [_match_term(item) for item in value] if isinstance(value, (list, tuple)) else [_match_term(value)]


def _mode_value(bare: str) -> Callable[[Any], str]:
    """A view's mode: the bare (or empty) key is ``bare``, by name; the spec's choices check the rest.
    Bare ``?powerquery`` and ``?connections`` reported ``mode: true`` (BACK-2525)."""
    def convert(value: Any) -> str:
        if value is True or value == '':
            return bare
        if not isinstance(value, str):
            raise TypeError(value)
        return value
    return convert


def _limit_value(value: Any) -> int:
    if isinstance(value, bool):  # a bare ?limit
        raise TypeError(value)
    return whole_number(value)


def _format_value(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError(value)
    return value


def _mode_flag(name: str) -> CliBinding:
    """A view's flag: bare, it is the view's default mode, as the bare URI key is."""
    return CliBinding((f'--{name}',), nargs='?', const=True, metavar='MODE')


_POWERPIVOT_MODES = ('tables', 'schema', 'measures', 'dax', 'relationships')
_POWERQUERY_LIST_MODES = ('list', 'show')
_SHEET_ANSWER, _SEARCH_ANSWER = ('xlsx_sheet',), ('xlsx_search',)
# The declaration `reveal xlsx` and xlsx:// are both generated from (D20, BACK-2626): each value is bound and checked
# before any work, and an unknown, unread or repeated control is an invalid request. The six views are answer selectors
# (ruling Q3): two in one request exit 2. ?range and ?search are the legacy words of --cells and --match.
_SHEET = ParamSpec('sheet', 'string|integer', 'Sheet to show (name, 0-based index or a unique part of a name)', None,
                   _text_value('sheet', '--sheet NAME'), ('sheet=Sales', 'sheet=0'), role='operation',
                   cli=CliBinding(('--sheet',), metavar='NAME'))
_CELLS = ParamSpec('cells', 'string', 'Cells of the sheet view: A1:C10, whole columns B:D, whole rows 5:7, or one '
                   'cell B2', None, _text_value('cells', '--cells A1:C10'), ('sheet=0&cells=A1:C10', 'sheet=0&cells=B:D', 'sheet=0&cells=5:7'),
                   cli=CliBinding(('--cells',), metavar='RANGE'), legacy=(LegacySpelling('range'),),
                   answers=_SHEET_ANSWER)
_MATCH = ParamSpec('match', 'array', 'Search every sheet for rows holding the text (case-insensitive); repeat to '
                   'require every term in a row', None, _match_terms, ('match=revenue', 'match=total'),
                   role='operation', repeatable=True, cli=CliBinding(('--match',), metavar='TEXT'),
                   legacy=(LegacySpelling('search'),))
# --format is the global flag; csv is the format only this noun renders (formats.noun_formats), so --format csv binds
# this control as ?format=csv spells it (BACK-2722 precedent: calls/imports --format dot).
_FORMAT = ParamSpec('format', 'string', 'Output override: csv (the sheet view as CSV, every row) or json; text follows '
                    '--format', None, _format_value, ('sheet=0&format=csv', 'format=json'), choices=('text', 'json', 'csv'),
                    role='presentation')
_LIMIT = ParamSpec('limit', 'integer', 'Rows (sheet view) or matches (search) to return; 0 = every row. Absent: the '
                   'sheet view shows 100 and says so; --format csv and the search return every row', None,
                   _limit_value, ('sheet=0&limit=500', 'sheet=0&limit=0', 'match=total&limit=20'), minimum=0, zero_policy='no cap',
                   cli=CliBinding(('--limit',), metavar='N'), answers=_SHEET_ANSWER + _SEARCH_ANSWER)
_FORMULAS = ParamSpec('formulas', 'boolean', 'Sheet view: on shows formulas instead of values (default off)', False,
                      switch_value, ('sheet=0&formulas=on',), cli=CliBinding(('--formulas',), metavar='on|off'),
                      answers=_SHEET_ANSWER)
_PARAM_SPECS: Tuple[ParamSpec, ...] = (
    _SHEET, _CELLS, _MATCH, _FORMAT, _LIMIT, _FORMULAS,
    ParamSpec('powerpivot', 'string', 'Extract the Power Pivot model; bare means schema', None,
              _mode_value('schema'), ('powerpivot=schema', 'powerpivot=dax', 'powerpivot=tables',
                                      'powerpivot=measures'), choices=_POWERPIVOT_MODES, role='operation',
              cli=_mode_flag('powerpivot')),
    ParamSpec('powerquery', 'string', 'Extract Power Query M code: list (bare), show (all M code) or one '
              'query by name (case-insensitive; a name that matches nothing exits 2)', None,
              _mode_value('list'), ('powerquery=list', 'powerquery=show', 'powerquery=SalesData'), role='operation',
              cli=_mode_flag('powerquery')),
    ParamSpec('names', 'string', 'List named ranges defined in the workbook: list (bare)', None,
              _mode_value('list'), ('names=list', 'names'), choices=('list',), role='operation',
              cli=_mode_flag('names')),
    ParamSpec('connections', 'string', 'List external data connections: list (bare) or show (full '
              'connection strings and commands)', None, _mode_value('list'),
              ('connections=list', 'connections'), choices=('list', 'show'), role='operation',
              cli=_mode_flag('connections')),
)
_SPEC = {spec.name: spec for spec in _PARAM_SPECS}
# --check never changed an xlsx answer (BACK-2708 ruling 2): an inert flag-only modifier with its note.
PARAM_SPECS: Tuple[ParamSpec, ...] = (*_PARAM_SPECS, legacy_check())
_SCHEMA_QUERY_PARAMS = param_schema(_PARAM_SPECS)

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
    '--cells A1:C10 uses standard A1 notation (also B:D, 5:7, B2); omit it to get the entire sheet',
    '--match TEXT is case-insensitive and searches all sheets; repeat it to require every term in a row',
    '--formulas on shows raw formulas instead of computed cell values',
    '--format csv exports every row of the sheet as CSV — pipe to other tools or save to file',
    '--limit 0 (or --all) shows every row; without --limit the sheet view shows 100 and says so',
    'The query-string spellings (?sheet=, ?range=, ?search=, ...) still work until 1.0, each with a note naming the flag',
    '--powerpivot schema shows Power Pivot tables and columns (Excel 2010/2013 XMLA format)',
    '--powerpivot dax shows DAX measure expressions (requires Excel 2010/2013 XMLA; modern Power BI exports not supported without reveal-cli[powerpivot])',
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'xlsx:///path/to/file.xlsx', 'description': 'List all sheets in workbook', 'output_type': 'xlsx_workbook'},
    {'uri': 'xlsx:///path/to/file.xlsx --sheet 0', 'description': 'Extract first sheet', 'output_type': 'xlsx_sheet'},
    {'uri': 'xlsx:///path/to/file.xlsx --sheet 0 --cells A1:C10', 'description': 'Extract cell range from the first sheet', 'output_type': 'xlsx_sheet'},
    {'uri': 'xlsx:///path/to/file.xlsx --sheet 0 --format csv', 'description': 'Export sheet as CSV', 'output_type': 'xlsx_sheet'},
    {'uri': 'xlsx:///path/to/file.xlsx --match revenue', 'description': 'Search all sheets for matching rows (case-insensitive)', 'output_type': 'xlsx_search'},
    {'uri': 'xlsx:///path/to/file.xlsx --match error --limit 20', 'description': 'Cross-sheet search with result limit', 'output_type': 'xlsx_search'},
    {'uri': 'xlsx:///path/to/file.xlsx --powerpivot tables', 'description': 'List Power Pivot tables with column counts', 'output_type': 'xlsx_powerpivot'},
    {'uri': 'xlsx:///path/to/file.xlsx --powerpivot schema', 'description': 'Show Power Pivot tables with all column names', 'output_type': 'xlsx_powerpivot'},
    {'uri': 'xlsx:///path/to/file.xlsx --powerpivot dax', 'description': 'Show DAX measure expressions', 'output_type': 'xlsx_powerpivot'},
]

_HELP_EXAMPLES = [
    {'uri': 'xlsx:///data/sales.xlsx', 'description': 'Show workbook overview with all sheets'},
    {'uri': 'xlsx:///data/sales.xlsx --sheet Sales', 'description': 'Extract "Sales" sheet data'},
    {'uri': 'xlsx:///data/sales.xlsx --sheet 0', 'description': 'Extract first sheet (by index)'},
    {'uri': 'xlsx:///data/sales.xlsx --sheet Sales --cells A1:D10', 'description': 'Extract cell range A1:D10 from the Sales sheet'},
    {'uri': 'xlsx:///data/sales.xlsx --sheet Sales --limit 50', 'description': 'Extract first 50 rows from the Sales sheet'},
    {'uri': 'xlsx:///data/sales.xlsx --sheet Sales --format csv', 'description': 'Export the Sales sheet as CSV'},
    {'uri': 'xlsx:///data/sales.xlsx --match revenue', 'description': 'Search for "revenue" across all sheets'},
    {'uri': 'xlsx:///data/model.xlsx --powerpivot schema', 'description': 'Show Power Pivot data model tables and columns'},
    {'uri': 'xlsx:///data/model.xlsx --powerpivot dax', 'description': 'Show all DAX measure expressions'},
    {'uri': 'xlsx:///data/model.xlsx --powerpivot relationships', 'description': 'Show table relationship graph'},
    {'uri': 'xlsx:///data/model.xlsx --powerquery list', 'description': 'List Power Query (M) queries embedded in the workbook'},
    {'uri': 'xlsx:///data/model.xlsx --powerquery show', 'description': 'Show all Power Query M code'},
    {'uri': 'xlsx:///data/model.xlsx --powerquery SalesData', 'description': 'Show M code for the "SalesData" query'},
    {'uri': 'xlsx:///data/model.xlsx --names list', 'description': 'List all named ranges and defined names'},
    {'uri': 'xlsx:///data/model.xlsx --connections list', 'description': 'List external data connections (ODBC, web, etc.)'},
    {'uri': 'xlsx:///data/model.xlsx --connections show', 'description': 'Show full connection strings and SQL commands'},
]

_HELP_FEATURES = [
    'Workbook overview with sheet list',
    'Sheet extraction by name or index',
    'Cell range extraction (A1 notation)',
    'CSV export',
    'Row limiting',
    'Cross-sheet search',
    'Power Pivot data model (tables, columns, DAX measures, relationships)',
    'Power Query M code extraction (--powerquery)',
    'Named ranges / defined names (--names list)',
    'External data connections (--connections)',
    'JSON and text output',
]

_HELP_TRY_NOW = [
    "reveal xlsx:///path/to/file.xlsx",
    "reveal xlsx:///path/to/file.xlsx --sheet 0",
    "reveal xlsx:///path/to/file.xlsx --powerpivot schema",
    "reveal xlsx:///path/to/file.xlsx --powerquery list",
]

_HELP_WORKFLOWS = [
    {
        'name': 'Extract Sheet Data',
        'scenario': 'Export Excel sheet to CSV for processing',
        'steps': [
            "reveal xlsx:///data/sales.xlsx              # See all sheets",
            "reveal xlsx:///data/sales.xlsx --sheet Sales --format csv > output.csv",
        ],
    },
    {
        'name': 'Quick Data Inspection',
        'scenario': 'Preview large Excel file',
        'steps': [
            "reveal xlsx:///data/huge.xlsx              # List sheets",
            "reveal xlsx:///data/huge.xlsx --sheet Summary --limit 20  # Preview first 20 rows",
        ],
    },
    {
        'name': 'Explore Power BI Export',
        'scenario': 'Understand a Power BI xlsx export data model',
        'steps': [
            "reveal xlsx:///data/report.xlsx                    # Overview — see model detected",
            "reveal xlsx:///data/report.xlsx --powerpivot schema  # Tables + columns",
            "reveal xlsx:///data/report.xlsx --powerpivot dax     # DAX measures",
            "reveal xlsx:///data/report.xlsx --powerquery list    # Power Query ETL queries",
        ],
    },
    {
        'name': 'Audit Data Sources',
        'scenario': 'Find where a workbook pulls its data from',
        'steps': [
            "reveal xlsx:///data/report.xlsx --connections list   # External connections",
            "reveal xlsx:///data/report.xlsx --connections show   # Full connection strings + SQL",
            "reveal xlsx:///data/report.xlsx --powerquery list    # Power Query sources",
        ],
    },
]


@register_adapter('xlsx')
@register_renderer(XlsxRenderer)
class XlsxAdapter(ResourceAdapter):
    """Adapter for exploring Excel spreadsheets via xlsx:// URIs.

    Example requests (the resource URI takes the same flags, D20):
        reveal xlsx /path/to/file.xlsx                          # Workbook overview (all sheets)
        reveal xlsx /path/to/file.xlsx --sheet 0                # First sheet (by index)
        reveal xlsx /path/to/file.xlsx --sheet Sales --cells A1:C10
        reveal xlsx /path/to/file.xlsx --match revenue          # Search across sheets
        reveal xlsx /path/to/file.xlsx --sheet Sales --format csv
    """
    HELP_CLUSTER = 'Data & Config'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    RESOURCE_IS_PATH = True  # a missing workbook is an invalid resource (D6 exit 2), not an adapter error
    RESULT_TYPE = _WORKBOOK
    DEFAULT_FAIL_ON = 'none'
    FINDINGS_POLICIES = ('none',)
    BOUND_QUERY_CALL = True
    PARAM_SPECS = PARAM_SPECS
    RESOURCE_SPEC = ResourceSpec(required=True, walks=False)
    # --all lifts the selected answer's row cap: it binds --limit 0's value (BACK-2729).
    CLI_QUERY_FLAGS = {'all': 'limit=1000000'}
    LEGACY_CHECK_TRANSPORT = True  # --check after the URI takes the router's check path, as json's and codex's
    result_type_for = staticmethod(_result_type)

    @classmethod
    def uri_execution_facts(cls, resource: str):
        """Every xlsx:// view shares D6 (BACK-2325); element, --check and batch modes stay legacy."""
        return cls.execution_facts

    @staticmethod
    def uri_result_type(resource: str) -> str:
        try:
            return _result_type(parse_query_params(resource.partition('?')[2]))
        except ValueError:  # a malformed query: construction rejects it (exit 2) before any view runs
            return _WORKBOOK

    @staticmethod
    def execution_facts(result: Any) -> ExecutionFacts:
        """A workbook, sheet or range that is not there, or a file that is not a workbook, is a
        request failure (exit 2); a failed read is a failed analysis and an answer missing a part
        it is built from (``_REQUIRED_PARTS``) is incomplete (exit 3)."""
        meta = result.get('meta', {}) if isinstance(result, dict) else {}
        codes = {entry.get('code') for entry in meta.get('errors', [])}
        cause = FailureCause.INVALID_REQUEST if 'invalid_request' in codes else FailureCause.ANALYSIS
        required = _REQUIRED_PARTS.get(result.get('type', '') if isinstance(result, dict) else '', frozenset())
        lost = any(warning.get('type') in required for warning in meta.get('warnings', []))
        return result_execution_facts(
            result, completeness=AnalysisCompleteness.INCOMPLETE if lost else AnalysisCompleteness.COMPLETE,
            failure_cause=cause)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for xlsx:// adapter."""
        return {
            'adapter': 'xlsx',
            'description': 'Excel spreadsheet inspection and data extraction',
            'uri_syntax': 'xlsx:///path/to/file.xlsx [--sheet NAME]',
            'query_params': _SCHEMA_QUERY_PARAMS,
            'resource': XlsxAdapter.RESOURCE_SPEC.schema(),
            'elements': {},
            'cli_flags': [flag for spec in _PARAM_SPECS for flag in spec.flags],
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
            'examples': _HELP_EXAMPLES,
            'features': _HELP_FEATURES,
            'try_now': _HELP_TRY_NOW,
            'workflows': _HELP_WORKFLOWS,
            'output_formats': ['text', 'json', 'csv'],
            'see_also': ['metrics://']
        }

    def __init__(self, resource: str, query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        """Initialize xlsx adapter.

        Args:
            resource: /path/to/file.xlsx, with or without the xlsx:// prefix and with or without an embedded query,
                so direct construction (XlsxAdapter("xlsx://x.xlsx?sheet=0")) and router construction (bare path plus
                a separate query) both work.
            query: The URI query when passed separately, bound through the declaration
            params: Already-bound or typed controls, in place of *query*

        Raises:
            RequestValidationError (a ValueError): an unknown, unread, repeated or invalid control, or a resource that
                is not a workbook
        """
        if not isinstance(resource, str) or not resource:
            raise RequestValidationError("xlsx requires a workbook path: reveal xlsx path/to/file.xlsx")
        if resource.startswith('xlsx://'):
            resource = resource[len('xlsx://'):]
        resource, _, embedded = resource.partition('?')
        query = query or embedded
        self.connection_string = resource + (f'?{query}' if query else '')
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(PARAM_SPECS, query or '', transport='uri')
        self.file_path: Optional[Path] = None
        self.analyzer: Optional[XlsxAnalyzer] = None

        self._parse_uri(resource)
        self._init_analyzer()

    def _parse_uri(self, path_part: str) -> None:
        """The workbook path (the query is bound in ``__init__``).

        Raises:
            RequestValidationError: no path, a missing file, or a file that is not a workbook
        """
        if not path_part:
            # An empty path read the cwd and named it absolutely in "Invalid Excel format" (BACK-2325).
            raise RequestValidationError("xlsx:// URI requires a workbook path: xlsx:///path/to/file.xlsx")
        # Handle absolute vs relative paths
        if path_part.startswith('/'):
            self.file_path = Path(path_part)
        else:
            self.file_path = Path.cwd() / path_part
        # Results name the file as the user did, not by its absolute path (BACK-1366).
        self.file_display = to_posix(path_part)

        if not self.file_path.exists():
            raise RequestValidationError(
                f"Invalid file path (file not found): {self.file_display}\n"
                f"Example: reveal xlsx:///path/to/existing/file.xlsx"
            )

        if not self.file_path.suffix.lower() in ('.xlsx', '.xlsm'):
            raise RequestValidationError(
                f"Invalid Excel format: {self.file_display}\n"
                f"Supported formats: .xlsx, .xlsm\n"
                f"Example: reveal xlsx:///data/sales.xlsx"
            )
        if self.file_path.is_file():
            self._check_workbook_file()

    def _check_workbook_file(self) -> None:
        """Reject a file that is not an Excel workbook (D6 exit 2); an unreadable one is a failed read
        (exit 3). ``zipfile.is_zipfile`` returns False on an OSError, so an unreadable workbook was
        reported as "not a zip archive" (BACK-2325); a corrupt or renamed file read as an empty
        workbook, exit 0 (BACK-2213), and so did a zip with no workbook part."""
        assert self.file_path is not None
        try:
            with open(self.file_path, 'rb'):
                pass
        except OSError as exc:
            raise OSError(f"{self.file_display} could not be read ({type(exc).__name__}: {exc.strerror})") from exc
        if not zipfile.is_zipfile(self.file_path):
            raise RequestValidationError(f"{self.file_display} is not a valid .xlsx workbook (not a zip archive)")
        with zipfile.ZipFile(self.file_path) as archive:
            names = set(archive.namelist())
        if XlsxAnalyzer.CONTENT_PATH not in names:
            raise RequestValidationError(
                f"{self.file_display} is not an Excel workbook: the zip has no {XlsxAnalyzer.CONTENT_PATH}")

    def _init_analyzer(self) -> None:
        """Initialize XlsxAnalyzer for the file."""
        if self.file_path:
            self.analyzer = XlsxAnalyzer(str(self.file_path))

    def get_structure(self) -> Dict[str, Any]:
        """Get workbook structure or sheet data based on query params.

        Returns:
            Dict containing workbook overview or sheet data
        """
        with self.composition_run():
            return self._get_structure()

    def _get_structure(self) -> Dict[str, Any]:
        if not self.analyzer:
            raise ValueError("No file loaded")
        view = next((key for key, _type in _VIEWS if self._value(key) is not None), None)
        if self._preferred_format() == 'csv' and view != 'sheet':
            raise RequestValidationError('--format csv renders the sheet view only: give --sheet NAME '
                                         '(json and text render every answer)')
        if view is None:
            return self._get_workbook_overview()
        value = self._value(view)
        handlers: Dict[str, Callable[[], Dict[str, Any]]] = {
            'powerpivot': lambda: self._get_powerpivot(value),
            'powerquery': lambda: self._get_powerquery(value),
            'names': self._get_named_ranges,
            'connections': lambda: self._get_connections(value),
            'sheet': lambda: self._get_sheet_data(value),
            'match': lambda: self._search_sheets(value),
        }
        return handlers[view]()

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
        # BACK-1166: fold the analyzer's own meta (e.g. a sheet_parse_failed
        # warning for a corrupt internal XML part) into this adapter's
        # composed meta -- previously discarded, so a corrupt sheet and a
        # genuinely empty sheet both rendered as a clean confidence:1.0 result.
        self.fold_meta(structure.get('meta'))
        if outcome_of(structure) == 'failed':
            return dict(ResultBuilder.create_error(
                result_type='xlsx_workbook', source=self.file_path or Path('unknown'),
                error=structure['error'], meta=dict(self.composed_meta() or {})))

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
            'file': self.file_display,
            'sheets': enhanced_sheets
        }

        format_param = self._preferred_format()
        if format_param:
            result_data['preferred_format'] = format_param

        # Power Pivot banner: detect model and show table names
        banner = self._build_powerpivot_banner()
        if banner:
            result_data['powerpivot_banner'] = banner

        return ResultBuilder.create(
            contract_version=CONTRACT_VERSION,
            result_type='xlsx_workbook',
            source=self.file_path or Path('unknown'),
            data=result_data,
            **self._meta_fields(),
        )

    def _get_sheet_data(self, sheet_identifier: str) -> Dict[str, Any]:
        """Extract data from specific sheet.

        Args:
            sheet_identifier: Sheet name or index (0-based)

        Returns:
            Dict with sheet data
        """
        if self.analyzer is None:
            raise ValueError("Analyzer not initialized")
        sheet_name = self._resolve_sheet_name(sheet_identifier)
        formulas = self._value('formulas')
        sheet = self.analyzer.sheet_rows(sheet_name, formulas=formulas)
        if sheet is None:
            raise ValueError(f"Failed to extract sheet: {sheet_name}")
        if sheet.get('too_large'):
            raise ValueError(f"Sheet '{sheet_name}' is too large to read ({sheet['size_mb']} MB)")
        if sheet.get('parse_failed'):
            raise ValueError(f"Sheet '{sheet_name}' could not be parsed (corrupt or malformed XML)")
        rows_data = sheet['rows_data']

        # Apply cell range if specified
        range_param = self._value('cells')
        first_row = 1
        if range_param:
            rows_data, first_row = self._apply_cell_range(rows_data, range_param)

        all_rows = rows_data = self._pad_rows(rows_data)
        format_param = self._preferred_format()
        limit, cause, hint = self._value('limit'), 'limit', 'raise --limit N (0 = every row)'
        if limit is None and format_param != 'csv':
            # BACK-1608: the view showed 20 rows of any sheet and said nothing; a CSV
            # export is every row, and the table view caps at a disclosed default.
            limit, cause = DEFAULT_SHEET_ROWS, 'auto_cap'
            hint = 'set --limit N (0 or --all = every row), or --format csv for every row'
        cap = _LIMIT.row_cap(limit)  # 0 is every row (COMMAND_MODEL Caps; ruling Q1)
        if cap is not None:
            rows_data = rows_data[:cap]

        # Build result data
        result_data = {
            'sheet_name': sheet_name,
            'rows': rows_data,
            'first_row': first_row,
            'dimension': sheet.get('dimension', ''),
            # The rows the view covers before ?limit=, blank ones included: the truncation
            # note's total. The analyzer's 'rows' counts stored rows only (BACK-2284).
            'rows_count': len(all_rows),
            'cols_count': sheet.get('cols', len(rows_data[0]) if rows_data else 0)
        }

        # Add preferred format if specified in query params
        if format_param:
            result_data['preferred_format'] = format_param

        result = ResultBuilder.create(
            contract_version=CONTRACT_VERSION,
            result_type='xlsx_sheet',
            source=self.file_path or Path('unknown'),
            data=result_data
        )
        # BACK-1543: '?sheet=S&limit=3' listed 3 of 701 rows; rows_count said 701 in JSON only.
        note_truncation(result, 'rows', len(rows_data), len(all_rows), cause, hint=hint)
        return result

    def _preferred_format(self) -> Optional[str]:
        """The ``?format=`` that overrides ``--format`` (csv, json); text follows ``--format``.
        A ``?format=text`` under ``--format json`` put the text cut note after the JSON (BACK-2525)."""
        value = self._value('format')
        return value if value != 'text' else None

    def _value(self, name: str) -> Any:
        """A bound control's value (its default when absent)."""
        return _SPEC[name].read(self.query_params)

    def _resolve_sheet_name(self, identifier: str) -> str:
        """The sheet ``?sheet=`` names: an exact name, a 0-based index, then a unique part of a name.

        Raises ValueError naming the sheets and their indexes when nothing matches, or
        listing the candidates when a partial name matches more than one (BACK-1608: the
        first partial match won, so ``?sheet=Sales`` could open ``Sales Archive``).
        """
        names = self.analyzer.sheet_names() if self.analyzer else []
        wanted = identifier.lower()
        exact = [n for n in names if n.lower() == wanted]
        if exact:
            return exact[0]
        if re.fullmatch(r'\d+', identifier) and int(identifier) < len(names):
            return names[int(identifier)]
        partial = [n for n in names if wanted in n.lower()]
        if len(partial) == 1:
            return partial[0]
        if partial:
            raise RequestValidationError(f"Sheet '{identifier}' is ambiguous: matches {', '.join(partial)}")
        listing = ', '.join(f'{i}={n}' for i, n in enumerate(names))
        raise RequestValidationError(
            f"Sheet not found: {identifier}. --sheet takes a name or a 0-based index: {listing}")

    @staticmethod
    def _pad_rows(rows: List[List[Any]]) -> List[List[Any]]:
        """Every row with cells padded with empty strings to the widest row's width.

        The reader drops trailing empty cells, so a short row had fewer fields than the header,
        and CSV and JSON consumers (pandas) shifted columns. A row with no cells at all stays
        empty: it keeps its Excel row number as a blank line.
        """
        width = max((len(row) for row in rows), default=0)
        return [list(row) + [''] * (width - len(row)) if row else list(row) for row in rows]

    def _apply_cell_range(self, rows: List[List[Any]], cell_range: str) -> Tuple[List[List[Any]], int]:
        """The cells of *cell_range*: ``A1:C10``, whole columns ``B:D``, whole rows ``5:7``, or one cell ``B2``,
        and the Excel row number of the first row returned.

        Raises ValueError on anything else (BACK-1608: an unparsed range, including the
        documented ``B:B`` and ``5:5``, returned the whole sheet as if it were the range).
        """
        spec = cell_range if ':' in cell_range else f'{cell_range}:{cell_range}'
        # Excel's last column is XFD: a column is at most three letters.
        match = re.fullmatch(r'([A-Z]{0,3})(\d*):([A-Z]{0,3})(\d*)', spec.strip(), re.IGNORECASE)
        start_col, start_row, end_col, end_row = match.groups() if match else ('', '', '', '')
        has_cols, has_rows = bool(start_col and end_col), bool(start_row and end_row)
        if (not (has_cols or has_rows) or bool(start_col) != bool(end_col)
                or bool(start_row) != bool(end_row) or (has_rows and int(start_row) < 1)):
            raise RequestValidationError(
                f"Invalid range: {cell_range} -- use A1:C10, B:D (columns), 5:7 (rows) or B2 (one cell)")
        first_row, last_row = (int(start_row) - 1, int(end_row)) if has_rows else (0, len(rows))
        if has_cols:
            first_col, last_col = self._col_letter_to_index(start_col), self._col_letter_to_index(end_col) + 1
            return [row[first_col:last_col] for row in rows[first_row:last_row]], first_row + 1
        return [list(row) for row in rows[first_row:last_row]], first_row + 1

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

    def _search_sheets(self, terms: List[str]) -> Dict[str, Any]:
        """The rows of every sheet that hold every term (case-insensitive, each in some cell of the row).

        Args:
            terms: The match terms, one or more

        Returns:
            Dict with search results grouped by sheet; ``pattern`` echoes the terms as a list
        """
        if self.analyzer is None:
            raise ValueError("Analyzer not initialized")

        found = self._matching_rows(terms)

        # BACK-1543: total_matches was counted after this cut, so ?limit=3 reported 3 of
        # 684 as the total. A negative limit dropped the tail instead of capping.
        cap = _LIMIT.row_cap(self._value('limit'))
        matches = found if cap is None else found[:cap]

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
            'pattern': list(terms),
            'total_matches': len(found),
            # Counted from every match, not the cut (B5: the cut's sheets were counted).
            'sheets_with_matches': len({m['sheet_name'] for m in found}),
            'sheet_results': sheet_results,
        }

        result = ResultBuilder.create(
            contract_version=CONTRACT_VERSION,
            result_type='xlsx_search',
            source=self.file_path or Path('unknown'),
            warnings=self._unsearched_warnings(),
            data=result_data
        )
        note_truncation(result, 'matches', len(matches), len(found), 'limit', hint='raise --limit N (0 = every match)')
        return result

    def _matching_rows(self, terms: List[str]) -> List[Dict[str, Any]]:
        """Every row holding the first term (the analyzer's search), kept when it also holds each other term."""
        assert self.analyzer is not None
        rest = [term.lower() for term in terms[1:]]
        return [m for m in self.analyzer.search_all_sheets(terms[0])
                if all(any(term in str(cell).lower() for cell in m['cells']) for term in rest)]

    def _unsearched_warnings(self) -> Optional[List[WarningEntry]]:
        """The ``sheets_unsearched`` warning when a sheet could not be read for the search, else None."""
        unsearched = list(getattr(self.analyzer, 'unsearched_sheets', []))
        if not unsearched:
            return None
        warning: WarningEntry = {
            'type': 'sheets_unsearched', 'count': len(unsearched),
            'files': [name for name, _ in unsearched[:5]],
            'failures': failure_records(unsearched),
            'message': (f"{len(unsearched)} sheet(s) could not be read and were not searched, so "
                        "matches may be missing: "
                        + ', '.join(f"{name} ({why})" for name, why in unsearched[:5])
                        + (f" and {len(unsearched) - 5} more" if len(unsearched) > 5 else '')),
        }
        return [warning]

    # -------------------------------------------------------------------------
    # Power Pivot helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _local(tag: str) -> str:
        """Strip XML namespace from an ElementTree tag."""
        return tag.split('}')[-1] if '}' in tag else tag

    def _meta_fields(self) -> Dict[str, Any]:
        """The composed warnings/errors/confidence as ResultBuilder.create kwargs."""
        meta = self.composed_meta() or {}
        return {'warnings': meta.get('warnings'), 'errors': meta.get('errors'),
                'confidence': meta.get('confidence')}

    def _note_unreadable_part(self, part: str, exc: Exception) -> None:
        """Disclose a workbook part that was skipped, so a corrupt part can't read as absent."""
        recorded = self.__dict__.get('_composed_warnings', [])
        if any(w.get('type') == 'part_unreadable' and w.get('file') == part for w in recorded):
            return
        self.fold_meta({'warnings': [{
            'type': 'part_unreadable',
            'file': part,
            'message': f"{part} could not be read ({type(exc).__name__}: {exc}); skipped",
        }]})

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
            except _PART_ERRORS as e:
                self._note_unreadable_part(name, e)
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
            except _PART_ERRORS as e:
                self._note_unreadable_part(name, e)
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
            except _PART_ERRORS as e:
                self._note_unreadable_part(name, e)
        return None

    def _parse_powerquery_stdlib(self, zf: zipfile.ZipFile, item_path: str) -> Dict[str, Any]:
        """Extract Power Query M code from a DataMashup blob using stdlib only.

        The DataMashup XML contains a base64-encoded binary.  The binary is a
        streaming ZIP (central directory may be empty) containing M formula
        files.  We scan for local file headers directly rather than relying on
        Python's ZipFile central-directory reader.
        """
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
        # No try/except here: a regex match means real base64 content was
        # found (the "no power query present" case is already handled
        # above), so a decode failure here is a genuine corruption/format
        # bug, not an absence. Let it propagate to the caller's own
        # except _POWERQUERY_ERRORS, which reports it via ResultBuilder.create_error
        # instead of silently degrading to a clean-looking empty result.
        binary = base64.b64decode(blob_b64)

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
                offset = data_start + comp_sz
                if method == 8 and comp_sz > 0:  # DEFLATE
                    try:
                        raw_data = _zlib.decompress(raw_data, -15)
                    except _zlib.error as e:
                        # The compressed bytes would decode as garbage M code: skip, say so.
                        self._note_unreadable_part(f'{item_path}:{fname}', e)
                        continue
                files[fname] = raw_data
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
        installed, allowing Tier 3 fallback.  An extraction failure raises:
        the caller falls back too, and says pbixray failed rather than that
        it is missing.
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
            # pbixray not installed — caller falls back to Tier 3 (pivot cache)
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
            except _PART_ERRORS as e:
                self._note_unreadable_part(name, e)
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
                    except _PART_ERRORS as e:
                        self._note_unreadable_part('xl/connections.xml', e)

                # Named ranges count (from workbook.xml definedNames)
                if 'xl/workbook.xml' in names_set:
                    try:
                        root = ET.fromstring(zf.read('xl/workbook.xml'))
                        count = sum(1 for el in root.iter() if self._local(el.tag) == 'definedName')
                        if count:
                            result['named_range_count'] = count
                    except _PART_ERRORS as e:
                        self._note_unreadable_part('xl/workbook.xml', e)

                return result if result else None
        except _ARCHIVE_ERRORS as e:
            logger.warning("powerpivot banner build failed for %s: %s", self.file_path, e)
            self.record_composed_error('_build_powerpivot_banner', self.file_path, e)
            return None

    def _get_powerquery(self, mode: str) -> Dict[str, Any]:
        """Extract Power Query M code for a ?powerquery=<mode> request.

        Modes:
            list  — query names and line counts (default)
            show  — full M code for all queries
            <name> — M code for a specific named query
        """
        if not self.file_path:
            return ResultBuilder.create_error(
                result_type='xlsx_powerquery',
                source=Path('unknown'),
                error="No file loaded",
            )
        named = mode not in _POWERQUERY_LIST_MODES
        try:
            with zipfile.ZipFile(self.file_path) as zf:
                pq_item = self._find_datamashup_item(zf)
                if not pq_item and named:  # plan rule 9: a name that matches nothing is not a clean answer
                    raise RequestValidationError(
                        f"Power Query not found: {mode} (no Power Query in {self.file_display})")
                if not pq_item:
                    return ResultBuilder.create(
                        contract_version=CONTRACT_VERSION,
                        result_type='xlsx_powerquery',
                        source=self.file_path,
                        data={
                            'file': self.file_display,
                            'mode': mode,
                            'has_powerquery': False,
                            'queries': [],
                        },
                        **self._meta_fields(),
                    )
                data = self._parse_powerquery_stdlib(zf, pq_item)
                if named:
                    data['queries'] = self._named_query(data.get('queries', []), mode)
                data['file'] = str(self.file_path)
                data['mode'] = mode
                return ResultBuilder.create(
                    contract_version=CONTRACT_VERSION,
                    result_type='xlsx_powerquery',
                    source=self.file_path,
                    data=data,
                    **self._meta_fields(),
                )
        except _POWERQUERY_ERRORS as e:
            return ResultBuilder.create_error(
                result_type='xlsx_powerquery',
                source=self.file_path,
                error=str(e),
            )

    def _named_query(self, queries: List[Dict[str, Any]], name: str) -> List[Dict[str, Any]]:
        """The query ``?powerquery=NAME`` names (case-insensitive). JSON listed every query and text
        said "not found", exit 0 (BACK-2525). With a query part unreadable the name may be in it: the
        answer is then empty and incomplete (exit 3), not a request that names nothing."""
        matches = [q for q in queries if q['name'].lower() == name.lower()]
        recorded = self.__dict__.get('_composed_warnings', [])
        if matches or any(w.get('type') == 'part_unreadable' for w in recorded):
            return matches
        available = ', '.join(sorted(q['name'] for q in queries)) or 'none'
        raise RequestValidationError(f"Power Query not found: {name}; available: {available}")

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
                        contract_version=CONTRACT_VERSION,
                        result_type='xlsx_names',
                        source=self.file_path,
                        data={'file': self.file_display, 'ranges': []},
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
                    contract_version=CONTRACT_VERSION,
                    result_type='xlsx_names',
                    source=self.file_path,
                    data={'file': self.file_display, 'ranges': ranges},
                )
        except _ARCHIVE_ERRORS as e:
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
                        contract_version=CONTRACT_VERSION,
                        result_type='xlsx_connections',
                        source=self.file_path,
                        data={'file': self.file_display, 'mode': mode, 'connections': []},
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
                    contract_version=CONTRACT_VERSION,
                    result_type='xlsx_connections',
                    source=self.file_path,
                    data={'file': self.file_display, 'mode': mode, 'connections': connections},
                )
        except _ARCHIVE_ERRORS as e:
            return ResultBuilder.create_error(
                result_type='xlsx_connections',
                source=self.file_path,
                error=str(e),
            )

    def _get_powerpivot(self, mode: str) -> Dict[str, Any]:
        """Extract Power Pivot model for a ?powerpivot=<mode> request (a mode in _POWERPIVOT_MODES)."""
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
                        contract_version=CONTRACT_VERSION,
                        result_type='xlsx_powerpivot',
                        source=self.file_path,
                        data={'file': self.file_display, 'has_model': False, 'mode': mode},
                        **self._meta_fields(),
                    )

                xmla_item = self._find_xmla_item(zf)
                if xmla_item:
                    # Tier 1: full XMLA metadata (Excel 2010/2013)
                    data = self._parse_xmla(zf, xmla_item)
                else:
                    # Tier 2: try pbixray for modern files (Power BI export, no XMLA)
                    pbixray_error: Optional[Exception] = None
                    try:
                        tier2 = self._parse_pbixray()
                    except Exception as e:  # boundary-ok: broad-except -- pbixray is a third-party package (not in this repo) whose failure set is not bounded; the fallback is disclosed as a part_unreadable warning and, for measures/dax, in the result's message
                        tier2, pbixray_error = None, e
                        self._note_unreadable_part(model_path, e)
                    if tier2 is not None:
                        data = tier2
                    else:
                        # Tier 3: pivot cache fallback (table names only)
                        data = self._parse_pivot_cache(zf)
                        if mode in ('measures', 'dax'):
                            data['message'] = (
                                'DAX measures not available — XMLA schema absent and pbixray could not '
                                f'read the model ({type(pbixray_error).__name__}: {pbixray_error}).'
                                if pbixray_error else
                                'DAX measures not available — XMLA schema absent (modern Power BI export). '
                                'Install pbixray (pip install "reveal-cli[powerpivot]") for full extraction.'
                            )

                data['file'] = str(self.file_path)
                data['model_path'] = model_path
                data['mode'] = mode

                return ResultBuilder.create(
                    contract_version=CONTRACT_VERSION,
                    result_type='xlsx_powerpivot',
                    source=self.file_path,
                    data=data,
                    **self._meta_fields(),
                )
        except _ARCHIVE_ERRORS as e:
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
        return self._get_sheet_data(element_name)

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the Excel file.

        Returns:
            Dict with file metadata
        """
        if not self.analyzer:
            return {'type': 'xlsx'}

        return self.analyzer.get_metadata()
