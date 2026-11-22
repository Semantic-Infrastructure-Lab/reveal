"""A control RETIREMENTS marks removed is refused on the Python API in its row's words (BACK-2752, plan rule 7).

``api.query`` refuses a typed keyword (``UnsupportedOverrideError``) or a URI key (``RequestValidationError``) whose
``param:<noun>.<key>`` row says it was removed, before the request binds or names an element, on the URI form and the
noun form; the CLI's URI route already refuses such a key with the row's text. Any other undeclared keyword keeps the
shared message. The rows here are test-local, set on sqlite (a declared noun with one control).
"""
import sqlite3
from contextlib import closing

import pytest

from reveal import api
from reveal.cli.invocation import RETIREMENTS, Retirement
from reveal.errors import RequestValidationError, UnsupportedOverrideError

TEXT = 'nothing: the test row says why'


@pytest.fixture
def database(tmp_path, monkeypatch):
    with closing(sqlite3.connect(tmp_path / 'app.db')) as connection, connection:
        connection.execute('CREATE TABLE items (id INTEGER PRIMARY KEY)')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(RETIREMENTS, 'param:sqlite.gone', Retirement('sqlite gone', TEXT, stage='error', removed=True))
    return 'app.db'


@pytest.mark.parametrize('call', [
    lambda db: api.query(f'sqlite://{db}', gone=True),
    lambda db: api.query(f'sqlite://{db}', element_name='items', gone=True),  # refused before the element
    lambda db: api.query('sqlite', db, gone=True),
])
def test_a_removed_keyword_is_unsupported_and_says_why(database, call):
    with pytest.raises(UnsupportedOverrideError) as raised:
        call(database)
    assert str(raised.value) == f"unsupported control 'gone': sqlite gone was removed; use {TEXT}."


def test_a_removed_uri_key_is_an_invalid_request_that_says_why(database):
    with pytest.raises(RequestValidationError) as raised:
        api.query(f'sqlite://{database}?gone=1')
    assert not isinstance(raised.value, UnsupportedOverrideError)
    assert str(raised.value) == f"unsupported control 'gone': sqlite gone was removed; use {TEXT}."


def test_another_undeclared_keyword_keeps_the_shared_message(database):
    """Negative control: a keyword with no removed row is refused as before, naming the supported controls."""
    with pytest.raises(UnsupportedOverrideError, match="unsupported control 'other'; supported controls: view"):
        api.query(f'sqlite://{database}', other=True)
    assert api.query(f'sqlite://{database}')['type'] == 'sqlite_database'


def test_a_note_stage_row_is_not_a_removal(database, monkeypatch):
    """Only a removed row refuses: a note-stage legacy word keeps answering with its note (sqlite --check)."""
    assert not RETIREMENTS['param:sqlite.check'].removed
    assert api.query(f'sqlite://{database}', check=True)['type'] == 'sqlite_health'
