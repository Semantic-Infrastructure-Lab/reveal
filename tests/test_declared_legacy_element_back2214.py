"""A declared noun's URI request is read by the noun's own parser (``declared_uri_request``), which refused a positional
element outright. A noun whose element is a legacy spelling (a ``target:NOUN.element`` RETIREMENTS row: diff's
``reveal diff://L:R NAME``, BACK-2768) answers it with its note until the cut: the element joins the resource after a
``/`` (``declared.legacy_element_resource``), the spelling the row names, as the generic URI route answers it
(BACK-2214).

Shared owner: ``cli/routing/declared.py`` (``run_declared_uri_command``, ``run_declared_uri``). Effect on every noun:
none without a row; a declared noun without one refuses the element as before. The seam is shown on sqlite given a
test-only row (``DB/TABLE`` is its resource), so it holds before diff is declared.
"""
import json
import sqlite3
from contextlib import closing

import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import RETIREMENTS, Retirement
from reveal.cli.routing.declared import legacy_element_resource

pytestmark = [pytest.mark.component]


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with closing(sqlite3.connect(tmp_path / 'app.db')) as connection, connection:
        connection.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    return 'sqlite://app.db'


@pytest.fixture
def row(monkeypatch):
    monkeypatch.setitem(RETIREMENTS, 'target:sqlite.element', Retirement('sqlite://DB TABLE', 'sqlite://DB/TABLE'))
    return 'target:sqlite.element'


def _noted(doc):
    return [w['field'] for w in (doc.get('meta') or {}).get('warnings') or [] if w.get('code') == 'retired_spelling']


def test_a_row_joins_the_element_and_notes_it(db, row):
    run = _run_reveal_direct(db, 'users', '--format', 'json')
    assert run.returncode == 0, run.stderr
    doc = json.loads(run.stdout)
    assert _noted(doc) == [row]
    embedded = json.loads(_run_reveal_direct(f'{db}/users', '--format', 'json').stdout)
    assert doc['type'] == embedded['type'] and doc.get('table') == embedded.get('table')


def test_without_a_row_the_element_is_refused_as_before(db):
    run = _run_reveal_direct(db, 'users', '--format', 'json')
    assert run.returncode == 2, run.stderr
    assert "takes no positional element ('users')" in run.stdout + run.stderr


def test_the_joined_resource(row):
    assert legacy_element_resource('sqlite', 'app.db', 'users') == 'app.db/users'
    assert legacy_element_resource('sqlite', 'app.db/', 'users') == 'app.db/users'
    assert legacy_element_resource('env', '', 'PATH') is None  # no row: the caller refuses the element
