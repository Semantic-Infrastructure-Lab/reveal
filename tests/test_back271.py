"""Tests for BACK-271: multi-tool filter ?tools=Bash,Read."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.adapters.claude.analysis.tools import get_tool_calls


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _tool_use_msg(tool_name: str, input_: dict, tool_id: str = 'tid1') -> dict:
    return {
        'type': 'assistant',
        'timestamp': '2026-03-14T10:00:00',
        'message': {
            'role': 'assistant',
            'content': [{'type': 'tool_use', 'id': tool_id, 'name': tool_name, 'input': input_}],
        },
    }


_CONTRACT_BASE = {'contract_version': '1.0', 'type': '', 'source': '', 'source_type': 'file'}


# ─── get_tool_calls: single-tool (backward compat) ──────────────────────────

class TestGetToolCallsSingleTool:

    def test_single_tool_still_works(self):
        messages = [_tool_use_msg('Bash', {'command': 'ls'})]
        result = get_tool_calls(messages, 'Bash', 'sess', _CONTRACT_BASE.copy())
        assert result['call_count'] == 1
        assert result['tool_name'] == 'Bash'

    def test_no_tool_field_on_single_tool(self):
        """Single-tool mode does not add a 'tool' field to call entries."""
        messages = [_tool_use_msg('Bash', {'command': 'pwd'})]
        result = get_tool_calls(messages, 'Bash', 'sess', _CONTRACT_BASE.copy())
        assert 'tool' not in result['calls'][0]


# ─── get_tool_calls: multi-tool ───────────────────────────────────────────────

class TestGetToolCallsMultiTool:

    def test_comma_separated_matches_both_tools(self):
        messages = [
            _tool_use_msg('Bash', {'command': 'ls'}, 'tid1'),
            _tool_use_msg('Read', {'file_path': '/etc/hosts'}, 'tid2'),
            _tool_use_msg('Write', {'file_path': '/tmp/x'}, 'tid3'),
        ]
        result = get_tool_calls(messages, 'Bash,Read', 'sess', _CONTRACT_BASE.copy())
        assert result['call_count'] == 2
        names = {c['tool'] for c in result['calls']}
        assert names == {'Bash', 'Read'}

    def test_multi_tool_excludes_unmatched(self):
        messages = [
            _tool_use_msg('Write', {'file_path': '/tmp/x'}, 'tid1'),
            _tool_use_msg('Edit', {'file_path': '/tmp/y'}, 'tid2'),
        ]
        result = get_tool_calls(messages, 'Bash,Read', 'sess', _CONTRACT_BASE.copy())
        assert result['call_count'] == 0

    def test_multi_tool_adds_tool_field_per_call(self):
        messages = [
            _tool_use_msg('Bash', {'command': 'ls'}, 'tid1'),
            _tool_use_msg('Read', {'file_path': '/tmp/f'}, 'tid2'),
        ]
        result = get_tool_calls(messages, 'Read,Bash', 'sess', _CONTRACT_BASE.copy())
        for call in result['calls']:
            assert 'tool' in call
            assert call['tool'] in ('Bash', 'Read')

    def test_preserves_original_tool_name_string_in_result(self):
        messages = [_tool_use_msg('Bash', {'command': 'ls'})]
        result = get_tool_calls(messages, 'Bash,Read', 'sess', _CONTRACT_BASE.copy())
        assert result['tool_name'] == 'Bash,Read'

    def test_whitespace_in_comma_list_is_tolerated(self):
        messages = [
            _tool_use_msg('Bash', {'command': 'ls'}, 'tid1'),
            _tool_use_msg('Read', {'file_path': '/f'}, 'tid2'),
        ]
        result = get_tool_calls(messages, 'Bash , Read', 'sess', _CONTRACT_BASE.copy())
        assert result['call_count'] == 2


# ─── Adapter routing: ?tools=Bash,Read ────────────────────────────────────────

class TestAdapterMultiToolRouting:

    def _make_jsonl(self, tmp_path: Path, messages: list) -> Path:
        proj = tmp_path / 'projects' / '-home-user-tia-sessions-my-sess'
        proj.mkdir(parents=True)
        f = proj / 'my-sess.jsonl'
        with open(f, 'w') as fh:
            for m in messages:
                fh.write(json.dumps(m) + '\n')
        return tmp_path / 'projects'

    def test_multi_tool_query_returns_tool_calls_type(self, tmp_path):
        messages = [
            _tool_use_msg('Bash', {'command': 'ls'}, 'tid1'),
            _tool_use_msg('Read', {'file_path': '/f'}, 'tid2'),
        ]
        projects = self._make_jsonl(tmp_path, messages)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', projects):
            adapter = ClaudeAdapter('session/my-sess', query='tools=Bash,Read')
            result = adapter.get_structure()
        assert result['type'] == 'claude_tool_calls'
        assert result['call_count'] == 2

    def test_single_tool_query_unchanged(self, tmp_path):
        messages = [_tool_use_msg('Bash', {'command': 'ls'}, 'tid1')]
        projects = self._make_jsonl(tmp_path, messages)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', projects):
            adapter = ClaudeAdapter('session/my-sess', query='tools=Bash')
            result = adapter.get_structure()
        assert result['call_count'] == 1
        assert result['tool_name'] == 'Bash'
