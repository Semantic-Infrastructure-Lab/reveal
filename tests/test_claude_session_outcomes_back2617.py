"""Direct transcript URI outcomes use measured source evidence, before display cuts."""
import json

import pytest

from conftest import _run_reveal_in
from test_claude_source_evidence_back2617 import transcript, deny_scan
from reveal.adapters.claude.adapter import ClaudeAdapter

VIEWS = [
    ('', 'claude_session_overview'), ('?summary', 'claude_analytics'),
    ('/messages', 'claude_messages'), ('/messages?raw', 'claude_assistant_messages'),
    ('/prompts', 'claude_user_prompts'), ('/prompts?raw', 'claude_user_messages'),
    ('/thinking', 'claude_thinking'), ('/tools', 'claude_tool_summary'),
    ('?tools=Bash', 'claude_tool_calls'), ('/files', 'claude_files'),
    ('/workflow', 'claude_workflow'), ('/agents', 'claude_session_agents'),
    ('/context', 'claude_context'), ('?tokens', 'claude_token_breakdown'),
    ('/timeline', 'claude_timeline'), ('?errors', 'claude_errors'),
    ('/digest', 'claude_digest'), ('/exchanges', 'claude_exchanges'),
    ('?search=auth', 'claude_search_results'),
    ('?tools=Bash&errors', 'claude_filtered_results'),
]


@pytest.mark.parametrize('suffix,kind', VIEWS)
def test_direct_transcript_view_identity_and_source_loss(transcript, suffix, kind):
    uri = 'claude://session/my-session' + suffix
    healthy = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert healthy.returncode == 0
    assert json.loads(healthy.stdout)['type'] == kind
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('broken\n')
    partial = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert partial.returncode == 3
    result = json.loads(partial.stdout)
    assert result['type'] == kind and result['meta']['transcript_analysis']['failed_records'] == 1
    assert any(w['code'] == 'analysis_incomplete' for w in result['meta']['warnings'])


def test_empty_source_request_and_output_failures_are_distinct(transcript):
    uri = 'claude://session/my-session'
    transcript.write_text('', encoding='utf-8')
    assert _run_reveal_in(transcript.parent, uri).returncode == 0
    missing = _run_reveal_in(transcript.parent, 'claude://session/missing-session', '--format', 'json')
    assert missing.returncode == 2
    assert json.loads(missing.stdout)['meta']['errors'][0]['code'] == 'invalid_request'
    failure = _run_reveal_in(transcript.parent, 'claude://session/missing-session', '--format', 'json',
                             '--output', 'json=' + str(transcript.parent / 'absent-dir' / 'answer.json'))
    assert failure.returncode == 3


def test_lookup_loss_preserves_partial_transcript_and_exits_incomplete(transcript, monkeypatch):
    blocked = transcript.parent.parent / 'blocked-project'
    blocked.mkdir()
    deny_scan(monkeypatch, blocked)
    result = _run_reveal_in(transcript.parent, 'claude://session/2627362f', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['message_count'] == 8


def test_postprocessing_cannot_erase_source_proof(transcript, monkeypatch):
    def erase(self, result, args):
        result['meta'].pop('transcript_analysis', None)
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', erase)
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('suffix,field', [('/messages', 'messages'), ('/workflow', 'workflow')])
def test_unreceipted_row_erasure_is_analysis_failure(transcript, monkeypatch, suffix, field):
    def erase(self, result, args):
        result[field] = []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', erase)
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session' + suffix, '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('suffix,field', [('/messages', 'messages'), ('/workflow', 'workflow')])
def test_display_cut_is_complete_with_a_source_receipt(transcript, suffix, field):
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session' + suffix, '--head', '1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert len(answer[field]) == 1
    assert answer['meta']['transcript_analysis']['analyzed_records'] == 8
    assert any(w.get('field') == field and w.get('shown') == 1 and w.get('total', 0) > 1
               for w in answer['meta']['warnings'])


def test_legacy_batches_keep_their_unqualified_boundary(transcript):
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('broken\n')
    partial = _run_reveal_in(transcript.parent, '--stdin', '--batch', '--format', 'json',
                             stdin='claude://session/my-session\n')
    assert partial.returncode == 0
    missing = _run_reveal_in(transcript.parent, '--stdin', '--batch', '--format', 'json',
                             stdin='claude://session/no-such-session\n')
    assert missing.returncode == 2  # batch aggregate error, preserving its legacy leaf classification
    assert json.loads(missing.stdout)['results'][0]['data']['meta']['errors'][0]['code'] == 'adapter_error'


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_partial_failed_and_fresh_followup(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(transcript.parent.parent.parent))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    original = transcript.read_bytes()
    transcript.write_bytes(original + b'broken\n')
    async def scenario(session):
        request = {'uri': 'claude://session/my-session', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['message_count'] == 8
        assert any(w.get('code') == 'analysis_incomplete' for w in answer['meta']['warnings'])
        transcript.write_text('broken\n', encoding='utf-8')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        transcript.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert not any(w.get('code') == 'analysis_incomplete' for w in json.loads(_text(healthy))['meta']['warnings'])
    _run(transcript.parent, scenario)


def test_overview_range_rejection_is_a_usage_error(transcript):
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session', '--range', '1-2', '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['meta']['errors'][0]['code'] == 'invalid_request'


def test_indexed_message_reads_use_qualified_request_policy(transcript):
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session/message/99999', '--format', 'json')
    assert result.returncode == 2


@pytest.mark.parametrize('timestamp,expected', [(b'2027-01-01T00:00:00Z', 0), (b'2027-01-\xffT00:00:00Z', 3)])
def test_timestamp_field_scope_controls_selection_completeness(transcript, timestamp, expected):
    named = transcript.parent.parent / 'project-my-session'
    named.mkdir()
    (named / 'good.jsonl').write_bytes(transcript.read_bytes())
    # Invalid bytes in unrelated text are recoverable for timestamp selection; the
    # selected transcript is still decoded strictly by the ordinary record reader.
    (named / 'bad.jsonl').write_bytes(b'{"timestamp":"' + timestamp + b'","message":{"content":"bad \xff"}}\n')
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session', '--format', 'json')
    assert result.returncode == expected
    assert json.loads(result.stdout)['message_count'] == 8


def test_selected_transcript_decode_failure_is_analysis_not_usage(transcript):
    from reveal.api import query
    transcript.write_bytes(b'\xff\n')
    with pytest.raises(UnicodeDecodeError):
        query('claude://session/my-session')
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['errors'][0]['code'] == 'adapter_error'
