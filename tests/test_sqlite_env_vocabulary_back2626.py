"""sqlite and env under the declared command model (BACK-2626 batch 1, BACK-2598's sqlite/env part).

Preservation pins first: what the two resource nouns answer today on the URI, the typed API and MCP, so the
declarations that follow cannot change an answer by accident. The fixtures are a throwaway database and variables the
test sets itself (never HOME, USER or another variable the host owns, V042).
"""
import json
import sqlite3

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
