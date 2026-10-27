"""sqlite:// views and the foreign-key setting (BACK-2213 lane A, F58/F59).

F58: the overview's "Foreign Keys: Disabled" (``foreign_keys_enabled``) read
``PRAGMA foreign_keys`` on reveal's own read-only connection. It is a per-connection
setting, never stored in the file, so it was Disabled for every database and said nothing
about the application's enforcement. It is gone; the FK count under Statistics stays.
F59: a view the overview listed (and whose Next Steps offered ``.../<table>``) could not be
opened: "Table not found".
"""

import contextlib
import io
import sqlite3

from reveal.adapters.sqlite.adapter import SQLiteAdapter
from reveal.adapters.sqlite.renderer import SqliteRenderer


def _db(tmp_path):
    path = tmp_path / 'app.db'
    con = sqlite3.connect(path)
    con.executescript(
        'CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);'
        'CREATE TABLE posts (id INTEGER PRIMARY KEY, author_id INTEGER REFERENCES users(id));'
        "INSERT INTO users (name) VALUES ('a'), ('b');"
        'CREATE VIEW v_users AS SELECT id, name FROM users;'
    )
    con.commit()
    con.close()
    return path


def _render(result):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        SqliteRenderer.render_structure(result, 'text')
    return out.getvalue()


def test_overview_has_no_connection_foreign_key_setting(tmp_path):
    with SQLiteAdapter(f'sqlite://{_db(tmp_path)}') as adapter:
        result = adapter.get_structure()
    assert 'foreign_keys_enabled' not in result['configuration']
    assert result['statistics']['foreign_keys'] == 1
    text = _render(result)
    assert 'Foreign Keys: Disabled' not in text and 'Foreign Keys: Enabled' not in text
    assert '  Foreign Keys: 1' in text


def test_listed_view_can_be_opened(tmp_path):
    with SQLiteAdapter(f'sqlite://{_db(tmp_path)}/v_users') as adapter:
        result = adapter.get_structure()
    assert result['table'] == 'v_users'
    assert result['kind'] == 'view'
    assert [c['name'] for c in result['columns']] == ['id', 'name']
    assert result['row_count'] == 2
    assert result['create_statement'].startswith('CREATE VIEW')
    assert _render(result).startswith('View: v_users\n')


def test_table_is_still_a_table(tmp_path):
    with SQLiteAdapter(f'sqlite://{_db(tmp_path)}/users') as adapter:
        result = adapter.get_structure()
    assert result['kind'] == 'table'
    assert _render(result).startswith('Table: users\n')
