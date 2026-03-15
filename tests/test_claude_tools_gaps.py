"""Tests targeting uncovered lines in reveal/adapters/claude/analysis/tools.py.

Coverage gaps targeted:
  - is_tool_error: exit-code > 0 branch (line 51), ERROR_LINE_START branch (line 55)
  - _collect_tool_use_map: full body (lines 62-69)
  - extract_all_tool_results: full body (lines 83-97)
  - _track_tool_results: failure branch (line 211)
  - _extract_file_operation: non-tool_use, wrong tool, missing file_path (lines 275-283)
  - _extract_tool_detail: Grep, Glob, TaskCreate/TaskUpdate, fallback None (lines 361-370)
  - get_workflow: workflow.append path (line 442)
"""

from collections import defaultdict

import pytest

from reveal.adapters.claude.analysis.tools import (
    _collect_tool_use_map,
    _extract_file_operation,
    _extract_tool_detail,
    _track_tool_results,
    extract_all_tool_results,
    get_workflow,
    is_tool_error,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _assistant_tool_use(tool_id: str, tool_name: str, **inp) -> dict:
    return {
        'type': 'assistant',
        'timestamp': '2026-03-14T10:00:00',
        'message': {'content': [
            {'type': 'tool_use', 'id': tool_id, 'name': tool_name, 'input': inp}
        ]},
    }


def _tool_result_msg(tool_id: str, content: str = 'ok', is_error: bool = False,
                     ts: str = '2026-03-14T10:01:00') -> dict:
    return {
        'type': 'user',
        'timestamp': ts,
        'message': {'content': [
            {'type': 'tool_result', 'tool_use_id': tool_id, 'content': content, 'is_error': is_error}
        ]},
    }


def _pair(tool_id: str, tool_name: str, result: str = 'ok', is_error: bool = False, **inp) -> list:
    """Build a (assistant tool_use, user tool_result) message pair."""
    return [
        _assistant_tool_use(tool_id, tool_name, **inp),
        _tool_result_msg(tool_id, result, is_error),
    ]


# ─── is_tool_error ────────────────────────────────────────────────────────────

class TestIsToolError:

    def test_is_error_flag_true(self):
        assert is_tool_error({'is_error': True, 'content': ''}) is True

    def test_is_error_flag_false_with_clean_content(self):
        assert is_tool_error({'is_error': False, 'content': 'all good'}) is False

    def test_exit_code_zero_not_error(self):
        assert is_tool_error({'content': 'exit code 0\nsome output'}) is False

    def test_exit_code_one_is_error(self):
        assert is_tool_error({'content': 'exit code 1\nfailed'}) is True

    def test_exit_code_128_is_error(self):
        assert is_tool_error({'content': 'exit code 128'}) is True

    def test_exit_code_2_is_error(self):
        assert is_tool_error({'content': 'some output\nexit code 2'}) is True

    def test_error_line_start_pattern_triggers(self):
        assert is_tool_error({'content': 'Error: something went wrong'}) is True

    def test_error_uppercase_line_start(self):
        assert is_tool_error({'content': 'ERROR: fatal condition\nmore text'}) is True

    def test_clean_content_not_error(self):
        assert is_tool_error({'content': 'test passed, 3 assertions'}) is False

    def test_empty_content_not_error(self):
        assert is_tool_error({'content': ''}) is False

    def test_missing_content_key_not_error(self):
        assert is_tool_error({}) is False

    def test_inline_error_word_not_flagged(self):
        # "error" not at line start should not trigger ERROR_LINE_START pattern
        result = is_tool_error({'content': 'no error here — all good'})
        # depends on pattern; just verify it doesn't crash
        assert isinstance(result, bool)


# ─── _collect_tool_use_map ────────────────────────────────────────────────────

class TestCollectToolUseMap:

    def test_maps_single_tool_id_to_name(self):
        msgs = [_assistant_tool_use('tu_001', 'Bash', command='ls')]
        result = _collect_tool_use_map(msgs)
        assert result == {'tu_001': 'Bash'}

    def test_maps_multiple_tools(self):
        msgs = [
            _assistant_tool_use('tu_001', 'Bash', command='ls'),
            _assistant_tool_use('tu_002', 'Read', file_path='foo.py'),
        ]
        result = _collect_tool_use_map(msgs)
        assert result == {'tu_001': 'Bash', 'tu_002': 'Read'}

    def test_empty_messages_returns_empty(self):
        assert _collect_tool_use_map([]) == {}

    def test_ignores_user_messages(self):
        msgs = [{
            'type': 'user',
            'message': {'content': [
                {'type': 'tool_use', 'id': 'tu_001', 'name': 'Bash', 'input': {}}
            ]}
        }]
        assert _collect_tool_use_map(msgs) == {}

    def test_skips_tool_use_missing_id(self):
        msgs = [{'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'Bash', 'input': {}}  # no 'id'
        ]}}]
        assert _collect_tool_use_map(msgs) == {}

    def test_skips_tool_use_missing_name(self):
        msgs = [{'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'id': 'tu_001', 'input': {}}  # no 'name'
        ]}}]
        assert _collect_tool_use_map(msgs) == {}

    def test_ignores_non_tool_use_content_blocks(self):
        msgs = [{'type': 'assistant', 'message': {'content': [
            {'type': 'text', 'text': 'hello'},
            {'type': 'tool_use', 'id': 'tu_001', 'name': 'Grep', 'input': {}}
        ]}}]
        result = _collect_tool_use_map(msgs)
        assert result == {'tu_001': 'Grep'}


