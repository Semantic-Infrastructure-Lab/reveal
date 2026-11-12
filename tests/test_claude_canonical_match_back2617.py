"""Canonical text matching keeps each resource's existing text population."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.api import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript
from test_claude_workspace_lists_back2617 import workspace_home


@pytest.mark.parametrize('resource,term,legacy,kind', [
    ('session/my-session', 'path traversal', 'search', 'claude_search_results'),
    ('session/my-session/messages', 'Fixed', 'contains', 'claude_messages'),
    ('session/my-session?tools=Bash', 'Error', 'contains', 'claude_filtered_results'),
    ('sessions', 'validate_token', 'search', 'claude_cross_session_search'),
    ('plans', 'signed token', 'search', 'claude_plans'),
    ('agents', 'Review', 'search', 'claude_agents'),
    ('memory', 'feedback tests', 'search', 'claude_memory'),
    ('history', 'auth', 'search', 'claude_history'),
])
def test_match_reaches_existing_population(transcript, workspace_home, monkeypatch, resource, term, legacy, kind):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_HOME', workspace_home)
    canonical = query('claude://' + resource, match=term)
    original = query('claude://' + resource, **{legacy: term})
    assert canonical == original
    assert canonical['type'] == kind
    separator = '&' if '?' in resource else '?'
    result = _run_reveal_in(transcript.parent, 'claude://' + resource + separator + 'match=' + term,
                            '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['type'] == kind


@pytest.mark.parametrize('resource', ['settings', 'config', 'info', 'hooks', 'plans/gentle',
                                     'session/my-session/thinking', 'session/my-session/chain'])
def test_match_rejects_resources_without_existing_text_matching(transcript, workspace_home, resource):
    with pytest.raises(RequestValidationError, match='match'):
        query('claude://' + resource, match='auth')


def test_match_is_literal_and_none_clears_uri_match(transcript):
    from urllib.parse import quote
    needle = 'a&errors=%26+雪'
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': needle}]}}) + '\n')
    answer = query('claude://session/my-session', match=needle)
    assert answer['match_count'] == 1
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session?match=' + quote(needle, safe=''),
                            '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['match_count'] == 1
    assert query('claude://session/my-session?match=absent', match=None)['type'] == 'claude_session_overview'


@pytest.mark.parametrize('resource', ['session/my-session/messages?raw', 'session/my-session?summary'])
def test_match_rejects_shadowed_or_raw_population(transcript, resource):
    with pytest.raises(RequestValidationError, match='match'):
        query('claude://' + resource, match='auth')


def test_match_conflicts_validate_before_api_override(transcript):
    with pytest.raises(RequestValidationError, match='conflicts'):
        query('claude://session/my-session?match=first&search=second', match='second')
    assert query('claude://session/my-session?match=auth&search=auth')['type'] == 'claude_search_results'
    with pytest.raises(UnicodeDecodeError):
        query('claude://session/my-session?match=%FF', match='auth')


def test_match_on_errors_uses_existing_error_content_filter(transcript):
    canonical = query('claude://session/my-session/errors', match='failed')
    original = query('claude://session/my-session', errors=True, contains='failed')
    assert canonical == original


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_match_keeps_source_loss_and_fresh_followups(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    original = transcript.read_bytes()
    transcript.write_bytes(original + b'{"broken\n')
    async def scenario(session):
        request = {'uri': 'claude://session/my-session?match=auth', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['meta']['transcript_analysis']['failed_records'] == 1
        transcript.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['transcript_analysis']['failed_records'] == 0
    _run(transcript.parent, scenario)
