"""xlsx under the declared command model (BACK-2626 batch 2, BACK-2598's xlsx part).

Preservation pins first: what xlsx:// answers today on the URI, the typed API and MCP, so the declarations that follow
cannot change an answer by accident. The fixture is a throwaway workbook: sheet ``Sales`` (a header and 150 rows, the
word "revenue" in three of them, one formula), ``Sales Archive`` (one row holding "revenue total"), ``Summary`` (one
formula) and one defined name, ``Regions``.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import RequestValidationError

pytestmark = pytest.mark.component

openpyxl = pytest.importorskip('openpyxl')


@pytest.fixture
def book(tmp_path, monkeypatch):
    from openpyxl.workbook.defined_name import DefinedName
    wb = openpyxl.Workbook()
    sales = wb.active
    sales.title = 'Sales'
    sales.append(['region', 'item', 'amount'])
    for i in range(1, 151):
        sales.append([f'r{i}', 'revenue' if i in (10, 50, 120) else 'cost', i])
    sales['D2'] = '=C2*2'
    wb.create_sheet('Sales Archive').append(['revenue total', 99])
    wb.create_sheet('Summary').append(['total', '=SUM(Sales!C2:C151)'])
    regions = DefinedName('Regions', attr_text='Sales!$A$2:$A$151')
    try:
        wb.defined_names['Regions'] = regions
    except TypeError:  # openpyxl before 3.1 keeps defined names in a list
        wb.defined_names.append(regions)
    wb.save(tmp_path / 'book.xlsx')
    (tmp_path / 'notazip.xlsx').write_text('plain text\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return 'book.xlsx'


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


def _rows(doc):
    return [row_num for sheet in doc['sheet_results'] for row_num in (m['row_num'] for m in sheet['matches'])]


# --- preservation pins -----------------------------------------------------------------------------------------------

def test_workbook_overview(book):
    run, doc = _json(f'xlsx://{book}')
    assert run.returncode == 0
    assert doc['type'] == 'xlsx_workbook' and doc['source'] == book
    assert [(s['name'], s['rows'], s['formulas']) for s in doc['sheets']] == [
        ('Sales', 151, 1), ('Sales Archive', 1, 0), ('Summary', 1, 1)]
    text = _run_reveal_direct(f'xlsx://{book}')
    assert text.returncode == 0 and 'Sheets (3)' in text.stdout and 'Sales Archive' in text.stdout


def test_sheet_view_caps_at_the_disclosed_default(book):
    run, doc = _json(f'xlsx://{book}?sheet=Sales')
    assert run.returncode == 0
    assert (doc['type'], doc['sheet_name'], len(doc['rows']), doc['rows_count']) == ('xlsx_sheet', 'Sales', 100, 151)
    cut = [w for w in doc['meta']['warnings'] if w.get('type') == 'truncated']
    assert [(w['shown'], w['total'], w['cause']) for w in cut] == [(100, 151, 'auto_cap')]
    text = _run_reveal_direct(f'xlsx://{book}?sheet=Sales')
    assert 'Sheet: Sales (A1:D151)' in text.stdout and 'Rows: 151, Cols: 4' in text.stdout


def test_sheet_view_by_index_limit_range_and_formulas(book):
    assert len(_json(f'xlsx://{book}?sheet=Sales&limit=3')[1]['rows']) == 3
    assert _json(f'xlsx://{book}?sheet=1')[1]['sheet_name'] == 'Sales Archive'
    doc = _json(f'xlsx://{book}?sheet=Sales&range=A2:B3')[1]
    assert (doc['rows'], doc['first_row']) == ([['r1', 'cost'], ['r2', 'cost']], 2)
    assert _json(f'xlsx://{book}?sheet=Sales&range=D2&formulas=true')[1]['rows'] == [['=C2*2']]


def test_sheet_csv_export_is_every_row(book):
    run = _run_reveal_direct(f'xlsx://{book}?sheet=Sales&format=csv')
    assert run.returncode == 0
    lines = run.stdout.replace('\r\n', '\n').splitlines()
    assert len(lines) == 151 and lines[0] == 'region,item,amount,' and lines[-1] == 'r150,cost,150,'


def test_search_counts_every_match(book):
    run, doc = _json(f'xlsx://{book}?search=revenue')
    assert run.returncode == 0
    assert (doc['type'], doc['total_matches'], doc['sheets_with_matches']) == ('xlsx_search', 4, 2)
    assert _rows(doc) == [11, 51, 121, 1]
    text = _run_reveal_direct(f'xlsx://{book}?search=revenue')
    assert '4 matches for "revenue" across 2 sheets' in text.stdout


def test_named_ranges(book):
    run, doc = _json(f'xlsx://{book}?names=list')
    assert run.returncode == 0
    assert [(r['name'], r['reference']) for r in doc['ranges']] == [('Regions', 'Sales!$A$2:$A$151')]


@pytest.mark.parametrize('uri, message', [
    ('xlsx://missing.xlsx', 'missing.xlsx'),
    ('xlsx://notazip.xlsx', 'not a valid .xlsx workbook'),
    ('xlsx://book.xlsx?sheet=Nope', 'Sheet not found: Nope'),
    ('xlsx://book.xlsx?sheet=Sal', 'ambiguous'),
    ('xlsx://book.xlsx?sheet=Sales&range=1A', 'Invalid range'),
])
def test_target_that_matches_nothing_exits_2(book, uri, message):
    run = _run_reveal_direct(uri)
    assert run.returncode == 2
    assert message in run.stderr


def test_api_and_mcp(book):
    from reveal.mcp_server import reveal_run
    assert len(api.query(f'xlsx://{book}?sheet=Sales&limit=3')['rows']) == 3
    assert api.query(f'xlsx://{book}')['type'] == 'xlsx_workbook'
    with pytest.raises(RequestValidationError, match='Sheet not found'):
        api.query(f'xlsx://{book}?sheet=Nope')
    assert len(json.loads(reveal_run([f'xlsx://{book}?sheet=Sales&limit=3', '--format', 'json']))['rows']) == 3
