"""Transcript parsing must distinguish measured records from skipped malformed input."""
import json

import pytest

from claude_session_fixture import build_claude_home
from reveal.api import query
from reveal.adapters.claude.adapter import ClaudeAdapter


@pytest.fixture
def transcript(tmp_path, monkeypatch):
    home = build_claude_home(tmp_path)
    monkeypatch.setattr(ClaudeAdapter, 'CONVERSATION_BASE', home / 'projects')
    return next((home / 'projects').rglob('my-session.jsonl'))


@pytest.mark.parametrize('suffix', ['', '/messages', '?summary', '/workflow'])
def test_malformed_record_keeps_observations_with_source_evidence(transcript, suffix):
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('{"truncated\n')
    answer = query('claude://session/my-session' + suffix)
    proof = answer['meta']['transcript_analysis']
    assert proof['candidate_records'] == 9
    assert proof['analyzed_records'] == 8 and proof['failed_records'] == 1
    assert proof['first_failed_line'] == 9
    assert any(w['code'] == 'analysis_incomplete' for w in answer['meta']['warnings'])
    assert answer.get('message_count', len(answer.get('messages', answer.get('workflow', [])))) > 0


def test_nonmapping_record_is_disclosed_without_erasing_valid_records(transcript):
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('["not", "an", "object"]\n')
    answer = query('claude://session/my-session')
    assert answer['message_count'] == 8
    assert answer['meta']['transcript_analysis']['failed_records'] == 1


def test_failed_empty_and_genuinely_empty_sources_are_distinct(transcript):
    transcript.write_text('broken\n', encoding='utf-8')
    failed = query('claude://session/my-session')
    transcript.write_text('\n \n', encoding='utf-8')
    empty = query('claude://session/my-session')
    assert failed['message_count'] == empty['message_count'] == 0
    assert failed['meta']['transcript_analysis']['failed_records'] == 1
    assert empty['meta']['transcript_analysis']['failed_records'] == 0
    assert not empty['meta']['warnings']


def test_reconfiguring_the_store_replaces_cached_records(transcript, tmp_path):
    adapter = ClaudeAdapter('session/my-session')
    assert adapter.get_structure()['message_count'] == 8
    other = build_claude_home(tmp_path / 'other')
    path = next((other / 'projects').rglob('my-session.jsonl'))
    path.write_text(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': 'a different store'}}) + '\n', encoding='utf-8')
    adapter.reconfigure_base_path(other / 'projects')
    answer = adapter.get_structure()
    assert answer['message_count'] == 1
    assert answer['meta']['transcript_analysis']['analyzed_records'] == 1
