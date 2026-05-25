"""Tests for the codex:// adapter."""

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from reveal.adapters.codex.adapter import CodexAdapter, _UUID_RE
from reveal.adapters.agent_base import pair_tool_calls


# ---------------------------------------------------------------------------
# Synthetic JSONL fixture
# ---------------------------------------------------------------------------

_SESSION_UUID = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890'

_FIXTURE_LINES = [
    # session_meta
    {'timestamp': '2026-05-24T10:00:00Z', 'type': 'session_meta',
     'payload': {'session_id': _SESSION_UUID, 'model': 'gpt-5.5'}},
    # turn_context
    {'timestamp': '2026-05-24T10:00:01Z', 'type': 'turn_context',
     'payload': {'cwd': '/home/user/project'}},
    # user_message
    {'timestamp': '2026-05-24T10:00:02Z', 'type': 'event_msg',
     'payload': {'type': 'user_message', 'message': 'Help me refactor this module.'}},
    # agent_message (first)
    {'timestamp': '2026-05-24T10:00:10Z', 'type': 'event_msg',
     'payload': {'type': 'agent_message', 'message': "Sure, I'll start by reading the file.", 'phase': 'thinking'}},
    # token_count — real Codex format: info.last_token_usage + info.total_token_usage
    {'timestamp': '2026-05-24T10:00:11Z', 'type': 'event_msg',
     'payload': {'type': 'token_count', 'info': {
         'last_token_usage': {'input_tokens': 500, 'cached_input_tokens': 0,
                              'output_tokens': 120, 'reasoning_output_tokens': 0, 'total_tokens': 620},
         'total_token_usage': {'input_tokens': 500, 'cached_input_tokens': 0,
                               'output_tokens': 120, 'reasoning_output_tokens': 0, 'total_tokens': 620},
         'model_context_window': 128000,
     }}},
    # task_complete
    {'timestamp': '2026-05-24T10:00:15Z', 'type': 'event_msg',
     'payload': {'type': 'task_complete', 'turn_id': 'turn-1',
                 'last_agent_message': 'Done.', 'duration_ms': 8000, 'time_to_first_token_ms': 500}},
    # function_call
    {'timestamp': '2026-05-24T10:00:20Z', 'type': 'response_item',
     'payload': {'type': 'function_call', 'name': 'read_file',
                 'namespace': 'default', 'arguments': '{"path": "foo.py"}', 'call_id': 'call-001'}},
    # function_call_output
    {'timestamp': '2026-05-24T10:00:21Z', 'type': 'response_item',
     'payload': {'type': 'function_call_output', 'call_id': 'call-001',
                 'output': 'def foo(): pass\n'}},
    # exec_command_end — real Codex format (no begin event; end has all info)
    {'timestamp': '2026-05-24T10:00:26Z', 'type': 'event_msg',
     'payload': {'type': 'exec_command_end', 'call_id': 'call-shell-001',
                 'command': ['/bin/bash', '-lc', 'ls -la'],
                 'cwd': '/home/user/project', 'exit_code': 0,
                 'aggregated_output': 'total 8\ndrwxr-xr-x 2 user user 4096 May 24 10:00 .\n',
                 'duration': {'secs': 0, 'nanos': 120_000_000}, 'status': 'completed'}},
    # error event
    {'timestamp': '2026-05-24T10:00:30Z', 'type': 'event_msg',
     'payload': {'type': 'error', 'message': 'Something went wrong.'}},
    # warning event
    {'timestamp': '2026-05-24T10:00:31Z', 'type': 'event_msg',
     'payload': {'type': 'warning', 'message': 'Rate limit approaching.'}},
    # second agent_message (last)
    {'timestamp': '2026-05-24T10:00:40Z', 'type': 'event_msg',
     'payload': {'type': 'agent_message', 'message': 'Refactoring complete!', 'phase': 'final'}},
]

_FIXTURE_JSONL = '\n'.join(json.dumps(line) for line in _FIXTURE_LINES) + '\n'


def _write_fixture_jsonl(tmp_path: Path) -> Path:
    p = tmp_path / 'rollout-2026-05-24T10-00-00Z-a1b2c3d4.jsonl'
    p.write_text(_FIXTURE_JSONL, encoding='utf-8')
    return p


