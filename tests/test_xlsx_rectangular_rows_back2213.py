"""xlsx:// rows are rectangular: CSV and JSON rows are padded to the sheet width (BACK-2213 V12).

The reader drops trailing empty cells, so a short row had fewer fields than the header and
`pd.read_csv` silently turned the first column into the index.
"""
import contextlib
import csv
import io

import pytest

from reveal.adapters.xlsx import XlsxAdapter, XlsxRenderer

openpyxl = pytest.importorskip('openpyxl')


@pytest.fixture()
def ragged(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'S'
    ws.append(['a', 'b'])
    ws.append([1, 2, 3])
    ws.append([4])
    path = tmp_path / 'rag.xlsx'
    wb.save(path)
    return path


def _rows(path, query):
    return XlsxAdapter(f'xlsx://{path}', query).get_structure()['rows']


def test_json_rows_have_one_width(ragged):
    rows = _rows(ragged, 'sheet=S')
    assert {len(r) for r in rows} == {3}
    assert rows[0] == ['a', 'b', ''] and rows[2] == ['4', '', '']


def test_csv_export_parses_as_a_rectangle(ragged):
    result = XlsxAdapter(f'xlsx://{ragged}', 'sheet=S&format=csv').get_structure()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        XlsxRenderer.render_structure(result, 'csv')
    parsed = list(csv.reader(io.StringIO(out.getvalue())))
    assert {len(r) for r in parsed} == {3}


def test_range_rows_are_rectangular_too(ragged):
    assert {len(r) for r in _rows(ragged, 'sheet=S&range=A1:C3')} == {3}


def test_a_sheet_that_is_already_rectangular_is_unchanged(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.title = 'S'
    wb.active.append(['a', 'b'])
    wb.active.append([1, 2])
    path = tmp_path / 'rect.xlsx'
    wb.save(path)
    assert _rows(path, 'sheet=S') == [['a', 'b'], ['1', '2']]
