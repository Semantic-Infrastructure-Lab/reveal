"""Constructor-bound Claude controls must reach existing session readers literally."""
import json

import pytest

from claude_session_fixture import build_claude_home
from reveal.api import query
from reveal.adapters.claude.adapter import ClaudeAdapter


@pytest.fixture
def claude(tmp_path, monkeypatch):
    home = build_claude_home(tmp_path)
    monkeypatch.setattr(ClaudeAdapter, 'CONVERSATION_BASE', home / 'projects')
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_HOME', home)
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_JSON', tmp_path / '.claude.json')
    return home


def test_typed_tool_override_reaches_existing_tool_reader(claude):
    result = query('claude://session/my-session?tools=Read', tools='Bash')
    assert result['type'] == 'claude_tool_calls'
    assert result['tool_name'] == 'Bash' and result['call_count'] == 1


def test_search_override_is_literal_and_does_not_become_a_control(claude):
    path = next((claude / 'projects').rglob('my-session.jsonl'))
    needle = 'a&errors=%26+雪'
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': needle}}) + '\n')
    result = query('claude://session/my-session?search=absent', search=needle)
    assert result['type'] == 'claude_search_results'
    assert result['match_count'] == 1


def test_false_summary_override_restores_overview(claude):
    result = query('claude://session/my-session?summary', summary=False)
    assert result['type'] == 'claude_session_overview'
    assert 'tool_success_rates' not in result


def test_none_tool_override_restores_omitted_default(claude):
    result = query('claude://session/my-session?tools=Read', tools=None)
    assert result['type'] == 'claude_session_overview'


def test_tail_zero_is_not_an_omitted_override(claude):
    result = query('claude://session/my-session?tail=2', tail=0)
    assert result['type'] == 'claude_messages' and result['messages'] == []
    assert result['total_turns'] > 0


def test_unknown_typed_override_rejects(claude):
    with pytest.raises(TypeError, match='Unsupported declared'):
        query('claude://session/my-session', invented_control=True)


def test_false_raw_override_restores_narrative_messages(claude):
    result = query('claude://session/my-session/messages?raw', raw=False)
    assert result['type'] == 'claude_messages'
    assert result['messages'] and all('text' in row for row in result['messages'])


def test_legacy_presence_and_snippet_fallback_are_preserved(claude):
    assert query('claude://session/my-session?summary=false')['type'] == 'claude_analytics'
    result = query('claude://sessions?search=auth&snippet=not-a-number')
    assert result['type'] == 'claude_cross_session_search' and result['match_count'] > 0


def test_original_invalid_tail_is_not_hidden_by_override(claude):
    with pytest.raises(ValueError):
        query('claude://session/my-session?tail=invalid', tail=1)


@pytest.mark.parametrize('name,kind', [('tools', 'claude_tool_calls'), ('search', 'claude_search_results')])
def test_empty_string_keeps_the_selected_legacy_reader(claude, name, kind):
    original = query(f'claude://session/my-session?{name}=')
    overridden = query(f'claude://session/my-session?{name}=absent', **{name: ''})
    assert original['type'] == overridden['type'] == kind
    if name == 'tools':
        assert original['call_count'] == overridden['call_count'] == 0
    else:
        assert original['match_count'] == overridden['match_count'] > 0


def test_patches_retains_legacy_string_rule_and_typed_false(claude):
    resource = 'claude://session/my-session/files'
    legacy = query(resource + '?patches=1')
    assert legacy['operations'] and all('patch' not in row for row in legacy['operations'])
    enabled = query(resource, patches=True)
    assert all('patch' in row for row in enabled['operations'])
    disabled = query(resource + '?patches=true', patches=False)
    assert disabled['operations'] and all('patch' not in row for row in disabled['operations'])