def _make_sqlite_db(tmp_path: Path, jsonl_path: Path) -> Path:
    db_path = tmp_path / 'state_5.sqlite'
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            rollout_path TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'cli',
            cwd TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            first_user_message TEXT NOT NULL DEFAULT '',
            preview TEXT NOT NULL DEFAULT '',
            model TEXT,
            model_provider TEXT NOT NULL DEFAULT 'openai',
            reasoning_effort TEXT,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            git_sha TEXT, git_branch TEXT, git_origin_url TEXT,
            cli_version TEXT NOT NULL DEFAULT '',
            archived INTEGER NOT NULL DEFAULT 0,
            thread_source TEXT,
            approval_mode TEXT,
            sandbox_policy TEXT,
            has_user_event INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        INSERT INTO threads (id, rollout_path, created_at, updated_at, source, cwd,
            title, first_user_message, model, model_provider, tokens_used, thread_source, archived)
        VALUES (?, ?, ?, ?, 'cli', '/home/user/project',
            'Help me refactor this module.', 'Help me refactor this module.',
            'gpt-5.5', 'openai', 620, NULL, 0)
    """, (_SESSION_UUID, str(jsonl_path), 1716544800, 1716544900))
    # Add a subagent row (should be filtered out)
    conn.execute("""
        INSERT INTO threads (id, rollout_path, created_at, updated_at, source, cwd,
            title, first_user_message, model, model_provider, tokens_used, thread_source, archived)
        VALUES ('subagent-0001', ?, ?, ?, 'cli', '/tmp', 'sub', 'sub', 'gpt-4', 'openai', 0, 'subagent', 0)
    """, (str(jsonl_path), 1716544700, 1716544750))
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# Helper: build a configured adapter pointing at tmp fixtures
# ---------------------------------------------------------------------------

def _make_adapter(resource: str, tmp_path: Path, jsonl_path: Path, query: str = '') -> CodexAdapter:
    db_path = _make_sqlite_db(tmp_path, jsonl_path)
    adapter = CodexAdapter(resource, query=query or None)
    adapter.CODEX_HOME = tmp_path
    adapter.CODEX_DB = db_path
    return adapter


# ---------------------------------------------------------------------------
# 1. CodexAdapter init and UUID detection
# ---------------------------------------------------------------------------

class TestCodexAdapterInit:
    def test_init_stores_resource(self):
        a = CodexAdapter('sessions')
        assert a.resource == 'sessions'

    def test_init_stores_query(self):
        a = CodexAdapter('sessions', query='search=foo')
        assert a.query == 'search=foo'

    def test_init_none_resource_raises(self):
        with pytest.raises(TypeError):
            CodexAdapter(None)  # type: ignore[arg-type]

    def test_uuid_detection_full_uuid(self):
        a = CodexAdapter('sessions')
        assert a._is_uuid('a1b2c3d4-e5f6-7890-abcd-ef1234567890')

    def test_uuid_detection_prefix(self):
        a = CodexAdapter('sessions')
        assert a._is_uuid('a1b2c3d')

    def test_uuid_detection_non_uuid(self):
        a = CodexAdapter('sessions')
        assert not a._is_uuid('sessions')
        assert not a._is_uuid('info')

    def test_session_id_from_resource_with_sub(self):
        a = CodexAdapter(f'{_SESSION_UUID}/messages')
        sid = a._session_id_from_resource()
        assert sid == _SESSION_UUID

    def test_session_sub_path(self):
        a = CodexAdapter(f'{_SESSION_UUID}/tools')
        assert a._session_sub_path() == 'tools'

    def test_session_sub_path_bare(self):
        a = CodexAdapter(_SESSION_UUID)
        assert a._session_sub_path() == ''


# ---------------------------------------------------------------------------
# 2. pair_tool_calls (agent_base)
# ---------------------------------------------------------------------------

class TestPairToolCalls:
    def test_pairs_by_call_id(self):
        records = [
            {'type': 'function_call', 'call_id': 'c1', 'name': 'read'},
            {'type': 'function_call_output', 'call_id': 'c1', 'output': 'ok'},
            {'type': 'function_call', 'call_id': 'c2', 'name': 'write'},
        ]
        pairs = pair_tool_calls(records, 'function_call', 'function_call_output', 'call_id')
        assert len(pairs) == 2
        assert pairs[0]['call']['name'] == 'read'
        assert pairs[0]['output']['output'] == 'ok'
        assert pairs[1]['call']['name'] == 'write'
        assert pairs[1]['output'] is None

    def test_empty_records(self):
        assert pair_tool_calls([], 'function_call', 'function_call_output') == []

    def test_no_outputs(self):
        records = [{'type': 'function_call', 'call_id': 'x', 'name': 'foo'}]
        pairs = pair_tool_calls(records, 'function_call', 'function_call_output')
        assert pairs[0]['output'] is None

    def test_custom_call_id_field(self):
        records = [
            {'type': 'call', 'id': 'abc', 'name': 'do'},
            {'type': 'result', 'id': 'abc', 'data': 'yes'},
        ]
        pairs = pair_tool_calls(records, 'call', 'result', call_id_field='id')
        assert pairs[0]['output']['data'] == 'yes'


# ---------------------------------------------------------------------------
# 3. Session list (mock SQLite)
# ---------------------------------------------------------------------------

class TestSessionList:
    def test_list_returns_user_sessions_only(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_session_list'
        assert result['total'] == 1  # subagent filtered out
        assert result['sessions'][0]['id'] == _SESSION_UUID

    def test_list_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result

    def test_empty_resource_also_lists(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_session_list'

    def test_missing_db_returns_graceful_error(self, tmp_path):
        adapter = CodexAdapter('sessions')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'nonexistent.sqlite'
        result = adapter.get_structure()
        assert result['type'] == 'codex_session_list'
        assert 'error' in result
        assert result['total'] == 0


# ---------------------------------------------------------------------------
# 4. Session search
# ---------------------------------------------------------------------------

class TestSessionSearch:
    def test_search_finds_match(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor')
        result = adapter.get_structure()
        assert result['type'] == 'codex_session_list'
        assert result['total'] == 1

    def test_search_no_match(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=zzznonexistent')
        result = adapter.get_structure()
        assert result['total'] == 0


# ---------------------------------------------------------------------------
# 5. Session overview
# ---------------------------------------------------------------------------

class TestSessionOverview:
    def test_overview_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_session_overview'

    def test_overview_metrics(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['user_turns'] == 1
        assert result['agent_turns'] == 2
        assert result['tool_calls'] == 1
        assert result['shell_calls'] == 1

    def test_overview_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result

    def test_overview_session_not_found(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('deadbeef', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_error'
        assert 'not found' in result['error'].lower()


# ---------------------------------------------------------------------------
# 6. ?last — returns last agent_message
# ---------------------------------------------------------------------------

class TestLastQuery:
    def test_last_returns_codex_messages(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='last')
        result = adapter.get_structure()
        assert result['type'] == 'codex_messages'
        assert len(result['messages']) == 1

    def test_last_returns_final_agent_message(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='last')
        result = adapter.get_structure()
        msg = result['messages'][0]
        assert msg['role'] == 'agent'
        assert 'complete' in msg['message'].lower()

    def test_last_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='last')
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


# ---------------------------------------------------------------------------
# 7. /tools — paired function_call+output
# ---------------------------------------------------------------------------

class TestToolsSubPath:
    def test_tools_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/tools', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_tools'

    def test_tools_pairs_correctly(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/tools', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['total'] == 1
        pair = result['tools'][0]
        assert pair['call']['name'] == 'read_file'
        assert pair['output']['output'] == 'def foo(): pass\n'

    def test_tools_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/tools', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


# ---------------------------------------------------------------------------
# 8. /errors
# ---------------------------------------------------------------------------

class TestErrorsSubPath:
    def test_errors_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/errors', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_errors'

    def test_errors_count(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/errors', tmp_path, jsonl_path)
        result = adapter.get_structure()
        # fixture has 1 error + 1 warning
        assert result['total'] == 2

    def test_errors_severity(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/errors', tmp_path, jsonl_path)
        result = adapter.get_structure()
        severities = {e['severity'] for e in result['errors']}
        assert 'error' in severities
        assert 'warning' in severities

    def test_errors_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/errors', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


# ---------------------------------------------------------------------------
# 9. /shell — exec_command_end records (Codex omits begin; end has all info)
# ---------------------------------------------------------------------------

class TestShellSubPath:
    def test_shell_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/shell', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_shell'

    def test_shell_count(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/shell', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['total'] == 1

    def test_shell_exit_code(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/shell', tmp_path, jsonl_path)
        result = adapter.get_structure()
        cmd = result['shell_calls'][0]
        assert cmd['exit_code'] == 0

    def test_shell_command(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/shell', tmp_path, jsonl_path)
        result = adapter.get_structure()
        cmd = result['shell_calls'][0]
        assert cmd['command'] == ['/bin/bash', '-lc', 'ls -la']

    def test_shell_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/shell', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


# ---------------------------------------------------------------------------
# 10. ?tokens — per-turn token breakdown
# ---------------------------------------------------------------------------

class TestTokensQuery:
    def test_tokens_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='tokens')
        result = adapter.get_structure()
        assert result['type'] == 'codex_tokens'

    def test_tokens_count(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='tokens')
        result = adapter.get_structure()
        assert result['total_turns'] == 1

    def test_tokens_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='tokens')
        result = adapter.get_structure()
        turn = result['token_turns'][0]
        assert turn['input_tokens'] == 500
        assert turn['output_tokens'] == 120
        assert turn['total_tokens'] == 620

    def test_tokens_grand_total(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='tokens')
        result = adapter.get_structure()
        assert result['grand_total'] == 620

    def test_tokens_turn_number(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='tokens')
        result = adapter.get_structure()
        assert result['token_turns'][0]['turn'] == 1

    def test_tokens_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='tokens')
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


# ---------------------------------------------------------------------------
# 11. ?content= — JSONL content search across sessions
# ---------------------------------------------------------------------------

class TestContentSearch:
    def test_content_search_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='content=refactor')
        result = adapter.get_structure()
        assert result['type'] == 'codex_content_search'

    def test_content_search_finds_match(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='content=refactor')
        result = adapter.get_structure()
        assert result['total'] == 1

    def test_content_search_no_match(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='content=xyzzy_no_match_xyz')
        result = adapter.get_structure()
        assert result['total'] == 0

    def test_content_search_has_snippets(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='content=refactor')
        result = adapter.get_structure()
        session = result['sessions'][0]
        assert session['match_count'] >= 1
        assert any('refactor' in m['snippet'].lower() for m in session['matches'])

    def test_content_search_query_field(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='content=refactor')
        result = adapter.get_structure()
        assert result['query'] == 'refactor'

    def test_content_search_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='content=refactor')
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


# ---------------------------------------------------------------------------
# 12. codex://info — graceful missing DB
# ---------------------------------------------------------------------------

class TestInfoResource:
    def test_info_type(self, tmp_path):
        adapter = CodexAdapter('info')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        result = adapter.get_structure()
        assert result['type'] == 'codex_info'

    def test_info_has_paths(self, tmp_path):
        adapter = CodexAdapter('info')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        result = adapter.get_structure()
        assert 'paths' in result

    def test_info_db_not_exists(self, tmp_path):
        adapter = CodexAdapter('info')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        result = adapter.get_structure()
        # Should not crash, paths.db.exists should be False
        assert result['paths']['db']['exists'] is False

    def test_info_contract_fields(self, tmp_path):
        adapter = CodexAdapter('info')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


# ---------------------------------------------------------------------------
# 13. Output contract: every get_structure() result has required fields
# ---------------------------------------------------------------------------

class TestOutputContract:
    _REQUIRED = ('contract_version', 'type', 'source', 'source_type')

    def _check(self, result: Dict[str, Any]) -> None:
        for field in self._REQUIRED:
            assert field in result, f"Missing field {field!r} in result type {result.get('type')!r}"

    def test_session_list_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path)
        self._check(adapter.get_structure())

    def test_overview_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path)
        self._check(adapter.get_structure())

    def test_messages_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/messages', tmp_path, jsonl_path)
        self._check(adapter.get_structure())

    def test_tools_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/tools', tmp_path, jsonl_path)
        self._check(adapter.get_structure())

    def test_errors_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/errors', tmp_path, jsonl_path)
        self._check(adapter.get_structure())

    def test_shell_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/shell', tmp_path, jsonl_path)
        self._check(adapter.get_structure())

    def test_last_query_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='last')
        self._check(adapter.get_structure())

    def test_tokens_query_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='tokens')
        self._check(adapter.get_structure())

    def test_content_search_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='content=refactor')
        self._check(adapter.get_structure())

    def test_info_contract(self, tmp_path):
        adapter = CodexAdapter('info')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        self._check(adapter.get_structure())

    def test_not_installed_contract(self, tmp_path):
        adapter = CodexAdapter(_SESSION_UUID)
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'nonexistent.sqlite'
        result = adapter.get_structure()
        self._check(result)
        assert result['type'] == 'codex_not_installed'


# ---------------------------------------------------------------------------
# Phase 3: /workflow, /timeline, ?goal, memories/pipeline
# ---------------------------------------------------------------------------

class TestWorkflow:
    def test_workflow_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/workflow', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_workflow'

    def test_workflow_has_events(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/workflow', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert 'events' in result
        assert result['total'] == len(result['events'])

    def test_workflow_includes_tool_and_shell(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/workflow', tmp_path, jsonl_path)
        result = adapter.get_structure()
        kinds = {e['kind'] for e in result['events']}
        assert 'tool_call' in kinds
        assert 'shell' in kinds

    def test_workflow_sorted_by_timestamp(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/workflow', tmp_path, jsonl_path)
        result = adapter.get_structure()
        timestamps = [e['timestamp'] for e in result['events'] if e['timestamp']]
        assert timestamps == sorted(timestamps)

    def test_workflow_tool_has_name(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/workflow', tmp_path, jsonl_path)
        result = adapter.get_structure()
        tools = [e for e in result['events'] if e['kind'] == 'tool_call']
        assert tools[0]['name'] == 'read_file'

    def test_workflow_shell_has_exit_code(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/workflow', tmp_path, jsonl_path)
        result = adapter.get_structure()
        shells = [e for e in result['events'] if e['kind'] == 'shell']
        assert shells[0]['exit_code'] == 0

    def test_workflow_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/workflow', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


class TestTimeline:
    def test_timeline_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/timeline', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_timeline'

    def test_timeline_has_events(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/timeline', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert 'events' in result
        assert result['total'] == len(result['events'])

    def test_timeline_count_matches_fixture(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/timeline', tmp_path, jsonl_path)
        result = adapter.get_structure()
        # Fixture has 12 JSONL lines
        assert result['total'] == 12

    def test_timeline_events_have_required_keys(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/timeline', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for ev in result['events']:
            assert 'timestamp' in ev
            assert 'event_type' in ev
            assert 'payload_type' in ev
            assert 'summary' in ev

    def test_timeline_sorted_by_timestamp(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/timeline', tmp_path, jsonl_path)
        result = adapter.get_structure()
        timestamps = [e['timestamp'] for e in result['events'] if e['timestamp']]
        assert timestamps == sorted(timestamps)

    def test_timeline_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/timeline', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


class TestGoal:
    def _make_goals_db(self, tmp_path: Path) -> Path:
        db_path = tmp_path / 'goals_1.sqlite'
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE thread_goals (
                thread_id TEXT PRIMARY KEY NOT NULL,
                goal_id TEXT NOT NULL,
                objective TEXT NOT NULL,
                status TEXT NOT NULL,
                token_budget INTEGER,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                time_used_seconds INTEGER NOT NULL DEFAULT 0,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO thread_goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_SESSION_UUID, 'goal-001', 'Refactor the auth module', 'active',
             50000, 12500, 300, 1716544800000, 1716544900000)
        )
        conn.commit()
        conn.close()
        return db_path

    def test_goal_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        self._make_goals_db(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='goal')
        result = adapter.get_structure()
        assert result['type'] == 'codex_goal'

    def test_goal_returns_objective(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        self._make_goals_db(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='goal')
        result = adapter.get_structure()
        assert result['goal'] is not None
        assert result['goal']['objective'] == 'Refactor the auth module'

    def test_goal_returns_status(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        self._make_goals_db(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='goal')
        result = adapter.get_structure()
        assert result['goal']['status'] == 'active'

    def test_goal_returns_token_budget(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        self._make_goals_db(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='goal')
        result = adapter.get_structure()
        assert result['goal']['token_budget'] == 50000
        assert result['goal']['tokens_used'] == 12500

    def test_goal_none_when_no_row(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        # goals db exists but no row for this thread
        db_path = tmp_path / 'goals_1.sqlite'
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE thread_goals (
                thread_id TEXT PRIMARY KEY NOT NULL,
                goal_id TEXT NOT NULL, objective TEXT NOT NULL,
                status TEXT NOT NULL, token_budget INTEGER,
                tokens_used INTEGER NOT NULL DEFAULT 0,
                time_used_seconds INTEGER NOT NULL DEFAULT 0,
                created_at_ms INTEGER NOT NULL, updated_at_ms INTEGER NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='goal')
        result = adapter.get_structure()
        assert result['type'] == 'codex_goal'
        assert result['goal'] is None

    def test_goal_none_when_no_db(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='goal')
        # no goals_1.sqlite in tmp_path
        result = adapter.get_structure()
        assert result['type'] == 'codex_goal'
        assert result['goal'] is None

    def test_goal_contract(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        self._make_goals_db(tmp_path)
        adapter = _make_adapter(_SESSION_UUID, tmp_path, jsonl_path, query='goal')
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


class TestMemoriesPipeline:
    def _make_pipeline_db(self, tmp_path: Path) -> Path:
        db_path = tmp_path / 'state_pipeline.sqlite'
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE stage1_outputs (
                thread_id TEXT PRIMARY KEY,
                source_updated_at INTEGER NOT NULL,
                raw_memory TEXT NOT NULL,
                rollout_summary TEXT NOT NULL,
                generated_at INTEGER NOT NULL,
                rollout_slug TEXT,
                usage_count INTEGER,
                last_usage INTEGER,
                selected_for_phase2 INTEGER NOT NULL DEFAULT 0,
                selected_for_phase2_source_updated_at INTEGER
            )
        """)
        conn.execute(
            "INSERT INTO stage1_outputs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('thread-aaa', 1716544800, 'raw memory text', 'Summary of session', 1716544900,
             'my-session-slug', 3, 1716545000, 1, None)
        )
        conn.execute(
            "INSERT INTO stage1_outputs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ('thread-bbb', 1716544700, 'another raw memory', 'Another summary', 1716544750,
             'other-session-slug', 0, None, 0, None)
        )
        conn.commit()
        conn.close()
        return db_path

    def _make_pipeline_adapter(self, tmp_path: Path) -> 'CodexAdapter':
        db_path = self._make_pipeline_db(tmp_path)
        adapter = CodexAdapter('memories/pipeline')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = db_path
        return adapter

    def test_pipeline_type(self, tmp_path):
        adapter = self._make_pipeline_adapter(tmp_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_memories_pipeline'

    def test_pipeline_stage1_count(self, tmp_path):
        adapter = self._make_pipeline_adapter(tmp_path)
        result = adapter.get_structure()
        assert result['stage1_total'] == 2

    def test_pipeline_stage2_selected(self, tmp_path):
        adapter = self._make_pipeline_adapter(tmp_path)
        result = adapter.get_structure()
        assert result['stage2_selected'] == 1

    def test_pipeline_recent_outputs(self, tmp_path):
        adapter = self._make_pipeline_adapter(tmp_path)
        result = adapter.get_structure()
        assert len(result['recent_outputs']) == 2

    def test_pipeline_output_has_slug(self, tmp_path):
        adapter = self._make_pipeline_adapter(tmp_path)
        result = adapter.get_structure()
        slugs = [r.get('rollout_slug') for r in result['recent_outputs']]
        assert 'my-session-slug' in slugs

    def test_pipeline_zero_when_empty(self, tmp_path):
        db_path = tmp_path / 'empty.sqlite'
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE stage1_outputs (
                thread_id TEXT PRIMARY KEY,
                source_updated_at INTEGER NOT NULL,
                raw_memory TEXT NOT NULL DEFAULT '',
                rollout_summary TEXT NOT NULL DEFAULT '',
                generated_at INTEGER NOT NULL DEFAULT 0,
                rollout_slug TEXT,
                usage_count INTEGER,
                last_usage INTEGER,
                selected_for_phase2 INTEGER NOT NULL DEFAULT 0,
                selected_for_phase2_source_updated_at INTEGER
            )
        """)
        conn.commit()
        conn.close()
        adapter = CodexAdapter('memories/pipeline')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = db_path
        result = adapter.get_structure()
        assert result['stage1_total'] == 0
        assert result['stage2_selected'] == 0
        assert result['recent_outputs'] == []

    def test_pipeline_contract(self, tmp_path):
        adapter = self._make_pipeline_adapter(tmp_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result

    def test_pipeline_contract_in_output_contract_suite(self, tmp_path):
        adapter = self._make_pipeline_adapter(tmp_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_memories_pipeline'
