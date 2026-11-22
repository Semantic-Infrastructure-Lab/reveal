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
    assert run.returncode == 1  # a foreign-key violation: a finding under the health view's default gate
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
    """api.query('env://NAME') answered the whole listing (type environment), not the variable the URI names. Both now
    carry the (here empty) meta: the CLI's element envelope omitted it until env was declared."""
    assert api.query(f'env://{name}') == _json(f'env://{name}')[1]


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
    assert (view_run.returncode, check_run.returncode, uri_run.returncode) == (1, 1, 1)  # findings, default gate
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


def _corrupt(path):
    """A database whose index no longer matches its table: PRAGMA integrity_check reports each row, no read raises."""
    connection = sqlite3.connect(path)
    connection.executescript("CREATE TABLE t(a INTEGER, b INTEGER); CREATE INDEX i ON t(a);"
                             "INSERT INTO t VALUES (1, 10), (2, 20);")
    connection.commit()
    connection.executescript("PRAGMA writable_schema=ON; UPDATE sqlite_master SET sql='CREATE INDEX i ON t(b)' "
                             "WHERE name='i'; PRAGMA writable_schema=OFF;")
    connection.commit()
    connection.close()


def test_sqlite_health_gates_on_findings(db, tmp_path):
    """D6 (ruling on BACK-2626 step 3, settling BACK-2753): a failed integrity check is a finding like a foreign-key
    violation, so --view health exits 1 under its default findings gate (--check exited 2 and the declared path called
    the answer an invalid request: the API raised, MCP said error); --fail-on none reports either with 0."""
    from reveal.mcp_server import reveal_run
    _corrupt(tmp_path / 'bad.db')
    for argv in (['sqlite', 'bad.db', '--view', 'health'], ['sqlite://bad.db', '--view', 'health'],
                 ['sqlite://bad.db', '--check']):
        run, doc = _json(*argv)
        assert run.returncode == 1, (argv, run.stderr)
        assert (doc['type'], doc['integrity'], doc['status'], doc['exit_code']) == ('sqlite_health', False, 'failure', 1)
        assert len(doc['detections']) == 2
    assert _json('sqlite', 'bad.db', '--view', 'health', '--fail-on', 'none')[0].returncode == 0
    assert api.query('sqlite', 'bad.db', view='health')['integrity'] is False  # an answer, not an invalid request
    assert json.loads(reveal_run(['sqlite://bad.db', '--view', 'health', '--format', 'json']))['status'] == 'failure'
    run, doc = _json('sqlite', 'app.db', '--view', 'health', '--fail-on', 'none')
    assert run.returncode == 0 and doc['foreign_key_violations'] == 1
    text = _run_reveal_direct('sqlite', 'app.db', '--view', 'health')  # the text answer, not the JSON document
    assert text.returncode == 1 and text.stdout.startswith('app.db: integrity ok') and 'foreign_key_check' in text.stdout
    assert _run_reveal_direct('sqlite://app.db').returncode == 0  # control: the overview has no findings to gate


def test_check_of_a_sqlite_uri_names_its_health_view(db):
    """reveal check is for paths; on a sqlite:// URI it recommended the deprecated --check, now the declared view. A
    noun with no such control keeps the old hint (negative control)."""
    run = _run_reveal_direct('check', 'sqlite://app.db')
    assert run.returncode == 2 and 'Did you mean: reveal sqlite://app.db --view health' in run.stderr
    run = _run_reveal_direct('check', 'json://data.json')
    assert run.returncode == 2 and 'Did you mean: reveal json://data.json --check' in run.stderr


def test_an_empty_sqlite_uri_names_the_missing_database(db):
    """B12: it named the Python class (SQLiteAdapter('sqlite:///path/to/db.db')); now the request's missing part."""
    run = _run_reveal_direct('sqlite://')
    assert run.returncode == 2 and 'SQLiteAdapter' not in run.stderr and 'resource is required' in run.stderr


# --- env under its declarations (BACK-2626; Scott's BACK-2752 ruling: show_secrets is removed) ----------------------
# Red until the declarations land: reveal env is generated from them, env takes no control, so an undeclared keyword or
# key is an invalid request, and show_secrets is refused naming the redaction rule on every API form.

REMOVED = ('show_secrets', 'redacted on every output', 'removed')


@pytest.mark.parametrize('sub, uri', [([], 'env://'), ([PLAIN], f'env://{PLAIN}'), ([TOKEN], f'env://{TOKEN}')])
def test_env_subcommand_answers_as_the_resource_uri(variables, sub, uri):
    """reveal env [NAME] is env://[NAME]: the same JSON, text and exit (D20); env was a URI-only noun."""
    sub_run, sub_doc = _json('env', *sub)
    uri_run, uri_doc = _json(uri)
    assert (sub_run.returncode, uri_run.returncode) == (0, 0), sub_run.stderr
    assert _answer(sub_doc) == _answer(uri_doc)
    sub_text, uri_text = _run_reveal_direct('env', *sub), _run_reveal_direct(uri)
    assert (sub_text.returncode, sub_text.stdout) == (uri_text.returncode, uri_text.stdout)
    assert 'fixture-secret-value' not in sub_run.stdout + sub_text.stdout


