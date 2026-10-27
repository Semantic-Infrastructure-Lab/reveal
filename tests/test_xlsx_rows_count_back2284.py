"""BACK-2284: an xlsx:// sheet's ``rows_count`` counts the rows the view lists.

``rows_count`` came from the analyzer's count of stored rows (Excel stores no row for a
blank one), while ``.rows`` keeps a blank row as ``[]`` so row numbers line up (BACK-1608)
and the truncation note counts every row. A sheet with a blank row 3 said ``Rows: 4`` over
five listed rows, and ``&limit=2`` said ``showing 2 of 5``. ``rows_count`` is now the number
of rows the view covers before ``?limit=``: the same total as the truncation note.
"""

import pytest

from reveal.adapters.xlsx import XlsxAdapter, XlsxRenderer
from reveal.utils.results import truncations_of

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl builds the fixture workbooks")


@pytest.fixture
def workbook(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Year", "Amount"])
    ws.append([2001, 10])
    ws["A4"] = 2003  # row 3 is blank: Excel stores no <row> for it
    ws["B4"] = 30
    ws.append([2004, 40])
    dense = wb.create_sheet("Dense")
    for i in range(4):
        dense.append([i, i * 2])
    path = tmp_path / "book.xlsx"
    wb.save(path)
    return path


def _sheet(path, query):
    return XlsxAdapter(f"xlsx://{path}?{query}").get_structure()


def test_rows_count_counts_the_blank_row(workbook):
    result = _sheet(workbook, "sheet=Sales")
    assert len(result['rows']) == 5
    assert not any(result['rows'][2])  # the blank row is listed
    assert result['rows_count'] == 5


def test_rows_count_matches_the_truncation_total(workbook):
    result = _sheet(workbook, "sheet=Sales&limit=2")
    [cut] = truncations_of(result)
    assert (cut['shown'], cut['total']) == (2, 5)
    assert result['rows_count'] == cut['total']


def test_text_header_says_the_listed_row_count(workbook, capsys):
    XlsxRenderer.render_structure(_sheet(workbook, "sheet=Sales"), 'text')
    out = capsys.readouterr().out
    assert "Rows: 5, Cols: 2" in out


def test_rows_count_of_a_range_is_the_range(workbook):
    result = _sheet(workbook, "sheet=Sales&range=A2:B4")
    assert result['first_row'] == 2
    assert len(result['rows']) == 3
    assert result['rows_count'] == 3


# Negative control: a sheet without gaps keeps the count it had.

def test_dense_sheet_count_is_unchanged(workbook):
    result = _sheet(workbook, "sheet=Dense")
    assert result['rows_count'] == len(result['rows']) == 4
