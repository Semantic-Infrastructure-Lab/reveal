"""Tests for BACK-028: ?tail=N, ?last, and message/-1 support."""

import pytest
from unittest.mock import patch, MagicMock

from reveal.adapters.claude.analysis.messages import get_messages, get_message


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_assistant_text(text, idx=0, ts='2026-03-14T10:00:00Z'):
    return {
        'type': 'assistant',
        'timestamp': ts,
        'message': {'content': [{'type': 'text', 'text': text}]},
    }


def _make_user_msg(text='hello', idx=0):
    return {'type': 'user', 'message': {'content': text}}


CONTRACT = {'contract_version': '1.0', 'source': '/fake', 'source_type': 'file'}


def _build_messages(n=5):
    """Build n assistant turns interleaved with user messages."""
    msgs = []
    for i in range(n):
        msgs.append(_make_user_msg(f'user {i}'))
        msgs.append(_make_assistant_text(f'assistant turn {i+1}'))
    return msgs


# ─── ?tail=N via _route_by_query ─────────────────────────────────────────────

class TestTailQueryParam:
    """Test ?tail=N by exercising the ClaudeAdapter routing directly."""

    def _get_adapter(self, query_str):
        from reveal.adapters.claude.adapter import ClaudeAdapter
        from unittest.mock import patch, PropertyMock
        adapter = ClaudeAdapter.__new__(ClaudeAdapter)
        adapter.resource = 'session/test'
        adapter.query = query_str
        from reveal.utils.query import parse_query_params
        adapter.query_params = parse_query_params(query_str) if query_str else {}
        adapter.session_name = 'test-session'
        return adapter

    def test_tail_3_returns_last_3_turns(self):
        adapter = self._get_adapter('tail=3')
        msgs = _build_messages(6)  # 6 turns
        contract = CONTRACT.copy()
        result = adapter._route_by_query(msgs, '/fake', contract)
        assert result is not None
        assert result['type'] == 'claude_messages'
        turns = result['messages']
        assert len(turns) == 3
        assert turns[0]['text'] == 'assistant turn 4'
        assert turns[-1]['text'] == 'assistant turn 6'

    def test_tail_1_returns_last_turn(self):
        adapter = self._get_adapter('tail=1')
        msgs = _build_messages(4)
        result = adapter._route_by_query(msgs, '/fake', CONTRACT.copy())
        assert result is not None
        assert len(result['messages']) == 1
        assert result['messages'][0]['text'] == 'assistant turn 4'

    def test_tail_larger_than_total_returns_all(self):
        adapter = self._get_adapter('tail=100')
        msgs = _build_messages(3)
        result = adapter._route_by_query(msgs, '/fake', CONTRACT.copy())
        assert result is not None
        assert len(result['messages']) == 3

    def test_tail_result_has_tail_of_when_truncated(self):
        adapter = self._get_adapter('tail=2')
        msgs = _build_messages(5)
        result = adapter._route_by_query(msgs, '/fake', CONTRACT.copy())
        assert result.get('tail_of') == 5

    def test_tail_no_tail_of_when_all_shown(self):
        adapter = self._get_adapter('tail=100')
        msgs = _build_messages(3)
        result = adapter._route_by_query(msgs, '/fake', CONTRACT.copy())
        assert 'tail_of' not in result

    def test_tail_total_turns_reflects_full_count(self):
        adapter = self._get_adapter('tail=2')
        msgs = _build_messages(5)
        result = adapter._route_by_query(msgs, '/fake', CONTRACT.copy())
        assert result['total_turns'] == 5

    def test_last_flag_returns_one_turn(self):
        adapter = self._get_adapter('last')
        msgs = _build_messages(4)
        result = adapter._route_by_query(msgs, '/fake', CONTRACT.copy())
        assert result is not None
        assert len(result['messages']) == 1
        assert result['messages'][0]['text'] == 'assistant turn 4'

    def test_no_tail_returns_none(self):
        adapter = self._get_adapter('errors')
        msgs = _build_messages(3)
        # Should NOT be handled by _route_by_query's tail branch
        # (errors is handled earlier so we can't test None directly via tail path)
        # Instead test that a non-tail query without tail returns None when no other match
        adapter2 = self._get_adapter(None)
        result = adapter2._route_by_query(msgs, '/fake', CONTRACT.copy())
        assert result is None

    def test_tail_0_returns_empty(self):
        adapter = self._get_adapter('tail=0')
        msgs = _build_messages(3)
        result = adapter._route_by_query(msgs, '/fake', CONTRACT.copy())
        # tail=0 means no turns — but total available
        assert result is not None
        assert len(result['messages']) == 0


# ─── message/-1 negative index ───────────────────────────────────────────────

class TestNegativeMessageIndex:
    """Test negative indices on message/<n> path."""

    def _make_msgs(self, n=5):
        return [_make_user_msg(f'msg {i}') for i in range(n)]

    def test_negative_one_returns_last_message(self):
        msgs = self._make_msgs(5)
        contract = CONTRACT.copy()
        result = get_message(msgs, -1 + len(msgs), 'test', contract)
        # After conversion: -1 + 5 = 4 (last)
        assert result['message_index'] == 4

    def test_routing_converts_negative_before_call(self):
        """Test that the adapter routing converts -1 to len-1."""
        from reveal.adapters.claude.adapter import ClaudeAdapter
        adapter = ClaudeAdapter.__new__(ClaudeAdapter)
        adapter.resource = 'session/test/message/-1'
        adapter.query = None
        adapter.query_params = {}
        adapter.session_name = 'test-session'
        adapter.conversation_path = None

        msgs = self._make_msgs(5)
        contract = CONTRACT.copy()
        contract['source'] = '/fake'
        contract['source_type'] = 'file'

        result = adapter._route_by_resource(msgs, '/fake', contract)
        assert result['type'] == 'claude_message'
        assert result['message_index'] == 4  # last of 5

    def test_negative_two_returns_second_to_last(self):
        msgs = self._make_msgs(5)
        contract = CONTRACT.copy()
        result = get_message(msgs, -2 + len(msgs), 'test', contract)
        assert result['message_index'] == 3

    def test_get_message_valid_index(self):
        msgs = self._make_msgs(3)
        result = get_message(msgs, 0, 'test', CONTRACT.copy())
        assert result['message_index'] == 0
        assert 'error' not in result

    def test_get_message_out_of_range_returns_error(self):
        msgs = self._make_msgs(3)
        result = get_message(msgs, 10, 'test', CONTRACT.copy())
        assert 'error' in result

    def test_routing_negative_index_out_of_range_gives_error(self):
        """message/-99 converts to a negative absolute index → out of range error."""
        from reveal.adapters.claude.adapter import ClaudeAdapter
        adapter = ClaudeAdapter.__new__(ClaudeAdapter)
        adapter.resource = 'session/test/message/-99'
        adapter.query = None
        adapter.query_params = {}
        adapter.session_name = 'test-session'
        adapter.conversation_path = None

        msgs = self._make_msgs(3)
        contract = {'contract_version': '1.0', 'source': '/fake', 'source_type': 'file'}
        result = adapter._route_by_resource(msgs, '/fake', contract)
        # -99 + 3 = -96, still negative → out of range
        assert 'error' in result
