"""The registered tools must return decoded Unicode matches across all owners."""
import json
import sqlite3

import pytest

from test_mcp_expected_errors_back1992 import _run, _text


@pytest.mark.mcp
@pytest.mark.parametrize('provenance', [False, True])
def test_registered_searches_and_source_edits(tmp_path, provenance):
    docs = tmp_path / 'docs'
    docs.mkdir()
    document = docs / 'one.md'
    document.write_text('CAFÉ\n', encoding='utf-8')
    projects = tmp_path / 'projects'
    project = projects / 'synthetic-project'
    project.mkdir(parents=True)
    transcript = project / 'sample.jsonl'
    record = {'type': 'user', 'message': {'role': 'user', 'content': 'CAFÉ Istanbul'}}
    transcript.write_text(json.dumps(record) + '\n', encoding='utf-8')
    rollout = tmp_path / 'rollout.jsonl'
    rollout.write_text(json.dumps({'type': 'event_msg', 'payload': {
        'type': 'user_message', 'message': 'CAFÉ'}}) + '\n', encoding='utf-8')
    database = tmp_path / 'state.sqlite'
    with sqlite3.connect(database) as conn:
        conn.execute('CREATE TABLE threads(id TEXT,rollout_path TEXT,title TEXT,first_user_message TEXT,model TEXT,updated_at INTEGER,thread_source TEXT,archived INTEGER)')
        conn.execute('INSERT INTO threads VALUES(?,?,?,?,?,?,?,?)',
                     ('synthetic', str(rollout), 'synthetic', '', 'synthetic', 1, 'user', 0))
    code = f'''
import os
os.environ['REVEAL_CLAUDE_DIR'] = {str(projects)!r}
os.environ['REVEAL_CODEX_DB'] = {str(database)!r}
from reveal import mcp_server
mcp_server.main()
'''

    async def scenario(client):
        requests = [
            (f'markdown://{docs.as_posix()}?body-contains=café', 'matched_files', 'CAFÉ'),
            ('claude://?search=café', 'match_count', 'CAFÉ'),
            ('claude://?search=ıstanbul&word', 'match_count', 'Istanbul'),
            ('codex://sessions/?search=café', 'total', 'CAFÉ'),
        ]
        for uri, count_key, expected_text in requests:
            reply = await client.call_tool('reveal_query', {'uri': uri, 'provenance': provenance})
            assert not reply.is_error, _text(reply)
            if provenance:
                answer, _ = json.JSONDecoder().raw_decode(_text(reply))
                assert answer[count_key] == 1
            elif not uri.startswith('markdown:'):
                assert expected_text in _text(reply)
            else:
                assert 'one.md' in _text(reply)
        if provenance:
            document.write_text('unrelated\n', encoding='utf-8')
            reply = await client.call_tool('reveal_query', {
                'uri': requests[0][0], 'provenance': True})
            answer, _ = json.JSONDecoder().raw_decode(_text(reply))
            assert answer['matched_files'] == 0
            record['message']['content'] = 'unrelated'
            transcript.write_text(json.dumps(record) + '\n', encoding='utf-8')
            reply = await client.call_tool('reveal_query', {
                'uri': 'claude://?search=café', 'provenance': True})
            answer, _ = json.JSONDecoder().raw_decode(_text(reply))
            assert answer['match_count'] == 0

    _run(tmp_path, scenario, code)
