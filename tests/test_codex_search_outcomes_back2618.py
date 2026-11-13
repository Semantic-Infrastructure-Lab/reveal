"""Content search cannot turn rollout loss into a clean negative result."""
import json
import sqlite3

import pytest

from conftest import _run_reveal_in
from codex_session_fixture import DOC_SESSION_ID
from reveal import query
from test_codex_declared_api_back2618 import codex


@pytest.mark.parametrize('state,exit_code', [('healthy', 0), ('empty', 0), ('partial', 3), ('failed', 3), ('missing', 3), ('repaired', 3)])
def test_search_retains_rollout_source_decisions(codex, state, exit_code):
    path = next((codex / 'sessions').rglob('*.jsonl'))
    if state == 'empty':
        path.write_bytes(b'\n')
    elif state == 'partial':
        path.write_bytes(path.read_bytes() + b'{broken\n[]\n')
    elif state == 'failed':
        path.write_bytes(b'{broken\n')
    elif state == 'missing':
        path.unlink()
    elif state == 'repaired':
        path.write_bytes(b'{"payload":{"type":"user_message","message":"authentication \xff"}}\n')
    result = _run_reveal_in(codex.parent, 'codex://sessions?search=authentication', '--format', 'json')
    assert result.returncode == exit_code
    answer = json.loads(result.stdout)
    proof = answer['meta']['content_analysis']
    assert proof['selected_sessions'] == 1 and len(proof['rollouts']) == 1
    assert proof['rollouts'][0]['session_id'] == DOC_SESSION_ID
    assert answer['total'] == int(state in ('healthy', 'partial', 'repaired'))
    assert proof['failed_sources'] == int(state in ('partial', 'failed', 'missing', 'repaired'))


def test_search_dates_select_corpus_before_rollout_reads(codex):
    next((codex / 'sessions').rglob('*.jsonl')).unlink()
    result = _run_reveal_in(codex.parent, 'codex://sessions?search=authentication&until=1900-01-01', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['meta']['session_catalog']['observed_rows'] == 1
    assert answer['meta']['content_analysis']['selected_sessions'] == 0
    assert answer['meta']['content_analysis']['rollouts'] == []


@pytest.mark.parametrize('state,exit_code', [('missing', 2), ('corrupt', 3)])
def test_search_required_index_outcomes(codex, state, exit_code):
    path = codex / 'state_5.sqlite'
    if state == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'broken')
    result = _run_reveal_in(codex.parent, 'codex://sessions?search=authentication', '--format', 'json')
    assert result.returncode == exit_code
    assert 'session_catalog' in json.loads(result.stdout)['meta']


@pytest.mark.parametrize('field', ['content', 'catalog', 'query', 'count', 'snippets', 'source'])
def test_search_source_and_match_receipts_survive_presentation(codex, monkeypatch, field):
    from reveal.adapters.codex.adapter import CodexAdapter
    def corrupt(self, result, args):
        if field in ('content', 'catalog'):
            result['meta'].pop('content_analysis' if field == 'content' else 'session_catalog', None)
        elif field == 'query':
            result['query'] = 'unapplied'
        elif field == 'count':
            result['sessions'][0]['match_count'] = 0
        elif field == 'snippets':
            result['sessions'][0]['matches'] = []
        else:
            result['source'] = 'unread database'
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://sessions?search=authentication', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_absent_rollout_path_is_failed_selection_not_a_skipped_session(codex):
    with sqlite3.connect(codex / 'state_5.sqlite') as conn:
        conn.execute('UPDATE threads SET rollout_path = ? WHERE id = ?', ('', DOC_SESSION_ID))
    answer = query('codex://sessions?search=authentication')
    proof = answer['meta']['content_analysis']
    assert proof['failed_sources'] == 1
    assert proof['rollouts'][0]['failures'][0]['phase'] == 'selection'


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_search_partial_failed_and_fresh_repair(codex, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    path = next((codex / 'sessions').rglob('*.jsonl'))
    original = path.read_bytes()
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(codex))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(codex / 'state_5.sqlite'))
    async def scenario(session):
        request = {'uri': 'codex://sessions?search=authentication', 'provenance': True}
        path.write_bytes(original + b'{broken\n')
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['total'] == 1 and answer['meta']['content_analysis']['failed_sources'] == 1
        path.write_bytes(b'{broken\n')
        assert (await session.call_tool('reveal_query', request)).is_error
        path.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['meta']['content_analysis']['failed_sources'] == 0
    _run(codex.parent, scenario)


def test_search_keeps_matches_from_interrupted_record_prefix(codex, monkeypatch):
    import reveal.adapters.codex.content as module
    path = next((codex / 'sessions').rglob('*.jsonl'))
    class Stream:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self):
            yield '{"payload":{"type":"user_message","message":"authentication prefix"}}\n'
            raise OSError('rollout read interrupted')
    monkeypatch.setattr(module, 'open', lambda *args, **kwargs: Stream(), raising=False)
    result = _run_reveal_in(codex.parent, 'codex://sessions?search=authentication', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['sessions'][0]['matches'][0]['snippet'] == 'authentication prefix'
    source = answer['meta']['content_analysis']['rollouts'][0]
    assert source['source'] == path.as_posix() and source['analyzed_records'] == 1
    assert source['decision'] == 'interrupted' and source['failures'][0]['phase'] == 'read'


def test_search_display_cut_and_output_failure_keep_execution_policy(codex, tmp_path):
    path = next((codex / 'sessions').rglob('*.jsonl'))
    with sqlite3.connect(codex / 'state_5.sqlite') as conn:
        conn.execute('INSERT INTO threads (id, rollout_path, created_at, updated_at) VALUES (?, ?, 1, 2)',
                     ('ffffffff-ffff-7fff-8fff-ffffffffffff', str(path)))
    uri = 'codex://sessions?search=authentication'
    result = _run_reveal_in(codex.parent, uri, '--max-items', '1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert len(answer['sessions']) == 1 and answer['total'] == 2
    assert answer['meta']['content_analysis']['selected_sessions'] == 2
    failed = _run_reveal_in(codex.parent, uri, '--output', 'json=' + str(tmp_path / 'absent' / 'search.json'))
    assert failed.returncode == 3


def test_repeated_search_refreshes_rollout_failure_and_recovery(codex):
    from reveal.adapters.codex.adapter import CodexAdapter
    path = next((codex / 'sessions').rglob('*.jsonl'))
    original = path.read_bytes()
    adapter = CodexAdapter('sessions', query='search=authentication')
    assert adapter.get_structure()['meta']['content_analysis']['failed_sources'] == 0
    path.write_bytes(b'{broken\n')
    assert adapter.get_structure()['meta']['content_analysis']['failed_sources'] == 1
    path.write_bytes(original)
    assert adapter.get_structure()['meta']['content_analysis']['failed_sources'] == 0
