"""codex:// UUID prefix: an ambiguous prefix is an error naming the matches.

`SELECT ... LIKE prefix% LIMIT 1` with no ORDER BY silently opened one of
several sessions sharing a 7-hex prefix.
"""

import sqlite3

from codex_session_fixture import SESSION_UUID, make_sqlite_db, write_fixture_jsonl
from reveal.adapters.codex.adapter import CodexAdapter

TWIN = SESSION_UUID[:7] + 'f-0000-7000-8000-000000000002'


def _adapter(tmp_path, resource, twin=True):
    jsonl = write_fixture_jsonl(tmp_path)
    db = make_sqlite_db(tmp_path, jsonl)
    if twin:
        conn = sqlite3.connect(str(db))
        conn.execute("INSERT INTO threads (id, rollout_path, created_at, updated_at) VALUES (?, ?, 1, 2)",
                     (TWIN, str(jsonl)))
        conn.commit()
        conn.close()
    adapter = CodexAdapter(resource)
    adapter.CODEX_HOME = tmp_path
    adapter.CODEX_DB = db
    return adapter


def test_ambiguous_prefix_is_an_error_listing_candidates(tmp_path):
    result = _adapter(tmp_path, SESSION_UUID[:7]).get_structure()
    assert result['type'] == 'codex_error'
    assert 'mbiguous' in result['error']
    assert SESSION_UUID in result['error'] and TWIN in result['error']


def test_longer_unique_prefix_still_resolves(tmp_path):
    result = _adapter(tmp_path, SESSION_UUID[:8]).get_structure()
    assert result['type'] != 'codex_error'


def test_unique_seven_char_prefix_resolves(tmp_path):
    result = _adapter(tmp_path, SESSION_UUID[:7], twin=False).get_structure()
    assert result['type'] != 'codex_error'
