"""Tests targeting uncovered lines in reveal/adapters/claude/adapter.py.

Coverage gaps targeted:
  - _find_conversation: no CONVERSATION_BASE, UUID fallback (lines 236, 252)
  - _route_by_query: ?tools=, ?search=, ?tail=, ?last (lines 293-308)
  - _route_by_resource: /messages with search (lines 334-335)
  - _handle_composite_query: all filter combos (lines 428-454)
  - _extract_text_from_content: list content blocks (lines 461-464)
  - _parse_jsonl_line_for_title: boilerplate, boot., non-user (lines 476-498)
  - _list_sessions: filter, error path (lines 596, 599-600, 603-604)
  - _search_sessions: since='today', error path (lines 641-643, 651-652)
  - _track_file_sessions: since='today', error path (lines 700-702, 724-725)
  - post_process: all three result types (lines 943-965)
  - _slice_list: head, tail, range (lines 970-980)
  - _post_process_workflow: type/search filter, slicing (lines 985-1007)
  - _post_process_session_list: search, since, head/all, title read (lines 1010-1037)
  - _post_process_messages: slicing (lines 1040-1047)
"""

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from reveal.adapters.claude.adapter import ClaudeAdapter


# ─── Fixtures / helpers ───────────────────────────────────────────────────────

def _write_session(base: Path, session_name: str, messages: list) -> Path:
    """Write JSONL session under base/<dir-name>/<session-name>.jsonl."""
    project_dir = base / f'-home-user-sessions-{session_name}'
    project_dir.mkdir(parents=True, exist_ok=True)
    jsonl = project_dir / f'{session_name}.jsonl'
    jsonl.write_text('\n'.join(json.dumps(m) for m in messages) + '\n')
    return jsonl


def _tool_use_msg(tool_name: str, tool_id: str = 'tu_001', **inp) -> dict:
    return {
        'type': 'assistant',
        'timestamp': '2026-03-14T10:00:00',
        'message': {'content': [
            {'type': 'tool_use', 'id': tool_id, 'name': tool_name, 'input': inp}
        ]},
    }


def _tool_result_msg(tool_id: str, content: str = 'ok', is_error: bool = False) -> dict:
    return {
        'type': 'user',
        'timestamp': '2026-03-14T10:01:00',
        'message': {'content': [
            {'type': 'tool_result', 'tool_use_id': tool_id, 'content': content, 'is_error': is_error}
        ]},
    }


def _user_msg(text: str) -> dict:
    return {
        'type': 'user',
        'timestamp': '2026-03-14T10:00:00',
        'message': {'role': 'user', 'content': text},
    }


def _assistant_msg(text: str) -> dict:
    return {
        'type': 'assistant',
        'timestamp': '2026-03-14T10:01:00',
        'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]},
    }


def _adapter(resource: str, query: str = None, base: Path = None) -> ClaudeAdapter:
    """Build a ClaudeAdapter with optional CONVERSATION_BASE override."""
    if base is not None:
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            return ClaudeAdapter(resource, query)
    return ClaudeAdapter(resource, query)


# ─── _find_conversation ───────────────────────────────────────────────────────

