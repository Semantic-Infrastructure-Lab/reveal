"""xlsx:// exits by the D6 contract (BACK-2325, the reader slice after BACK-2521).

Every failure exited 1, the findings code: a missing file, a file that is not a workbook, a sheet or
range that names nothing, and an unreadable file alike. Now a request naming something that is not
there, or a file that is not an Excel workbook, is an invalid resource (exit 2, ``invalid_request``);
a workbook that could not be read, or an answer missing a part it needs, is a failed or incomplete
analysis (exit 3). A zip with no workbook inside read as "No sheets found", exit 0, and an unreadable
file was reported as "not a zip archive".
"""
import json
import os
import sys
import zipfile

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

openpyxl = pytest.importorskip('openpyxl')

_NS = ('xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
_PIVOT = 'xl/pivotCache/pivotCacheDefinition1.xml'


def _cell(value):
    return (f'<worksheet {_NS}><sheetData><row r="1"><c r="A1" t="inlineStr">'
            f'<is><t>{value}</t></is></c></row></sheetData></worksheet>')


@pytest.fixture
def books(tmp_path, monkeypatch):
    """Files under a cwd the queries name relatively, so a leaked absolute path is visible."""
    monkeypatch.chdir(tmp_path)
    wb = openpyxl.Workbook()
    wb.active.title = 'Data'
    wb.active.append(['revenue', 1])
    wb.create_sheet('Sales')
    wb.create_sheet('Sales Archive')
    wb.save(tmp_path / 'book.xlsx')
    (tmp_path / 'notzip.xlsx').write_text('hello', encoding='utf-8')
    (tmp_path / 'book.csv').write_text('a,b\n', encoding='utf-8')
    with zipfile.ZipFile(tmp_path / 'nobook.xlsx', 'w') as zf:
        zf.writestr('docProps/app.xml', '<Properties/>')
    with zipfile.ZipFile(tmp_path / 'corrupt.xlsx', 'w') as zf:
        zf.writestr('xl/workbook.xml', f'<workbook {_NS}><sheets><sheet name="S1" sheetId="1" r:id="rId1"/>'
                                       '<sheet name="S2" sheetId="2" r:id="rId2"/></sheets></workbook>')
        zf.writestr('xl/worksheets/sheet1.xml', _cell('one'))
        zf.writestr('xl/worksheets/sheet2.xml', '<worksheet><unclosed>')
    return tmp_path


def _json(uri):
    response = _run_reveal_direct(uri, '--format', 'json')
    return response.returncode, json.loads(response.stdout), response


def _codes(result):
    return [e.get('code') for e in result.get('meta', {}).get('errors', [])]


@pytest.mark.parametrize('uri,says', [
    ('xlsx://missing.xlsx', 'missing.xlsx'),
    ('xlsx://book.csv', 'book.csv'),
    ('xlsx://notzip.xlsx', 'not a zip archive'),
    ('xlsx://nobook.xlsx', 'xl/workbook.xml'),
    ('xlsx://book.xlsx?sheet=Nope', 'Sheet not found: Nope'),
    ('xlsx://book.xlsx?sheet=Sale', 'ambiguous'),
    ('xlsx://book.xlsx?sheet=Data&range=A1:', 'Invalid range'),
])
def test_a_resource_that_is_not_there_exits_2(books, uri, says):
    code, result, response = _json(uri)
    assert code == 2, result
    assert _codes(result) == ['invalid_request']
    assert says in result['error']
    assert str(books) not in response.stdout + response.stderr  # named as typed (BACK-1366)


def test_bare_scheme_is_an_invalid_request_not_the_cwd(books):
    code, result, response = _json('xlsx://')
    assert code == 2, result
    assert str(books) not in response.stdout + response.stderr


@pytest.mark.skipif(sys.platform == 'win32' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
                    reason='POSIX permissions; root reads a mode-000 file')
def test_an_unreadable_workbook_exits_3_and_says_so(books):
    locked = books / 'locked.xlsx'
    locked.write_bytes((books / 'book.xlsx').read_bytes())
    locked.chmod(0)
    try:
        code, result, _ = _json('xlsx://locked.xlsx')
    finally:
        locked.chmod(0o644)
    assert code == 3, result
    assert 'not a zip archive' not in result['error']
    assert 'Permission' in result['error'] or 'not readable' in result['error']


def test_a_corrupt_requested_sheet_exits_3(books):
    code, result, _ = _json('xlsx://corrupt.xlsx?sheet=S2')
    assert code == 3, result
    assert 'could not be parsed' in result['error']


def test_an_overview_with_a_corrupt_sheet_is_incomplete(books):
    code, result, _ = _json('xlsx://corrupt.xlsx')
    assert code == 3, result
    assert [w['type'] for w in result['meta']['warnings']] == ['sheet_parse_failed']
    assert len(result['sheets']) == 2  # the readable sheet is still listed beside the lost one


def test_a_search_that_skipped_a_sheet_is_incomplete(books):
    code, result, _ = _json('xlsx://corrupt.xlsx?search=one')
    assert code == 3, result
    assert result['total_matches'] == 1
    assert [w['type'] for w in result['meta']['warnings']] == ['sheets_unsearched']


def _lzma_book(root):
    """A workbook whose pivot cache part is a damaged LZMA member (the BACK-1853 fixture)."""
    path = root / 'pivot.xlsx'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_LZMA) as zf:
        zf.writestr('xl/workbook.xml', f'<workbook {_NS}><sheets><sheet name="S1" sheetId="1" r:id="rId1"/>'
                                       '</sheets></workbook>', compress_type=zipfile.ZIP_STORED)
        zf.writestr('xl/worksheets/sheet1.xml', _cell('one'), compress_type=zipfile.ZIP_STORED)
        zf.writestr(_PIVOT, b'<a>' + b'x' * 5000 + b'</a>')
    raw = bytearray(path.read_bytes())
    start = raw.index(_PIVOT.encode()) + len(_PIVOT) + 4
    for i in range(start, start + 40):
        raw[i] ^= 0xFF
    path.write_bytes(bytes(raw))
    return path


def test_a_model_view_missing_its_part_is_incomplete(books):
    _lzma_book(books)
    code, result, _ = _json('xlsx://pivot.xlsx?powerpivot=tables')
    assert code == 3, result
    assert 'part_unreadable' in [w['type'] for w in result['meta']['warnings']]


def test_the_overview_banner_part_is_disclosed_but_not_required(books):
    """The overview's Power Pivot banner is optional decoration: a lost banner part is a warning, exit 0."""
    _lzma_book(books)
    code, result, _ = _json('xlsx://pivot.xlsx')
    assert code == 0, result
    assert 'part_unreadable' in [w['type'] for w in result['meta']['warnings']]


@pytest.mark.parametrize('query,result_type', [
    ('', 'xlsx_workbook'),
    ('?sheet=Data', 'xlsx_sheet'),
    ('?sheet=1', 'xlsx_sheet'),
    ('?sheet=Data&range=A1:B1', 'xlsx_sheet'),
    ('?search=revenue', 'xlsx_search'),
    ('?names', 'xlsx_names'),
    ('?connections', 'xlsx_connections'),
    ('?powerquery', 'xlsx_powerquery'),
    ('?powerpivot=tables', 'xlsx_powerpivot'),
])
def test_clean_answers_exit_0_with_their_type(books, query, result_type):
    """Control: passes before and after the fix."""
    code, result, _ = _json(f'xlsx://book.xlsx{query}')
    assert code == 0, result
    assert result['type'] == result_type
    assert not result.get('meta', {}).get('errors')
