"""BACK-1566: current Codex rollouts (item_completed items) read as real turns.

Codex CLI from 2026-08-09 writes each turn as ``event_msg`` / ``item_completed``
with the kind in ``payload.item.type``; every reader keyed on the older
``user_message`` / ``agent_message`` / ``exec_command_end`` events, so every
current session read as 0 turns, 0 exchanges and 0 shell calls. The fixture is
the shape of a real 2026-09-30 rollout, content replaced. The legacy fixture in
test_codex_adapter.py stays the positive control for the old shape.
"""

import json
from pathlib import Path

import pytest

from test_codex_adapter import _SESSION_UUID, _make_adapter

pytestmark = pytest.mark.component


def _item(ts, item):
    return {'timestamp': ts, 'type': 'event_msg',
            'payload': {'type': 'item_completed', 'thread_id': _SESSION_UUID, 'turn_id': 't1', 'item': item}}


_LINES = [
    {'timestamp': '2026-09-30T20:08:04Z', 'type': 'session_meta', 'payload': {'id': _SESSION_UUID}},
    {'timestamp': '2026-09-30T20:08:04Z', 'type': 'event_msg', 'payload': {'type': 'task_started'}},
    # Injected context: a response_item user message that is not a prompt.
    {'timestamp': '2026-09-30T20:08:06Z', 'type': 'response_item',
     'payload': {'type': 'message', 'role': 'user',
                 'content': [{'type': 'input_text', 'text': '# AGENTS.md instructions'}]}},
    _item('2026-09-30T20:08:06Z', {'type': 'UserMessage', 'id': 'u1',
                                   'content': [{'type': 'text', 'text': 'Refactor the parser module.'}]}),
    _item('2026-09-30T20:08:08Z', {'type': 'AgentMessage', 'id': 'a1', 'phase': 'commentary',
                                   'content': [{'type': 'Text', 'text': "I'll read it first."}]}),
    {'timestamp': '2026-09-30T20:08:09Z', 'type': 'response_item',
     'payload': {'type': 'function_call', 'name': 'exec_command', 'arguments': '{"cmd":"ls"}',
                 'call_id': 'call-1'}},
    {'timestamp': '2026-09-30T20:08:10Z', 'type': 'response_item',
     'payload': {'type': 'function_call_output', 'call_id': 'call-1', 'output': 'parser.py\n'}},
    _item('2026-09-30T20:08:10Z', {'type': 'CommandExecution', 'id': 'call-1',
                                   'command': ['/bin/bash', '-lc', 'ls'], 'cwd': 'file:///proj',
                                   'aggregated_output': 'parser.py\n', 'exit_code': 0,
                                   'duration': {'secs': 0, 'nanos': 5_000_000}, 'status': 'completed'}),
    {'timestamp': '2026-09-30T20:08:11Z', 'type': 'response_item',
     'payload': {'type': 'custom_tool_call', 'name': 'exec', 'call_id': 'call-2',
                 'input': 'const r = await tools.exec_command({"cmd": "cat parser.py"})'}},
    {'timestamp': '2026-09-30T20:08:12Z', 'type': 'response_item',
     'payload': {'type': 'custom_tool_call_output', 'call_id': 'call-2',
                 'output': [{'type': 'input_text', 'text': 'Script completed'}]}},
    _item('2026-09-30T20:08:20Z', {'type': 'AgentMessage', 'id': 'a2', 'phase': 'final_answer',
                                   'content': [{'type': 'Text', 'text': 'Parser refactored.'}]}),
    {'timestamp': '2026-09-30T20:08:21Z', 'type': 'event_msg',
     'payload': {'type': 'task_complete', 'duration_ms': 15000}},
    _item('2026-09-30T20:09:00Z', {'type': 'UserMessage', 'id': 'u2',
                                   'content': [{'type': 'text', 'text': 'Now add tests.'}]}),
    _item('2026-09-30T20:09:30Z', {'type': 'AgentMessage', 'id': 'a3', 'phase': 'final_answer',
                                   'content': [{'type': 'Text', 'text': 'Tests added.'}]}),
    {'timestamp': '2026-09-30T20:09:31Z', 'type': 'event_msg',
     'payload': {'type': 'task_complete', 'duration_ms': 30000}},
]


def _adapter(tmp_path: Path, resource: str, query: str = ''):
    path = tmp_path / f'rollout-2026-09-30T20-08-04-{_SESSION_UUID}.jsonl'
    path.write_text('\n'.join(json.dumps(line) for line in _LINES) + '\n', encoding='utf-8')
    return _make_adapter(resource, tmp_path, path, query=query)


def test_overview_counts_item_completed_turns_tools_and_shell(tmp_path):
    result = _adapter(tmp_path, _SESSION_UUID).get_structure()
    assert result['user_turns'] == 2  # the injected response_item user message is not a prompt
    assert result['agent_turns'] == 3
    assert result['tool_calls'] == 2  # function_call + custom_tool_call
    assert result['shell_calls'] == 1
    assert result['duration_ms'] == 45000  # both tasks, not the last one


def test_exchanges_pair_each_prompt_with_its_final_answer(tmp_path):
    result = _adapter(tmp_path, f'{_SESSION_UUID}/exchanges').get_structure()
    assert [(e['prompt'], e['answer']) for e in result['exchanges']] == [
        ('Refactor the parser module.', 'Parser refactored.'),
        ('Now add tests.', 'Tests added.'),
    ]


def test_tools_pair_custom_tool_calls_by_call_id(tmp_path):
    result = _adapter(tmp_path, f'{_SESSION_UUID}/tools').get_structure()
    pairs = result['tools']
    outputs = {p['call']['call_id']: (p['output'] or {}).get('output') for p in pairs}
    assert outputs == {'call-1': 'parser.py\n', 'call-2': 'Script completed'}


def test_cross_session_search_finds_item_completed_text(tmp_path):
    result = _adapter(tmp_path, 'sessions', query='search=parser module').get_structure()
    assert result['total'] == 1
    assert result['sessions'][0]['matches'][0]['role'] == 'user'
