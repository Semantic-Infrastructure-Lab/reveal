"""xlsx:// rejects a query value it cannot apply (BACK-2525, plan rule 9, guideline 5).

Each value was silently replaced: ``?powerpivot=bogus`` answered as ``schema``, ``?connections=``
and ``?formulas=``/``?format=`` took any value and read as their default, ``?limit=abc`` and
``?limit=-5`` read as no limit, ``?powerquery=Nope`` returned every query with exit 0, and a bare
``?search`` crashed with ``'bool' object has no attribute 'lower'`` (exit 3). Bare ``?powerquery``
and ``?connections`` reported ``mode: true``. Now each parameter is declared once, checked before
any work, and a value that names nothing exits 2 naming what it accepts.
"""
import base64
import json
import struct
import zipfile
import zlib

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

openpyxl = pytest.importorskip('openpyxl')


def _member(name, body):
    """One local-file-header entry (deflate), as a DataMashup blob holds them."""
    header = struct.pack('<HHHHHIIIHH', 20, 0, 8, 0, 0, 0, len(body), 0, len(name), 0)
    return b'PK\x03\x04' + header + name.encode('utf-8') + body


def _query_member(name, code):
    deflater = zlib.compressobj(wbits=-15)
    return _member(name, deflater.compress(code.encode('utf-8')) + deflater.flush())


@pytest.fixture
def books(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wb = openpyxl.Workbook()
    wb.active.title = 'Data'
    for i in range(150):
        wb.active.append(['revenue', i])
    wb.save(tmp_path / 'book.xlsx')
    wb.save(tmp_path / 'queries.xlsx')
    inner = (_query_member('Formulas/Sales.m', 'let\n    Source = 1\nin\n    Source')
             + _query_member('Formulas/Costs.m', 'let\n    Source = 2\nin\n    Source'))
    blob = base64.b64encode(inner + b'\x00' * 100).decode('ascii')
    with zipfile.ZipFile(tmp_path / 'queries.xlsx', 'a') as zf:
        zf.writestr('customXml/item1.xml',
                    f'<?xml version="1.0" encoding="utf-8"?><DataMashup>{blob}</DataMashup>')
    return tmp_path


def _json(uri):
    response = _run_reveal_direct(uri, '--format', 'json')
    return response.returncode, json.loads(response.stdout)


@pytest.mark.parametrize('query,says', [
    ('powerpivot=bogus', 'relationships'),
    ('connections=bogus', "'show'"),
    ('sheet=Data&limit=abc', 'limit'),
    ('sheet=Data&limit=-5', 'limit must be >= 0'),
    ('sheet=Data&limit=1.5', 'limit'),
    ('search=revenue&limit=abc', 'limit'),
    ('sheet=Data&formulas=maybe', 'formulas'),
    ('sheet=Data&format=xml', "'csv'"),
    ('search', 'search'),
    ('search=', 'search'),
    ('names=bogus', "'list'"),
    ('names=true', "'list'"),
    ('powerquery=Nope', 'no Power Query'),
])
def test_a_value_it_cannot_apply_exits_2_and_says_what_it_accepts(books, query, says):
    code, result = _json(f'xlsx://book.xlsx?{query}')
    assert code == 2, result
    assert [e.get('code') for e in result['meta']['errors']] == ['invalid_request']
    assert says in result['error']


def test_a_query_name_that_matches_nothing_lists_the_queries(books):
    code, result = _json('xlsx://queries.xlsx?powerquery=Nope')
    assert code == 2, result
    assert 'Nope' in result['error'] and 'Costs, Sales' in result['error']


def test_a_name_that_may_be_in_an_unreadable_query_is_incomplete_not_invalid(books):
    inner = (_query_member('Formulas/Sales.m', 'let\n    Source = 1\nin\n    Source')
             + _member('Formulas/Bad.m', b'\xff' * 20))  # does not inflate: a part_unreadable warning
    blob = base64.b64encode(inner + b'\x00' * 100).decode('ascii')
    with zipfile.ZipFile(books / 'damaged.xlsx', 'w') as zf:
        with zipfile.ZipFile(books / 'book.xlsx') as src:
            for item in src.infolist():
                zf.writestr(item, src.read(item.filename))
        zf.writestr('customXml/item1.xml',
                    f'<?xml version="1.0" encoding="utf-8"?><DataMashup>{blob}</DataMashup>')
    code, result = _json('xlsx://damaged.xlsx?powerquery=Bad')
    assert code == 3, result
    assert result['queries'] == []
    assert [w['type'] for w in result['meta']['warnings']] == ['part_unreadable']


def test_a_named_query_answers_with_that_query_only(books):
    code, result = _json('xlsx://queries.xlsx?powerquery=sales')  # names match case-insensitively
    assert code == 0, result
    assert [q['name'] for q in result['queries']] == ['Sales']
    text = _run_reveal_direct('xlsx://queries.xlsx?powerquery=sales')
    assert text.returncode == 0 and '// Sales' in text.stdout and 'Costs' not in text.stdout


@pytest.mark.parametrize('query,mode', [
    ('powerquery', 'list'), ('powerquery=show', 'show'),
    ('connections', 'list'), ('connections=show', 'show'),
    ('powerpivot', 'schema'), ('powerpivot=relationships', 'relationships'),
])
def test_a_bare_view_takes_its_default_mode_by_name(books, query, mode):
    code, result = _json(f'xlsx://queries.xlsx?{query}')
    assert code == 0, result
    assert result['mode'] == mode


@pytest.mark.parametrize('query,rows,cause', [
    ('sheet=Data', 100, 'auto_cap'),
    ('sheet=Data&limit=0', 100, 'auto_cap'),  # explicit zero keeps its meaning: the default cap
    ('sheet=Data&limit=5', 5, 'limit'),
    ('sheet=Data&formulas=true&limit=5', 5, 'limit'),
    ('sheet=Data&formulas=false&format=text&limit=5', 5, 'limit'),
])
def test_valid_values_still_answer(books, query, rows, cause):
    code, result = _json(f'xlsx://book.xlsx?{query}')
    assert code == 0, result
    assert len(result['rows']) == rows
    assert [w['cause'] for w in result['meta']['warnings'] if w['type'] == 'truncated'] == [cause]


def test_csv_still_returns_every_row(books):
    response = _run_reveal_direct('xlsx://book.xlsx?sheet=Data&format=csv')
    assert response.returncode == 0
    assert len(response.stdout.strip().splitlines()) == 150


@pytest.mark.parametrize('query', ['names', 'names=list', 'search=revenue&limit=3'])
def test_flag_and_search_controls(books, query):
    code, result = _json(f'xlsx://book.xlsx?{query}')
    assert code == 0, result


def test_the_library_call_raises_before_any_work(books):
    from reveal.adapters.xlsx import XlsxAdapter
    from reveal.errors import RequestValidationError
    with pytest.raises(RequestValidationError, match='powerpivot'):
        XlsxAdapter('xlsx://book.xlsx?powerpivot=bogus')


def test_the_schema_comes_from_the_declarations(books):
    from reveal.adapters.xlsx import XlsxAdapter
    params = XlsxAdapter.get_schema()['query_params']
    assert params['powerpivot']['choices'] == ['tables', 'schema', 'measures', 'dax', 'relationships']
    assert params['connections']['choices'] == ['list', 'show']
    assert params['names']['choices'] == ['list']
    assert params['format']['choices'] == ['text', 'json', 'csv']
    assert params['limit']['minimum'] == 0