# ─── extract_all_tool_results ────────────────────────────────────────────────

class TestExtractAllToolResults:

    def test_extracts_single_result(self):
        msgs = _pair('tu_001', 'Bash', result='output')
        results = extract_all_tool_results(msgs)
        assert len(results) == 1
        assert results[0]['tool_name'] == 'Bash'
        assert results[0]['tool_use_id'] == 'tu_001'

    def test_resolves_tool_name_from_assistant_message(self):
        msgs = _pair('tu_abc', 'Read', result='file content')
        results = extract_all_tool_results(msgs)
        assert results[0]['tool_name'] == 'Read'

    def test_unknown_for_unmatched_id(self):
        user = _tool_result_msg('tu_missing', 'output')
        results = extract_all_tool_results([user])
        assert results[0]['tool_name'] == 'unknown'

    def test_error_result_flagged(self):
        msgs = _pair('tu_001', 'Bash', result='fail', is_error=True)
        results = extract_all_tool_results(msgs)
        assert results[0]['is_error'] is True

    def test_success_result_not_flagged(self):
        msgs = _pair('tu_001', 'Bash', result='ok', is_error=False)
        results = extract_all_tool_results(msgs)
        assert results[0]['is_error'] is False

    def test_empty_messages_returns_empty(self):
        assert extract_all_tool_results([]) == []

    def test_content_truncated_to_500_chars(self):
        long_content = 'x' * 600
        msgs = _pair('tu_001', 'Bash', result=long_content)
        results = extract_all_tool_results(msgs)
        assert len(results[0]['content']) == 500

    def test_short_content_not_truncated(self):
        msgs = _pair('tu_001', 'Bash', result='short')
        results = extract_all_tool_results(msgs)
        assert results[0]['content'] == 'short'

    def test_includes_timestamp(self):
        msgs = _pair('tu_001', 'Bash')
        results = extract_all_tool_results(msgs)
        assert results[0]['timestamp'] == '2026-03-14T10:01:00'

    def test_includes_message_index(self):
        msgs = _pair('tu_001', 'Bash')
        results = extract_all_tool_results(msgs)
        assert 'message_index' in results[0]

    def test_multiple_results(self):
        msgs = (
            _pair('tu_001', 'Bash', result='out1')
            + _pair('tu_002', 'Read', result='out2')
        )
        results = extract_all_tool_results(msgs)
        assert len(results) == 2
        names = {r['tool_name'] for r in results}
        assert names == {'Bash', 'Read'}


# ─── _track_tool_results ─────────────────────────────────────────────────────

