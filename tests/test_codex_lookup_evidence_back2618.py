"""SQLite lookup must distinguish absence, ambiguity and failed acquisition."""
from contextlib import closing
import sqlite3
from pathlib import Path

import pytest

from codex_session_fixture import DOC_SESSION_ID
from reveal import query
from test_codex_declared_api_back2618 import codex


@pytest.mark.parametrize('identifier,phases', [(DOC_SESSION_ID, ['exact']), (DOC_SESSION_ID[:8], ['exact', 'prefix'])])
def test_healthy_lookup_records_the_observed_query_scope(codex, identifier, phases):
    answer = query('codex://' + identifier + '/messages')
    proof = answer['meta']['session_lookup']
    assert proof['source'] == (codex / 'state_5.sqlite').as_posix()
    assert proof['source_present'] is True and proof['opened'] is True
    assert proof['decision'] == 'selected' and proof['selected_id'] == DOC_SESSION_ID
    assert [step['phase'] for step in proof['queries']] == phases
    assert all(step['complete'] for step in proof['queries'])
    assert proof['failed_operations'] == 0


def test_missing_target_and_unreadable_index_have_different_decisions(codex):
    missing = query('codex://ffffffff-ffff-7fff-8fff-ffffffffffff')
    assert missing['meta']['session_lookup']['decision'] == 'missing'
    (codex / 'state_5.sqlite').write_bytes(b'not a SQLite database')
    failed = query('codex://' + DOC_SESSION_ID)
    proof = failed['meta']['session_lookup']
    assert proof['decision'] == 'failed' and proof['failed_operations'] == 1
    assert proof['failures'][0]['phase'] == 'exact'
    assert 'not found' not in failed['error'].lower()
    assert any(w['code'] == 'analysis_incomplete' for w in failed['meta']['warnings'])


def test_absent_install_has_a_measured_missing_source(codex):
    (codex / 'state_5.sqlite').unlink()
    answer = query('codex://' + DOC_SESSION_ID)
    proof = answer['meta']['session_lookup']
    assert answer['type'] == 'codex_not_installed'
    assert proof['decision'] == 'source_absent' and proof['source_present'] is False
    assert proof['failed_operations'] == 0 and not proof['queries']


def test_metadata_denial_is_not_target_absence(codex, monkeypatch):
    database = codex / 'state_5.sqlite'
    original = Path.stat
    def stat(path, *args, **kwargs):
        if path == database:
            raise PermissionError('index metadata denied')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    answer = query('codex://' + DOC_SESSION_ID)
    proof = answer['meta']['session_lookup']
    assert proof['decision'] == 'failed' and proof['source_present'] is None
    assert proof['failures'][0]['phase'] == 'metadata'


def test_open_race_cannot_create_an_empty_database(codex, monkeypatch):
    import reveal.adapters.codex.adapter as module
    database = codex / 'state_5.sqlite'
    original = sqlite3.connect
    def connect(*args, **kwargs):
        database.unlink()
        return original(*args, **kwargs)
    monkeypatch.setattr(module.sqlite3, 'connect', connect)
    answer = query('codex://' + DOC_SESSION_ID)
    assert not database.exists()
    proof = answer['meta']['session_lookup']
    assert proof['source_present'] is True and proof['opened'] is False
    assert proof['failures'][0]['phase'] == 'open'


def test_ambiguity_reports_bounded_observed_candidates(codex):
    database = codex / 'state_5.sqlite'
    path = next((codex / 'sessions').rglob('*.jsonl'))
    with closing(sqlite3.connect(database)) as conn, conn:
        for index in range(2, 11):
            identifier = DOC_SESSION_ID[:-3] + f'{index:03d}'
            conn.execute('INSERT INTO threads (id, rollout_path, created_at, updated_at) VALUES (?, ?, 1, 2)',
                         (identifier, str(path)))
    answer = query('codex://' + DOC_SESSION_ID[:8])
    proof = answer['meta']['session_lookup']
    assert proof['decision'] == 'ambiguous' and proof['selected_id'] is None
    assert len(proof['observed_ids']) == 6
    assert proof['queries'][-1]['limit'] == 6 and proof['queries'][-1]['rows'] == 6
    assert 'Ambiguous' in answer['error']


