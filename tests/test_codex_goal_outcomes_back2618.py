"""Goal absence is optional; failed goal acquisition is not empty success."""
import json
import sqlite3
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from codex_session_fixture import DOC_SESSION_ID
from reveal import query
from test_codex_declared_api_back2618 import codex


def goals(codex):
    path = codex / 'goals_1.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE thread_goals (thread_id TEXT PRIMARY KEY, objective TEXT)')
        conn.execute('INSERT INTO thread_goals VALUES (?, ?)', (DOC_SESSION_ID, 'Keep the acquired goal'))
    return path


@pytest.mark.parametrize('state,exit_code', [('absent', 0), ('empty', 0), ('selected', 0), ('corrupt', 3)])
def test_goal_source_decisions(codex, state, exit_code):
    if state != 'absent':
        path = goals(codex)
        if state == 'empty':
            with sqlite3.connect(path) as conn:
                conn.execute('DELETE FROM thread_goals')
        elif state == 'corrupt':
            path.write_bytes(b'broken')
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '?goal', '--format', 'json')
    assert result.returncode == exit_code
    answer = json.loads(result.stdout)
    proof = answer['meta']['goal_lookup']
    assert proof['decision'] == {'absent': 'source_absent', 'empty': 'missing', 'selected': 'selected', 'corrupt': 'failed'}[state]
    assert proof['failed_operations'] == int(state == 'corrupt')
    assert (answer['goal'] is not None) == (state == 'selected')
    assert 'rollout_analysis' not in answer['meta']


def test_goal_metadata_denial_is_not_optional_absence(codex, monkeypatch):
    path = codex / 'goals_1.sqlite'
    original = Path.stat
    def stat(self, *args, **kwargs):
        if self == path:
            raise PermissionError('goal metadata denied')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat)
    answer = query('codex://' + DOC_SESSION_ID + '?goal')
    assert answer['meta']['goal_lookup']['failures'][0]['phase'] == 'metadata'
    assert answer['error'] == 'goal metadata denied'


def test_goal_does_not_acquire_unrelated_rollout(codex, monkeypatch):
    from reveal.adapters.codex.adapter import CodexAdapter
    def unexpected(*args):
        pytest.fail('goal read reached rollout reader')
    monkeypatch.setattr(CodexAdapter, '_load_records', unexpected)
    assert query('codex://' + DOC_SESSION_ID + '?goal')['goal'] is None


@pytest.mark.parametrize('field', ['goal', 'receipt', 'source', 'thread_id', 'error'])
def test_goal_observations_and_decisions_survive_presentation(codex, monkeypatch, field):
    from reveal.adapters.codex.adapter import CodexAdapter
    goals(codex)
    def corrupt(self, result, args):
        if field == 'goal':
            result['goal'] = None
        elif field == 'receipt':
            result['meta']['goal_lookup']['decision'] = 'missing'
        elif field == 'error':
            result['error'] = 'unowned error'
        else:
            result[field] = 'changed'
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', corrupt)
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '?goal', '--format', 'json')
    assert result.returncode == 3
    assert any(e['code'] == 'invalid_adapter_answer' for e in json.loads(result.stdout)['meta']['errors'])


@pytest.mark.parametrize('state,exit_code', [('missing', 2), ('corrupt', 3)])
def test_goal_preserves_required_primary_index_outcomes(codex, state, exit_code):
    path = codex / 'state_5.sqlite'
    if state == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'broken')
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '?goal', '--format', 'json')
    assert result.returncode == exit_code


