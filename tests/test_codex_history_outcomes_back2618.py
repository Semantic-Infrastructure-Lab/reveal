"""History preserves native JSON values and raw fallbacks with measured source loss."""
import json

import pytest

from conftest import _run_reveal_in
from reveal import query
from test_codex_declared_api_back2618 import codex


@pytest.mark.parametrize('state,exit_code', [('healthy', 0), ('empty', 0), ('missing', 2), ('partial', 3), ('failed', 3), ('repaired', 3)])
def test_history_source_and_recovery_outcomes(codex, state, exit_code):
    path = codex / 'history.jsonl'
    payload = b'{"text":"first"}\nnull\nfalse\n0\n[]\n"text"\n'
    if state == 'empty':
        payload = b'\n'
    elif state == 'partial':
        payload += b'{broken\n'
    elif state == 'failed':
        payload = b'{broken\n'
    elif state == 'repaired':
        payload = b'{"text":"\xff"}\n'
    if state != 'missing':
        path.write_bytes(payload)
    result = _run_reveal_in(codex.parent, 'codex://history', '--format', 'json')
    assert result.returncode == exit_code
    answer = json.loads(result.stdout)
    proof = answer['meta']['history_analysis']
    assert proof['request_absent'] == (state == 'missing')
    assert proof['failed_records'] == int(state in ('partial', 'failed'))
    assert proof['recovered_records'] == int(state == 'repaired')
    if state in ('healthy', 'partial'):
        assert answer['entries'][:6] == [{'text': 'first'}, None, False, 0, [], 'text']
        assert proof['analyzed_records'] == 6
    if state in ('partial', 'failed'):
        assert answer['entries'][-1] == {'raw': '{broken'}


def test_history_read_failure_keeps_decoded_prefix_and_native_error_marker(codex, monkeypatch):
    import reveal.adapters.codex.handlers.system as module
    class Stream:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def __iter__(self):
            yield 'null\n'
            yield '{"text":"prefix"}\n'
            raise OSError('history read interrupted')
    monkeypatch.setattr(module, 'open', lambda *args, **kwargs: Stream(), raising=False)
    answer = query('codex://history')
    assert answer['entries'] == [None, {'text': 'prefix'}]
    assert answer['error'] == 'history read interrupted'
    assert answer['meta']['history_analysis']['analyzed_records'] == 2
    assert answer['meta']['history_analysis']['failures'][0]['phase'] == 'read'
    cli = _run_reveal_in(codex.parent, 'codex://history', '--format', 'json')
    assert cli.returncode == 3
    assert json.loads(cli.stdout)['entries'] == answer['entries']


@pytest.mark.parametrize('field', ['receipt', 'source', 'entries', 'count'])
def test_history_receipts_and_observations_survive_presentation(codex, monkeypatch, field):
    from reveal.adapters.codex.adapter import CodexAdapter
    (codex / 'history.jsonl').write_text('null\n{"text":"first"}\n', encoding='utf-8')
    def corrupt(self, result, args):
        if field == 'receipt':
            result['meta'].pop('history_analysis', None)
        elif field == 'source':
            result['source'] = 'unread history'
        elif field == 'entries':
            result['entries'] = []
        else:
            result['total_entries'] = 0
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://history', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_history_display_cut_and_output_failure_keep_source_counts(codex, tmp_path):
    (codex / 'history.jsonl').write_text('null\nfalse\n', encoding='utf-8')
    result = _run_reveal_in(codex.parent, 'codex://history', '--max-items', '1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['entries'] == [None] and answer['total_entries'] == 2
    assert answer['meta']['history_analysis']['analyzed_records'] == 2
    failed = _run_reveal_in(codex.parent, 'codex://history', '--output', 'json=' + str(tmp_path / 'absent' / 'history.json'))
    assert failed.returncode == 3


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_history_partial_failed_and_fresh_repair(codex, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    path = codex / 'history.jsonl'
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(codex))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(codex / 'state_5.sqlite'))
    async def scenario(session):
        request = {'uri': 'codex://history', 'provenance': True}
        path.write_bytes(b'null\n{broken\n')
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        assert json.loads(_text(partial))['entries'] == [None, {'raw': '{broken'}]
        path.write_bytes(b'{broken\n')
        assert (await session.call_tool('reveal_query', request)).is_error
        path.write_bytes(b'null\n')
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        assert json.loads(_text(healthy))['entries'] == [None]
    _run(codex.parent, scenario)


@pytest.mark.parametrize('objects_only,keep_invalid,analyzed,failed,first_failed', [
    (True, False, 1, 5, 1), (False, False, 5, 1, 6), (False, True, 5, 1, 6),
])
def test_shared_reader_value_and_recovery_policies_are_explicit(tmp_path, objects_only, keep_invalid, analyzed, failed, first_failed):
    from reveal.utils.jsonl_records import TranscriptRecords
    path = tmp_path / 'records.jsonl'
    path.write_text('null\nfalse\n0\n[]\n{}\n{broken\n', encoding='utf-8')
    reader = TranscriptRecords(path, objects_only=objects_only, keep_invalid=keep_invalid)
    values = list(reader.records())
    expected = [{}] if objects_only else [None, False, 0, [], {}]
    if keep_invalid:
        expected.append({'raw': '{broken'})
    assert values == expected
    assert reader.record_proof() == {'candidate_records': 6, 'analyzed_records': analyzed,
                                     'failed_records': failed, 'first_failed_line': first_failed}


def test_repeated_history_read_refreshes_absence_loss_and_recovery(codex):
    from reveal.adapters.codex.adapter import CodexAdapter
    path = codex / 'history.jsonl'
    adapter = CodexAdapter('history')
    assert adapter.get_structure()['meta']['history_analysis']['request_absent']
    path.write_text('{broken\n', encoding='utf-8')
    assert adapter.get_structure()['meta']['history_analysis']['failed_records'] == 1
    path.write_text('null\n', encoding='utf-8')
    healthy = adapter.get_structure()
    assert healthy['entries'] == [None]
    assert healthy['meta']['history_analysis']['analyzed_records'] == 1
    assert not healthy['meta']['history_analysis']['request_absent']


def test_history_permission_error_is_required_loss_and_programming_error_propagates(codex, monkeypatch):
    import reveal.adapters.codex.handlers.system as module
    def denied(*args, **kwargs): raise PermissionError('history denied')
    monkeypatch.setattr(module, 'open', denied, raising=False)
    result = _run_reveal_in(codex.parent, 'codex://history', '--format', 'json')
    assert result.returncode == 3
    proof = json.loads(result.stdout)['meta']['history_analysis']
    assert not proof['request_absent'] and proof['failures'][0]['cause'] == 'PermissionError'
    bug = RuntimeError('history implementation bug')
    def broken(*args, **kwargs): raise bug
    monkeypatch.setattr(module, 'open', broken)
    with pytest.raises(RuntimeError) as raised:
        query('codex://history')
    assert raised.value is bug