def test_interrupted_prefix_retains_observed_ids_without_claiming_uniqueness(codex, monkeypatch):
    import reveal.adapters.codex.adapter as module
    class Connection:
        def execute(self, sql, params):
            if ' LIKE ' not in sql:
                return iter(())
            def rows():
                yield {'id': DOC_SESSION_ID}
                raise sqlite3.OperationalError('prefix read interrupted')
            return rows()
        def close(self): pass
    monkeypatch.setattr(module.sqlite3, 'connect', lambda *args, **kwargs: Connection())
    answer = query('codex://' + DOC_SESSION_ID[:8])
    proof = answer['meta']['session_lookup']
    assert proof['decision'] == 'failed' and proof['selected_id'] is None
    assert proof['observed_ids'] == [DOC_SESSION_ID]
    assert proof['queries'][-1]['rows'] == 1 and proof['queries'][-1]['complete'] is False
    assert proof['failures'][0]['phase'] == 'prefix'


def test_close_failure_keeps_the_acquired_row_and_rollout(codex, monkeypatch):
    import reveal.adapters.codex.adapter as module
    original = sqlite3.connect
    class Connection:
        def __init__(self, *args, **kwargs): self.real = original(*args, **kwargs)
        @property
        def row_factory(self): return self.real.row_factory
        @row_factory.setter
        def row_factory(self, value): self.real.row_factory = value
        def execute(self, *args): return self.real.execute(*args)
        def close(self):
            self.real.close()
            raise sqlite3.OperationalError('close interrupted')
    monkeypatch.setattr(module.sqlite3, 'connect', Connection)
    answer = query('codex://' + DOC_SESSION_ID + '/messages')
    assert answer['messages']
    proof = answer['meta']['session_lookup']
    assert proof['selected_id'] == DOC_SESSION_ID and proof['decision'] == 'selected'
    assert proof['failures'][0]['phase'] == 'close'


@pytest.mark.parametrize('filename', ['state #% 雪.sqlite', 'state #?% 雪.sqlite'])
def test_readonly_uri_keeps_literal_database_filenames(codex, monkeypatch, filename):
    from reveal.adapters.codex.adapter import CodexAdapter
    from filename_fixture import require_filename
    unusual = codex / filename
    require_filename(unusual)
    (codex / 'state_5.sqlite').rename(unusual)
    monkeypatch.setattr(CodexAdapter, 'CODEX_DB', unusual)
    answer = query('codex://' + DOC_SESSION_ID + '/messages')
    assert answer['messages']
    assert answer['meta']['session_lookup']['source'] == unusual.as_posix()
    assert answer['meta']['session_lookup']['decision'] == 'selected'


def test_repeated_lookup_refreshes_failure_and_recovery(codex):
    from reveal.adapters.codex.adapter import CodexAdapter
    database = codex / 'state_5.sqlite'
    original = database.read_bytes()
    adapter = CodexAdapter(DOC_SESSION_ID + '/messages')
    assert adapter.get_structure()['meta']['session_lookup']['decision'] == 'selected'
    database.write_bytes(b'broken')
    failed = adapter.get_structure()
    assert failed['meta']['session_lookup']['decision'] == 'failed'
    assert 'rollout_analysis' not in failed['meta']
    database.write_bytes(original)
    assert adapter.get_structure()['meta']['session_lookup']['decision'] == 'selected'


def test_goal_keeps_required_index_proof_without_unrelated_rollout_loss(codex):
    next((codex / 'sessions').rglob('*.jsonl')).write_text('{broken\n', encoding='utf-8')
    answer = query('codex://' + DOC_SESSION_ID + '?goal')
    assert answer['type'] == 'codex_goal' and answer['goal'] is None
    assert answer['meta']['session_lookup']['decision'] == 'selected'
    assert 'rollout_analysis' not in answer['meta']
    assert not answer['meta']['warnings']


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_lookup_refreshes_failure_and_recovery(codex, monkeypatch):
    import json
    from test_mcp_expected_errors_back1992 import _run, _text
    database = codex / 'state_5.sqlite'
    original = database.read_bytes()
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(codex))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(database))
    async def scenario(session):
        request = {'uri': 'codex://' + DOC_SESSION_ID + '/messages', 'provenance': True}
        first = await session.call_tool('reveal_query', request)
        assert not first.is_error, _text(first)
        assert json.loads(_text(first))['meta']['session_lookup']['decision'] == 'selected'
        database.write_bytes(b'broken')
        failed = await session.call_tool('reveal_query', request)
        assert failed.is_error
        assert 'Internal error executing tool reveal_query' in _text(failed)
        database.write_bytes(original)
        healthy = await session.call_tool('reveal_query', request)
        assert not healthy.is_error, _text(healthy)
        proof = json.loads(_text(healthy))['meta']['session_lookup']
        assert proof['decision'] == 'selected' and proof['failed_operations'] == 0
    _run(codex.parent, scenario)
