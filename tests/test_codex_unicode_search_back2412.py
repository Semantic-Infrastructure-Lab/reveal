"""JSON serialization cannot erase a decoded Codex content match."""
import json
import sqlite3
from unittest.mock import patch

import pytest

from reveal import api
from reveal.adapters.codex.adapter import CodexAdapter


@pytest.mark.parametrize('text,term,expected', [
    ('CAFÉ', 'café', 2), ('a"b', 'a"b', 2), ('C:\\work', 'C:\\work', 2),
    ('line\nbreak', 'line\nbreak', 2),
    ('🔧', '🔧', 2), ('Straße', 'STRASSE', 0), ('cafe\u0301', 'café', 0),
])
def test_serialization_equivalence_and_caps(tmp_path, text, term, expected):
    db = tmp_path / 'state.sqlite'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE threads(id TEXT,rollout_path TEXT,title TEXT,first_user_message TEXT,model TEXT,updated_at INTEGER,thread_source TEXT,archived INTEGER)')
        for escaped in (False, True):
            name = str(escaped)
            path = tmp_path / (name + '.jsonl')
            record = {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': text}}
            malformed = [[], {'type': 'event_msg', 'payload': 42},
                         {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': {'wrong': 'shape'}}}]
            prefix = ''.join(json.dumps(item) + '\n' for item in malformed)
            path.write_text(prefix + (json.dumps(record, ensure_ascii=escaped) + '\n') * 3, encoding='utf-8')
            conn.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)',
                         (name, str(path), name, '', 'synthetic', 1, 'user', 0))
    with patch.object(CodexAdapter, 'CODEX_DB', db):
        result = api.query('codex://sessions/?search=' + term + '&matches=1')
        full = api.query('codex://sessions/?search=' + term + '&matches=0')
    assert result['total'] == full['total'] == expected
    if expected:
        assert all(s['match_count'] == 1 for s in result['sessions'])
        assert all(s['match_count'] == 3 for s in full['sessions'])
        assert any(w['type'] == 'truncated' for w in result['meta']['warnings'])
