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

    def test_returns_none_for_boot_command(self):
        line = self._line({'type': 'user', 'message': {'content': 'boot.'}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result is None

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

    def test_tia_system_instructions_boilerplate(self):
        text = '# TIA System Instructions\n\nsome preamble without separator'
        line = self._line({'type': 'user', 'message': {'content': text}})
        result = ClaudeAdapter._parse_jsonl_line_for_title(line)
        assert result is None

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
                        max_snippet_chars=None, type=None, search=None,
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
        defaults = dict(head=None, tail=None, range=None, type=None, search=None)
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
        ClaudeAdapter._post_process_workflow(result, self._args(search='config'))
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
        defaults = dict(head=None, tail=None, range=None, search=None, since=None, all=False)
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
        ClaudeAdapter._post_process_session_list(result, self._args(search='alpha', all=True))
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
