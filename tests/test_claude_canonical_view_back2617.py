"""Canonical view selects existing session readers without changing populations."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.api import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript
from test_claude_workspace_lists_back2617 import workspace_home


@pytest.mark.parametrize('view', ['overview', 'messages', 'prompts', 'thinking', 'tools', 'files',
                                 'workflow', 'agents', 'context', 'timeline', 'errors', 'tokens',
                                 'digest', 'exchanges', 'message', 'chain'])
def test_view_matches_existing_resource_reader(transcript, workspace_home, view):
    suffix = '' if view == 'overview' else '/' + view
    canonical = query('claude://session/my-session', view=view)
    original = query('claude://session/my-session' + suffix)
    assert canonical == original
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session?view=' + view,
                            '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['type'] == canonical['type']


def test_search_view_uses_existing_content_search_and_match(transcript):
    answer = query('claude://session/my-session', view='search', match='auth')
    assert answer == query('claude://session/my-session', search='auth')
    assert query('claude://session/my-session', view='search')['type'] == 'claude_search_results'


@pytest.mark.parametrize('resource,kwargs', [
    ('info', {'view': 'messages'}),
    ('session/my-session', {'view': 'invented'}),
    ('session/my-session/messages', {'view': 'tools'}),
    ('session/my-session/unknown', {'view': 'messages'}),
    ('session/my-session?tokens', {'view': 'messages'}),
])
def test_view_rejects_conflicting_or_unsupported_scope(transcript, resource, kwargs):
    with pytest.raises(RequestValidationError):
        query('claude://' + resource, **kwargs)


def test_view_presence_overrides_and_original_validation(transcript):
    assert query('claude://session/my-session?view=messages', view=None)['type'] == 'claude_session_overview'
    assert query('claude://session/my-session/messages', view='messages')['type'] == 'claude_messages'
    with pytest.raises(RequestValidationError):
        query('claude://session/my-session?view=invented', view='messages')


@pytest.mark.parametrize('view,term', [('messages', 'Fixed'), ('errors', 'failed')])
def test_view_and_match_compose_at_existing_population(transcript, view, term):
    canonical = query('claude://session/my-session', view=view, match=term)
    original = query('claude://session/my-session/' + view, match=term)
    assert canonical == original


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_view_preserves_partial_failed_and_fresh_sources(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    original = transcript.read_bytes()
    transcript.write_bytes(original + b'{"broken\n')
    async def scenario(session):
        request = {'uri': 'claude://session/my-session?view=messages', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['type'] == 'claude_messages' and answer['messages']
        assert answer['meta']['transcript_analysis']['failed_records'] == 1
        transcript.write_bytes(b'{"broken\n')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        transcript.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['transcript_analysis']['failed_records'] == 0
    _run(transcript.parent, scenario)
