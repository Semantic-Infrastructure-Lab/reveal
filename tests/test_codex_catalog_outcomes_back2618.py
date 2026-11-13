"""SQLite catalog source decisions precede metadata filtering and display."""
import json
from contextlib import closing
import sqlite3
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from codex_session_fixture import DOC_SESSION_ID
from reveal import query
from test_codex_declared_api_back2618 import codex


@pytest.mark.parametrize('suffix', ['', 'sessions', 'sessions?filter=auth-refactor'])
@pytest.mark.parametrize('state,exit_code', [('healthy', 0), ('missing', 2), ('corrupt', 3)])
def test_catalog_source_outcomes(codex, suffix, state, exit_code):
    path = codex / 'state_5.sqlite'
    if state == 'missing':
        path.unlink()
    elif state == 'corrupt':
        path.write_bytes(b'broken')
    result = _run_reveal_in(codex.parent, 'codex://' + suffix, '--format', 'json')
    assert result.returncode == exit_code
    answer = json.loads(result.stdout)
    proof = answer['meta']['session_catalog']
    assert proof['source'] == path.as_posix()
    assert proof['observed_rows'] == int(state == 'healthy')
    assert proof['failed_operations'] == int(state == 'corrupt')
    assert answer['total'] == int(state == 'healthy')


def test_catalog_metadata_denial_is_not_absence(codex, monkeypatch):
    path = codex / 'state_5.sqlite'
    original = Path.stat
    def stat(self, *args, **kwargs):
        if self == path:
            raise PermissionError('catalog metadata denied')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    answer = query('codex://sessions')
    assert answer['meta']['session_catalog']['failures'][0]['phase'] == 'metadata'


def test_partial_catalog_rows_survive_interrupted_acquisition_and_filtering(codex, monkeypatch):
    import reveal.adapters.codex.handlers.sessions as module
    class Connection:
        def execute(self, sql):
            def rows():
                yield {'id': DOC_SESSION_ID, 'title': 'auth-refactor', 'updated_at': 1783000000}
                raise sqlite3.OperationalError('catalog interrupted')
            return rows()
        def close(self): pass
    monkeypatch.setattr(module, '_connect', lambda path: Connection())
    answer = query('codex://sessions?filter=auth-refactor')
    assert answer['total'] == 1 and answer['sessions'][0]['id'] == DOC_SESSION_ID
    assert 'error' not in answer
    proof = answer['meta']['session_catalog']
    assert proof['observed_rows'] == 1 and not proof['query_complete']
    assert proof['failures'][0]['phase'] == 'query'
    assert any(w['code'] == 'analysis_incomplete' for w in answer['meta']['warnings'])


@pytest.mark.parametrize('field', ['receipt', 'sessions', 'total', 'source', 'error'])
def test_catalog_decisions_survive_presentation(codex, monkeypatch, field):
    from reveal.adapters.codex.adapter import CodexAdapter
    def corrupt(self, result, args):
        if field == 'receipt':
            result['meta']['session_catalog']['observed_rows'] = 0
        elif field == 'sessions':
            result['sessions'] = []
        elif field == 'total':
            result['total'] = 0
        else:
            result[field] = 'changed'
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://sessions', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_catalog_zero_display_cut_keeps_source_population(codex):
    result = _run_reveal_in(codex.parent, 'codex://sessions', '--max-items', '0', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert answer['meta']['session_catalog']['observed_rows'] == 1


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_catalog_failure_and_repair(codex, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    path = codex / 'state_5.sqlite'
    original = path.read_bytes()
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(codex))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(path))
    async def scenario(session):
        request = {'uri': 'codex://sessions', 'provenance': True}
        assert not (await session.call_tool('reveal_query', request)).is_error
        path.write_bytes(b'broken')
        assert (await session.call_tool('reveal_query', request)).is_error
        path.write_bytes(original)
        repaired = await session.call_tool('reveal_query', request)
        assert not repaired.is_error, _text(repaired)
        assert json.loads(_text(repaired))['total'] == 1
    _run(codex.parent, scenario)


def test_catalog_invalid_timestamp_is_disclosed_before_date_filter(codex):
    with closing(sqlite3.connect(codex / 'state_5.sqlite')) as conn, conn:
        conn.execute('UPDATE threads SET updated_at = ? WHERE id = ?', ('not-a-timestamp', DOC_SESSION_ID))
    result = _run_reveal_in(codex.parent, 'codex://sessions?filter=auth-refactor&until=2100-01-01', '--format', 'json')
    assert result.returncode == 3
    proof = json.loads(result.stdout)['meta']['session_catalog']
    assert proof['observed_rows'] == 1 and proof['query_complete']
    assert proof['failures'][0]['phase'] == 'updated_at'


def test_catalog_readonly_open_race_cannot_create_source(codex, monkeypatch):
    import reveal.adapters.codex.handlers.sessions as module
    path = codex / 'state_5.sqlite'
    original = module._connect
    def connect(database):
        path.unlink()
        return original(database)
    monkeypatch.setattr(module, '_connect', connect)
    answer = query('codex://sessions')
    assert not path.exists()
    assert answer['meta']['session_catalog']['failures'][0]['phase'] == 'open'


def test_repeated_catalog_refreshes_failed_and_repaired_sources(codex):
    from reveal.adapters.codex.adapter import CodexAdapter
    path = codex / 'state_5.sqlite'
    original = path.read_bytes()
    adapter = CodexAdapter('sessions')
    assert adapter.get_structure()['total'] == 1
    path.write_bytes(b'broken')
    assert adapter.get_structure()['meta']['session_catalog']['failed_operations'] == 1
    path.write_bytes(original)
    assert adapter.get_structure()['meta']['session_catalog']['failed_operations'] == 0


def test_metadata_selection_receipt_cannot_change_after_read(codex, monkeypatch):
    from reveal.adapters.codex.adapter import CodexAdapter
    def corrupt(self, result, args):
        result['filter'] = 'unapplied filter'
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://sessions?filter=auth-refactor', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_catalog_display_cut_and_output_failure_keep_execution_policy(codex, tmp_path):
    path = next((codex / 'sessions').rglob('*.jsonl'))
    with closing(sqlite3.connect(codex / 'state_5.sqlite')) as conn, conn:
        conn.execute('INSERT INTO threads (id, rollout_path, created_at, updated_at) VALUES (?, ?, 1, 2)',
                     ('ffffffff-ffff-7fff-8fff-ffffffffffff', str(path)))
    result = _run_reveal_in(codex.parent, 'codex://sessions', '--max-items', '1', '--format', 'json')
    assert result.returncode == 0
    answer = json.loads(result.stdout)
    assert len(answer['sessions']) == 1 and answer['total'] == 2
    assert answer['meta']['session_catalog']['observed_rows'] == 2
    failed = _run_reveal_in(codex.parent, 'codex://sessions', '--output', 'json=' + str(tmp_path / 'absent' / 'catalog.json'))
    assert failed.returncode == 3
