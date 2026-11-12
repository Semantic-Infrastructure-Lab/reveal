"""Competing session selectors cannot silently win by branch order."""
import json

import pytest

from conftest import _run_reveal_in
from reveal import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript


@pytest.mark.parametrize('resource,params', [
    ('session/my-session', {'tokens': True, 'digest': True}),
    ('session/my-session', {'tools': 'Bash', 'search': 'token'}),
    ('session/my-session', {'errors': True, 'timeline': True}),
    ('session/my-session', {'tail': 2, 'last': 1}),
    ('sessions', {'errors': True}),
    ('plans', {'tools': 'Bash'}),
    ('history', {'tokens': True}),
    ('info', {'digest': True}),
    ('settings', {'search': 'token'}),
    ('plans/my-plan', {'search': 'token'}),
])
def test_invalid_selector_combination_rejects_in_api_and_uri(transcript, resource, params):
    with pytest.raises(RequestValidationError, match='selector'):
        query('claude://' + resource, **params)
    query_string = '&'.join(name + '=' + str(value).lower() for name, value in params.items())
    result = _run_reveal_in(transcript.parent, 'claude://' + resource + '?' + query_string, '--format', 'json')
    assert result.returncode == 2
    assert any(e['code'] == 'invalid_request' for e in json.loads(result.stdout)['meta']['errors'])


def test_equivalent_tail_aliases_keep_chronological_slice(transcript):
    expected = query('claude://session/my-session', tail=2)
    assert query('claude://session/my-session', tail=2, last=2) == expected


@pytest.mark.parametrize('params', [{'tools': 'Bash', 'errors': True},
                                  {'tools': 'Bash', 'errors': True, 'contains': 'failed'}])
def test_supported_tool_result_composites_remain_valid(transcript, params):
    answer = query('claude://session/my-session', **params)
    assert answer['type'] == 'claude_filtered_results'
    assert answer['filters_applied'] == list(params)


def test_named_command_rejects_competing_selectors(transcript):
    result = _run_reveal_in(transcript.parent, 'claude', 'session/my-session',
                            '--tokens', '--digest', '--format', 'json')
    assert result.returncode == 2
    assert any(e['code'] == 'invalid_request' for e in json.loads(result.stdout)['meta']['errors'])


def test_invalid_original_selectors_cannot_be_hidden_by_an_override(transcript):
    with pytest.raises(RequestValidationError, match='selectors'):
        query('claude://session/my-session?tokens&digest', digest=False)


def test_false_selector_restores_omission(transcript):
    assert query('claude://session/my-session', tokens=True, digest=False)['type'] == 'claude_token_breakdown'


def test_schema_publishes_selector_composition_rules():
    from reveal.adapters.claude.adapter import ClaudeAdapter
    rules = ClaudeAdapter.get_schema()['selector_rules']
    assert rules['combined_selectors'] == [['tools', 'errors']]
    assert 'tokens' in rules['session_only']
    assert 'claude_history' in rules['search_populations']
    assert 'claude_settings' not in rules['search_populations']


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_rejects_conflict_then_accepts_a_valid_composite(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    async def scenario(session):
        failed = await session.call_tool('reveal_query', {'uri': 'claude://session/my-session?tokens&digest'})
        assert failed.is_error
        assert 'selectors' in _text(failed)
        healthy = await session.call_tool('reveal_query', {
            'uri': 'claude://session/my-session?tools=Bash&errors', 'provenance': True})
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['type'] == 'claude_filtered_results'
    _run(transcript.parent, scenario)
