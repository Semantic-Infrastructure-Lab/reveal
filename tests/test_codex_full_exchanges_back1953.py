"""Codex paired exchanges expose an explicit full-text display control."""
import json

import pytest

from codex_session_fixture import SESSION_UUID, make_sqlite_db
from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.codex.adapter import CodexAdapter
from reveal.utils.results import truncations_of

PROMPT = 'question ' + 'q' * 320 + ' PROMPT_END'
ANSWER = 'answer ' + 'a' * 640 + ' ANSWER_END'


@pytest.fixture
def session(tmp_path, monkeypatch):
    records = [
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': PROMPT}},
        {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': 'Working...'}},
        {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': ANSWER, 'phase': 'final'}},
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'second question'}},
        {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': 'second answer'}},
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'unanswered'}},
    ]
    rollout = tmp_path / 'rollout.jsonl'
    rollout.write_text(''.join(json.dumps(record) + '\n' for record in records), encoding='utf-8')
    database = make_sqlite_db(tmp_path, rollout)
    monkeypatch.setattr(CodexAdapter, 'CODEX_HOME', tmp_path)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', database)
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(tmp_path))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(database))
    return f'codex://{SESSION_UUID}/exchanges'


@pytest.mark.parametrize('query', ['full', 'full=1', 'full=true'])
def test_full_text_cli_displays_complete_paired_prompt_and_answer(session, query):
    result = run(f'{session}?{query}')
    assert result.returncode == 0, result.stderr
    assert PROMPT in result.stdout
    assert ANSWER in result.stdout
    assert 'more chars' not in result.stdout
    assert 'Unknown query param' not in result.stderr
    assert 'has no effect' not in result.stderr


@pytest.mark.parametrize('query', ['', 'full=false', 'full=0'])
def test_default_and_explicit_false_keep_bounded_actionable_previews(session, query):
    result = run(session + ('?' + query if query else ''))
    assert result.returncode == 0, result.stderr
    assert 'PROMPT_END' not in result.stdout and 'ANSWER_END' not in result.stdout
    assert 'more chars' in result.stdout and '?full' in result.stdout
    assert 'second question' in result.stdout and 'second answer' in result.stdout
    assert '[no agent reply found before the next prompt]' in result.stdout


@pytest.mark.parametrize('query, expected', [('full', True), ('full=1', True),
                                             ('full=true', True), ('full=false', False), ('full=0', False)])
def test_api_control_preserves_complete_json_pairing(session, query, expected):
    answer = api.query(f'{session}?{query}')
    assert answer['full'] is expected
    assert answer['exchange_count'] == 3
    assert [(row['prompt'], row['answer']) for row in answer['exchanges']] == [
        (PROMPT, ANSWER), ('second question', 'second answer'), ('unanswered', None)]


def test_default_json_already_contains_full_strings_and_messages_are_unchanged(session):
    result = run(session, '--format', 'json')
    answer = json.loads(result.stdout)
    assert answer['exchanges'][0]['prompt'] == PROMPT
    assert answer['exchanges'][0]['answer'] == ANSWER
    baseline = api.query(session.replace('/exchanges', '/messages'))
    api.query(session + '?full')
    assert api.query(session.replace('/exchanges', '/messages')) == baseline


def test_repeated_full_and_false_requests_do_not_leak_display_state(session):
    full = run(session + '?full')
    brief = run(session + '?full=false')
    clean = run(session)
    assert ANSWER in full.stdout
    assert 'ANSWER_END' not in brief.stdout and 'ANSWER_END' not in clean.stdout
    assert brief.stdout == clean.stdout


@pytest.mark.parametrize('query', ['full=invalid', 'full=2'])
def test_invalid_full_boolean_is_rejected(session, query):
    with pytest.raises(ValueError, match='full'):
        api.query(session + '?' + query)


def test_limit_zero_remains_a_warned_unsupported_count_control(session):
    result = run(session + '?limit=0')
    assert result.returncode == 0, result.stderr
    assert 'limit' in result.stderr and 'ignored' in result.stderr
    assert 'ANSWER_END' not in result.stdout


def test_full_preserves_existing_count_budget(session):
    result = run(session + '?full', '--head', '1', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert len(answer['exchanges']) == 1
    assert answer['exchanges'][0]['answer'] == ANSWER
    cut = truncations_of(answer)
    assert [(row['field'], row['shown'], row['total']) for row in cut] == [('exchanges', 1, 3)]


def test_normalized_item_records_keep_the_same_pairs(session, tmp_path):
    items = [('UserMessage', PROMPT), ('AgentMessage', 'Working...'), ('AgentMessage', ANSWER)]
    records = [{'type': 'event_msg', 'payload': {'type': 'item_completed', 'item': {
        'type': kind, 'content': [{'type': 'Text', 'text': text}]}}} for kind, text in items]
    records.insert(2, {'type': 'response_item', 'payload': {
        'type': 'function_call', 'name': 'read_file', 'arguments': '{}', 'call_id': 'tool1'}})
    (tmp_path / 'rollout.jsonl').write_text(
        ''.join(json.dumps(record) + '\n' for record in records), encoding='utf-8')
    full = api.query(session + '?full')
    brief = api.query(session + '?full=false')
    assert full['exchanges'] == brief['exchanges']
    assert [(row['prompt'], row['answer']) for row in full['exchanges']] == [(PROMPT, ANSWER)]


@pytest.mark.mcp
def test_registered_sdk_preserves_full_text_and_json_pairing(session, tmp_path):
    from test_mcp_expected_errors_back1992 import _run, _text

    async def scenario(client):
        result = await client.call_tool('reveal_query', {'uri': session + '?full'})
        assert not result.is_error, _text(result)
        assert PROMPT in _text(result) and ANSWER in _text(result)
        result = await client.call_tool('reveal_query', {'uri': session + '?full=false'})
        assert not result.is_error, _text(result)
        assert 'ANSWER_END' not in _text(result) and '?full' in _text(result)
        result = await client.call_tool('reveal_query', {
            'uri': session + '?full=false', 'provenance': True})
        assert not result.is_error, _text(result)
        answer = json.loads(_text(result))
        assert answer['exchanges'][0]['answer'] == ANSWER
        assert answer['full'] is False

    _run(tmp_path, scenario)
