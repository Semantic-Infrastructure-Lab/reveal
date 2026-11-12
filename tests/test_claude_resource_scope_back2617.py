"""Unsupported resource suffixes must not silently execute a different request."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.api import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript
from test_claude_workspace_lists_back2617 import workspace_home


@pytest.mark.parametrize('resource', ['info/chain', 'history/chain', 'settings/theme', 'config/projects',
                                     'sessions/ignored', 'session/my-session/unknown', 'session/my-session/messages-extra',
                                     'session/my-session/chain-extra', 'session/my-session/tools/ignored'])
def test_unsupported_resource_suffix_is_request_error(transcript, workspace_home, resource):
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 2
    answer = json.loads(result.stdout)
    assert any(e['code'] == 'invalid_request' for e in answer['meta']['errors'])
    with pytest.raises(RequestValidationError):
        query('claude://' + resource)


@pytest.mark.parametrize('resource,kind', [('settings/', 'claude_settings'), ('config/', 'claude_config'),
                                         ('info/', 'claude_info'), ('history/', 'claude_history')])
def test_trailing_slash_keeps_root_namespace_owner(transcript, workspace_home, monkeypatch, resource, kind):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_HOME', workspace_home)
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_JSON', workspace_home.parent / '.claude.json')
    result = _run_reveal_in(transcript.parent, 'claude://' + resource, '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['type'] == kind


@pytest.mark.parametrize('suffix', ['user', 'assistant'])
def test_removed_role_suffix_keeps_legacy_overview_fallback(transcript, suffix):
    answer = query('claude://session/my-session/' + suffix)
    assert answer['type'] == 'claude_session_overview'


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_rejects_bad_scope_and_accepts_followup(transcript, workspace_home, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(workspace_home))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(workspace_home / 'projects'))
    async def scenario(session):
        failed = await session.call_tool('reveal_query', {'uri': 'claude://info/chain'})
        assert failed.is_error
        assert 'does not support a resource suffix' in _text(failed)
        healthy = await session.call_tool('reveal_query', {'uri': 'claude://info/', 'provenance': True})
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['type'] == 'claude_info'
    _run(transcript.parent, scenario)
