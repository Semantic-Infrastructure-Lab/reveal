"""The xlsx part-level handlers disclose a member zipfile cannot decode (BACK-1853).

``_PART_ERRORS`` lacked ``NotImplementedError`` (unsupported compression) and
``lzma.LZMAError`` (a damaged LZMA member, which is not an OSError), so a customXml or
pivotCache part like that crashed the handler instead of reading as ``part_unreadable``.
"""
import zipfile

import pytest

from reveal.adapters.xlsx import XlsxAdapter

pytestmark = pytest.mark.component

_PIVOT = 'xl/pivotCache/pivotCacheDefinition1.xml'
_ITEM = 'customXml/item1.xml'
_PARTS = [_PIVOT, _ITEM]


def _book(tmp_path, compression=zipfile.ZIP_STORED, corrupt=()):
    path = tmp_path / 'book.xlsx'
    with zipfile.ZipFile(path, 'w', compression) as zf:
        zf.writestr('xl/workbook.xml', '<workbook/>', compress_type=zipfile.ZIP_STORED)
        for part in _PARTS:
            zf.writestr(part, b'<a>' + b'x' * 5000 + b'</a>')
    raw = bytearray(path.read_bytes())
    for part in corrupt:
        start = raw.index(part.encode()) + len(part) + 4
        for i in range(start, start + 40):
            raw[i] ^= 0xFF
    path.write_bytes(bytes(raw))
    return path


def _adapter(path):
    adapter = XlsxAdapter(f'xlsx://{path}', None)
    adapter.file_path = path
    return adapter


def _unreadable(adapter):
    meta = adapter.composed_meta() or {}
    return sorted(w['file'] for w in meta.get('warnings', []) if w.get('type') == 'part_unreadable')


HANDLERS = {
    'detect_powerpivot': (lambda a, zf: a._detect_powerpivot(zf), _PIVOT),
    'parse_pivot_cache': (lambda a, zf: a._parse_pivot_cache(zf), _PIVOT),
    'find_xmla_item': (lambda a, zf: a._find_xmla_item(zf), _ITEM),
    'find_datamashup_item': (lambda a, zf: a._find_datamashup_item(zf), _ITEM),
}


@pytest.mark.parametrize('handler', HANDLERS)
def test_corrupt_lzma_member_is_part_unreadable(tmp_path, handler):
    run, part = HANDLERS[handler]
    adapter = _adapter(_book(tmp_path, zipfile.ZIP_LZMA, corrupt=_PARTS))
    with zipfile.ZipFile(adapter.file_path) as zf:
        run(adapter, zf)
    assert _unreadable(adapter) == [part]


@pytest.mark.parametrize('handler', HANDLERS)
def test_unsupported_compression_member_is_part_unreadable(tmp_path, monkeypatch, handler):
    run, part = HANDLERS[handler]
    adapter = _adapter(_book(tmp_path))

    def read(self, name, *a, **k):
        raise NotImplementedError('That compression method is not supported')

    monkeypatch.setattr(zipfile.ZipFile, 'read', read)
    with zipfile.ZipFile(adapter.file_path) as zf:
        run(adapter, zf)
    assert _unreadable(adapter) == [part]


def test_readable_parts_are_not_reported(tmp_path):
    adapter = _adapter(_book(tmp_path))
    with zipfile.ZipFile(adapter.file_path) as zf:
        for run, _part in HANDLERS.values():
            run(adapter, zf)
    assert _unreadable(adapter) == []


# ------------------------------------------- an unreadable sheet is not an empty sheet

_NS = ('xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _sheet_book(tmp_path, bad_sheet2):
    path = tmp_path / 'sheets.xlsx'
    sheet = lambda v: (f'<worksheet {_NS}><sheetData><row r="1"><c r="A1" t="inlineStr">'
                       f'<is><t>{v}</t></is></c></row></sheetData></worksheet>')
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('xl/workbook.xml', f'<workbook {_NS}><sheets><sheet name="S1" sheetId="1" r:id="rId1"/>'
                                       '<sheet name="S2" sheetId="2" r:id="rId2"/></sheets></workbook>')
        zf.writestr('xl/worksheets/sheet1.xml', sheet('one'))
        zf.writestr('xl/worksheets/sheet2.xml', '<worksheet><unclosed>' if bad_sheet2 else sheet('two'))
    return path


def test_element_view_of_a_corrupt_sheet_is_not_rows_zero(tmp_path):
    from reveal.analyzers.office.openxml import XlsxAnalyzer
    analyzer = XlsxAnalyzer(str(_sheet_book(tmp_path, bad_sheet2=True)))
    source = analyzer.extract_element('sheet', 'S2')['source']
    assert 'Rows: 0' not in source
    assert 'Not read: corrupt or malformed XML' in source
    clean = XlsxAnalyzer(str(_sheet_book(tmp_path, bad_sheet2=False))).extract_element('sheet', 'S2')['source']
    assert 'Rows: 1, Cols: 1' in clean and 'Not read' not in clean


def _search(path, pattern):
    adapter = XlsxAdapter(f'xlsx://{path}', f'search={pattern}')
    adapter.file_path = path
    return adapter.get_structure()


def test_search_discloses_the_sheet_it_could_not_read(tmp_path):
    result = _search(_sheet_book(tmp_path, bad_sheet2=True), 'two')
    assert result['total_matches'] == 0
    (warning,) = [w for w in result['meta']['warnings'] if w.get('type') == 'sheets_unsearched']
    assert warning['files'] == ['S2'] and 'corrupt or malformed XML' in warning['message']


def test_search_of_a_readable_book_has_no_unsearched_warning(tmp_path):
    result = _search(_sheet_book(tmp_path, bad_sheet2=False), 'two')
    assert result['total_matches'] == 1
    assert not [w for w in result.get('meta', {}).get('warnings', []) if w.get('type') == 'sheets_unsearched']
