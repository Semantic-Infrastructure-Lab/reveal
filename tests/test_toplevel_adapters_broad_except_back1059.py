"""BACK-1059: the top-level adapter modules (xlsx, pack, imports, help) catch the
errors their input can produce and let a bug in reveal propagate; a failed optional
signal is disclosed in the result.

Unexpected failure is injected as ``_InjectedBug`` (an Exception subclass that no
handler lists). Negative controls: the expected error still takes the old path.
"""

import zipfile

import pytest

from reveal.adapters import help as help_mod
from reveal.adapters.help import HelpAdapter
from reveal.adapters.imports import ImportsAdapter, _extract_one_file
from reveal.adapters.pack import PackAdapter
from reveal.adapters.xlsx import XlsxAdapter

pytestmark = pytest.mark.component


class _InjectedBug(Exception):
    """A failure no handler here expects: stands in for a bug in reveal."""


def _raise_bug(*_a, **_k):
    raise _InjectedBug('injected')


# ---------------------------------------------------------------- xlsx

_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
    '<definedNames><definedName name="Rate">Sheet1!$A$1</definedName></definedNames>'
    '</workbook>'
)
_CONNECTIONS = (
    '<connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<connection name="c1" type="1" connectionString="x"/></connections>'
)


def _xlsx(tmp_path, extra=None, workbook=_WORKBOOK, connections=_CONNECTIONS):
    path = tmp_path / 'book.xlsx'
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('xl/workbook.xml', workbook)
        zf.writestr('xl/connections.xml', connections)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return path


def _adapter(path, query):
    return XlsxAdapter(f'xlsx://{path}', query)


def _lzma_member_corrupt(tmp_path):
    """A workbook whose xl/workbook.xml member is LZMA-compressed and damaged."""
    path = tmp_path / 'lzma.xlsx'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_LZMA) as zf:
        zf.writestr('xl/workbook.xml', b'<a>' + b'x' * 5000 + b'</a>')
        zf.writestr('xl/connections.xml', b'<a>' + b'y' * 5000 + b'</a>')
    raw = bytearray(path.read_bytes())
    for name in (b'xl/workbook.xml', b'xl/connections.xml'):
        start = raw.index(name) + len(name) + 4
        for i in range(start, start + 40):
            raw[i] ^= 0xFF
    path.write_bytes(bytes(raw))
    return path


def _truncated(tmp_path):
    path = tmp_path / 'trunc.xlsx'
    path.write_bytes(b'PK\x03\x04 this is not a workbook')
    return path


_XLSX_VIEWS = [
    ('names', 'xlsx_names', 'xl/workbook.xml'),
    ('connections', 'xlsx_connections', 'xl/connections.xml'),
    ('powerquery', 'xlsx_powerquery', 'customXml/item1.xml'),
    ('powerpivot', 'xlsx_powerpivot', 'customXml/item1.xml'),
]


@pytest.mark.parametrize('query,result_type', [(q, t) for q, t, _ in _XLSX_VIEWS])
def test_xlsx_view_bug_propagates(tmp_path, monkeypatch, query, result_type):
    """A bug inside the view (here: zipfile cannot be opened by our own code) is not an error result."""
    path = _xlsx(tmp_path, {'xl/model/item.data': b'', 'customXml/item1.xml': '<a/>'})
    adapter = _adapter(path, query)
    # Reached by every one of the four views once the zip is open.
    monkeypatch.setattr(XlsxAdapter, '_local', staticmethod(_raise_bug))
    monkeypatch.setattr(XlsxAdapter, '_find_datamashup_item', _raise_bug)
    monkeypatch.setattr(XlsxAdapter, '_detect_powerpivot', _raise_bug)
    with pytest.raises(_InjectedBug):
        adapter.get_structure()


@pytest.mark.parametrize('query,result_type', [(q, t) for q, t, _ in _XLSX_VIEWS])
def test_xlsx_view_corrupt_zip_is_an_error_result(tmp_path, query, result_type):
    """Control: a file that is not a zip still comes back as the view's error result."""
    adapter = _adapter(_xlsx(tmp_path), query)
    adapter.file_path = _truncated(tmp_path)
    result = adapter.get_structure()
    assert result['type'] == result_type
    assert result.get('error')


@pytest.mark.parametrize('query', ['names', 'connections'])
def test_xlsx_view_malformed_xml_is_an_error_result(tmp_path, query):
    """Control: malformed XML in the part (ET.ParseError) is the view's error result."""
    path = _xlsx(tmp_path, workbook='<workbook><unclosed>', connections='<connections><unclosed>')
    result = _adapter(path, query).get_structure()
    assert result.get('error')


@pytest.mark.parametrize('query', ['names', 'connections'])
def test_xlsx_view_corrupt_lzma_member_is_an_error_result(tmp_path, query):
    """Control: a damaged LZMA member raises lzma.LZMAError, which is not in the stdlib
    zipfile exception family; the view still reports it as an error result."""
    result = _adapter(_lzma_member_corrupt(tmp_path), query).get_structure()
    assert result.get('error')


def test_xlsx_powerquery_bad_base64_is_an_error_result(tmp_path):
    """Control: a DataMashup blob that is not valid base64 (binascii.Error) is the error result."""
    blob = 'A' * 101  # 101 base64 chars: incorrect padding
    item = f'<DataMashup xmlns="http://schemas.microsoft.com/DataMashup">{blob}</DataMashup>'
    path = _xlsx(tmp_path, {'customXml/item1.xml': item})
    result = _adapter(path, 'powerquery').get_structure()
    assert result['type'] == 'xlsx_powerquery'
    assert result.get('error')


