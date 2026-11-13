"""Content scans qualify records actually required for a session search decision."""
import json

import pytest

from conftest import _run_reveal_in
from reveal.api import query
from test_claude_source_evidence_back2617 import transcript


@pytest.mark.parametrize('uri', ['claude://sessions?search=auth',
                                'claude://files//home/user/proj/auth.py'])
def test_malformed_prefix_preserves_matches_with_content_loss(transcript, uri):
    transcript.write_bytes(b'broken\n' + transcript.read_bytes())
    answer = query(uri)
    assert answer['match_count'] > 0
    proof = answer['meta']['session_content']
    assert proof['candidate_sessions'] == proof['scanned_sessions'] == 3
    assert proof['degraded_sessions'] == 1
    assert any(s['failed_records'] == 1 for s in proof['sources'])
    result = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert result.returncode == 3


def test_search_does_not_claim_to_scan_after_decisive_match(transcript):
    with transcript.open('a', encoding='utf-8') as handle:
        handle.write('broken\n')
    result = _run_reveal_in(transcript.parent, 'claude://sessions?search=auth', '--format', 'json')
    assert result.returncode == 0
    proof = json.loads(result.stdout)['meta']['session_content']
    source = next(s for s in proof['sources'] if s['source'] == transcript.as_posix())
    assert source['decision'] == 'matched-prefix'
    assert source['candidate_records'] < 9 and source['failed_records'] == 0


@pytest.mark.parametrize('uri', ['claude://sessions?search=unfindable',
                                'claude://files//unfindable.py'])
def test_failed_content_cannot_look_like_healthy_absence(transcript, uri):
    transcript.write_text('broken\n', encoding='utf-8')
    result = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['session_content']['degraded_sessions'] == 1


def test_replaced_decode_in_search_prefix_is_disclosed(transcript):
    transcript.write_bytes(b'{"type":"user","message":{"content":"auth \xff"}}\n')
    result = _run_reveal_in(transcript.parent, 'claude://sessions?search=auth', '--format', 'json')
    assert result.returncode == 3
    proof = json.loads(result.stdout)['meta']['session_content']
    assert any(s['recovered_records'] == 1 for s in proof['sources'])


@pytest.mark.parametrize('uri,field', [('claude://sessions?search=auth', 'matches'),
                                     ('claude://files//home/user/proj/auth.py', 'sessions')])
@pytest.mark.parametrize('erase', ['proof', 'rows'])
def test_content_presentation_cannot_erase_acquisition(transcript, monkeypatch, uri, field, erase):
    from reveal.adapters.claude.adapter import ClaudeAdapter
    def post_process(self, result, args):
        if erase == 'proof':
            result['meta'].pop('session_content')
        else:
            result[field] = []
        return result
    monkeypatch.setattr(ClaudeAdapter, 'post_process', post_process)
    result = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_search_cut_keeps_source_and_match_counts(transcript):
    uri = 'claude://sessions?search=auth'
    result = _run_reveal_in(transcript.parent, uri, '--head', '1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert len(answer['matches']) == 1 and answer['match_count'] > 1
    assert answer['meta']['session_content']['scanned_sessions'] == 3


def test_missing_tracking_path_and_failed_output_are_distinct(transcript):
    result = _run_reveal_in(transcript.parent, 'claude://files', '--format', 'json')
    assert result.returncode == 2
    assert json.loads(result.stdout)['meta']['errors'][0]['code'] == 'invalid_request'
    failed = _run_reveal_in(transcript.parent, 'claude://files', '--format', 'json',
                            '--output', 'json=' + str(transcript.parent / 'absent' / 'answer.json'))
    assert failed.returncode == 3


def test_legacy_empty_search_requires_no_content_reads(transcript):
    result = _run_reveal_in(transcript.parent, 'claude://search', '--format', 'json')
    assert result.returncode == 0
    proof = json.loads(result.stdout)['meta']['session_content']
    assert proof['candidate_sessions'] == proof['scanned_sessions'] == 0


@pytest.mark.parametrize('uri', ['claude://sessions?search=auth',
                                'claude://files//home/user/proj/auth.py'])
def test_content_read_failure_is_measured_without_hiding_healthy_sessions(transcript, monkeypatch, uri):
    import builtins
    original = builtins.open
    def denied(path, *args, **kwargs):
        if str(path) == str(transcript):
            raise PermissionError('injected content read failure')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(builtins, 'open', denied)
    result = _run_reveal_in(transcript.parent, uri, '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['match_count'] > 0
    proof = answer['meta']['session_content']
    source = next(s for s in proof['sources'] if s['source'] == transcript.as_posix())
    assert source['decision'] == 'interrupted' and source['candidate_records'] == 0
    assert source['failures'] == [{'phase': 'read', 'cause': 'PermissionError',
                                   'message': 'injected content read failure'}]


@pytest.mark.mcp
@pytest.mark.component
@pytest.mark.parametrize('uri', ['claude://sessions?search=auth',
                                'claude://files//home/user/proj/auth.py'])
def test_sdk_content_partial_failed_and_repaired(transcript, monkeypatch, uri):
    from test_mcp_expected_errors_back1992 import _run, _text
    monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(transcript.parent.parent.parent))
    monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(transcript.parent.parent))
    originals = {path: path.read_bytes() for path in transcript.parent.glob('*.jsonl')}
    transcript.write_bytes(b'broken\n' + originals[transcript])
    async def scenario(session):
        request = {'uri': uri, 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['meta']['session_content']['degraded_sessions'] == 1
        for path in originals:
            path.write_text('broken\n', encoding='utf-8')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        for path, data in originals.items():
            path.write_bytes(data)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['session_content']['degraded_sessions'] == 0
    _run(transcript.parent, scenario)
