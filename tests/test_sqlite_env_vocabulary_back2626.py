"""sqlite and env under the declared command model (BACK-2626 batch 1, BACK-2598's sqlite/env part).

Preservation pins first: what the two resource nouns answer today on the URI, the typed API and MCP, so the
declarations that follow cannot change an answer by accident. The fixtures are a throwaway database and variables the
test sets itself (never HOME, USER or another variable the host owns, V042).
"""
import json
import os
import sqlite3
import sys

import pytest

from conftest import _run_reveal_direct
from reveal import api
from reveal.errors import RequestValidationError

TOKEN, PLAIN, MISSING = 'REVEAL_T2626_TOKEN', 'REVEAL_T2626_PLAIN', 'REVEAL_T2626_NOT_SET'


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / 'app.db'
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, name TEXT);"
        "CREATE TABLE posts(id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), title TEXT);"
        "CREATE INDEX idx_posts_user ON posts(user_id);"
        "CREATE VIEW v_titles AS SELECT title FROM posts;"
        "INSERT INTO users(email, name) VALUES ('a@example.test', 'A'), ('b@example.test', 'B');"
        "INSERT INTO posts(user_id, title) VALUES (1, 'one'), (2, 'two'), (9, 'orphan');")
    connection.commit()
    connection.close()
    (tmp_path / 'notadb.db').write_text('plain text\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return 'app.db'


@pytest.fixture
def variables(monkeypatch):
    monkeypatch.setenv(TOKEN, 'fixture-secret-value')
    monkeypatch.setenv(PLAIN, 'fixture-plain-value')
    monkeypatch.delenv(MISSING, raising=False)


def _json(*argv):
    run = _run_reveal_direct(*argv, '--format', 'json')
    return run, (json.loads(run.stdout) if run.stdout.strip().startswith('{') else {})


# --- preservation pins: sqlite ---------------------------------------------------------------------------------------

def test_sqlite_database_overview(db):
    run, doc = _json(f'sqlite://{db}')
    assert run.returncode == 0
    assert doc['type'] == 'sqlite_database' and doc['source'] == db and doc['path'] == db
    assert doc['statistics'] == {'tables': 2, 'views': 1, 'total_rows': 5, 'foreign_keys': 1}
    assert [(t['name'], t['type']) for t in doc['tables']] == [('posts', 'table'), ('users', 'table'),
                                                              ('v_titles', 'view')]
    text = _run_reveal_direct(f'sqlite://{db}')
    assert text.returncode == 0 and 'SQLite Database: app.db' in text.stdout


@pytest.mark.parametrize('table, kind, rows', [('users', 'table', 2), ('v_titles', 'view', 3)])
def test_sqlite_table_and_view(db, table, kind, rows):
    run, doc = _json(f'sqlite://{db}/{table}')
    assert run.returncode == 0
    assert (doc['type'], doc['table'], doc['kind'], doc['row_count']) == ('sqlite_table', table, kind, rows)


@pytest.mark.parametrize('uri, message', [
    ('sqlite://app.db/nope', 'Table not found: nope'),
    ('sqlite://missing.db', 'Database file not found: missing.db'),
    ('sqlite://notadb.db', 'is not a SQLite database'),
])
def test_sqlite_target_that_matches_nothing_exits_2(db, uri, message):
    run = _run_reveal_direct(uri)
    assert run.returncode == 2
    assert message in run.stderr


def test_sqlite_health_check(db):
    run, doc = _json(f'sqlite://{db}', '--check')
    assert run.returncode == 1  # a foreign-key violation only (BACK-2753 owns the health exit codes)
    assert (doc['type'], doc['status'], doc['integrity'], doc['foreign_key_violations']) == (
        'sqlite_health', 'warning', True, 1)


def test_sqlite_api_and_mcp(db):
    from reveal.mcp_server import reveal_run
    cli = _json(f'sqlite://{db}')[1]
    assert api.query(f'sqlite://{db}')['statistics'] == cli['statistics']
    assert api.query(f'sqlite://{db}/users')['row_count'] == 2
    with pytest.raises(RequestValidationError, match='Table not found'):
        api.query(f'sqlite://{db}/nope')
    assert json.loads(reveal_run([f'sqlite://{db}', '--format', 'json']))['statistics'] == cli['statistics']


# --- preservation pins: env ------------------------------------------------------------------------------------------

def test_env_variable_redacts_a_secret(variables):
    run, doc = _json(f'env://{TOKEN}')
    assert run.returncode == 0
    assert (doc['type'], doc['name'], doc['value'], doc['sensitive'], doc['raw_value']) == (
        'env_variable', TOKEN, '***', True, None)
    assert 'fixture-secret-value' not in run.stdout + run.stderr


def test_env_variable_and_listing(variables):
    run, doc = _json(f'env://{PLAIN}')
    assert run.returncode == 0
    assert (doc['name'], doc['value'], doc['sensitive'], doc['category']) == (PLAIN, 'fixture-plain-value', False,
                                                                              'Custom')
    run, doc = _json('env://')
    assert run.returncode == 0 and doc['type'] == 'environment'
    listed = {v['name']: v for rows in doc['categories'].values() for v in rows}
    assert (listed[TOKEN]['value'], listed[PLAIN]['value']) == ('***', 'fixture-plain-value')


def test_env_missing_variable_exits_2_on_the_cli_and_mcp(variables):
    from reveal.mcp_server import reveal_run
    run = _run_reveal_direct(f'env://{MISSING}')
    assert run.returncode == 2
    assert f"Element '{MISSING}' not found" in run.stderr
    assert 'not found' in reveal_run([f'env://{MISSING}'])


def test_env_text_answer(variables):
    run = _run_reveal_direct(f'env://{TOKEN}')
    assert run.returncode == 0
    assert f'Environment Variable: {TOKEN}' in run.stdout and 'Value: ***' in run.stdout


# --- B2: the typed API answers the variable the URI names (one answer, CLI/API parity, rule 9) ----------------------

@pytest.mark.parametrize('name', [PLAIN, TOKEN])
def test_api_env_uri_answers_the_variable_as_the_cli_does(variables, name):
    """api.query('env://NAME') answered the whole listing (type environment), not the variable the URI names. The API's
    structure envelope always carries a (here empty) meta, which the CLI's element envelope omits."""
    answer = api.query(f'env://{name}')
    assert answer.pop('meta', {'warnings': [], 'errors': []}) == {'warnings': [], 'errors': []}
    assert answer == _json(f'env://{name}')[1]


def test_api_env_uri_naming_no_variable_is_an_invalid_request(variables):
    """A variable that is not set is not a listing: the CLI exits 2, so the API raises the request error."""
    with pytest.raises(RequestValidationError, match=MISSING):
        api.query(f'env://{MISSING}')


def test_api_env_listing_is_unchanged(variables):
    """Negative control: the bare env:// is still the listing on the API."""
    doc = api.query('env://')
    assert doc['type'] == 'environment'
    assert {v['name'] for rows in doc['categories'].values() for v in rows} >= {TOKEN, PLAIN}


# --- sqlite under its declarations (ruled: Q4 --view health with --check its translated legacy spelling; B10) -------
# Red until the declarations land: reveal sqlite is generated from them, typed keywords bind, health is a view.

def _answer(doc):
    from conftest import without_request_notes
    doc = without_request_notes(doc)
    doc.get('execution', {}).pop('command', None)
    return doc


@pytest.mark.parametrize('sub, uri', [(['app.db'], 'sqlite://app.db'), (['app.db/users'], 'sqlite://app.db/users'),
                                      (['app.db/v_titles'], 'sqlite://app.db/v_titles')])
def test_sqlite_subcommand_answers_as_the_resource_uri(db, sub, uri):
    sub_run, sub_doc = _json('sqlite', *sub)
    uri_run, uri_doc = _json(uri)
    assert (sub_run.returncode, uri_run.returncode) == (0, 0)
    assert _answer(sub_doc) == _answer(uri_doc)


def test_sqlite_view_health_is_the_health_answer_and_check_its_legacy_spelling(db):
    view_run, view_doc = _json('sqlite', 'app.db', '--view', 'health')
    check_run, check_doc = _json('sqlite', 'app.db', '--check')
    uri_run, uri_doc = _json('sqlite://app.db', '--view', 'health')
    assert (view_run.returncode, check_run.returncode, uri_run.returncode) == (1, 1, 1)  # BACK-2753 owns the codes
    assert view_doc['type'] == 'sqlite_health' and view_doc['foreign_key_violations'] == 1
    assert _answer(view_doc)['foreign_key_violations'] == _answer(check_doc)['foreign_key_violations']
    notes = [w for w in check_doc['meta']['warnings'] if '--check' in w.get('message', '')]
    assert notes and '--view health' in notes[0]['message']
    assert not [w for w in view_doc['meta']['warnings'] if '--check' in w.get('message', '')]


def test_sqlite_typed_api_binds_its_controls(db):
    from reveal.errors import UnsupportedOverrideError
    assert api.query('sqlite', 'app.db')['type'] == 'sqlite_database'
    assert api.query('sqlite', 'app.db', view='health')['type'] == 'sqlite_health'
    with pytest.raises(UnsupportedOverrideError):
        api.query('sqlite://app.db', bogus_kw=1)


def test_sqlite_unknown_query_key_is_refused(db):
    run = _run_reveal_direct('sqlite://app.db?bogus=1')
    assert run.returncode == 2 and 'bogus' in run.stderr


@pytest.mark.skipif(sys.platform == 'win32' or getattr(os, 'geteuid', lambda: 1)() == 0,
                    reason='chmod 000 does not make a file unreadable on Windows or for root')
def test_sqlite_health_of_an_unreadable_database_is_incomplete_exit_3(db, tmp_path):
    locked = tmp_path / 'locked.db'
    locked.write_bytes((tmp_path / db).read_bytes())
    locked.chmod(0)
    try:
        for argv in (['sqlite://locked.db', '--check'], ['sqlite', 'locked.db', '--view', 'health']):
            run = _run_reveal_direct(*argv)
            assert run.returncode == 3, (argv, run.returncode, run.stderr)  # B10: --check exited 1
        assert _run_reveal_direct('sqlite://locked.db').returncode == 3  # control: the plain read already exits 3
    finally:
        locked.chmod(0o600)
