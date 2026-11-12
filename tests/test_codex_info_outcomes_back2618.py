"""Installation inspection distinguishes confirmed absence from lost metadata/stats."""
import json
import sqlite3
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal import query
from test_codex_declared_api_back2618 import codex


@pytest.mark.parametrize('state,exit_code', [('healthy', 0), ('missing', 0), ('corrupt', 3)])
def test_info_database_presence_and_loss_are_inspection_outcomes(codex, state, exit_code):
    path = codex / 'state_5.sqlite'
    if state == 'missing':
        path.unlink()
    elif state == 'corrupt':
        path.write_bytes(b'broken')
    result = _run_reveal_in(codex.parent, 'codex://info', '--format', 'json')
    assert result.returncode == exit_code
    answer = json.loads(result.stdout)
    proof = answer['meta']['info_analysis']
    assert proof['candidate_paths'] == 7
    assert proof['failed_db_operations'] == int(state == 'corrupt')
    assert answer['paths']['db']['exists'] == (state != 'missing')
    if state == 'healthy':
        assert answer['db_stats']['total_threads'] == 2
        assert answer['db_stats']['user_sessions'] == 1


def test_info_metadata_denial_is_unknown_and_retains_other_paths(codex, monkeypatch):
    target = codex / 'config.toml'
    original = Path.stat
    def stat(self, *args, **kwargs):
        if self == target:
            raise PermissionError('config metadata denied')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    answer = query('codex://info')
    assert answer['paths']['config']['exists'] is None
    assert answer['paths']['sessions_dir']['exists'] is True
    assert answer['meta']['info_analysis']['failed_paths'] == 1
    text = _run_reveal_in(codex.parent, 'codex://info')
    assert text.returncode == 3
    assert '? config:' in text.stdout


def test_interrupted_directory_count_retains_seen_prefix(codex, monkeypatch):
    original = Path.iterdir
    def entries(self):
        if self == codex / 'sessions':
            yield self / 'seen.jsonl'
            raise PermissionError('session count interrupted')
        else:
            yield from original(self)
    monkeypatch.setattr(Path, 'iterdir', entries)
    answer = query('codex://info')
    row = answer['paths']['sessions_dir']
    assert row['count'] is None and row['entries_seen'] == 1
    assert row['error_phase'] == 'directory-count'
    assert answer['meta']['info_analysis']['failed_paths'] == 1


@pytest.mark.parametrize('field', ['receipt', 'paths', 'stats', 'source'])
def test_info_observations_and_decisions_survive_presentation(codex, monkeypatch, field):
    from reveal.adapters.codex.adapter import CodexAdapter
    def corrupt(self, result, args):
        if field == 'receipt':
            result['meta'].pop('info_analysis', None)
        elif field == 'paths':
            result['paths']['db']['exists'] = False
        elif field == 'stats':
            result['db_stats']['total_threads'] = 0
        else:
            result['source'] = 'unread index'
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://info', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


def test_sqlite_close_failure_keeps_acquired_info_counts(codex, monkeypatch):
    import reveal.adapters.codex.handlers.system as module
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
            raise sqlite3.OperationalError('info close interrupted')
    monkeypatch.setattr(module.sqlite3, 'connect', Connection)
    result = _run_reveal_in(codex.parent, 'codex://info', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['db_stats']['total_threads'] == 2 and answer['db_stats']['user_sessions'] == 1
    assert answer['meta']['info_analysis']['db_operations'][-1]['phase'] == 'close'


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_info_partial_loss_and_fresh_repair(codex, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    path = codex / 'state_5.sqlite'
    original = path.read_bytes()
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(codex))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(path))
    async def scenario(session):
        request = {'uri': 'codex://info', 'provenance': True}
        path.write_bytes(b'broken')
        partial = await session.call_tool('reveal_query', request)
        assert not partial.is_error, _text(partial)
        answer = json.loads(_text(partial))
        assert answer['paths']['db']['exists']
        assert answer['meta']['info_analysis']['failed_db_operations'] == 1
        path.write_bytes(original)
        repaired = await session.call_tool('reveal_query', request)
        assert not repaired.is_error, _text(repaired)
        assert json.loads(_text(repaired))['meta']['info_analysis']['failed_db_operations'] == 0
    _run(codex.parent, scenario)


def test_info_all_metadata_loss_is_failed_inspection(codex, monkeypatch):
    targets = {codex, codex / 'state_5.sqlite', codex / 'sessions', codex / 'history.jsonl',
               codex / 'config.toml', codex / 'memories', codex / 'rules'}
    original = Path.stat
    def stat(self, *args, **kwargs):
        if self in targets:
            raise PermissionError('all inspection metadata denied')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    result = _run_reveal_in(codex.parent, 'codex://info', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['meta']['info_analysis']['usable_paths'] == 0
    assert answer['meta']['info_analysis']['failed_paths'] == 7
    assert answer['meta']['errors'] == []


def test_info_readonly_open_race_cannot_create_database(codex, monkeypatch):
    import reveal.adapters.codex.handlers.system as module
    path = codex / 'state_5.sqlite'
    original = sqlite3.connect
    def connect(*args, **kwargs):
        path.unlink()
        return original(*args, **kwargs)
    monkeypatch.setattr(module.sqlite3, 'connect', connect)
    result = _run_reveal_in(codex.parent, 'codex://info', '--format', 'json')
    assert result.returncode == 3
    assert not path.exists()
    answer = json.loads(result.stdout)
    assert answer['meta']['info_analysis']['db_operations'][0]['phase'] == 'open'
    assert answer['meta']['info_analysis']['failed_db_operations'] == 1


def test_info_repeated_reads_refresh_loss_and_repaired_counts(codex):
    from reveal.adapters.codex.adapter import CodexAdapter
    path = codex / 'state_5.sqlite'
    original = path.read_bytes()
    adapter = CodexAdapter('info')
    assert adapter.get_structure()['db_stats']['user_sessions'] == 1
    path.write_bytes(b'broken')
    assert adapter.get_structure()['meta']['info_analysis']['failed_db_operations'] == 1
    path.write_bytes(original)
    assert adapter.get_structure()['meta']['info_analysis']['failed_db_operations'] == 0


def test_info_output_failure_is_exit_three(codex, tmp_path):
    result = _run_reveal_in(codex.parent, 'codex://info', '--output', 'json=' + str(tmp_path / 'absent' / 'info.json'))
    assert result.returncode == 3