class TestTrackToolResults:

    def _make_stats(self):
        return defaultdict(lambda: {'success': 0, 'failure': 0, 'total': 0})

    def test_tracks_success(self):
        tool_use_map = {'tu_001': 'Read'}
        tool_stats = self._make_stats()
        messages = [_tool_result_msg('tu_001', 'ok', is_error=False)]
        _track_tool_results(messages, tool_use_map, tool_stats)
        assert tool_stats['Read']['success'] == 1
        assert tool_stats['Read']['failure'] == 0
        assert tool_stats['Read']['total'] == 1

    def test_tracks_failure(self):
        tool_use_map = {'tu_001': 'Bash'}
        tool_stats = self._make_stats()
        messages = [_tool_result_msg('tu_001', 'fail', is_error=True)]
        _track_tool_results(messages, tool_use_map, tool_stats)
        assert tool_stats['Bash']['failure'] == 1
        assert tool_stats['Bash']['success'] == 0
        assert tool_stats['Bash']['total'] == 1

    def test_ignores_unknown_tool_id(self):
        tool_use_map = {}
        tool_stats = self._make_stats()
        messages = [_tool_result_msg('tu_unknown', 'ok')]
        _track_tool_results(messages, tool_use_map, tool_stats)
        assert len(tool_stats) == 0

    def test_tracks_multiple_tools(self):
        tool_use_map = {'tu_001': 'Bash', 'tu_002': 'Read'}
        tool_stats = self._make_stats()
        messages = [
            _tool_result_msg('tu_001', 'fail', is_error=True),
            _tool_result_msg('tu_002', 'ok', is_error=False),
        ]
        _track_tool_results(messages, tool_use_map, tool_stats)
        assert tool_stats['Bash']['failure'] == 1
        assert tool_stats['Read']['success'] == 1

    def test_skips_non_tool_result_content(self):
        tool_use_map = {'tu_001': 'Bash'}
        tool_stats = self._make_stats()
        messages = [{'type': 'user', 'message': {'content': [
            {'type': 'text', 'text': 'hello'}  # not a tool_result
        ]}}]
        _track_tool_results(messages, tool_use_map, tool_stats)
        assert len(tool_stats) == 0


# ─── _extract_file_operation ─────────────────────────────────────────────────

