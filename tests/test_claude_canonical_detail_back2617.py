"""Detail levels preserve existing readers and make requested display intent durable."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.api import query
from reveal.errors import RequestValidationError
from test_claude_source_evidence_back2617 import transcript
from test_claude_workspace_lists_back2617 import workspace_home


def test_summary_detail_uses_existing_analytics(transcript):
    assert query('claude://session/my-session', detail='summary') == query('claude://session/my-session', summary=True)
    answer = query('claude://session/my-session', view='overview', detail='summary')
    assert answer['type'] == 'claude_analytics'


@pytest.mark.parametrize('view', ['messages', 'message', 'exchanges', 'workflow'])
def test_full_detail_keeps_existing_body_and_marks_intent(transcript, view):
    answer = query('claude://session/my-session', view=view, detail='full')
    assert answer['full'] is True
    result = _run_reveal_in(transcript.parent, f'claude://session/my-session?view={view}&detail=full', '--format', 'json')
    assert result.returncode == 0
    assert json.loads(result.stdout)['full'] is True


@pytest.mark.parametrize('view,kind', [('messages', 'claude_assistant_messages'), ('prompts', 'claude_user_messages')])
def test_raw_detail_uses_existing_role_record_population(transcript, view, kind):
    canonical = query('claude://session/my-session', view=view, detail='raw')
    original = query('claude://session/my-session/' + view, raw=True, full=True)
    assert canonical['type'] == original['type'] == kind
    assert canonical['messages'] == original['messages']
    assert canonical['full'] is True


def test_full_tool_calls_and_indexed_message_use_existing_verbose_output(transcript):
    assert query('claude://session/my-session', tools='Bash', detail='full')['full'] is True
    assert query('claude://session/my-session/message/1', detail='full')['full'] is True


def test_normal_detail_does_not_claim_to_filter_source(transcript):
    canonical = query('claude://session/my-session', errors=True, contains='failed', detail='normal')
    original = query('claude://session/my-session', errors=True, contains='failed')
    assert canonical == original


@pytest.mark.parametrize('resource,level', [('info', 'summary'), ('settings', 'raw'),
                                         ('session/my-session', 'raw'), ('session/my-session/thinking', 'full'),
                                         ('session/my-session/tools', 'full'),
                                         ('session/my-session/messages', 'summary')])
def test_unsupported_detail_scope_rejects(transcript, resource, level):
    with pytest.raises(RequestValidationError, match='detail'):
        query('claude://' + resource, detail=level)


def test_detail_original_validation_and_none_override(transcript):
    assert query('claude://session/my-session?detail=summary', detail=None)['type'] == 'claude_session_overview'
    with pytest.raises(RequestValidationError):
        query('claude://session/my-session?detail=invented', detail='normal')


def test_presentation_cannot_drop_full_detail_intent(transcript, monkeypatch):
    def post_process(self, result, args):
        result.pop('full', None)
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://session/my-session?view=messages&detail=full', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('resource', ['?view=messages', '?view=workflow', '?tools=Bash', '/message/3', '?view=exchanges'])
def test_full_detail_expands_existing_text_output(transcript, resource):
    records = [json.loads(line) for line in transcript.read_text(encoding='utf-8').splitlines()]
    marker = 'END_FULL_DETAIL'
    long = 'x' * 1800 + marker
    records[3]['message']['content'][1]['input']['command'] = 'echo ' + long
    if resource == '/message/3':
        # This reader's existing verbose mode expands raw blocks when no narrative text exists.
        records[3]['message']['content'][0]['text'] = ''
    records[7]['message']['content'][0]['text'] = long
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf-8')
    uri = 'claude://session/my-session' + resource
    normal = _run_reveal_in(transcript.parent, uri)
    full = _run_reveal_in(transcript.parent, uri + ('&' if '?' in uri else '?') + 'detail=full')
    assert normal.returncode == full.returncode == 0
    assert marker not in normal.stdout
    assert marker in full.stdout


def test_raw_prompt_detail_exposes_existing_tool_result_body(transcript):
    rows = [json.loads(line) for line in transcript.read_text(encoding='utf-8').splitlines()]
    marker = 'END_RAW_TOOL_RESULT'
    rows[2]['message']['content'][0]['content'] = 'x' * 1800 + marker
    transcript.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    legacy = _run_reveal_in(transcript.parent, 'claude://session/my-session/prompts?raw')
    raw = _run_reveal_in(transcript.parent, 'claude://session/my-session?view=prompts&detail=raw')
    assert legacy.returncode == raw.returncode == 0
    assert marker not in legacy.stdout and marker in raw.stdout


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_detail_preserves_source_loss_and_full_intent(transcript, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    original = transcript.read_bytes()
    transcript.write_bytes(original + b'{"broken\n')
    async def scenario(session):
        request = {'uri': 'claude://session/my-session?view=messages&detail=raw', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['type'] == 'claude_assistant_messages' and answer['full'] is True
        assert answer['meta']['transcript_analysis']['failed_records'] == 1
        transcript.write_bytes(b'{"broken\n')
        assert (await session.call_tool('reveal_query', request)).is_error
        transcript.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['full'] is True
    _run(transcript.parent, scenario)
