"""Raw message indices and conversation-turn ranges keep distinct source-qualified views."""
import json

import pytest

from conftest import _run_reveal_in
from test_claude_source_evidence_back2617 import transcript


@pytest.mark.parametrize('suffix,kind', [('/message/0', 'claude_message'),
                                       ('/message/-1', 'claude_message'),
                                       ('/message', 'claude_message_range')])
def test_indexed_views_retain_source_loss(transcript, suffix, kind):
    uri = 'claude://session/my-session' + suffix
    healthy = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert healthy.returncode == 0
    assert json.loads(healthy.stdout)['type'] == kind
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('broken\n')
    partial = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert partial.returncode == 3
    assert json.loads(partial.stdout)['meta']['transcript_analysis']['failed_records'] == 1


@pytest.mark.parametrize('index', ['99999', '-99999', 'not-an-int'])
def test_invalid_raw_message_index_is_a_usage_error(transcript, index):
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/message/' + index,
                            '--format', 'json')
    assert result.returncode == 2
    answer = json.loads(result.stdout)
    assert answer['type'] == 'claude_message'
    assert answer['meta']['errors'][0]['code'] == 'invalid_request'


def test_conversation_range_cut_preserves_raw_indices_and_receipts(transcript):
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/message',
                            '--range', '2-3', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert [m['turn'] for m in answer['messages']] == [2, 3]
    assert [m['message_index'] for m in answer['messages']] == [1, 2]
    assert answer['total_messages'] > len(answer['messages'])
    assert any(w.get('field') == 'messages' and w.get('shown') == 2
               for w in answer['meta']['warnings'])


def test_lost_records_cannot_prove_that_a_requested_index_is_absent(transcript):
    transcript.write_text('broken\n', encoding='utf-8')
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/message/0', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['transcript_analysis']['failed_records'] == 1


@pytest.mark.parametrize('suffix,field', [('/message/0', 'message'), ('/message', 'messages')])
def test_indexed_presentation_cannot_erase_proof_or_observations(transcript, monkeypatch, suffix, field):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    def erase(self, result, args):
        result[field] = {} if field == 'message' else []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', erase)
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session' + suffix, '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.mcp
@pytest.mark.component
@pytest.mark.parametrize('suffix', ['/message/0', '/message'])
def test_sdk_indexed_partial_failed_and_fresh_followup(transcript, monkeypatch, suffix):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(transcript.parent.parent.parent))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    original = transcript.read_bytes()
    transcript.write_bytes(original + b'broken\n')
    async def scenario(session):
        request = {'uri': 'claude://session/my-session' + suffix, 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['meta']['transcript_analysis']['failed_records'] == 1
        transcript.write_text('broken\n', encoding='utf-8')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        transcript.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['transcript_analysis']['failed_records'] == 0
    _run(transcript.parent, scenario)
