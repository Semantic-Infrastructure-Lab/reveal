"""BACK-1608: xlsx:// sheet data is the sheet's data, and ?sheet=N is the sheet listed as N.

The sheet view and ``?format=csv`` "export" parsed the analyzer's 20-row text preview
back into cells: every sheet stopped at 20 rows with no marker, a leading number in a
row was stripped as if it were a line number, and a skipped cell shifted the rest left.
The overview numbered sheets from 1 while ``?sheet=`` counts from 0, and a partial name
opened the first sheet that contained it. An unparsed ``?range=`` (including the
documented ``B:B`` and ``5:5``) returned the whole sheet, and a blank row (which Excel
does not store) moved every later row up, so ``A10:C20`` was not Excel's rows 10-20.
"""

import pytest

from reveal.adapters.xlsx import DEFAULT_SHEET_ROWS, XlsxAdapter, XlsxRenderer
from reveal.analyzers.office.openxml import XlsxAnalyzer
from reveal.display.formatting import print_truncations
from reveal.utils.results import truncations_of

openpyxl = pytest.importorskip("openpyxl", reason="openpyxl builds the fixture workbooks")

ROWS = 119  # data rows below the header; more than both the old 20 and DEFAULT_SHEET_ROWS


@pytest.fixture
def workbook(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales Archive"
    ws.append(["old", "data"])
    data = wb.create_sheet("Sales")
    data.append(["Year", "Region", "Amount"])
    for i in range(ROWS):
        data.append([2000 + i, f"R{i}", i])
    sparse = wb.create_sheet("Sparse")
    sparse["A1"] = "a"
    sparse["C1"] = "c"
    gaps = wb.create_sheet("Gaps")
    gaps["A1"] = "top"
    gaps["A4"] = "after two blank rows"
    path = tmp_path / "book.xlsx"
    wb.save(path)
    return path


def _sheet(path, query):
    return XlsxAdapter(f"xlsx://{path}?{query}").get_structure()


def test_csv_export_has_every_row(workbook):
    result = _sheet(workbook, "sheet=Sales&format=csv")
    assert len(result['rows']) == ROWS + 1
    assert truncations_of(result) == []


def test_leading_number_is_data_not_a_line_number(workbook):
    rows = _sheet(workbook, "sheet=Sales&format=csv")['rows']
    assert rows[1] == ['2000', 'R0', '0']
    assert rows[-1] == [str(2000 + ROWS - 1), f'R{ROWS - 1}', str(ROWS - 1)]


def test_default_view_cap_is_disclosed(workbook):
    result = _sheet(workbook, "sheet=Sales")
    assert len(result['rows']) == DEFAULT_SHEET_ROWS
    [cut] = truncations_of(result)
    assert (cut['shown'], cut['total']) == (DEFAULT_SHEET_ROWS, ROWS + 1)


def test_limit_beyond_the_old_preview(workbook):
    assert len(_sheet(workbook, "sheet=Sales&limit=110")['rows']) == 110


def test_skipped_cell_keeps_its_column(workbook):
    assert _sheet(workbook, "sheet=Sparse")['rows'] == [['a', '', 'c']]


def test_exact_name_beats_earlier_partial_match(workbook):
    assert _sheet(workbook, "sheet=Sales")['sheet_name'] == 'Sales'


def test_ambiguous_partial_name_is_an_error(workbook):
    with pytest.raises(ValueError, match="ambiguous"):
        _sheet(workbook, "sheet=ale")


def test_index_counts_from_zero_like_the_overview(workbook, capsys):
    assert _sheet(workbook, "sheet=1")['sheet_name'] == 'Sales'
    XlsxRenderer.render_structure(XlsxAdapter(f"xlsx://{workbook}").get_structure(), 'text')
    out = capsys.readouterr().out
    assert '[0]  Sales Archive' in out and '[1]  Sales' in out


def test_out_of_range_index_names_the_valid_ones(workbook):
    with pytest.raises(ValueError, match=r"0-based index: 0=Sales Archive, 1=Sales, 2=Sparse, 3=Gaps"):
        _sheet(workbook, "sheet=4")


def test_csv_cut_goes_to_stderr_not_into_the_csv(workbook, capsys):
    result = _sheet(workbook, "sheet=Sales&format=csv&limit=2")
    print_truncations(result, 'text')
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'showing 2 of' in captured.err


def test_file_element_preview_says_what_it_left_out(workbook):
    source = XlsxAnalyzer(str(workbook)).extract_element('sheet', 'Sales')['source']
    assert f"{ROWS + 1 - XlsxAnalyzer.PREVIEW_ROWS} more rows not shown" in source


@pytest.mark.parametrize('cell_range, expected', [
    ('A2:B3', [['2000', 'R0'], ['2001', 'R1']]),
    ('B2', [['R0']]),
    ('5:5', [['2003', 'R3', '3']]),
])
def test_documented_range_forms(workbook, cell_range, expected):
    assert _sheet(workbook, f"sheet=Sales&range={cell_range}")['rows'] == expected


def test_whole_column_range(workbook):
    rows = _sheet(workbook, "sheet=Sales&range=B:B&format=csv")['rows']
    assert rows[:2] == [['Region'], ['R0']] and len(rows) == ROWS + 1


@pytest.mark.parametrize('cell_range', ['junk', 'A:C5', '0:3'])
def test_unparsed_range_is_an_error_not_the_whole_sheet(workbook, cell_range):
    with pytest.raises(ValueError, match="Invalid range"):
        _sheet(workbook, f"sheet=Sales&range={cell_range}")


def test_blank_rows_keep_later_rows_at_their_numbers(workbook):
    assert _sheet(workbook, "sheet=Gaps&format=csv")['rows'] == [['top'], [], [], ['after two blank rows']]
    assert _sheet(workbook, "sheet=Gaps&range=A4")['rows'] == [['after two blank rows']]