class TestFindConversation:

    def test_returns_none_when_base_does_not_exist(self, tmp_path):
        missing = tmp_path / 'no-such-dir'
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', missing):
            adapter = ClaudeAdapter('session/my-session')
        assert adapter.conversation_path is None

    def test_returns_none_for_empty_session_name(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        assert adapter.conversation_path is None

    def test_finds_named_session_by_dir(self, tmp_path):
        _write_session(tmp_path, 'my-session', [_user_msg('hello')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('session/my-session')
        assert adapter.conversation_path is not None
        assert 'my-session' in str(adapter.conversation_path)

    def test_uuid_fallback_strategy(self, tmp_path):
        """UUID filename under a project dir should be found via strategy 2."""
        uuid = '12345678-1234-5678-1234-567812345678'
        project_dir = tmp_path / 'some-project-dir'
        project_dir.mkdir()
        jsonl = project_dir / f'{uuid}.jsonl'
        jsonl.write_text(json.dumps(_user_msg('hi')) + '\n')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter(f'session/{uuid}')
        assert adapter.conversation_path == jsonl


# ─── _route_by_query ─────────────────────────────────────────────────────────

class TestRouteByQuery:

    def _make_session(self, tmp_path, messages):
        jsonl = _write_session(tmp_path, 'test-session', messages)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('session/test-session')
        adapter.conversation_path = jsonl
        adapter.messages = messages
        return adapter

    def test_tools_prefix_routes_to_tool_calls(self, tmp_path):
        msgs = [_tool_use_msg('Bash', command='ls')]
        adapter = self._make_session(tmp_path, msgs)
        adapter.query = 'tools=Bash'
        adapter.query_params = {'tools': 'Bash'}
        base = adapter._get_contract_base()
        result = adapter._route_by_query(msgs, '', base)
        assert result is not None
        assert result.get('type') == 'claude_tool_calls'
        assert result.get('tool_name') == 'Bash'

    def test_search_prefix_routes_to_search(self, tmp_path):
        msgs = [_user_msg('looking for something'), _assistant_msg('here it is')]
        adapter = self._make_session(tmp_path, msgs)
        adapter.query = 'search=something'
        adapter.query_params = {'search': 'something'}
        base = adapter._get_contract_base()
        result = adapter._route_by_query(msgs, '', base)
        assert result is not None

    def test_tail_query_param(self, tmp_path):
        msgs = [_user_msg('turn 1'), _assistant_msg('resp 1'),
                _user_msg('turn 2'), _assistant_msg('resp 2')]
        adapter = self._make_session(tmp_path, msgs)
        adapter.query = 'tail=1'
        adapter.query_params = {'tail': '1'}
        base = adapter._get_contract_base()
        result = adapter._route_by_query(msgs, '', base)
        assert result is not None
        assert result.get('type') == 'claude_messages'

    def test_last_query_param(self, tmp_path):
        msgs = [_user_msg('hello'), _assistant_msg('hi')]
        adapter = self._make_session(tmp_path, msgs)
        adapter.query = 'last'
        adapter.query_params = {'last': ''}
        base = adapter._get_contract_base()
        result = adapter._route_by_query(msgs, '', base)
        assert result is not None
        assert result.get('type') == 'claude_messages'

    def test_unrecognized_query_returns_none(self, tmp_path):
        msgs = [_user_msg('hello')]
        adapter = self._make_session(tmp_path, msgs)
        adapter.query = None
        adapter.query_params = {}
        base = adapter._get_contract_base()
        result = adapter._route_by_query(msgs, '', base)
        assert result is None


# ─── _route_by_resource: /messages with search ────────────────────────────────

class TestRouteByResourceMessages:

    def test_messages_resource_with_search_param(self, tmp_path):
        msgs = [_user_msg('find this'), _assistant_msg('found')]
        jsonl = _write_session(tmp_path, 'sess', msgs)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('session/sess', query='search=find')
        adapter.conversation_path = jsonl
        adapter.messages = msgs
        adapter.resource = 'session/sess/messages'
        adapter.query_params = {'search': 'find'}
        base = adapter._get_contract_base()
        result = adapter._route_by_resource(msgs, '', base)
        assert result.get('type') == 'claude_messages'

    def test_messages_resource_with_contains_param(self, tmp_path):
        msgs = [_user_msg('hello')]
        jsonl = _write_session(tmp_path, 'sess', msgs)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('session/sess', query='contains=hello')
        adapter.conversation_path = jsonl
        adapter.messages = msgs
        adapter.resource = 'session/sess/messages'
        base = adapter._get_contract_base()
        result = adapter._route_by_resource(msgs, '', base)
        assert result.get('type') == 'claude_messages'


# ─── _handle_composite_query ──────────────────────────────────────────────────

class TestHandleCompositeQuery:

    def _make_adapter_with_messages(self, tmp_path, messages, query):
        jsonl = _write_session(tmp_path, 'sess', messages)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('session/sess', query=query)
        adapter.conversation_path = jsonl
        adapter.messages = messages
        return adapter

    def test_tools_and_errors_filter(self, tmp_path):
        msgs = [
            _tool_use_msg('Bash', 'tu_001', command='ls'),
            _tool_result_msg('tu_001', 'fail', is_error=True),
        ]
        adapter = self._make_adapter_with_messages(tmp_path, msgs, 'tools=Bash&errors')
        result = adapter._handle_composite_query(msgs)
        assert result['type'] == 'claude_filtered_results'
        assert 'results' in result

    def test_errors_and_contains_filter(self, tmp_path):
        msgs = [
            _tool_use_msg('Bash', 'tu_001', command='ls'),
            _tool_result_msg('tu_001', 'traceback here', is_error=True),
        ]
        adapter = self._make_adapter_with_messages(tmp_path, msgs, 'errors&contains=traceback')
        result = adapter._handle_composite_query(msgs)
        assert result['type'] == 'claude_filtered_results'
        assert result['result_count'] >= 1

    def test_tools_and_contains_filter(self, tmp_path):
        msgs = [
            _tool_use_msg('Read', 'tu_001', file_path='config.py'),
            _tool_result_msg('tu_001', 'config content here'),
        ]
        adapter = self._make_adapter_with_messages(tmp_path, msgs, 'tools=Read&contains=config')
        result = adapter._handle_composite_query(msgs)
        assert result['type'] == 'claude_filtered_results'

    def test_empty_messages_returns_zero_results(self, tmp_path):
        adapter = self._make_adapter_with_messages(tmp_path, [], 'tools=Bash&errors')
        result = adapter._handle_composite_query([])
        assert result['result_count'] == 0

    def test_filters_applied_list_in_result(self, tmp_path):
        msgs = [_tool_use_msg('Bash', 'tu_001', command='ls'), _tool_result_msg('tu_001')]
        adapter = self._make_adapter_with_messages(tmp_path, msgs, 'tools=Bash&errors')
        result = adapter._handle_composite_query(msgs)
        assert 'filters_applied' in result


# ─── _extract_text_from_content ───────────────────────────────────────────────

class TestExtractTextFromContent:

    def test_string_content(self):
        result = ClaudeAdapter._extract_text_from_content('  hello  ')
        assert result == 'hello'

    def test_list_with_text_block(self):
        content = [{'type': 'text', 'text': 'hello world'}]
        result = ClaudeAdapter._extract_text_from_content(content)
        assert result == 'hello world'

    def test_list_skips_non_text_blocks(self):
        content = [
            {'type': 'tool_use', 'name': 'Bash'},
            {'type': 'text', 'text': 'found me'},
        ]
        result = ClaudeAdapter._extract_text_from_content(content)
        assert result == 'found me'

    def test_empty_list_returns_empty(self):
        result = ClaudeAdapter._extract_text_from_content([])
        assert result == ''

    def test_list_with_no_text_block_returns_empty(self):
        content = [{'type': 'tool_use', 'name': 'Bash'}]
        result = ClaudeAdapter._extract_text_from_content(content)
        assert result == ''

    def test_empty_string_returns_empty(self):
        result = ClaudeAdapter._extract_text_from_content('')
        assert result == ''


# ─── _parse_jsonl_line_for_title ─────────────────────────────────────────────

class TestParseJsonlLineForTitle:

    def _line(self, msg: dict) -> str:
        return json.dumps(msg)

    def test_returns_user_text(self):
        line = self._line({'type': 'user', 'message': {'content': 'What is Python?'}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result == 'What is Python?'

    def test_returns_none_for_non_user_type(self):
        line = self._line({'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hi'}]}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result is None

    def test_returns_none_for_empty_content(self):
        line = self._line({'type': 'user', 'message': {'content': ''}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result is None

    def test_returns_boot_dot_as_title(self):
        # 'boot.' is not a reserved skip word — only bare 'boot' is skipped
        line = self._line({'type': 'user', 'message': {'content': 'boot.'}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result == 'boot.'

    def test_returns_none_for_bare_boot(self):
        line = self._line({'type': 'user', 'message': {'content': 'boot'}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result is None

    def test_returns_none_for_invalid_json(self):
        result = ClaudeAdapter._parse_jsonl_line_for_title('not json at all {')
        assert result is None

    def test_boilerplate_with_separator_extracts_real_text(self):
        text = '# Session Continuation Context\n\n---\n\nafter boot, process: fix the bug'
        line = self._line({'type': 'user', 'message': {'content': text}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result is not None
        assert 'fix the bug' in result

    def test_boilerplate_without_separator_returns_none(self):
        text = '# Session Continuation Context\n\nsome context without separator'
        line = self._line({'type': 'user', 'message': {'content': text}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result is None

    def test_unknown_heading_returned_as_title(self):
        # Only '# Session Continuation Context' is a boilerplate prefix; other headings become titles
        text = '# Some Unknown Heading\n\nsome content'
        line = self._line({'type': 'user', 'message': {'content': text}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result == '# Some Unknown Heading'

    def test_truncates_to_80_chars(self):
        long_text = 'A' * 100
        line = self._line({'type': 'user', 'message': {'content': long_text}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result is not None
        assert len(result) <= 80

    def test_list_content_with_text_block(self):
        content = [{'type': 'text', 'text': 'What is a generator?'}]
        line = self._line({'type': 'user', 'message': {'content': content}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result == 'What is a generator?'


# ─── _list_sessions ───────────────────────────────────────────────────────────

class TestListSessions:

    def test_lists_sessions(self, tmp_path):
        _write_session(tmp_path, 'alpha-session', [_user_msg('hi')])
        _write_session(tmp_path, 'beta-session', [_user_msg('hello')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
            result = adapter._list_sessions()
        assert result['type'] == 'claude_session_list'
        assert result['session_count'] == 2

    def test_filter_by_name(self, tmp_path):
        _write_session(tmp_path, 'alpha-session', [_user_msg('hi')])
        _write_session(tmp_path, 'beta-session', [_user_msg('hi')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='filter=alpha')
            result = adapter._list_sessions()
        sessions = result['recent_sessions']
        assert all('alpha' in s['session'].lower() for s in sessions)

    def test_search_param_as_filter_alias(self, tmp_path):
        _write_session(tmp_path, 'zebra-session', [_user_msg('hi')])
        _write_session(tmp_path, 'alpha-session', [_user_msg('hi')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=zebra')
            result = adapter._list_sessions()
        sessions = result['recent_sessions']
        assert all('zebra' in s['session'].lower() for s in sessions)

    def test_empty_base_returns_zero_sessions(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
            result = adapter._list_sessions()
        assert result['session_count'] == 0

    def test_error_in_iteration_sets_error_key(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        with patch.object(type(tmp_path), 'iterdir', side_effect=PermissionError('denied')):
            result = adapter._list_sessions()
        assert 'error' in result

    def test_result_has_usage_block(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
            result = adapter._list_sessions()
        assert 'usage' in result


# ─── _search_sessions ────────────────────────────────────────────────────────

class TestSearchSessions:

    def test_basic_search_returns_results_type(self, tmp_path):
        _write_session(tmp_path, 'sess-1', [_user_msg('target keyword')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=target')
            result = adapter._search_sessions()
        assert result['type'] == 'claude_cross_session_search'
        assert result['term'] == 'target'

    def test_no_results_returns_empty_matches(self, tmp_path):
        _write_session(tmp_path, 'sess-1', [_user_msg('hello world')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=zzznomatch')
            result = adapter._search_sessions()
        assert result['match_count'] == 0
        assert result['matches'] == []

    def test_since_today_normalised(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=foo&since=today')
            result = adapter._search_sessions()
        # since should have been normalised to an ISO date, not 'today'
        assert result.get('since') != 'today'

    def test_error_during_iteration_returns_error_dict(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=foo')
        with patch.object(type(tmp_path), 'iterdir', side_effect=OSError('io error')):
            result = adapter._search_sessions()
        assert 'error' in result
        assert result['type'] == 'claude_cross_session_search'

    def test_since_filters_sessions(self, tmp_path):
        _write_session(tmp_path, 'sess-old', [_user_msg('old content')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=old&since=2030-01-01')
            result = adapter._search_sessions()
        # No sessions modified after 2030-01-01
        assert result['sessions_scanned'] == 0

    def test_until_filters_sessions(self, tmp_path):
        _write_session(tmp_path, 'sess-recent', [_user_msg('some content')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=some&until=2020-01-01')
            result = adapter._search_sessions()
        # Sessions created today are after 2020-01-01 upper bound
        assert result['sessions_scanned'] == 0

    def test_until_today_normalised(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=foo&until=today')
            result = adapter._search_sessions()
        # until='today' must not be passed through as literal string
        assert result.get('until') != 'today'

    def test_snippet_invalid_value_uses_default(self, tmp_path):
        _write_session(tmp_path, 'sess-1', [_user_msg('hello world')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=hello&snippet=notanint')
            result = adapter._search_sessions()
        # Should not raise — returns normal result with default snippet window
        assert result['type'] == 'claude_cross_session_search'


# ─── _track_file_sessions ────────────────────────────────────────────────────

class TestTrackFileSessions:

    def test_no_file_path_returns_error(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files')
            result = adapter._track_file_sessions()
        assert 'error' in result
        assert result['type'] == 'claude_file_sessions'

    def test_basic_tracking_returns_result_type(self, tmp_path):
        _write_session(tmp_path, 'sess', [
            _tool_use_msg('Read', 'tu_001', file_path='/home/user/foo.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/foo.py')
            result = adapter._track_file_sessions()
        assert result['type'] == 'claude_file_sessions'
        assert result['file_path'] == 'foo.py'

    def test_since_today_normalised(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/foo.py', query='since=today')
            result = adapter._track_file_sessions()
        assert result.get('since') != 'today'

    def test_error_during_iteration_returns_error(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/foo.py')
        with patch.object(type(tmp_path), 'iterdir', side_effect=OSError('denied')):
            result = adapter._track_file_sessions()
        assert 'error' in result

    def test_since_filters_old_sessions(self, tmp_path):
        _write_session(tmp_path, 'sess', [_tool_use_msg('Read', 'tu_001', file_path='foo.py')])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/foo.py', query='since=2030-01-01')
            result = adapter._track_file_sessions()
        assert result['sessions_scanned'] == 0


# ─── post_process ─────────────────────────────────────────────────────────────

class TestPostProcess:

    def _args(self, **kwargs) -> Namespace:
        defaults = dict(head=None, tail=None, range=None, verbose=False,
                        max_snippet_chars=None, type=None, name=None,
                        since=None, all=False)
        defaults.update(kwargs)
        return Namespace(**defaults)

    def test_non_dict_result_returned_unchanged(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process('not a dict', self._args())
        assert result == 'not a dict'

    def test_non_claude_type_returned_unchanged(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process({'type': 'other_type', 'data': 1}, self._args())
        assert result['type'] == 'other_type'

    def test_claude_type_gets_display_block(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process({'type': 'claude_session_list', 'recent_sessions': []}, self._args())
        assert '_display' in result

    def test_post_process_workflow_result(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        workflow = [
            {'step': 1, 'tool': 'Bash', 'detail': 'ls', 'message_index': 0, 'timestamp': None},
            {'step': 2, 'tool': 'Read', 'detail': 'foo.py', 'message_index': 1, 'timestamp': None},
        ]
        result = adapter.post_process(
            {'type': 'claude_workflow', 'workflow': workflow, 'total_steps': 2, 'collapsed_steps': 2},
            self._args()
        )
        assert '_display' in result
        assert 'workflow' in result

    def test_post_process_messages_result(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        msgs = [{'role': 'user', 'text': 'hi'}, {'role': 'assistant', 'text': 'hello'}]
        result = adapter.post_process(
            {'type': 'claude_messages', 'messages': msgs},
            self._args()
        )
        assert '_display' in result


# ─── _slice_list ──────────────────────────────────────────────────────────────

class TestSliceList:

    def _args(self, **kwargs) -> Namespace:
        defaults = dict(head=None, tail=None, range=None)
        defaults.update(kwargs)
        return Namespace(**defaults)

    def test_no_args_returns_full_list(self):
        items = list(range(10))
        result = ClaudeAdapter._slice_list(items, self._args())
        assert result == items

    def test_head_slices_from_start(self):
        items = list(range(10))
        result = ClaudeAdapter._slice_list(items, self._args(head=3))
        assert result == [0, 1, 2]

    def test_tail_slices_from_end(self):
        items = list(range(10))
        result = ClaudeAdapter._slice_list(items, self._args(tail=3))
        assert result == [7, 8, 9]

    def test_range_slices_by_1indexed_inclusive(self):
        items = list(range(1, 11))  # [1..10]
        result = ClaudeAdapter._slice_list(items, self._args(range=(2, 4)))
        assert result == [2, 3, 4]

    def test_head_takes_priority_over_tail(self):
        items = list(range(10))
        result = ClaudeAdapter._slice_list(items, self._args(head=2, tail=3))
        assert result == [0, 1]


# ─── _post_process_workflow ───────────────────────────────────────────────────

class TestPostProcessWorkflow:

    def _args(self, **kwargs) -> Namespace:
        defaults = dict(head=None, tail=None, range=None, type=None, name=None)
        defaults.update(kwargs)
        return Namespace(**defaults)

    def _workflow_result(self, steps):
        return {
            'type': 'claude_workflow',
            'total_steps': len(steps),
            'collapsed_steps': len(steps),
            'workflow': steps,
        }

    def _step(self, tool, detail, idx=0):
        return {'step': idx + 1, 'tool': tool, 'detail': detail, 'message_index': idx, 'timestamp': None}

    def test_no_filter_returns_all_steps(self):
        steps = [self._step('Bash', 'ls'), self._step('Read', 'foo.py')]
        result = dict(self._workflow_result(steps))
        ClaudeAdapter._post_process_workflow(result, self._args())
        assert len(result['workflow']) == 2

    def test_type_filter(self):
        steps = [self._step('Bash', 'ls'), self._step('Read', 'foo.py')]
        result = dict(self._workflow_result(steps))
        ClaudeAdapter._post_process_workflow(result, self._args(type='bash'))
        assert all(s['tool'] == 'Bash' for s in result['workflow'])

    def test_search_filter(self):
        steps = [self._step('Bash', 'ls'), self._step('Read', 'config.py')]
        result = dict(self._workflow_result(steps))
        ClaudeAdapter._post_process_workflow(result, self._args(name='config'))
        assert len(result['workflow']) == 1
        assert result['workflow'][0]['detail'] == 'config.py'

    def test_head_slicing(self):
        steps = [self._step('Bash', f'cmd-{i}') for i in range(5)]
        result = dict(self._workflow_result(steps))
        ClaudeAdapter._post_process_workflow(result, self._args(head=2))
        assert len(result['workflow']) == 2

    def test_filtered_from_added_when_filtered(self):
        steps = [self._step('Bash', 'ls'), self._step('Read', 'foo.py')]
        result = dict(self._workflow_result(steps))
        ClaudeAdapter._post_process_workflow(result, self._args(type='bash'))
        assert 'filtered_from' in result

    def test_none_workflow_returns_early(self):
        result = {'type': 'claude_workflow', 'workflow': None}
        ClaudeAdapter._post_process_workflow(result, self._args())
        assert result['workflow'] is None


# ─── _post_process_session_list ──────────────────────────────────────────────

class TestPostProcessSessionList:

    def _args(self, **kwargs) -> Namespace:
        defaults = dict(head=None, tail=None, range=None, name=None, since=None, until=None,
                        with_stats=False, all=False)
        defaults.update(kwargs)
        return Namespace(**defaults)

    def _sessions(self, names):
        return [{'session': n, 'modified': '2026-03-14T10:00:00', 'path': None} for n in names]

    def test_default_limits_to_20(self):
        sessions = self._sessions([f'sess-{i}' for i in range(30)])
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args())
        assert len(result['recent_sessions']) == 20

    def test_all_flag_shows_all(self):
        sessions = self._sessions([f'sess-{i}' for i in range(30)])
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(all=True))
        assert len(result['recent_sessions']) == 30

    def test_search_filters_by_session_name(self):
        sessions = self._sessions(['alpha-session', 'beta-session', 'alpha-two'])
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(name='alpha', all=True))
        assert all('alpha' in s['session'] for s in result['recent_sessions'])

    def test_since_filters_by_modified_date(self):
        sessions = [
            {'session': 'old', 'modified': '2025-01-01T00:00:00', 'path': None},
            {'session': 'new', 'modified': '2026-03-14T00:00:00', 'path': None},
        ]
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(since='2026-01-01', all=True))
        assert all(s['modified'] >= '2026-01-01' for s in result['recent_sessions'])

    def test_since_today_normalised(self):
        sessions = []
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(since='today', all=True))
        # Should not crash; sessions already empty

    def test_head_arg_limits(self):
        sessions = self._sessions([f'sess-{i}' for i in range(10)])
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(head=3))
        assert len(result['recent_sessions']) == 3

    def test_displayed_count_added(self):
        sessions = self._sessions(['s1', 's2'])
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args())
        assert 'displayed_count' in result

    def test_none_sessions_returns_early(self):
        result = {'type': 'claude_session_list', 'recent_sessions': None}
        ClaudeAdapter._post_process_session_list(result, self._args())
        assert result['recent_sessions'] is None

    def test_until_filters_by_modified_date(self):
        sessions = [
            {'session': 'old', 'modified': '2025-01-01T10:00:00', 'path': None},
            {'session': 'new', 'modified': '2026-06-18T10:00:00', 'path': None},
        ]
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(until='2026-01-01', all=True))
        names = [s['session'] for s in result['recent_sessions']]
        assert names == ['old']

    def test_until_includes_sessions_on_boundary_date(self):
        sessions = [
            {'session': 'boundary', 'modified': '2026-01-01T23:59:59.999999', 'path': None},
            {'session': 'next-day', 'modified': '2026-01-02T00:00:00', 'path': None},
        ]
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(until='2026-01-01', all=True))
        names = [s['session'] for s in result['recent_sessions']]
        assert names == ['boundary']

    def test_until_today_normalised(self):
        from datetime import date
        sessions = [
            {'session': 'today-sess', 'modified': date.today().isoformat() + 'T12:00:00', 'path': None},
            {'session': 'future', 'modified': '2099-12-31T00:00:00', 'path': None},
        ]
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(until='today', all=True))
        names = [s['session'] for s in result['recent_sessions']]
        assert names == ['today-sess']

    def test_since_and_until_together(self):
        sessions = [
            {'session': 'before', 'modified': '2025-06-01T00:00:00', 'path': None},
            {'session': 'in-range', 'modified': '2026-01-15T00:00:00', 'path': None},
            {'session': 'after', 'modified': '2026-06-18T00:00:00', 'path': None},
        ]
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(
            result, self._args(since='2026-01-01', until='2026-03-01', all=True)
        )
        names = [s['session'] for s in result['recent_sessions']]
        assert names == ['in-range']


# ─── BACK-348 --with-stats ────────────────────────────────────────────────────

class TestReadSessionStats:

    from reveal.adapters.claude.handlers.sessions import _read_session_stats

    def _write_jsonl(self, path, lines):
        path.write_text('\n'.join(json.dumps(l) for l in lines) + '\n')

    def test_returns_message_count(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _read_session_stats
        f = tmp_path / 'sess.jsonl'
        self._write_jsonl(f, [
            {'type': 'user', 'timestamp': '2026-06-18T10:00:00Z'},
            {'type': 'assistant', 'timestamp': '2026-06-18T10:01:00Z'},
            {'type': 'user', 'timestamp': '2026-06-18T10:02:00Z'},
        ])
        stats = _read_session_stats(f)
        assert stats['message_count'] == 3

    def test_returns_duration(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _read_session_stats
        f = tmp_path / 'sess.jsonl'
        self._write_jsonl(f, [
            {'type': 'user', 'timestamp': '2026-06-18T10:00:00Z'},
            {'type': 'assistant', 'timestamp': '2026-06-18T11:30:00Z'},
        ])
        stats = _read_session_stats(f)
        assert stats['duration'] == '1h30m'

    def test_duration_minutes_only(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _read_session_stats
        f = tmp_path / 'sess.jsonl'
        self._write_jsonl(f, [
            {'type': 'user', 'timestamp': '2026-06-18T10:00:00Z'},
            {'type': 'assistant', 'timestamp': '2026-06-18T10:45:00Z'},
        ])
        stats = _read_session_stats(f)
        assert stats['duration'] == '45m'

    def test_missing_timestamp_no_duration(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _read_session_stats
        f = tmp_path / 'sess.jsonl'
        self._write_jsonl(f, [{'type': 'user'}, {'type': 'assistant'}])
        stats = _read_session_stats(f)
        assert stats['message_count'] == 2
        assert 'duration' not in stats

    def test_empty_file_returns_empty(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _read_session_stats
        f = tmp_path / 'sess.jsonl'
        f.write_text('')
        stats = _read_session_stats(f)
        assert stats == {}

    def test_missing_file_returns_empty(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _read_session_stats
        stats = _read_session_stats(tmp_path / 'missing.jsonl')
        assert stats == {}


class TestPostProcessSessionListWithStats:

    def _args(self, **kwargs):
        defaults = dict(head=None, name=None, since=None, until=None, with_stats=False, all=True)
        defaults.update(kwargs)
        return Namespace(**defaults)

    def test_with_stats_false_no_stats_fields(self, tmp_path):
        f = tmp_path / 'sess.jsonl'
        f.write_text(json.dumps({'type': 'user', 'timestamp': '2026-06-18T10:00:00Z'}) + '\n')
        sessions = [{'session': 's1', 'modified': '2026-06-18T10:00:00', 'path': str(f)}]
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(with_stats=False))
        assert 'message_count' not in result['recent_sessions'][0]
        assert 'with_stats' not in result

    def test_with_stats_true_adds_stats_to_sessions(self, tmp_path):
        f = tmp_path / 'sess.jsonl'
        f.write_text(
            json.dumps({'type': 'user', 'timestamp': '2026-06-18T10:00:00Z'}) + '\n' +
            json.dumps({'type': 'assistant', 'timestamp': '2026-06-18T10:30:00Z'}) + '\n'
        )
        sessions = [{'session': 's1', 'modified': '2026-06-18T10:00:00', 'path': str(f)}]
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(with_stats=True))
        s = result['recent_sessions'][0]
        assert s['message_count'] == 2
        assert s['duration'] == '30m'
        assert result.get('with_stats') is True

    def test_with_stats_none_path_skipped(self):
        sessions = [{'session': 's1', 'modified': '2026-06-18T10:00:00', 'path': None}]
        result = {'type': 'claude_session_list', 'recent_sessions': sessions}
        ClaudeAdapter._post_process_session_list(result, self._args(with_stats=True))
        assert 'message_count' not in result['recent_sessions'][0]


class TestRenderSessionListWithStats:

    def _result(self, sessions, with_stats=False):
        return {
            'type': 'claude_session_list',
            'session_count': len(sessions),
            'recent_sessions': sessions,
            'displayed_count': len(sessions),
            'with_stats': with_stats,
            'usage': {},
        }

    def _capture(self, result):
        from io import StringIO
        import sys
        buf = StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            from reveal.adapters.claude.render_sessions import _render_claude_session_list
            _render_claude_session_list(result)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_default_shows_size_column(self):
        sessions = [{'session': 'my-sess', 'modified': '2026-06-18T10:00:00',
                     'size_kb': 42, 'readme_present': True, 'project': 'reveal', 'title': 'hi'}]
        out = self._capture(self._result(sessions, with_stats=False))
        assert 'SIZE' in out
        assert '42kb' in out
        assert 'MSGS' not in out

    def test_with_stats_shows_msgs_and_duration(self):
        sessions = [{'session': 'my-sess', 'modified': '2026-06-18T10:00:00',
                     'readme_present': True, 'project': 'reveal', 'title': 'hi',
                     'message_count': 120, 'duration': '45m'}]
        out = self._capture(self._result(sessions, with_stats=True))
        assert 'MSGS' in out
        assert 'DUR' in out
        assert '120' in out
        assert '45m' in out
        assert 'SIZE' not in out

    def test_hint_shown_when_no_stats(self):
        out = self._capture(self._result([], with_stats=False))
        assert '--with-stats' in out

    def test_hint_not_shown_when_stats_active(self):
        out = self._capture(self._result([], with_stats=True))
        assert '--with-stats' not in out


# ─── _post_process_messages ───────────────────────────────────────────────────

class TestPostProcessMessages:

    def _args(self, **kwargs) -> Namespace:
        defaults = dict(head=None, tail=None, range=None)
        defaults.update(kwargs)
        return Namespace(**defaults)

    def test_no_slice_returns_all_messages(self):
        msgs = [{'role': 'user'}, {'role': 'assistant'}, {'role': 'user'}]
        result = {'type': 'claude_messages', 'messages': msgs}
        ClaudeAdapter._post_process_messages(result, self._args())
        assert len(result['messages']) == 3

    def test_head_slices_messages(self):
        msgs = [{'role': 'user'} for _ in range(5)]
        result = {'type': 'claude_messages', 'messages': msgs}
        ClaudeAdapter._post_process_messages(result, self._args(head=2))
        assert len(result['messages']) == 2

    def test_tail_slices_messages(self):
        msgs = [{'n': i} for i in range(6)]
        result = {'type': 'claude_messages', 'messages': msgs}
        ClaudeAdapter._post_process_messages(result, self._args(tail=2))
        assert result['messages'] == [{'n': 4}, {'n': 5}]

    def test_total_turns_updated(self):
        msgs = [{'role': 'user'} for _ in range(5)]
        result = {'type': 'claude_messages', 'messages': msgs}
        ClaudeAdapter._post_process_messages(result, self._args(head=2))
        assert result['total_turns'] == 2

    def test_none_messages_returns_early(self):
        result = {'type': 'claude_messages', 'messages': None}
        ClaudeAdapter._post_process_messages(result, self._args())
        assert result['messages'] is None


# ─── chain traversal ──────────────────────────────────────────────────────────

def _write_readme(sessions_dir: Path, session_name: str, frontmatter: dict) -> Path:
    """Write a README*.md with YAML frontmatter to sessions_dir/<session_name>/."""
    import yaml
    session_dir = sessions_dir / session_name
    session_dir.mkdir(parents=True, exist_ok=True)
    readme = session_dir / f'README_2026-01-01_00-00.md'
    fm_text = yaml.dump(frontmatter, default_flow_style=False)
    readme.write_text(f'---\n{fm_text}---\n\n# {session_name}\n')
    return readme


class TestFindSessionReadme:

    def test_returns_none_when_sessions_dir_is_none(self):
        result = ClaudeAdapter._find_session_readme('any-session', None)
        assert result is None

    def test_returns_none_when_sessions_dir_missing(self, tmp_path):
        missing = tmp_path / 'no-such-dir'
        result = ClaudeAdapter._find_session_readme('any-session', missing)
        assert result is None

    def test_returns_none_when_session_subdir_missing(self, tmp_path):
        (tmp_path / 'other-session').mkdir()
        result = ClaudeAdapter._find_session_readme('my-session', tmp_path)
        assert result is None

    def test_finds_readme_in_session_dir(self, tmp_path):
        readme = _write_readme(tmp_path, 'my-session', {'badge': 'test'})
        result = ClaudeAdapter._find_session_readme('my-session', tmp_path)
        assert result == readme

    def test_returns_most_recent_readme(self, tmp_path):
        session_dir = tmp_path / 'my-session'
        session_dir.mkdir()
        (session_dir / 'README_2026-01-01_00-00.md').write_text('---\nbadge: old\n---\n')
        newest = session_dir / 'README_2026-03-15_22-00.md'
        newest.write_text('---\nbadge: new\n---\n')
        result = ClaudeAdapter._find_session_readme('my-session', tmp_path)
        assert result == newest


class TestParseReadmeFrontmatter:

    def test_parses_yaml_frontmatter(self, tmp_path):
        readme = tmp_path / 'README.md'
        readme.write_text('---\nbadge: test badge\ncontinuing_from: prev-session\n---\n# body\n')
        result = ClaudeAdapter._parse_readme_frontmatter(readme)
        assert result['badge'] == 'test badge'
        assert result['continuing_from'] == 'prev-session'

    def test_returns_empty_for_no_frontmatter(self, tmp_path):
        readme = tmp_path / 'README.md'
        readme.write_text('# Just a heading\nNo frontmatter here.\n')
        result = ClaudeAdapter._parse_readme_frontmatter(readme)
        assert result == {}

    def test_returns_empty_for_unclosed_frontmatter(self, tmp_path):
        readme = tmp_path / 'README.md'
        readme.write_text('---\nbadge: test\n# no closing ---\n')
        result = ClaudeAdapter._parse_readme_frontmatter(readme)
        assert result == {}

    def test_returns_empty_on_invalid_yaml(self, tmp_path):
        readme = tmp_path / 'README.md'
        readme.write_text('---\n: bad: yaml: [\n---\n')
        result = ClaudeAdapter._parse_readme_frontmatter(readme)
        assert result == {}


class TestGetChain:

    def _make_adapter(self, session_name: str, tmp_path: Path,
                      sessions_dir: Path = None) -> ClaudeAdapter:
        """Build adapter with CONVERSATION_BASE and optionally SESSIONS_DIR mocked."""
        _write_session(tmp_path, session_name, [_user_msg('boot')])
        adapter = _adapter(f'session/{session_name}/chain', base=tmp_path)
        if sessions_dir is not None:
            adapter.__class__.SESSIONS_DIR = sessions_dir
        return adapter

    def test_chain_type_and_session(self, tmp_path):
        adapter = self._make_adapter('head-session', tmp_path)
        result = adapter._get_chain()
        assert result['type'] == 'claude_chain'
        assert result['session'] == 'head-session'

    def test_chain_length_one_with_no_readme(self, tmp_path):
        adapter = self._make_adapter('head-session', tmp_path)
        result = adapter._get_chain()
        assert result['chain_length'] == 1
        assert result['chain'][0]['session'] == 'head-session'
        assert result['chain'][0]['readme'] is None

    def test_chain_traverses_continuing_from(self, tmp_path):
        sessions_dir = tmp_path / 'sessions'
        _write_readme(sessions_dir, 'session-c', {'badge': 'C', 'continuing_from': 'session-b'})
        _write_readme(sessions_dir, 'session-b', {'badge': 'B', 'continuing_from': 'session-a'})
        _write_readme(sessions_dir, 'session-a', {'badge': 'A'})

        _write_session(tmp_path, 'session-c', [_user_msg('boot')])
        adapter = _adapter('session/session-c/chain', base=tmp_path)
        adapter.__class__.SESSIONS_DIR = sessions_dir
        result = adapter._get_chain()

        assert result['chain_length'] == 3
        assert [e['session'] for e in result['chain']] == ['session-c', 'session-b', 'session-a']
        assert result['chain'][0]['badge'] == 'C'
        assert result['chain'][2]['badge'] == 'A'
        assert result['chain'][2]['continuing_from'] is None

    def test_chain_stops_on_cycle(self, tmp_path):
        sessions_dir = tmp_path / 'sessions'
        _write_readme(sessions_dir, 'session-a', {'continuing_from': 'session-b'})
        _write_readme(sessions_dir, 'session-b', {'continuing_from': 'session-a'})

        _write_session(tmp_path, 'session-a', [_user_msg('boot')])
        adapter = _adapter('session/session-a/chain', base=tmp_path)
        adapter.__class__.SESSIONS_DIR = sessions_dir
        result = adapter._get_chain()

        assert result['chain_length'] == 2
        assert [e['session'] for e in result['chain']] == ['session-a', 'session-b']

    def test_chain_includes_test_counts_and_commits(self, tmp_path):
        sessions_dir = tmp_path / 'sessions'
        _write_readme(sessions_dir, 'head-session', {
            'badge': 'test',
            'tests_start': 6000,
            'tests_end': 6125,
            'commits': 14,
        })
        _write_session(tmp_path, 'head-session', [_user_msg('boot')])
        adapter = _adapter('session/head-session/chain', base=tmp_path)
        adapter.__class__.SESSIONS_DIR = sessions_dir
        result = adapter._get_chain()

        entry = result['chain'][0]
        assert entry['tests_start'] == 6000
        assert entry['tests_end'] == 6125
        assert entry['commits'] == 14

    def test_chain_sessions_dir_none_shown_in_result(self, tmp_path):
        _write_session(tmp_path, 'my-session', [_user_msg('boot')])
        adapter = _adapter('session/my-session/chain', base=tmp_path)
        adapter.__class__.SESSIONS_DIR = None
        result = adapter._get_chain()
        assert result['sessions_dir'] is None


# ─── BACK-074: _post_process_search_results ────────────────────────────────────

class TestPostProcessSearchResults:

    def _args(self, **kwargs) -> Namespace:
        defaults = dict(head=None, tail=None, range=None, verbose=False,
                        max_snippet_chars=None, all=False)
        defaults.update(kwargs)
        return Namespace(**defaults)

    def _result(self, n: int) -> dict:
        return {
            'type': 'claude_cross_session_search',
            'term': 'foo',
            'matches': [{'session': f'sess-{i}'} for i in range(n)],
            'match_count': n,
        }

    def test_default_limits_to_20(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process(self._result(50), self._args())
        assert len(result['matches']) == 20
        assert result['displayed_count'] == 20

    def test_all_flag_skips_limit(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process(self._result(50), self._args(**{'all': True}))
        assert len(result['matches']) == 50

    def test_head_overrides_default(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process(self._result(50), self._args(head=5))
        assert len(result['matches']) == 5
        assert result['displayed_count'] == 5

    def test_fewer_than_20_returns_all(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process(self._result(8), self._args())
        assert len(result['matches']) == 8

    def test_empty_matches_returns_zero(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process(self._result(0), self._args())
        assert result['displayed_count'] == 0

    def test_post_process_attaches_display_block(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process(self._result(5), self._args())
        assert '_display' in result

    def test_missing_matches_key_no_crash(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
        result = adapter.post_process(
            {'type': 'claude_cross_session_search', 'term': 'x'},
            self._args()
        )
        # No 'matches' key — should not raise
        assert result['type'] == 'claude_cross_session_search'


# ─── BACK-074: schema includes cross-session search ────────────────────────────

class TestSchemaIncludesCrossSessionSearch:

    def test_output_types_include_cross_session_search(self):
        schema = ClaudeAdapter.get_schema()
        types = [t['type'] for t in schema['output_types']]
        assert 'claude_cross_session_search' in types

    def test_example_queries_include_sessions_search(self):
        schema = ClaudeAdapter.get_schema()
        uris = [e['uri'] for e in schema['example_queries']]
        assert any('sessions' in u and 'search' in u for u in uris)

    def test_notes_mention_cross_session_search(self):
        schema = ClaudeAdapter.get_schema()
        notes_text = ' '.join(schema['notes'])
        assert 'cross-session' in notes_text.lower() or 'sessions' in notes_text.lower()

    def test_cross_session_schema_has_match_count_field(self):
        schema = ClaudeAdapter.get_schema()
        cs_type = next(t for t in schema['output_types'] if t['type'] == 'claude_cross_session_search')
        props = cs_type['schema']['properties']
        assert 'match_count' in props
        assert 'matches' in props

    def test_help_examples_include_cross_session_search(self):
        help_data = ClaudeAdapter.get_help()
        example_uris = [e.get('uri', '') for e in help_data.get('examples', [])]
        assert any('sessions' in u and 'search' in u for u in example_uris)


# ─── get_message_range ────────────────────────────────────────────────────────

class TestGetMessageRange:
    """Tests for analysis/messages.py:get_message_range()."""

    def _make_messages(self):
        return [
            {'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'hello'}]},
             'timestamp': '2026-01-01T10:00:00.000Z'},
            {'type': 'assistant', 'message': {'content': [{'type': 'text', 'text': 'hi there'}]},
             'timestamp': '2026-01-01T10:01:00.000Z'},
            {'type': 'file-history-snapshot', 'message': {}},  # metadata — should be excluded
            {'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'follow up'}]},
             'timestamp': '2026-01-01T10:02:00.000Z'},
        ]

    def test_returns_correct_type(self):
        from reveal.adapters.claude.analysis.messages import get_message_range
        result = get_message_range(self._make_messages(), 'my-session', {})
        assert result['type'] == 'claude_message_range'

    def test_filters_out_metadata_records(self):
        from reveal.adapters.claude.analysis.messages import get_message_range
        result = get_message_range(self._make_messages(), 'my-session', {})
        roles = [m['role'] for m in result['messages']]
        assert roles == ['user', 'assistant', 'user']

    def test_turn_numbering_is_1indexed(self):
        from reveal.adapters.claude.analysis.messages import get_message_range
        result = get_message_range(self._make_messages(), 'my-session', {})
        turns = [m['turn'] for m in result['messages']]
        assert turns == [1, 2, 3]

    def test_message_index_is_raw_position(self):
        from reveal.adapters.claude.analysis.messages import get_message_range
        result = get_message_range(self._make_messages(), 'my-session', {})
        # file-history-snapshot is at raw index 2, so user at index 3 is turn 3
        assert result['messages'][2]['message_index'] == 3

    def test_total_messages_excludes_metadata(self):
        from reveal.adapters.claude.analysis.messages import get_message_range
        result = get_message_range(self._make_messages(), 'my-session', {})
        assert result['total_messages'] == 3

    def test_empty_messages_returns_empty_list(self):
        from reveal.adapters.claude.analysis.messages import get_message_range
        result = get_message_range([], 'empty-session', {})
        assert result['messages'] == []
        assert result['total_messages'] == 0

    def test_session_name_stored(self):
        from reveal.adapters.claude.analysis.messages import get_message_range
        result = get_message_range([], 'test-session-xyz', {})
        assert result['session'] == 'test-session-xyz'


# ─── _post_process_message_range ──────────────────────────────────────────────

class TestPostProcessMessageRange:
    """Tests for ClaudeAdapter._post_process_message_range()."""

    def _args(self, **kwargs):
        defaults = dict(head=None, tail=None, range=None)
        defaults.update(kwargs)
        return Namespace(**defaults)

    def _result(self, n=5):
        return {
            'type': 'claude_message_range',
            'messages': [{'turn': i + 1, 'role': 'user'} for i in range(n)],
            'total_messages': n,
        }

    def test_no_slice_returns_all(self):
        result = self._result(4)
        ClaudeAdapter._post_process_message_range(result, self._args())
        assert len(result['messages']) == 4
        assert result['displayed'] == 4

    def test_range_slices_messages(self):
        result = self._result(10)
        ClaudeAdapter._post_process_message_range(result, self._args(range=(2, 4)))
        assert len(result['messages']) == 3
        assert result['messages'][0]['turn'] == 2
        assert result['messages'][-1]['turn'] == 4

    def test_open_ended_range_returns_to_end(self):
        result = self._result(10)
        ClaudeAdapter._post_process_message_range(result, self._args(range=(8, None)))
        assert len(result['messages']) == 3  # turns 8, 9, 10
        assert result['messages'][0]['turn'] == 8

    def test_filtered_from_set_when_sliced(self):
        result = self._result(10)
        ClaudeAdapter._post_process_message_range(result, self._args(head=3))
        assert result['filtered_from'] == 10
        assert result['displayed'] == 3

    def test_none_messages_returns_early(self):
        result = {'type': 'claude_message_range', 'messages': None}
        ClaudeAdapter._post_process_message_range(result, self._args())
        assert result['messages'] is None  # unchanged


# ─── S3.3: Schema parameter parity ───────────────────────────────────────────

class TestClaudeSchemaParamParity:
    """S3.3: _SCHEMA_QUERY_PARAMS must document every param used by handlers."""

    HANDLER_PARAMS = {'summary', 'errors', 'tools', 'contains', 'role',
                      'search', 'since', 'word', 'filter', 'project', 'key',
                      'tail', 'last', 'tokens'}

    def _schema_params(self):
        from reveal.adapters.claude.adapter import _SCHEMA_QUERY_PARAMS
        return set(_SCHEMA_QUERY_PARAMS.keys())

    def test_all_handler_params_in_schema(self):
        missing = self.HANDLER_PARAMS - self._schema_params()
        assert missing == set(), f"Handler params missing from schema: {missing}"

    def test_since_documented(self):
        from reveal.adapters.claude.adapter import _SCHEMA_QUERY_PARAMS
        assert 'since' in _SCHEMA_QUERY_PARAMS
        assert 'today' in _SCHEMA_QUERY_PARAMS['since']['examples'][0] or \
               any('today' in ex for ex in _SCHEMA_QUERY_PARAMS['since']['examples'])

    def test_word_documented(self):
        from reveal.adapters.claude.adapter import _SCHEMA_QUERY_PARAMS
        assert 'word' in _SCHEMA_QUERY_PARAMS
        assert _SCHEMA_QUERY_PARAMS['word']['type'] == 'flag'

    def test_filter_documented(self):
        from reveal.adapters.claude.adapter import _SCHEMA_QUERY_PARAMS
        assert 'filter' in _SCHEMA_QUERY_PARAMS

    def test_project_documented(self):
        from reveal.adapters.claude.adapter import _SCHEMA_QUERY_PARAMS
        assert 'project' in _SCHEMA_QUERY_PARAMS

    def test_key_documented(self):
        from reveal.adapters.claude.adapter import _SCHEMA_QUERY_PARAMS
        assert 'key' in _SCHEMA_QUERY_PARAMS

    def test_cli_flags_include_all_and_base_path(self):
        from reveal.adapters.claude.adapter import _SCHEMA_CLI_FLAGS
        assert '--all' in _SCHEMA_CLI_FLAGS
        assert '--base-path' in _SCHEMA_CLI_FLAGS

    def test_schema_cli_flags_wired_into_get_schema(self):
        schema = ClaudeAdapter.get_schema()
        assert '--all' in schema['cli_flags']
        assert '--base-path' in schema['cli_flags']


# ─── BACK-341: session title — harness XML tag skip ─────────────────────────

class TestParseJsonlLineForTitleXmlSkip:

    def _line(self, text: str) -> str:
        return json.dumps({'type': 'user', 'message': {'content': text}})

    def test_skips_local_command_caveat(self):
        caveat = '<local-command-caveat>Caveat: DO NOT respond to these messages.</local-command-caveat>'
        assert ClaudeAdapter._parse_jsonl_line_for_title(self._line(caveat)) is None

    def test_skips_command_name_tag(self):
        assert ClaudeAdapter._parse_jsonl_line_for_title(self._line('<command-name>/clear</command-name>')) is None

    def test_skips_bash_input_tag(self):
        assert ClaudeAdapter._parse_jsonl_line_for_title(self._line('<bash-input>ls -la</bash-input>')) is None

    def test_skips_bash_stdout_tag(self):
        assert ClaudeAdapter._parse_jsonl_line_for_title(self._line('<bash-stdout>output here</bash-stdout>')) is None

    def test_preserves_less_than_in_sentence(self):
        # '<' mid-sentence is not a tag — should not be skipped
        result = ClaudeAdapter._parse_jsonl_line_for_title(self._line('Is x < y the right syntax?'))
        assert result == 'Is x < y the right syntax?'

    def test_scan_skips_xml_and_finds_real_prompt(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _scan_jsonl_for_title
        p = tmp_path / 'sess.jsonl'
        p.write_text('\n'.join(json.dumps(m) for m in [
            _user_msg('<local-command-caveat>DO NOT respond.</local-command-caveat>'),
            _user_msg('<command-name>/clear</command-name>'),
            _user_msg('how can we improve the login flow'),
        ]) + '\n')
        assert _scan_jsonl_for_title(p) == 'how can we improve the login flow'


# ─── BACK-341: session title — min-length skip ───────────────────────────────

class TestParseJsonlLineForTitleMinLength:

    def _line(self, text: str) -> str:
        return json.dumps({'type': 'user', 'message': {'content': text}})

    def test_skips_single_short_word(self):
        # "aye" is Zack's common boot confirmation — should not become a title
        assert ClaudeAdapter._parse_jsonl_line_for_title(self._line('aye')) is None

    def test_skips_four_char_word(self):
        assert ClaudeAdapter._parse_jsonl_line_for_title(self._line('okay')) is None

    def test_accepts_five_char_candidate(self):
        result = ClaudeAdapter._parse_jsonl_line_for_title(self._line('hello'))
        assert result == 'hello'

    def test_accepts_normal_prompt(self):
        result = ClaudeAdapter._parse_jsonl_line_for_title(self._line('run a review on the week'))
        assert result == 'run a review on the week'

    def test_boot_dot_still_accepted(self):
        # 'boot.' is 5 chars and is not the reserved 'boot' skip
        result = ClaudeAdapter._parse_jsonl_line_for_title(self._line('boot.'))
        assert result == 'boot.'


# ─── BACK-341: session title — badge extraction in listing ───────────────────

class TestScanJsonlForTitleBadge:

    def _write_jsonl(self, tmp_path: Path, messages: list) -> Path:
        p = tmp_path / 'session.jsonl'
        p.write_text('\n'.join(json.dumps(m) for m in messages) + '\n')
        return p

    def _badge_msg(self, badge_text: str) -> dict:
        return {
            'type': 'assistant',
            'message': {'content': [
                {'type': 'tool_use', 'name': 'Bash',
                 'input': {'command': f'tia session badge "{badge_text}"'}}
            ]},
        }

    def test_badge_wins_over_user_text(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _scan_jsonl_for_title
        p = self._write_jsonl(tmp_path, [
            _user_msg('aye'),
            self._badge_msg('reveal — fix title extraction'),
        ])
        assert _scan_jsonl_for_title(p) == 'reveal — fix title extraction'

    def test_falls_back_to_user_text_when_no_badge(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _scan_jsonl_for_title
        p = self._write_jsonl(tmp_path, [
            _user_msg('aye'),
            _user_msg('run a review on the week'),
        ])
        # "aye" is skipped (<5 chars); falls back to the next prompt
        assert _scan_jsonl_for_title(p) == 'run a review on the week'

    def test_badge_with_spaces_in_command(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _scan_jsonl_for_title
        p = self._write_jsonl(tmp_path, [
            {'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'name': 'Bash',
                 'input': {'command': 'some prefix\ntia session badge "peyton — live soak"\nsome suffix'}}
            ]}},
        ])
        assert _scan_jsonl_for_title(p) == 'peyton — live soak'

    def test_non_bash_tool_use_ignored(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import _scan_jsonl_for_title
        p = self._write_jsonl(tmp_path, [
            {'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'name': 'Read',
                 'input': {'file_path': 'session badge "should not match"'}}
            ]}},
            _user_msg('real user prompt here'),
        ])
        assert _scan_jsonl_for_title(p) == 'real user prompt here'


# ─── BACK-340: /prompts resource ─────────────────────────────────────────────

class TestGetHumanPrompts:

    def _cb(self):
        return {'contract_version': '1.0', 'source': 'test', 'source_type': 'file'}

    def test_returns_correct_type(self):
        from reveal.adapters.claude.analysis.messages import get_human_prompts
        result = get_human_prompts([], 'sess', self._cb())
        assert result['type'] == 'claude_user_prompts'

    def test_excludes_pure_tool_result_messages(self):
        from reveal.adapters.claude.analysis.messages import get_human_prompts
        messages = [
            _tool_result_msg('tu_1', 'output'),
            _tool_result_msg('tu_2', 'output2'),
        ]
        result = get_human_prompts(messages, 'sess', self._cb())
        assert result['message_count'] == 0
        assert result['messages'] == []

    def test_includes_text_messages(self):
        from reveal.adapters.claude.analysis.messages import get_human_prompts
        messages = [_user_msg('hello'), _user_msg('fix the bug')]
        result = get_human_prompts(messages, 'sess', self._cb())
        assert result['message_count'] == 2

    def test_mixed_filters_correctly(self):
        from reveal.adapters.claude.analysis.messages import get_human_prompts
        messages = [
            _user_msg('first real prompt'),
            _tool_result_msg('tu_1'),
            _user_msg('second real prompt'),
            _tool_result_msg('tu_2'),
            _tool_result_msg('tu_3'),
        ]
        result = get_human_prompts(messages, 'sess', self._cb())
        assert result['message_count'] == 2
        texts = [b['text'] for m in result['messages'] for b in m['content'] if b.get('type') == 'text']
        assert texts == ['first real prompt', 'second real prompt']

    def test_preserves_message_index(self):
        from reveal.adapters.claude.analysis.messages import get_human_prompts
        messages = [
            _tool_result_msg('tu_1'),
            _user_msg('real prompt'),
        ]
        result = get_human_prompts(messages, 'sess', self._cb())
        assert result['messages'][0]['message_index'] == 1

    def test_excludes_assistant_messages(self):
        from reveal.adapters.claude.analysis.messages import get_human_prompts
        messages = [_assistant_msg('hi'), _user_msg('hello')]
        result = get_human_prompts(messages, 'sess', self._cb())
        assert result['message_count'] == 1

    def test_message_with_text_and_tool_result_blocks_is_included(self):
        # Edge case: a user message with both text and tool_result blocks should be included
        from reveal.adapters.claude.analysis.messages import get_human_prompts
        msg = {
            'type': 'user',
            'timestamp': '2026-01-01T00:00:00Z',
            'message': {'content': [
                {'type': 'text', 'text': 'also typed this'},
                {'type': 'tool_result', 'tool_use_id': 'x', 'content': 'result'},
            ]},
        }
        result = get_human_prompts([msg], 'sess', self._cb())
        assert result['message_count'] == 1


class TestPromptsRoute:

    def _make_adapter(self, tmp_path, messages, resource_suffix):
        jsonl = _write_session(tmp_path, 'test-sess', messages)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter(f'session/test-sess', query=None)
        adapter.conversation_path = jsonl
        adapter.messages = messages
        adapter.resource = f'session/test-sess/{resource_suffix}'
        return adapter

    def test_prompts_route_returns_human_prompts_type(self, tmp_path):
        msgs = [_user_msg('real prompt'), _tool_result_msg('tu_1')]
        adapter = self._make_adapter(tmp_path, msgs, 'prompts')
        result = adapter._route_by_resource(msgs, '', adapter._get_contract_base())
        assert result is not None
        assert result.get('type') == 'claude_user_prompts'

    def test_prompts_excludes_tool_results(self, tmp_path):
        msgs = [_user_msg('real prompt'), _tool_result_msg('tu_1'), _tool_result_msg('tu_2')]
        adapter = self._make_adapter(tmp_path, msgs, 'prompts')
        result = adapter._route_by_resource(msgs, '', adapter._get_contract_base())
        assert result['message_count'] == 1

    def test_user_route_still_includes_tool_results(self, tmp_path):
        # Existing /user behaviour must not change
        msgs = [_user_msg('real prompt'), _tool_result_msg('tu_1')]
        adapter = self._make_adapter(tmp_path, msgs, 'user')
        result = adapter._route_by_resource(msgs, '', adapter._get_contract_base())
        assert result['message_count'] == 2


# ─── BACK-342: ?snippet=N for cross-session search ───────────────────────────

class TestSnippetWindowParam:

    def test_default_window_is_120(self, tmp_path):
        from reveal.adapters.claude.analysis.search import _extract_first_snippet
        long_text = 'x' * 50 + 'TARGET' + 'y' * 200
        p = tmp_path / 'sess.jsonl'
        p.write_text(json.dumps({
            'type': 'user',
            'message': {'content': long_text},
        }) + '\n')
        result = _extract_first_snippet(p, 'TARGET')
        assert len(result['excerpt']) < 150  # ~120 chars of context

    def test_larger_window_returns_more_context(self, tmp_path):
        from reveal.adapters.claude.analysis.search import _extract_first_snippet
        long_text = 'x' * 100 + 'TARGET' + 'y' * 300
        p = tmp_path / 'sess.jsonl'
        p.write_text(json.dumps({
            'type': 'user',
            'message': {'content': long_text},
        }) + '\n')
        default = _extract_first_snippet(p, 'TARGET', window_chars=120)
        wider = _extract_first_snippet(p, 'TARGET', window_chars=300)
        assert len(wider['excerpt']) > len(default['excerpt'])

    def test_snippet_param_threads_through_search_sessions(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import search_sessions
        long_text = 'a' * 100 + 'FINDME' + 'b' * 300
        proj = tmp_path / 'proj'
        proj.mkdir()
        jsonl = proj / 'sess.jsonl'
        jsonl.write_text(json.dumps({
            'type': 'user',
            'timestamp': '2026-06-01T00:00:00',
            'message': {'content': long_text},
        }) + '\n')
        default_result = search_sessions(tmp_path, {'search': 'FINDME'})
        wide_result = search_sessions(tmp_path, {'search': 'FINDME', 'snippet': '300'})
        default_excerpt = default_result['matches'][0]['excerpt']
        wide_excerpt = wide_result['matches'][0]['excerpt']
        assert len(wide_excerpt) > len(default_excerpt)

    def test_snippet_param_clamped_below_60(self, tmp_path):
        from reveal.adapters.claude.handlers.sessions import search_sessions
        long_text = 'a' * 100 + 'FINDME' + 'b' * 300
        proj = tmp_path / 'proj'
        proj.mkdir()
        jsonl = proj / 'sess.jsonl'
        jsonl.write_text(json.dumps({
            'type': 'user',
            'timestamp': '2026-06-01T00:00:00',
            'message': {'content': long_text},
        }) + '\n')
        # snippet=5 should clamp to 60
        result = search_sessions(tmp_path, {'search': 'FINDME', 'snippet': '5'})
        assert result['matches']  # no crash

    def test_snippet_documented_in_schema(self):
        from reveal.adapters.claude.adapter import _SCHEMA_QUERY_PARAMS
        assert 'snippet' in _SCHEMA_QUERY_PARAMS


class TestBack344TimelineRenderer:
    """BACK-344: /timeline had no renderer — always fell back to key/value dump."""

    def _make_timeline_result(self, events):
        return {
            'type': 'claude_timeline',
            'session': 'test-session-0101',
            'event_count': len(events),
            'timeline': events,
        }

    def test_timeline_renderer_dispatched(self, capsys):
        from reveal.adapters.claude.renderer import ClaudeRenderer
        result = self._make_timeline_result([
            {'index': 0, 'timestamp': '2026-01-01T10:00:00Z', 'event_type': 'tool_call', 'tool_name': 'Bash'},
        ])
        ClaudeRenderer._render_text(result)
        out = capsys.readouterr().out
        assert 'Timeline:' in out
        assert 'tool_call' not in out  # rendered as label, not raw type

    def test_tool_call_shows_tool_name(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_timeline
        result = self._make_timeline_result([
            {'index': 2, 'timestamp': '2026-01-01T09:15:00Z', 'event_type': 'tool_call', 'tool_name': 'Read'},
        ])
        _render_claude_timeline(result)
        out = capsys.readouterr().out
        assert 'Read' in out
        assert 'TOOL' in out

    def test_tool_result_shows_status(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_timeline
        result = self._make_timeline_result([
            {'index': 3, 'timestamp': '2026-01-01T09:15:01Z', 'event_type': 'tool_result',
             'tool_name': 'Read', 'is_error': False, 'content_preview': 'file contents here'},
        ])
        _render_claude_timeline(result)
        out = capsys.readouterr().out
        assert '[ok]' in out
        assert 'file contents here' in out

    def test_thinking_shows_tokens(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_timeline
        result = self._make_timeline_result([
            {'index': 1, 'timestamp': '2026-01-01T09:14:00Z', 'event_type': 'thinking', 'tokens_approx': 42},
        ])
        _render_claude_timeline(result)
        out = capsys.readouterr().out
        assert '42 tokens' in out
        assert 'THINK' in out

    def test_assistant_message_shows_preview(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_timeline
        result = self._make_timeline_result([
            {'index': 4, 'timestamp': '2026-01-01T09:16:00Z', 'event_type': 'assistant_message',
             'content_preview': 'Here is what I found'},
        ])
        _render_claude_timeline(result)
        out = capsys.readouterr().out
        assert 'Here is what I found' in out
        assert 'ASST' in out

    def test_empty_timeline(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_timeline
        result = self._make_timeline_result([])
        _render_claude_timeline(result)
        out = capsys.readouterr().out
        assert '0 events' in out

    def test_timeline_in_schema_elements(self):
        from reveal.adapters.claude.adapter import _SCHEMA_ELEMENTS
        assert 'timeline' in _SCHEMA_ELEMENTS

    def test_timeline_in_schema_example_queries(self):
        from reveal.adapters.claude.adapter import _SCHEMA_EXAMPLE_QUERIES
        uris = [q.get('uri', '') for q in _SCHEMA_EXAMPLE_QUERIES]
        assert any('/timeline' in u for u in uris)


class TestBack345ThinkingEmptyBlocks:
    """BACK-345: /thinking emitted 141 lines of empty encrypted blocks."""

    def _make_thinking_result(self, blocks):
        return {
            'type': 'claude_thinking',
            'session': 'test-session-0101',
            'thinking_block_count': len(blocks),
            'total_tokens_estimate': sum(b.get('char_count', 0) // 4 for b in blocks),
            'blocks': blocks,
        }

    def test_all_empty_emits_summary_line(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_thinking
        result = self._make_thinking_result([
            {'message_index': 1, 'timestamp': '2026-06-01T10:00:00Z', 'char_count': 0, 'content': ''},
            {'message_index': 3, 'timestamp': '2026-06-01T10:01:00Z', 'char_count': 0, 'content': ''},
        ])
        _render_claude_thinking(result)
        out = capsys.readouterr().out
        assert 'encrypted' in out
        assert '2 thinking blocks' in out
        # No per-block separator lines — should NOT have the separator dashes
        assert '─' * 60 not in out

    def test_all_empty_no_per_block_output(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_thinking
        result = self._make_thinking_result([
            {'message_index': 1, 'timestamp': '2026-06-01T10:00:00Z', 'char_count': 0, 'content': '  '},
        ])
        _render_claude_thinking(result)
        out = capsys.readouterr().out
        # The word 'Message' appears in per-block headers — should not be present for empty blocks
        assert 'Message 1' not in out

    def test_non_empty_blocks_render_normally(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_thinking
        result = self._make_thinking_result([
            {'message_index': 2, 'timestamp': '2026-01-01T09:00:00Z', 'char_count': 30, 'content': 'actual thinking here'},
        ])
        _render_claude_thinking(result)
        out = capsys.readouterr().out
        assert 'actual thinking here' in out
        assert '─' * 60 in out

    def test_mixed_empty_and_content_skips_empty(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_thinking
        result = self._make_thinking_result([
            {'message_index': 1, 'timestamp': '2026-01-01T09:00:00Z', 'char_count': 0, 'content': ''},
            {'message_index': 3, 'timestamp': '2026-01-01T09:05:00Z', 'char_count': 20, 'content': 'real content'},
        ])
        _render_claude_thinking(result)
        out = capsys.readouterr().out
        assert 'real content' in out
        # Should not show the summary line since not all-empty
        assert 'encrypted' not in out

    def test_no_blocks_does_not_crash(self, capsys):
        from reveal.adapters.claude.render_messages import _render_claude_thinking
        result = self._make_thinking_result([])
        _render_claude_thinking(result)
        capsys.readouterr()  # no crash


class TestBack346MessagesDiscoverable:
    """BACK-346: /messages missing from schema elements and help examples."""

    def test_messages_in_schema_elements(self):
        from reveal.adapters.claude.adapter import _SCHEMA_ELEMENTS
        assert 'messages' in _SCHEMA_ELEMENTS

    def test_prompts_in_schema_elements(self):
        from reveal.adapters.claude.adapter import _SCHEMA_ELEMENTS
        assert 'prompts' in _SCHEMA_ELEMENTS

    def test_messages_in_schema_example_queries(self):
        from reveal.adapters.claude.adapter import _SCHEMA_EXAMPLE_QUERIES
        uris = [q.get('uri', '') for q in _SCHEMA_EXAMPLE_QUERIES]
        assert any('/messages' in u for u in uris)

    def test_messages_in_help_examples(self):
        from reveal.adapters.claude.adapter import ClaudeAdapter
        examples = ClaudeAdapter._get_help_examples()
        uris = [e.get('uri', '') for e in examples]
        assert any('/messages' in u for u in uris)

    def test_messages_output_type_in_schema(self):
        from reveal.adapters.claude.adapter import _SCHEMA_OUTPUT_TYPES
        types = [ot.get('type') for ot in _SCHEMA_OUTPUT_TYPES]
        assert 'claude_messages' in types


# ─── BACK-353: ?summary=true / ?errors=true / ?timeline=true ─────────────────

class TestBack353ValueFormQueryParams:
    """BACK-353: bare-flag check only matched ?summary; value form ?summary=true fell through."""

    def _make_session(self, tmp_path, messages):
        jsonl = _write_session(tmp_path, 'test-session', messages)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('session/test-session')
        adapter.conversation_path = jsonl
        adapter.messages = messages
        return adapter

    def test_summary_bare_flag_still_works(self, tmp_path):
        adapter = self._make_session(tmp_path, [_user_msg('hi'), _assistant_msg('hello')])
        adapter.query = 'summary'
        adapter.query_params = {}
        result = adapter._route_by_query(adapter.messages, '', adapter._get_contract_base())
        assert result is not None
        assert result.get('type') == 'claude_analytics'

    def test_summary_value_form_routes_correctly(self, tmp_path):
        adapter = self._make_session(tmp_path, [_user_msg('hi'), _assistant_msg('hello')])
        adapter.query = 'summary=true'
        adapter.query_params = {'summary': 'true'}
        result = adapter._route_by_query(adapter.messages, '', adapter._get_contract_base())
        assert result is not None
        assert result.get('type') == 'claude_analytics'

    def test_summary_value_1_routes_correctly(self, tmp_path):
        adapter = self._make_session(tmp_path, [_user_msg('hi'), _assistant_msg('hello')])
        adapter.query = 'summary=1'
        adapter.query_params = {'summary': '1'}
        result = adapter._route_by_query(adapter.messages, '', adapter._get_contract_base())
        assert result is not None
        assert result.get('type') == 'claude_analytics'

    def test_errors_value_form_routes_correctly(self, tmp_path):
        msgs = [_tool_use_msg('Bash', tool_id='tu1', command='ls'),
                _tool_result_msg('tu1', 'error output', is_error=True)]
        adapter = self._make_session(tmp_path, msgs)
        adapter.query = 'errors=true'
        adapter.query_params = {'errors': 'true'}
        result = adapter._route_by_query(adapter.messages, '', adapter._get_contract_base())
        assert result is not None
        assert result.get('type') == 'claude_errors'

    def test_timeline_value_form_routes_correctly(self, tmp_path):
        msgs = [_user_msg('hi'), _assistant_msg('hello')]
        adapter = self._make_session(tmp_path, msgs)
        adapter.query = 'timeline=true'
        adapter.query_params = {'timeline': 'true'}
        result = adapter._route_by_query(adapter.messages, '', adapter._get_contract_base())
        assert result is not None
        assert result.get('type') == 'claude_timeline'

    def test_tokens_value_form_routes_correctly(self, tmp_path):
        msgs = [_user_msg('hi'), _assistant_msg('hello')]
        adapter = self._make_session(tmp_path, msgs)
        adapter.query = 'tokens=true'
        adapter.query_params = {'tokens': 'true'}
        result = adapter._route_by_query(adapter.messages, '', adapter._get_contract_base())
        assert result is not None
        assert result.get('type') == 'claude_token_breakdown'


# ─── BACK-350 + BACK-358: short UUID + shared identifier ─────────────────────

class TestBack350ShortUuidSubPath:
    """BACK-350: 'claude://c318161b/workflow' — truncated UUID + sub-path was broken.
    BACK-358: _parse_session_identifier is now the single source of truth for all shapes.
    """

    def test_parse_session_identifier_named_session(self):
        from reveal.adapters.claude.adapter import _parse_session_identifier
        name, sub = _parse_session_identifier('burning-antimatter-0501')
        assert name == 'burning-antimatter-0501'
        assert sub == ''

    def test_parse_session_identifier_named_session_with_subpath(self):
        from reveal.adapters.claude.adapter import _parse_session_identifier
        name, sub = _parse_session_identifier('burning-antimatter-0501/workflow')
        assert name == 'burning-antimatter-0501'
        assert sub == 'workflow'

    def test_parse_session_identifier_full_uuid(self):
        from reveal.adapters.claude.adapter import _parse_session_identifier
        uuid = '12345678-1234-5678-1234-567812345678'
        name, sub = _parse_session_identifier(uuid)
        assert name == uuid
        assert sub == ''

    def test_parse_session_identifier_full_uuid_with_subpath(self):
        from reveal.adapters.claude.adapter import _parse_session_identifier
        uuid = '12345678-1234-5678-1234-567812345678'
        name, sub = _parse_session_identifier(f'{uuid}/workflow')
        assert name == uuid
        assert sub == 'workflow'

    def test_parse_session_identifier_short_uuid(self):
        from reveal.adapters.claude.adapter import _parse_session_identifier
        name, sub = _parse_session_identifier('c318161b')
        assert name == 'c318161b'
        assert sub == ''

    def test_parse_session_identifier_short_uuid_with_subpath(self):
        from reveal.adapters.claude.adapter import _parse_session_identifier
        name, sub = _parse_session_identifier('c318161b/workflow')
        assert name == 'c318161b'
        assert sub == 'workflow'

    def test_parse_session_name_short_uuid_extracts_prefix(self):
        """_parse_session_name delegates to identifier and returns session name."""
        adapter = ClaudeAdapter.__new__(ClaudeAdapter)
        name = adapter._parse_session_name('c318161b/workflow')
        assert name == 'c318161b'

    def test_find_conversation_strategy4_short_uuid(self, tmp_path):
        """Strategy 4: startswith match for 8-char UUID prefix (BACK-350)."""
        full_uuid = 'c318161b-abcd-ef01-2345-678901234567'
        project_dir = tmp_path / 'some-project-dir'
        project_dir.mkdir()
        jsonl = project_dir / f'{full_uuid}.jsonl'
        jsonl.write_text(json.dumps(_user_msg('hi')) + '\n')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('c318161b/workflow')
        assert adapter.conversation_path == jsonl

    def test_find_conversation_strategy4_does_not_match_non_hex(self, tmp_path):
        """Strategy 4 must only trigger for 8 hex chars — not generic 8-char strings.

        'settings' is 8 chars but not hex — ensure the startswith strategy only fires
        when session_name matches _SHORT_UUID_RE.
        """
        project_dir = tmp_path / 'some-project-dir'
        project_dir.mkdir()
        # Filename starts with 'settings' but is not 'settings.jsonl' exactly (avoids S2)
        jsonl = project_dir / 'settings-full-uuid-extension.jsonl'
        jsonl.write_text(json.dumps(_user_msg('hi')) + '\n')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('settings')
        # 'settings' is not a short UUID hex — strategy 4 must not fire
        assert adapter.conversation_path is None

    def test_session_prefix_form_still_works(self):
        from reveal.adapters.claude.adapter import _parse_session_identifier
        name, sub = _parse_session_identifier('session/ancient-quasar-0501/message/3')
        assert name == 'ancient-quasar-0501'
        assert sub == 'message/3'
