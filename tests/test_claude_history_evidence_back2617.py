"""Prompt history retains consumed record evidence before date/text/display scope."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.claude.adapter import ClaudeAdapter
from test_claude_source_evidence_back2617 import transcript


@pytest.fixture
def history(transcript, monkeypatch):
    home = transcript.parent.parent.parent
    monkeypatch.setattr(ClaudeAdapter, 'CLAUDE_HOME', home)
    return home / 'history.jsonl'


@pytest.mark.parametrize('suffix', ['', '?search=unfindable', '?since=2099-01-01'])
def test_history_record_loss_survives_filters(transcript, history, suffix):
    with history.open('a', encoding='utf-8') as handle:
        handle.write('broken\n')
    result = _run_reveal_in(transcript.parent, 'claude://history' + suffix, '--format', 'json')
    assert result.returncode == 3
    proof = json.loads(result.stdout)['meta']['history_analysis']
    assert proof['candidate_records'] == 3
    assert proof['analyzed_records'] == 2 and proof['failed_records'] == 1


def test_history_decode_repair_is_not_complete_input(transcript, history):
    history.write_bytes(b'{"display":"auth \xff","timestamp":0}\n')
    result = _run_reveal_in(transcript.parent, 'claude://history', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['match_count'] == 1
    assert answer['meta']['history_analysis']['recovered_records'] == 1


def test_history_payload_failure_retains_preceding_entries(transcript, history):
    with history.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'display': 'unrepresentable date', 'timestamp': 10 ** 100}) + '\n')
    result = _run_reveal_in(transcript.parent, 'claude://history', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['match_count'] == 2
    assert answer['meta']['history_analysis']['analyzed_entries'] == 2
    assert answer['meta']['history_analysis']['failed_entries'] == 1


def test_missing_history_and_empty_history_are_distinct(transcript, history):
    history.write_text('', encoding='utf-8')
    empty = _run_reveal_in(transcript.parent, 'claude://history', '--format', 'json')
    assert empty.returncode == 0
    history.unlink()
    missing = _run_reveal_in(transcript.parent, 'claude://history', '--format', 'json')
    assert missing.returncode == 2
    assert json.loads(missing.stdout)['meta']['errors'][0]['code'] == 'invalid_request'


def test_python_missing_history_keeps_its_error_dictionary(transcript, history):
    from reveal.api import query
    history.unlink()
    answer = query('claude://history')
    assert answer['error'] and answer['entries'] == []
    assert answer['meta']['history_analysis']['request_absent'] is True


@pytest.mark.parametrize('erase', ['proof', 'rows'])
def test_history_presentation_cannot_erase_required_evidence(transcript, history, monkeypatch, erase):
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('history_analysis')
        else:
            result['entries'] = []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, 'claude://history', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_history_display_cut_preserves_source_decisions(transcript, history):
    result = _run_reveal_in(transcript.parent, 'claude://history', '--head', '1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['match_count'] == 2 and len(answer['entries']) == 1
    assert answer['meta']['history_analysis']['analyzed_entries'] == 2
    assert any(w.get('field') == 'entries' and w.get('shown') == 1 and w.get('total') == 2
               for w in answer['meta']['warnings'])


def test_file_not_found_after_open_is_source_loss_not_a_missing_request(transcript, history, monkeypatch):
    import builtins
    from io import StringIO
    original = builtins.open
    class Interrupted(StringIO):
        def __next__(self):
            if self.tell():
                raise FileNotFoundError('injected read loss after the source opened')
            return super().__next__()
    def interrupted(path, *args, **kwargs):
        if str(path) == str(history):
            return Interrupted('{"display":"known prefix","timestamp":0}\n')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', interrupted)
    result = _run_reveal_in(transcript.parent, 'claude://history', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['entries'][0]['prompt'] == 'known prefix'
    proof = answer['meta']['history_analysis']
    assert proof['source_opened'] is True and proof['request_absent'] is False


def test_legacy_batch_keeps_its_authored_history_error(transcript, history):
    with history.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'display': 'bad timestamp', 'timestamp': 10 ** 100}) + '\n')
    result = _run_reveal_in(transcript.parent, '--stdin', '--batch', '--format', 'json',
                            stdin='claude://history\n')
    assert result.returncode == 2
    answer = json.loads(result.stdout)['results'][0]['data']
    assert answer['error'] and len(answer['entries']) == 2


def test_text_history_retains_the_known_prefix_after_timestamp_loss(transcript, history):
    with history.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps({'display': 'bad timestamp', 'timestamp': 10 ** 100}) + '\n')
    result = _run_reveal_in(transcript.parent, 'claude://history')
    assert result.returncode == 3
    assert 'review auth' in result.stdout and 'fix validate_token' in result.stdout


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_history_partial_failed_repaired_and_absent(transcript, history, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(history.parent))
    original = history.read_bytes()
    history.write_bytes(original + b'broken\n')
    async def scenario(session):
        request = {'uri': 'claude://history', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['meta']['history_analysis']['failed_records'] == 1
        history.write_text('broken\n', encoding='utf-8')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        history.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['history_analysis']['failed_records'] == 0
        history.unlink()
        missing = await session.call_tool('reveal_query', request)
        assert missing.is_error
        assert 'not found' in _text(missing) and 'Internal error' not in _text(missing)
    _run(transcript.parent, scenario)


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_partial_source_does_not_excuse_corrupted_presentation(transcript, history, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(history.parent))
    with history.open('a', encoding='utf-8') as handle:
        handle.write('broken\n')
    server = '''
from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal import mcp_server
def erase(self, result, args):
    if result.get('type') == 'claude_history':
        result['entries'] = []
    return result
ClaudeAdapter.post_process = erase
mcp_server.main()
'''
    async def scenario(session):
        answer = await session.call_tool('reveal_query', {'uri': 'claude://history', 'provenance': True})
        assert answer.is_error, _text(answer)
    _run(transcript.parent, scenario, code=server)
