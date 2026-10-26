"""BACK-2240: /timeline lists typed prompts stored as plain strings; /message/-1 hint names live views; schema lists /agents and /chain."""
import json

from claude_transcript_builder import (SESSION, assistant, install, prompt, record, run_json,
                                       run_text, tool_result, tool_use)
from conftest import _run_reveal_direct


def _session():
    return [
        record('summary', 0, {'content': []}),
        prompt(1, 'first typed prompt'),
        assistant(2, [{'type': 'text', 'text': 'Reading.'}, tool_use('t1', 'Read', file_path='/p/a.py')], 'm1'),
        tool_result(3, 't1', 'contents'),
        prompt(4, [{'type': 'text', 'text': 'second prompt as a block list'}]),
        assistant(5, [{'type': 'text', 'text': 'Done.'}], 'm2'),
        prompt(6, 'third typed prompt'),
        record('file-history-snapshot', 7, {}),
    ]


def test_timeline_includes_prompts_stored_as_plain_strings(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _session())
    events = run_json(f'claude://session/{SESSION}/timeline')['timeline']
    prompts = [e for e in events if e['event_type'] == 'user_message']
    assert [e['content_preview'] for e in prompts] == [
        'first typed prompt', 'second prompt as a block list', 'third typed prompt']
    # negative control: the other event kinds are exactly what they were
    kinds = [e['event_type'] for e in events]
    assert kinds.count('tool_call') == 1 and kinds.count('tool_result') == 1
    assert kinds.count('assistant_message') == 2


def test_timeline_agrees_with_prompts_view(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _session())
    timeline = run_json(f'claude://session/{SESSION}/timeline')['timeline']
    listed = run_json(f'claude://session/{SESSION}/prompts')
    assert sum(e['event_type'] == 'user_message' for e in timeline) == len(listed['messages'])


def test_last_record_hint_names_views_that_exist(monkeypatch, tmp_path):
    install(monkeypatch, tmp_path, _session())
    out = run_json(f'claude://session/{SESSION}/message/-1')
    assert out['message_type'] == 'file-history-snapshot'
    hint = out['hint']
    assert '/user' not in hint and '/assistant' not in hint and '/message/2' not in hint
    assert '/prompts' in hint and '/messages' in hint
    # negative control: a real message carries no hint
    assert 'hint' not in run_json(f'claude://session/{SESSION}/message/1')


def test_schema_lists_agents_and_chain_and_every_emitted_output_type():
    schema = json.loads(_run_reveal_direct('help://schemas/claude', '--format', 'json').stdout)
    elements = set(schema['elements']) if isinstance(schema['elements'], dict) else {e['name'] for e in schema['elements']}
    assert {'agents', 'chain'} <= elements
    types = {t['type'] for t in schema['output_types']}
    assert {'claude_session_agents', 'claude_filtered_results', 'claude_token_breakdown',
            'claude_message_range'} <= types
    assert 'claude_session_overview' in types and 'claude_timeline' in types  # control
