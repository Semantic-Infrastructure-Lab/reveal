"""Direct Codex transcript outcomes use measured required sources, not empty success."""
import json

import pytest

from conftest import _run_reveal_in
from codex_session_fixture import DOC_SESSION_ID
from test_codex_declared_api_back2618 import codex

VIEWS = ['', '/messages', '/tools', '/errors', '/shell', '/workflow', '/timeline',
         '/digest', '/exchanges', '?last', '?tokens', '/message/0']


@pytest.mark.parametrize('suffix', VIEWS)
@pytest.mark.parametrize('state', ['healthy', 'empty', 'partial', 'failed'])
def test_transcript_views_share_source_outcome_policy(codex, suffix, state):
    path = next((codex / 'sessions').rglob('*.jsonl'))
    if state == 'empty':
        path.write_text('\n', encoding='utf-8')
    elif state == 'partial':
        path.write_bytes(path.read_bytes() + b'{broken\n')
    elif state == 'failed':
        path.write_text('{broken\n', encoding='utf-8')
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + suffix, '--format', 'json')
    expected = 3 if state in ('partial', 'failed') else (2 if state == 'empty' and suffix == '/message/0' else 0)
    assert result.returncode == expected, result.stderr
    answer = json.loads(result.stdout)
    assert answer['meta']['session_lookup']['selected_id'] == DOC_SESSION_ID
    assert answer['meta']['rollout_analysis']['failed_records'] == int(state in ('partial', 'failed'))


@pytest.mark.parametrize('problem,expected', [('missing_db', 2), ('corrupt_db', 3), ('missing_id', 2), ('missing_rollout', 3)])
def test_lookup_and_rollout_absence_have_qualified_causes(codex, problem, expected):
    identifier = DOC_SESSION_ID
    if problem == 'missing_db':
        (codex / 'state_5.sqlite').unlink()
    elif problem == 'corrupt_db':
        (codex / 'state_5.sqlite').write_bytes(b'broken')
    elif problem == 'missing_id':
        identifier = 'ffffffff-ffff-7fff-8fff-ffffffffffff'
    else:
        next((codex / 'sessions').rglob('*.jsonl')).unlink()
    result = _run_reveal_in(codex.parent, 'codex://' + identifier + '/messages', '--format', 'json')
    assert result.returncode == expected


def test_bad_index_rejects_before_index_read(codex, monkeypatch):
    from reveal.adapters.codex.lookup import SessionLookup
    def unexpected(self):
        pytest.fail('invalid index reached SQLite acquisition')
    monkeypatch.setattr(SessionLookup, 'find', unexpected)
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '/message/not-an-integer', '--format', 'json')
    assert result.returncode == 2


def test_budget_stage_cannot_erase_source_proof_with_inherited_postprocessor(codex, monkeypatch):
    from reveal.cli.routing import uri
    original = uri._apply_budget_constraints
    def corrupt(result, *args, **kwargs):
        result = original(result, *args, **kwargs)
        result['meta'].pop('rollout_analysis', None)
        return result
    monkeypatch.setattr(uri, '_apply_budget_constraints', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '/messages', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_declared_display_cut_is_complete_and_output_write_failure_is_not(codex, tmp_path):
    uri = 'codex://' + DOC_SESSION_ID + '/messages'
    complete = _run_reveal_in(codex.parent, uri, '--max-items', '1', '--format', 'json')
    assert complete.returncode == 0
    assert len(json.loads(complete.stdout)['messages']) == 1
    failed = _run_reveal_in(codex.parent, uri, '--output', 'json=' + str(tmp_path / 'absent' / 'answer.json'))
    assert failed.returncode == 3


@pytest.mark.parametrize('field', ['lookup', 'rollout', 'rows', 'counts', 'kind'])
def test_presentation_cannot_erase_or_invent_session_evidence(codex, monkeypatch, field):
    from reveal.adapters.codex.adapter import CodexAdapter
    def corrupt(self, result, args):
        if field == 'lookup':
            result['meta']['session_lookup']['queries'][0]['rows'] = 999
        elif field == 'rollout':
            result['meta']['rollout_analysis']['failures'].append({'phase': 'injected'})
        elif field == 'rows':
            result['messages'] = []
        elif field == 'counts':
            result['total_turns'] = 0
        else:
            result['type'] = 'codex_error'
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '/messages', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_token_grand_total_cannot_change_in_presentation(codex, monkeypatch):
    from reveal.adapters.codex.adapter import CodexAdapter
    def corrupt(self, result, args):
        result['grand_total'] = 0
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '?tokens', '--format', 'json')
    assert result.returncode == 3


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_partial_failed_and_repaired_transcripts_keep_source_policy(codex, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    path = next((codex / 'sessions').rglob('*.jsonl'))
    original = path.read_bytes()
    path.write_bytes(original + b'{broken\n')
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(codex))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(codex / 'state_5.sqlite'))
    async def scenario(session):
        request = {'uri': 'codex://' + DOC_SESSION_ID + '/messages', 'provenance': True}
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['messages'] and answer['meta']['rollout_analysis']['failed_records'] == 1
        path.write_bytes(b'{broken\n')
        assert (await session.call_tool('reveal_query', request)).is_error
        path.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['rollout_analysis']['failed_records'] == 0
    _run(codex.parent, scenario)
