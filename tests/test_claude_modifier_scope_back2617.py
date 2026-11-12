"""Declared noun modifiers must reach their documented population, or reject."""
import json

import pytest

from conftest import _run_reveal_in
from reveal import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript


@pytest.mark.parametrize('resource,control,value', [
    ('session/my-session', 'key', 'model'),
    ('settings', 'project', 'proj'),
    ('session/my-session/messages', 'patches', True),
    ('sessions', 'word', True),
    ('session/my-session', 'snippet', 80),
    ('session/my-session/messages', 'since', '2026-01-01'),
    ('history', 'until', '2026-01-01'),
    ('sessions?match=token', 'filter', 'my-session'),
])
def test_misplaced_modifier_rejects_in_api_and_both_cli_forms(transcript, resource, control, value):
    uri = 'claude://' + resource
    with pytest.raises(RequestValidationError, match=control):
        query(uri, **{control: value})
    separator = '&' if '?' in resource else '?'
    encoded = str(value).lower() if isinstance(value, bool) else str(value)
    result = _run_reveal_in(transcript.parent, uri + separator + control + '=' + encoded, '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['meta']['errors'][0]['code'] == 'invalid_request'
    base, _, match = resource.partition('?match=')
    flags = ['--' + control] + ([] if control == 'word' else [encoded])
    if match:
        flags += ['--match', match]
    # filter is deliberately URI/API-only during vocabulary migration.
    if control != 'filter':
        command = _run_reveal_in(transcript.parent, 'claude', base, *flags, '--format', 'json')
        assert command.returncode == 2
        assert json.loads(command.stdout)['meta']['errors'][0]['code'] == 'invalid_request'


def test_original_modifier_scope_validates_before_api_overlays(transcript):
    with pytest.raises(RequestValidationError, match='key'):
        query('claude://session/my-session?key=model', key=None)


def test_none_omits_a_misplaced_api_modifier(transcript):
    assert query('claude://session/my-session', key=None)['type'] == 'claude_session_overview'


def test_invalid_scope_precedes_transcript_lookup(monkeypatch):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    def unexpected_lookup(self):
        pytest.fail('invalid request reached transcript lookup')
    monkeypatch.setattr(ClaudeAdapter, '_refresh_conversation', unexpected_lookup)
    with pytest.raises(RequestValidationError, match='key'):
        query('claude://session/my-session', key='model')


@pytest.mark.parametrize('resource,params,kind', [
    ('sessions', {'filter': 'my', 'since': 'today', 'until': 'today'}, 'claude_session_list'),
    ('sessions', {'match': 'token', 'word': True, 'snippet': 80}, 'claude_cross_session_search'),
    ('session/my-session', {'view': 'files', 'patches': True}, 'claude_files'),
])
def test_supported_modifiers_still_reach_existing_readers(transcript, resource, params, kind):
    assert query('claude://' + resource, **params)['type'] == kind


def test_schema_publishes_the_enforced_modifier_scopes():
    from reveal.adapters.claude.adapter import ClaudeAdapter
    scopes = ClaudeAdapter.get_schema()['modifier_scopes']
    assert scopes['key'] == ['claude_settings', 'claude_config']
    assert scopes['until'] == ['claude_session_list', 'claude_cross_session_search']
    assert scopes['patches'] == ['claude_files']