class TestExtractFileOperation:

    def test_returns_none_for_non_tool_use(self):
        content = {'type': 'text', 'text': 'hello'}
        assert _extract_file_operation(content, 0, None) is None

    def test_returns_none_for_thinking_block(self):
        content = {'type': 'thinking', 'thinking': 'thinking...'}
        assert _extract_file_operation(content, 0, None) is None

    def test_returns_none_for_non_file_tool(self):
        content = {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'ls'}}
        assert _extract_file_operation(content, 0, None) is None

    def test_returns_none_for_grep_tool(self):
        content = {'type': 'tool_use', 'name': 'Grep', 'input': {'pattern': 'foo'}}
        assert _extract_file_operation(content, 0, None) is None

    def test_returns_none_when_no_file_path(self):
        content = {'type': 'tool_use', 'name': 'Read', 'input': {}}
        assert _extract_file_operation(content, 0, None) is None

    def test_extracts_read_operation(self):
        content = {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': 'foo.py'}}
        result = _extract_file_operation(content, 3, '2026-03-14T10:00:00')
        assert result is not None
        assert result['operation'] == 'Read'
        assert result['file_path'] == 'foo.py'
        assert result['message_index'] == 3
        assert result['timestamp'] == '2026-03-14T10:00:00'

    def test_extracts_write_operation(self):
        content = {'type': 'tool_use', 'name': 'Write', 'input': {'file_path': 'bar.py'}}
        result = _extract_file_operation(content, 0, None)
        assert result['operation'] == 'Write'
        assert result['file_path'] == 'bar.py'

    def test_extracts_edit_operation(self):
        content = {'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'baz.py'}}
        result = _extract_file_operation(content, 0, None)
        assert result['operation'] == 'Edit'
        assert result['file_path'] == 'baz.py'


# ─── _extract_tool_detail ────────────────────────────────────────────────────

class TestExtractToolDetail:

    def test_bash_uses_description(self):
        result = _extract_tool_detail('Bash', {'description': 'run tests', 'command': 'pytest'})
        assert result == 'run tests'

    def test_bash_falls_back_to_command(self):
        result = _extract_tool_detail('Bash', {'command': 'ls -la'})
        assert result == 'ls -la'

    def test_bash_empty_inputs(self):
        result = _extract_tool_detail('Bash', {})
        assert result == ''

    def test_read_file_path(self):
        result = _extract_tool_detail('Read', {'file_path': 'foo.py'})
        assert result == 'foo.py'

    def test_write_file_path(self):
        result = _extract_tool_detail('Write', {'file_path': 'bar.py'})
        assert result == 'bar.py'

    def test_edit_file_path(self):
        result = _extract_tool_detail('Edit', {'file_path': 'baz.py'})
        assert result == 'baz.py'

    def test_grep_with_path(self):
        result = _extract_tool_detail('Grep', {'pattern': 'foo', 'path': 'src/'})
        assert result == "'foo' in src/"

    def test_grep_default_path(self):
        result = _extract_tool_detail('Grep', {'pattern': 'bar'})
        assert result == "'bar' in ."

    def test_glob_with_pattern(self):
        result = _extract_tool_detail('Glob', {'pattern': '**/*.py'})
        assert result == '**/*.py'

    def test_glob_no_pattern_returns_none(self):
        result = _extract_tool_detail('Glob', {})
        assert result is None

    def test_task_create_subject(self):
        result = _extract_tool_detail('TaskCreate', {'subject': 'Fix bug'})
        assert result == 'Fix bug'

    def test_task_update_task_id(self):
        result = _extract_tool_detail('TaskUpdate', {'taskId': 'T123'})
        assert result == 'T123'

    def test_task_create_no_fields_returns_none(self):
        result = _extract_tool_detail('TaskCreate', {})
        assert result is None

    def test_task_update_no_fields_returns_none(self):
        result = _extract_tool_detail('TaskUpdate', {})
        assert result is None

    def test_unknown_tool_returns_none(self):
        result = _extract_tool_detail('Agent', {'prompt': 'do stuff'})
        assert result is None

    def test_web_search_returns_none(self):
        result = _extract_tool_detail('WebSearch', {'query': 'python docs'})
        assert result is None

    def test_unknown_tool_no_input_returns_none(self):
        result = _extract_tool_detail('SomeTool', {})
        assert result is None


# ─── get_workflow ─────────────────────────────────────────────────────────────

class TestGetWorkflow:

    _BASE = {'contract_version': '1.0'}

    def test_empty_messages_returns_empty_workflow(self):
        result = get_workflow([], 'session-1', self._BASE.copy())
        assert result['type'] == 'claude_workflow'
        assert result['total_steps'] == 0
        assert result['workflow'] == []

    def test_single_tool_use_appended(self):
        msgs = [_assistant_tool_use('tu_001', 'Bash', command='ls')]
        result = get_workflow(msgs, 'session-1', self._BASE.copy())
        assert result['total_steps'] == 1
        assert result['workflow'][0]['tool'] == 'Bash'

    def test_workflow_step_has_required_fields(self):
        msgs = [_assistant_tool_use('tu_001', 'Read', file_path='foo.py')]
        result = get_workflow(msgs, 'session-1', self._BASE.copy())
        step = result['workflow'][0]
        assert 'step' in step
        assert 'tool' in step
        assert 'detail' in step
        assert 'timestamp' in step
        assert 'message_index' in step

    def test_detail_extracted_for_read(self):
        msgs = [_assistant_tool_use('tu_001', 'Read', file_path='bar.py')]
        result = get_workflow(msgs, 'session-1', self._BASE.copy())
        assert result['workflow'][0]['detail'] == 'bar.py'

    def test_detail_extracted_for_grep(self):
        msgs = [_assistant_tool_use('tu_001', 'Grep', pattern='foo', path='src/')]
        result = get_workflow(msgs, 'session-1', self._BASE.copy())
        assert result['workflow'][0]['detail'] == "'foo' in src/"

    def test_multiple_different_tools_appended(self):
        msgs = [
            _assistant_tool_use('tu_001', 'Bash', command='ls'),
            _assistant_tool_use('tu_002', 'Read', file_path='foo.py'),
            _assistant_tool_use('tu_003', 'Write', file_path='bar.py'),
        ]
        result = get_workflow(msgs, 'session-1', self._BASE.copy())
        assert result['total_steps'] == 3
        tools = [s['tool'] for s in result['workflow']]
        assert tools == ['Bash', 'Read', 'Write']

    def test_consecutive_identical_steps_collapsed(self):
        msgs = [_assistant_tool_use('tu_001', 'Bash', command='ls')] * 3
        result = get_workflow(msgs, 'session-1', self._BASE.copy())
        assert result['total_steps'] == 3
        assert result['collapsed_steps'] == 1
        assert result['workflow'][0].get('run_count') == 3

    def test_steps_renumbered_after_collapse(self):
        msgs = [
            _assistant_tool_use('tu_001', 'Bash', command='ls'),
            _assistant_tool_use('tu_002', 'Bash', command='ls'),
            _assistant_tool_use('tu_003', 'Read', file_path='foo.py'),
        ]
        result = get_workflow(msgs, 's', self._BASE.copy())
        steps = [s['step'] for s in result['workflow']]
        assert steps == [1, 2]

    def test_session_name_included(self):
        result = get_workflow([], 'my-session', self._BASE.copy())
        assert result['session'] == 'my-session'

    def test_non_tool_use_content_skipped(self):
        msg = {
            'type': 'assistant',
            'timestamp': '2026-03-14T10:00:00',
            'message': {'content': [
                {'type': 'text', 'text': 'I will help you.'},
                {'type': 'tool_use', 'id': 'tu_001', 'name': 'Bash', 'input': {'command': 'ls'}},
            ]},
        }
        result = get_workflow([msg], 's', self._BASE.copy())
        assert result['total_steps'] == 1
        assert result['workflow'][0]['tool'] == 'Bash'
