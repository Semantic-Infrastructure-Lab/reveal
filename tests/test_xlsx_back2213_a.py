"""xlsx:// range row numbers and non-zip workbooks (BACK-2213 lane A, F63/F69).

F63: ``?range=A3:C5`` printed its rows numbered 1-3; the guide promises Excel's own row
numbers, and the full-sheet view already numbers them that way.
F69: a file named .xlsx that is not a zip archive exited 0 with "No sheets found" and
warnings that named reveal's internal functions; it is now one error, exit 1.
"""

import contextlib
import io

import pytest

from reveal.adapters.xlsx import XlsxAdapter, XlsxRenderer

openpyxl = pytest.importorskip('openpyxl')


def _book(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Data'
    for r in range(1, 8):
        ws.append([f'a{r}', f'b{r}', r])
    path = tmp_path / 'book.xlsx'
    wb.save(path)
    return path


def _text(path, query):
    result = XlsxAdapter(f'xlsx://{path}', query).get_structure()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        XlsxRenderer.render_structure(result, 'text')
    return result, [line for line in out.getvalue().splitlines() if '|' in line]


@pytest.mark.parametrize('query,first,expected', [
    ('sheet=Data&range=A3:C5', 3, ['3  a3 | b3 | 3', '4  a4 | b4 | 4', '5  a5 | b5 | 5']),
    ('sheet=Data&range=4:4', 4, ['4  a4 | b4 | 4']),
    ('sheet=Data&range=B6', 6, []),  # one column: no ' | ' separator to find
    ('sheet=Data&range=B:C', 1, ['1  b1 | 1', '2  b2 | 2']),
])
def test_range_rows_keep_excel_numbers(tmp_path, query, first, expected):
    result, rows = _text(_book(tmp_path), query)
    assert result['first_row'] == first
    assert [r.strip() for r in rows[:len(expected)]] == expected


def test_single_cell_range_is_numbered_by_its_row(tmp_path):
    result = XlsxAdapter(f'xlsx://{_book(tmp_path)}', 'sheet=Data&range=B6').get_structure()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        XlsxRenderer.render_structure(result, 'text')
    assert '     6  b6' in out.getvalue()


def test_whole_sheet_starts_at_row_one(tmp_path):
    result, rows = _text(_book(tmp_path), 'sheet=Data')
    assert result['first_row'] == 1
    assert rows[0].strip() == '1  a1 | b1 | 1'


def test_non_zip_xlsx_is_an_error(tmp_path):
    bad = tmp_path / 'bad.xlsx'
    bad.write_text('junk\n', encoding='utf-8')
    with pytest.raises(ValueError, match=r'not a valid \.xlsx workbook \(not a zip archive\)'):
        XlsxAdapter(f'xlsx://{bad}')