@pytest.mark.mcp
@pytest.mark.component
def test_sdk_goal_failure_and_fresh_repair(codex, monkeypatch):
    from test_mcp_expected_errors_back1992 import _run, _text
    path = goals(codex)
    original = path.read_bytes()
    monkeypatch.setenv('REVEAL_CODEX_HOME', str(codex))
    monkeypatch.setenv('REVEAL_CODEX_DB', str(codex / 'state_5.sqlite'))
    async def scenario(session):
        request = {'uri': 'codex://' + DOC_SESSION_ID + '?goal', 'provenance': True}
        assert not (await session.call_tool('reveal_query', request)).is_error
        path.write_bytes(b'broken')
        assert (await session.call_tool('reveal_query', request)).is_error
        path.write_bytes(original)
        repaired = await session.call_tool('reveal_query', request)
        assert not repaired.is_error, _text(repaired)
        assert json.loads(_text(repaired))['goal']['objective'] == 'Keep the acquired goal'
    _run(codex.parent, scenario)


def test_goal_open_race_cannot_create_database(codex, monkeypatch):
    import reveal.adapters.codex.handlers.goals as module
    path = goals(codex)
    original = module.connect_readonly
    def connect(database):
        path.unlink()
        return original(database)
    monkeypatch.setattr(module, 'connect_readonly', connect)
    answer = query('codex://' + DOC_SESSION_ID + '?goal')
    assert not path.exists()
    assert answer['meta']['goal_lookup']['failures'][0]['phase'] == 'open'
    assert answer['error'] and answer['goal'] is None


def test_goal_close_loss_keeps_acquired_row_and_exit_three(codex, monkeypatch):
    import reveal.adapters.codex.handlers.goals as module
    goals(codex)
    original = module.connect_readonly
    class Connection:
        def __init__(self, path): self.real = original(path)
        def execute(self, *args): return self.real.execute(*args)
        def close(self):
            self.real.close()
            raise sqlite3.OperationalError('goal close interrupted')
    monkeypatch.setattr(module, 'connect_readonly', Connection)
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '?goal', '--format', 'json')
    assert result.returncode == 3
    answer = json.loads(result.stdout)
    assert answer['goal']['objective'] == 'Keep the acquired goal'
    assert 'error' not in answer
    assert answer['meta']['goal_lookup']['query_complete']
    assert answer['meta']['goal_lookup']['failures'][0]['phase'] == 'close'


def test_repeated_goal_read_refreshes_acquisition_evidence(codex):
    from reveal.adapters.codex.adapter import CodexAdapter
    path = goals(codex)
    original = path.read_bytes()
    adapter = CodexAdapter(DOC_SESSION_ID, query='goal')
    assert adapter.get_structure()['goal']['objective'] == 'Keep the acquired goal'
    path.write_bytes(b'broken')
    assert adapter.get_structure()['meta']['goal_lookup']['decision'] == 'failed'
    path.write_bytes(original)
    repaired = adapter.get_structure()
    assert repaired['meta']['goal_lookup']['decision'] == 'selected'
    assert repaired['meta']['goal_lookup']['failed_operations'] == 0


def test_goal_metadata_cannot_hide_transcript_source_loss(codex, monkeypatch):
    from reveal.adapters.codex.adapter import CodexAdapter
    path = next((codex / 'sessions').rglob('*.jsonl'))
    path.write_bytes(path.read_bytes() + b'{broken\n')
    def inject(self, result, args):
        result['meta']['goal_lookup'] = {'decision': 'source_absent'}
        return result
    monkeypatch.setattr(CodexAdapter, 'post_process', inject)
    result = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '/messages', '--format', 'json')
    assert result.returncode == 3
    assert json.loads(result.stdout)['meta']['rollout_analysis']['failed_records'] == 1


def test_goal_selector_has_no_false_unused_warning_and_preserves_legacy_priority(codex):
    selected = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '?goal', '--format', 'json')
    assert selected.returncode == 0
    assert 'has no effect' not in selected.stderr
    overridden = _run_reveal_in(codex.parent, 'codex://' + DOC_SESSION_ID + '?last&goal', '--format', 'json')
    assert overridden.returncode == 0
    assert json.loads(overridden.stdout)['type'] == 'codex_messages'