@pytest.mark.parametrize('argv', [['env', MISSING], [f'env://{MISSING}']])
def test_env_variable_not_set_exits_2_naming_it(variables, argv):
    """Rule 9 on both transports: a variable that is not set is an invalid request naming it, with a JSON document."""
    run, doc = _json(*argv)
    assert run.returncode == 2, run.stderr
    assert MISSING in run.stderr
    assert [e['message'] for e in doc['meta']['errors'] if MISSING in e['message']], doc


def test_env_typed_api_refuses_show_secrets_naming_the_redaction_rule(variables):
    """Scott 2026-11-22 (BACK-2752): show_secrets returned sensitive values unredacted through api.query; it is removed,
    so every API form refuses it as an undeclared keyword whose message says secrets are redacted on every output and
    the control was removed (the generic list of supported controls would hide that)."""
    from reveal.errors import UnsupportedOverrideError
    for args, keywords in (
            (('env://',), {}), (('env://',), {'element_name': TOKEN}), ((f'env://{TOKEN}',), {}),
            (('env', TOKEN), {})):
        with pytest.raises(UnsupportedOverrideError) as raised:
            api.query(*args, show_secrets=True, **keywords)
        message = str(raised.value)
        assert all(word in message for word in REMOVED), (args, message)
        assert 'fixture-secret-value' not in message


def test_env_show_secrets_uri_key_is_refused_naming_the_redaction_rule(variables):
    """The URI key never disclosed anything (it was read as a variable name, B3), but it names the removed control on
    the CLI, MCP and the API alike."""
    from reveal.mcp_server import reveal_run
    run = _run_reveal_direct('env://?show_secrets=1', '--format', 'json')
    assert run.returncode == 2 and all(word in run.stderr for word in REMOVED), run.stderr
    assert all(word in reveal_run(['env://?show_secrets=1']) for word in REMOVED)
    with pytest.raises(RequestValidationError, match='redacted on every output'):
        api.query('env://?show_secrets=1')


def test_env_listing_redacts_without_the_removed_control(variables):
    """Negative control: the listing and the variable redact the secret on the API, with no keyword."""
    listed = {v['name']: v for rows in api.query('env://')['categories'].values() for v in rows}
    assert (listed[TOKEN]['value'], listed[PLAIN]['value']) == ('***', 'fixture-plain-value')
    variable = api.query(f'env://{TOKEN}')
    assert (variable['value'], variable['raw_value']) == ('***', None)


def test_env_typed_api_binds_no_control(variables):
    """env declares no control: an undeclared keyword raises, with the shared message (BACK-2214 class: it was dropped
    silently); the noun form answers as the URI form."""
    from reveal.errors import UnsupportedOverrideError
    with pytest.raises(UnsupportedOverrideError, match="unsupported control 'bogus_kw'; supported controls"):
        api.query('env://', bogus_kw=1)
    assert _answer(api.query('env', PLAIN)) == _answer(api.query(f'env://{PLAIN}'))


@pytest.mark.parametrize('argv, word', [
    (['env://?bogus=1'], 'bogus'), (['env://?limit=1'], 'limit'), (['env://', '--limit', '1'], '--limit'),
    (['env://', '--head', '1'], '--head'), (['env', '--sort', 'name'], '--sort')])
def test_env_controls_it_never_read_exit_2(variables, argv, word):
    """Unsupported controls (rule 3) and flags after the URI (rule 23): env reads none, so each exits 2 naming the
    word; they printed a no-effect note with exit 0 (?bogus=1 was read as a variable named '?bogus=1', B3)."""
    run = _run_reveal_direct(*argv)
    assert run.returncode == 2, run.stderr
    assert f"unsupported control '{word}'" in run.stderr


def test_env_check_is_an_inert_legacy_flag(variables):
    """--check/--lint never changed an env answer: they answer as without them, with the replaced-by note (BACK-2708)."""
    run, doc = _json(f'env://{PLAIN}', '--check')
    assert run.returncode == 0 and doc['value'] == 'fixture-plain-value'
    notes = [w['message'] for w in doc['meta']['warnings'] if w.get('field') == 'flag:env.--check']
    assert notes and 'reveal check' in notes[0]


def test_env_positional_element_beside_the_uri_is_refused(variables):
    """Q5: the guide teaches only env://NAME, so env:// NAME is refused naming the resource forms (BACK-2526 seam)."""
    run, doc = _json('env://', PLAIN)
    assert run.returncode == 2
    assert f"takes no positional element ('{PLAIN}')" in run.stderr
    assert 'env://' in run.stderr and 'reveal env' in run.stderr
    assert _json(f'env://{PLAIN}')[0].returncode == 0  # control: the resource form answers