def test_xlsx_banner_bug_propagates(tmp_path, monkeypatch):
    adapter = _adapter(_xlsx(tmp_path), None)
    monkeypatch.setattr(XlsxAdapter, '_detect_powerpivot', _raise_bug)
    with pytest.raises(_InjectedBug):
        adapter._build_powerpivot_banner()


def test_xlsx_banner_corrupt_zip_is_disclosed(tmp_path):
    """Control: an unreadable archive gives no banner and a composed error naming the builder."""
    adapter = _adapter(_xlsx(tmp_path), None)
    adapter.file_path = _truncated(tmp_path)
    assert adapter._build_powerpivot_banner() is None
    meta = adapter.composed_meta()
    assert meta and any('_build_powerpivot_banner' in e['message'] for e in meta['errors'])


def test_xlsx_banner_corrupt_lzma_member_is_disclosed(tmp_path):
    adapter = _adapter(_xlsx(tmp_path), None)
    adapter.file_path = _lzma_member_corrupt(tmp_path)
    assert adapter._build_powerpivot_banner() is None
    assert adapter.composed_meta()['errors']


def test_xlsx_pbixray_failure_still_falls_back_and_is_disclosed(tmp_path, monkeypatch):
    """Control: the third-party pbixray boundary stays broad; the fallback names the failure."""
    path = _xlsx(tmp_path, {'xl/model/item.data': b''})
    adapter = _adapter(path, 'powerpivot=measures')
    monkeypatch.setattr(XlsxAdapter, '_parse_pbixray', _raise_bug)
    result = adapter.get_structure()
    assert not result.get('error')
    assert 'pbixray could not read the model (_InjectedBug: injected)' in result['message']


# ---------------------------------------------------------------- pack


def _pack_dir(tmp_path):
    (tmp_path / 'app.py').write_text('import util\n', encoding='utf-8')
    (tmp_path / 'util.py').write_text('x = 1\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('query', ['architecture=true', 'focus=util'])
def test_pack_failed_graph_is_disclosed(tmp_path, monkeypatch, query):
    """--architecture / --focus ask for the import graph; when building it fails the
    pack says so instead of ranking as if the signal were zero."""
    monkeypatch.setattr(ImportsAdapter, '_build_graph', _raise_bug)
    adapter = PackAdapter(str(_pack_dir(tmp_path)), query)
    result = adapter.get_structure()
    warning = result['meta'].get('relevance_warning') or ''
    assert 'import graph' in warning and '_InjectedBug: injected' in warning
    assert adapter.relevance_warning == warning


def test_pack_failed_graph_still_returns_a_pack(tmp_path, monkeypatch):
    """Control: the failure does not end the pack (the signal is additive)."""
    monkeypatch.setattr(ImportsAdapter, '_build_graph', _raise_bug)
    result = PackAdapter(str(_pack_dir(tmp_path)), 'architecture=true').get_structure()
    assert result['meta']['selected'] == 2


def test_pack_working_graph_has_no_failure_warning(tmp_path):
    """Control: nothing to disclose when the graph builds."""
    result = PackAdapter(str(_pack_dir(tmp_path)), 'architecture=true').get_structure()
    assert 'relevance_warning' not in result['meta']


# ---------------------------------------------------------------- imports


def test_imports_structure_bug_propagates(tmp_path, monkeypatch):
    """_extract_one_file no longer turns an escaped analysis bug into 'no structure'."""
    f = tmp_path / 'a.py'
    f.write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.setattr('reveal.adapters.ast.analysis.analyze_file', _raise_bug)
    with pytest.raises(_InjectedBug):
        _extract_one_file(str(f), True)


def test_imports_structure_none_is_still_none(tmp_path, monkeypatch):
    """Control: analyze_file's own 'could not analyze' (None) still yields structure None."""
    f = tmp_path / 'a.py'
    f.write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.setattr('reveal.adapters.ast.analysis.analyze_file', lambda _p: None)
    assert _extract_one_file(str(f), True)[3] is None


def test_imports_structure_collected_for_a_real_file(tmp_path):
    f = tmp_path / 'a.py'
    f.write_text('def f():\n    return 1\n', encoding='utf-8')
    structure = _extract_one_file(str(f), True)[3]
    assert structure and structure['elements']


# ---------------------------------------------------------------- help


def test_static_guide_bug_propagates(monkeypatch):
    """A bug in the guide-rendering code is not reported as 'Load failed'."""
    adapter = HelpAdapter()
    monkeypatch.setattr(HelpAdapter, '_add_related_next', _raise_bug)
    with pytest.raises(_InjectedBug):
        adapter._load_static_help('tricks')


@pytest.mark.parametrize('exc', [PermissionError('denied'), IsADirectoryError('is a dir'),
                                 UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid start byte')])
def test_static_guide_unreadable_file_is_a_load_failure(monkeypatch, exc):
    """Control: a guide file that cannot be read or decoded is the 'Load failed' result."""
    def _open(*_a, **_k):
        raise exc
    adapter = HelpAdapter()
    monkeypatch.setattr(help_mod, 'open', _open, raising=False)
    result = adapter._load_static_help('tricks')
    assert result['error'] == 'Load failed'
    assert str(exc) in result['message']


def test_static_guide_missing_file_is_file_not_found(monkeypatch):
    def _open(*_a, **_k):
        raise FileNotFoundError('gone')
    adapter = HelpAdapter()
    monkeypatch.setattr(help_mod, 'open', _open, raising=False)
    assert adapter._load_static_help('tricks')['error'] == 'File not found'


def test_static_guide_still_loads():
    result = HelpAdapter()._load_static_help('tricks')
    assert result['type'] == 'static_guide' and result['content']
