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
from codex_session_fixture import (
    FIXTURE_JSONL as _FIXTURE_JSONL, FIXTURE_LINES as _FIXTURE_LINES, SESSION_UUID as _SESSION_UUID,
    make_sqlite_db as _make_sqlite_db, write_fixture_jsonl as _write_fixture_jsonl,
)

# BACK-1149: component-layer test -- single adapter/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


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

class TestSessionFilter:
    def test_filter_finds_match(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='filter=refactor')
        result = adapter.get_structure()
        assert result['type'] == 'codex_session_list'
        assert result['total'] == 1

    def test_filter_no_match(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='filter=zzznonexistent')
        result = adapter.get_structure()
        assert result['total'] == 0

    # -- since/until date scoping (BACK-945) --------------------------------
    # Fixture session's updated_at (1716544900) formats to 2024-05-24T10:01:40Z.

    def test_filter_since_includes_match_on_or_after(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='filter=refactor&since=2024-05-24')
        result = adapter.get_structure()
        assert result['total'] == 1
        assert result['since'] == '2024-05-24'

    def test_filter_since_excludes_match_before(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='filter=refactor&since=2024-05-25')
        result = adapter.get_structure()
        assert result['total'] == 0

    def test_filter_until_excludes_match_after(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='filter=refactor&until=2024-05-23')
        result = adapter.get_structure()
        assert result['total'] == 0

    def test_filter_until_includes_match_on_same_day(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='filter=refactor&until=2024-05-24')
        result = adapter.get_structure()
        assert result['total'] == 1

    def test_filter_since_today_resolves(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='filter=refactor&since=today')
        result = adapter.get_structure()
        # Fixture is from 2024 — "today" always excludes it.
        assert result['total'] == 0
        assert result['since'] != 'today'


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
# 11. ?search= — JSONL content search across sessions (renamed from ?content=, BACK-947)
# ---------------------------------------------------------------------------

class TestContentSearch:
    def test_content_search_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor')
        result = adapter.get_structure()
        assert result['type'] == 'codex_content_search'

    def test_content_search_finds_match(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor')
        result = adapter.get_structure()
        assert result['total'] == 1

    def test_content_search_no_match(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=xyzzy_no_match_xyz')
        result = adapter.get_structure()
        assert result['total'] == 0

    def test_content_search_has_snippets(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor')
        result = adapter.get_structure()
        session = result['sessions'][0]
        assert session['match_count'] >= 1
        assert any('refactor' in m['snippet'].lower() for m in session['matches'])

    def test_content_search_query_field(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor')
        result = adapter.get_structure()
        assert result['query'] == 'refactor'

    def test_content_search_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor')
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result

    # -- since/until date scoping (BACK-945) --------------------------------
    # Fixture session's updated_at (1716544900) formats to 2024-05-24T10:01:40Z.

    def test_content_search_since_includes_match_on_or_after(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor&since=2024-05-24')
        result = adapter.get_structure()
        assert result['total'] == 1

    def test_content_search_since_excludes_match_before(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor&since=2024-05-25')
        result = adapter.get_structure()
        assert result['total'] == 0

    def test_content_search_until_excludes_match_after(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor&until=2024-05-23')
        result = adapter.get_structure()
        assert result['total'] == 0


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
# 12b. codex://config?key= — dot-path drill-down (BACK-944)
# ---------------------------------------------------------------------------

class TestConfigKeyLookup:
    _TOML = (
        'model = "gpt-5.6-terra"\n'
        'model_reasoning_effort = "medium"\n'
        '\n'
        '[projects."/home/user/proj"]\n'
        'trust_level = "trusted"\n'
        '\n'
        '[secrets]\n'
        'api_key = "sk-verysecretvalue1234567890"\n'
    )

    def _adapter(self, tmp_path, resource='config', query=None):
        (tmp_path / 'config.toml').write_text(self._TOML, encoding='utf-8')
        adapter = CodexAdapter(resource, query=query)
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        return adapter

    def test_no_key_returns_full_config(self, tmp_path):
        result = self._adapter(tmp_path).get_structure()
        assert result['type'] == 'codex_config'
        assert result['config']['model'] == 'gpt-5.6-terra'

    def test_top_level_key(self, tmp_path):
        result = self._adapter(tmp_path, query='key=model').get_structure()
        assert result['key'] == 'model'
        assert result['value'] == 'gpt-5.6-terra'

    def test_nested_key(self, tmp_path):
        result = self._adapter(tmp_path, query='key=projects./home/user/proj.trust_level').get_structure()
        assert result['value'] == 'trusted'

    def test_missing_key_returns_none(self, tmp_path):
        result = self._adapter(tmp_path, query='key=does.not.exist').get_structure()
        assert result['value'] is None

    def test_key_lookup_does_not_unmask_secret(self, tmp_path):
        """?key= must read the masked dict, not raw parsed TOML — a secret must
        stay masked even when looked up directly by its dot-path (BACK-944)."""
        result = self._adapter(tmp_path, query='key=secrets.api_key').get_structure()
        assert result['value'] != 'sk-verysecretvalue1234567890'
        assert result['value'].endswith('***')

    def test_key_contract_fields(self, tmp_path):
        result = self._adapter(tmp_path, query='key=model').get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


# ---------------------------------------------------------------------------
# 12c. codex://skills, codex://plugins (BACK-946)
# ---------------------------------------------------------------------------

_SKILL_MD = (
    '---\n'
    'name: "test-skill"\n'
    'description: "A test skill for verifying discovery."\n'
    '---\n'
    '\n'
    '# Test Skill\n'
    '\n'
    'Body content here.\n'
)

_PLUGIN_JSON = (
    '{"name": "test-plugin", "version": "0.2.0", '
    '"description": "A test plugin for verifying discovery."}'
)


class TestSkillsResource:
    def _adapter(self, tmp_path, resource='skills'):
        skill_dir = tmp_path / 'skills' / 'vendor' / 'test-skill'
        skill_dir.mkdir(parents=True)
        (skill_dir / 'SKILL.md').write_text(_SKILL_MD, encoding='utf-8')
        adapter = CodexAdapter(resource)
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        return adapter

    def test_list_type(self, tmp_path):
        result = self._adapter(tmp_path).get_structure()
        assert result['type'] == 'codex_skills'

    def test_list_finds_nested_skill(self, tmp_path):
        result = self._adapter(tmp_path).get_structure()
        assert result['total'] == 1
        assert result['skills'][0]['name'] == 'test-skill'
        assert 'verifying discovery' in result['skills'][0]['description']

    def test_missing_dir_errors_not_crashes(self, tmp_path):
        adapter = CodexAdapter('skills')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        result = adapter.get_structure()
        assert result['total'] == 0
        assert 'error' in result

    def test_single_skill_read(self, tmp_path):
        result = self._adapter(tmp_path, resource='skills/test-skill').get_structure()
        assert result['type'] == 'codex_skill'
        assert result['name'] == 'test-skill'
        assert 'Body content here.' in result['content']

    def test_single_skill_not_found(self, tmp_path):
        result = self._adapter(tmp_path, resource='skills/nonexistent').get_structure()
        assert 'error' in result

    def test_list_contract_fields(self, tmp_path):
        result = self._adapter(tmp_path).get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


class TestPluginsResource:
    def _adapter(self, tmp_path, resource='plugins'):
        plugin_dir = tmp_path / 'plugins' / 'cache' / 'marketplace' / 'test-plugin' / '0.2.0' / '.codex-plugin'
        plugin_dir.mkdir(parents=True)
        (plugin_dir / 'plugin.json').write_text(_PLUGIN_JSON, encoding='utf-8')
        adapter = CodexAdapter(resource)
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        return adapter

    def test_list_type(self, tmp_path):
        result = self._adapter(tmp_path).get_structure()
        assert result['type'] == 'codex_plugins'

    def test_list_finds_cached_plugin(self, tmp_path):
        result = self._adapter(tmp_path).get_structure()
        assert result['total'] == 1
        assert result['plugins'][0]['name'] == 'test-plugin'
        assert result['plugins'][0]['version'] == '0.2.0'

    def test_missing_dir_errors_not_crashes(self, tmp_path):
        adapter = CodexAdapter('plugins')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = tmp_path / 'state_5.sqlite'
        result = adapter.get_structure()
        assert result['total'] == 0
        assert 'error' in result

    def test_single_plugin_read(self, tmp_path):
        result = self._adapter(tmp_path, resource='plugins/test-plugin').get_structure()
        assert result['type'] == 'codex_plugin'
        assert result['manifest']['description'] == 'A test plugin for verifying discovery.'

    def test_single_plugin_not_found(self, tmp_path):
        result = self._adapter(tmp_path, resource='plugins/nonexistent').get_structure()
        assert 'error' in result

    def test_list_contract_fields(self, tmp_path):
        result = self._adapter(tmp_path).get_structure()
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
        adapter = _make_adapter('sessions', tmp_path, jsonl_path, query='search=refactor')
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


# ---------------------------------------------------------------------------
# 14. digest / exchanges / message/<n> (BACK-943)
# Fixture has 1 user turn ("Help me refactor this module.") and 2 agent turns:
# "Sure, I'll start by reading the file." (idx 3) then "Refactoring complete!" (idx 10, last record).
# ---------------------------------------------------------------------------

class TestDigest:
    def test_digest_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/digest', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_digest'

    def test_digest_prompts(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/digest', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['prompt_count'] == 1
        assert result['prompts'][0]['message'] == 'Help me refactor this module.'

    def test_digest_narrative(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/digest', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['narrative_turn_count'] == 2
        assert result['assistant_narrative'][-1]['message'] == 'Refactoring complete!'

    def test_digest_has_overview_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/digest', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['title'] == 'Help me refactor this module.'
        assert result['user_turns'] == 1
        assert result['agent_turns'] == 2

    def test_digest_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/digest', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


class TestExchanges:
    def test_exchanges_type(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/exchanges', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_exchanges'

    def test_exchanges_count(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/exchanges', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['exchange_count'] == 1

    def test_exchanges_pairs_prompt_with_final_reply(self, tmp_path):
        """Answer must be the LAST agent turn before the next prompt, not the first —
        an agent often narrates an initial 'I'll start by...' before its real conclusion."""
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/exchanges', tmp_path, jsonl_path)
        result = adapter.get_structure()
        exchange = result['exchanges'][0]
        assert exchange['prompt'] == 'Help me refactor this module.'
        assert exchange['answer'] == 'Refactoring complete!'

    def test_exchanges_no_answer_is_none(self, tmp_path):
        # A session with a prompt but no agent reply at all.
        lines = [
            {'timestamp': '2026-05-24T10:00:00Z', 'type': 'event_msg',
             'payload': {'type': 'user_message', 'message': 'Hello?'}},
        ]
        jsonl_text = '\n'.join(json.dumps(line) for line in lines) + '\n'
        jsonl_path = tmp_path / 'rollout-no-answer.jsonl'
        jsonl_path.write_text(jsonl_text, encoding='utf-8')
        adapter = _make_adapter(f'{_SESSION_UUID}/exchanges', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['exchanges'][0]['answer'] is None

    def test_exchanges_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/exchanges', tmp_path, jsonl_path)
        result = adapter.get_structure()
        for field in ('contract_version', 'type', 'source', 'source_type'):
            assert field in result


class TestMessageByIndex:
    def test_message_zero_is_first_record(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/message/0', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['type'] == 'codex_message'
        assert result['record_index'] == 0
        assert result['record_type'] == 'session_meta'

    def test_message_negative_one_is_last_record(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/message/-1', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert result['payload_type'] == 'agent_message'
        assert result['record']['payload']['message'] == 'Refactoring complete!'

    def test_message_out_of_range_errors(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/message/999', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert 'error' in result

    def test_message_non_integer_errors(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/message/notanumber', tmp_path, jsonl_path)
        result = adapter.get_structure()
        assert 'error' in result

    def test_message_contract_fields(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        adapter = _make_adapter(f'{_SESSION_UUID}/message/0', tmp_path, jsonl_path)
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


# ---------------------------------------------------------------------------
# Regression tests — bugs found in review
# ---------------------------------------------------------------------------

def _make_nullable_rollout_db(tmp_path: Path, jsonl_path: Path) -> Path:
    """DB with a session whose rollout_path is SQL NULL (not empty string)."""
    db_path = tmp_path / 'state_null.sqlite'
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            rollout_path TEXT,
            created_at INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            first_user_message TEXT NOT NULL DEFAULT '',
            model TEXT,
            model_provider TEXT NOT NULL DEFAULT 'openai',
            tokens_used INTEGER NOT NULL DEFAULT 0,
            thread_source TEXT,
            archived INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Session with NULL rollout_path
    conn.execute(
        "INSERT INTO threads (id, rollout_path, title, first_user_message, tokens_used, thread_source, archived) "
        "VALUES ('null-session', NULL, 'null rollout', 'do something', 0, NULL, 0)"
    )
    # Session with valid rollout_path
    conn.execute(
        "INSERT INTO threads (id, rollout_path, title, first_user_message, tokens_used, thread_source, archived) "
        "VALUES ('valid-session', ?, 'refactor module', 'Help me refactor this module.', 620, NULL, 0)",
        (str(jsonl_path),)
    )
    conn.commit()
    conn.close()
    return db_path


class TestRegressionNullRolloutPath:
    """Regression: search_sessions must not crash on NULL rollout_path."""

    def test_null_rollout_path_does_not_crash(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        db_path = _make_nullable_rollout_db(tmp_path, jsonl_path)
        from reveal.adapters.codex.handlers.sessions import search_sessions
        result = search_sessions(db_path, 'refactor')
        assert result['type'] == 'codex_content_search'
        assert result['total'] >= 0

    def test_null_rollout_session_excluded_from_results(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        db_path = _make_nullable_rollout_db(tmp_path, jsonl_path)
        from reveal.adapters.codex.handlers.sessions import search_sessions
        result = search_sessions(db_path, 'refactor')
        ids = [s['id'] for s in result['sessions']]
        assert 'null-session' not in ids

    def test_valid_session_still_found(self, tmp_path):
        jsonl_path = _write_fixture_jsonl(tmp_path)
        db_path = _make_nullable_rollout_db(tmp_path, jsonl_path)
        from reveal.adapters.codex.handlers.sessions import search_sessions
        result = search_sessions(db_path, 'refactor')
        ids = [s['id'] for s in result['sessions']]
        assert 'valid-session' in ids


class TestRegressionContentSearchFalsePositive:
    """Regression: sessions with no user/agent message matches must be excluded."""

    def test_tool_only_match_not_in_results(self, tmp_path):
        # JSONL with term only in a function_call_output (not in user/agent message)
        tool_only_line = json.dumps({
            'timestamp': '2026-05-24T11:00:00Z', 'type': 'response_item',
            'payload': {'type': 'function_call_output', 'call_id': 'c1',
                        'output': 'unique_term_xyz appears here'}
        })
        jsonl_path = tmp_path / 'tool_only.jsonl'
        jsonl_path.write_text(tool_only_line + '\n', encoding='utf-8')

        db_path = tmp_path / 'state_tool.sqlite'
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE threads (
                id TEXT PRIMARY KEY, rollout_path TEXT,
                created_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT '',
                first_user_message TEXT NOT NULL DEFAULT '',
                model TEXT, model_provider TEXT NOT NULL DEFAULT 'openai',
                tokens_used INTEGER NOT NULL DEFAULT 0,
                thread_source TEXT, archived INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute(
            "INSERT INTO threads VALUES ('s1', ?, 0, 0, '', '', 'gpt-4', 'openai', 0, NULL, 0)",
            (str(jsonl_path),)
        )
        conn.commit()
        conn.close()

        from reveal.adapters.codex.handlers.sessions import search_sessions
        result = search_sessions(db_path, 'unique_term_xyz')
        assert result['total'] == 0, "Session with term only in tool output must not appear in results"


class TestRegressionGrandTotalCumulative:
    """Regression: grand_total must use total_token_usage (cumulative), not last_token_usage (per-request)."""

    def test_grand_total_uses_cumulative_not_last_delta(self, tmp_path):
        # Two token_count events:
        #   turn 1: last=500, cumulative=500
        #   turn 2: last=300 (per-request delta), cumulative=800 (grand total)
        lines = [
            json.dumps({'timestamp': 't1', 'type': 'event_msg', 'payload': {
                'type': 'token_count',
                'info': {
                    'last_token_usage': {'input_tokens': 400, 'output_tokens': 100, 'total_tokens': 500},
                    'total_token_usage': {'input_tokens': 400, 'output_tokens': 100, 'total_tokens': 500},
                }
            }}),
            json.dumps({'timestamp': 't2', 'type': 'event_msg', 'payload': {
                'type': 'token_count',
                'info': {
                    'last_token_usage': {'input_tokens': 200, 'output_tokens': 100, 'total_tokens': 300},
                    'total_token_usage': {'input_tokens': 600, 'output_tokens': 200, 'total_tokens': 800},
                }
            }}),
        ]
        jsonl_path = tmp_path / 'multi_turn.jsonl'
        jsonl_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

        db_path = _make_sqlite_db(tmp_path, jsonl_path)
        adapter = CodexAdapter(_SESSION_UUID, query='tokens')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = db_path
        result = adapter.get_structure()

        assert result['total_turns'] == 2
        assert result['grand_total'] == 800, (
            f"grand_total should be 800 (cumulative total_token_usage), got {result['grand_total']}"
        )

    def test_grand_total_not_last_turn_delta(self, tmp_path):
        # Verify grand_total != last turn's per-request delta when they differ
        lines = [
            json.dumps({'timestamp': 't1', 'type': 'event_msg', 'payload': {
                'type': 'token_count',
                'info': {
                    'last_token_usage': {'total_tokens': 500},
                    'total_token_usage': {'total_tokens': 500},
                }
            }}),
            json.dumps({'timestamp': 't2', 'type': 'event_msg', 'payload': {
                'type': 'token_count',
                'info': {
                    'last_token_usage': {'total_tokens': 300},
                    'total_token_usage': {'total_tokens': 800},
                }
            }}),
        ]
        jsonl_path = tmp_path / 'multi2.jsonl'
        jsonl_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

        db_path = _make_sqlite_db(tmp_path, jsonl_path)
        adapter = CodexAdapter(_SESSION_UUID, query='tokens')
        adapter.CODEX_HOME = tmp_path
        adapter.CODEX_DB = db_path
        result = adapter.get_structure()

        assert result['grand_total'] != 300, "grand_total must not equal last-turn per-request delta"
        assert result['grand_total'] == 800


class TestRegressionTokensUsedZero:
    """Regression: tokens_used=0 in SQLite must not be replaced by JSONL-derived total."""

    def test_zero_tokens_used_not_overridden(self, tmp_path):
        from reveal.adapters.codex.analysis.overview import get_overview
        # Session row with explicit 0 (e.g. aborted session)
        session_row = {'tokens_used': 0, 'title': 'test', 'model': 'gpt-4',
                       'model_provider': 'openai', 'reasoning_effort': None, 'cwd': '/tmp',
                       'approval_mode': None, 'cli_version': None, 'git_branch': None}
        # Records with some token events
        records = [{'timestamp': 't1', 'type': 'event_msg', 'payload': {
            'type': 'token_count',
            'info': {'total_token_usage': {'total_tokens': 999}}
        }}]
        result = get_overview(records, session_row)
        assert result['tokens_used'] == 0, (
            f"tokens_used=0 must not be replaced by JSONL total, got {result['tokens_used']}"
        )


class TestRegressionCliFlags:
    """Regression: _render_schema_cli_flags must handle dict-format cli_flags."""

    def test_dict_cli_flags_renders_without_crash(self, capsys):
        from reveal.rendering.adapters.help import _render_schema_cli_flags
        flags = {
            '--all': {'description': 'Return all results', 'applies_to': ['claude://sessions/?search=']},
            '--base-path': {'description': 'Override the sessions base directory'},
        }
        _render_schema_cli_flags(flags)
        out = capsys.readouterr().out
        assert '--all' in out
        assert '--base-path' in out

    def test_dict_cli_flags_includes_descriptions(self, capsys):
        from reveal.rendering.adapters.help import _render_schema_cli_flags
        flags = {'--all': {'description': 'Return all results'}}
        _render_schema_cli_flags(flags)
        out = capsys.readouterr().out
        assert 'Return all results' in out

    def test_list_cli_flags_still_works(self, capsys):
        from reveal.rendering.adapters.help import _render_schema_cli_flags
        _render_schema_cli_flags(['--json', '--verbose'])
        out = capsys.readouterr().out
        assert '--json' in out
        assert '--verbose' in out


# ---------------------------------------------------------------------------
# BACK-1604: --head/--tail/--range slice the list each codex view returns
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('result_type, field', [
    ('codex_session_list', 'sessions'), ('codex_history', 'entries'),
    ('codex_memories', 'memories'), ('codex_rules', 'rules'), ('codex_skills', 'skills'),
    ('codex_messages', 'messages'), ('codex_tools', 'tools'), ('codex_errors', 'errors'),
    ('codex_timeline', 'events'), ('codex_exchanges', 'exchanges'), ('codex_tokens', 'token_turns'),
])
def test_head_slices_each_codex_views_list(result_type, field, capsys):
    """Undeclared, the router's probe found none of these names: 'codex://sessions/ --head 3'
    printed "no list to slice" and returned every session."""
    from argparse import Namespace
    from reveal.cli.routing.uri import _apply_head_tail_range
    result = {'type': result_type, field: [1, 2, 3]}
    out = _apply_head_tail_range(result, Namespace(head=1, tail=None, range=None),
                                 adapter=CodexAdapter, scheme='codex')
    assert out[field] == [1]
    assert 'no list to slice' not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# token_count with "info": null -- the overview of 29 of 138 real sessions crashed
# ---------------------------------------------------------------------------

_NULL_INFO = {'timestamp': '2026-04-26T00:00:01Z', 'type': 'event_msg',
              'payload': {'type': 'token_count', 'info': None, 'rate_limits': {}}}
_REAL_INFO = {'timestamp': '2026-04-26T00:00:02Z', 'type': 'event_msg',
              'payload': {'type': 'token_count', 'info': {
                  'total_token_usage': {'total_tokens': 1234},
                  'last_token_usage': {'input_tokens': 10, 'total_tokens': 12}}}}


def test_overview_survives_a_token_count_with_null_info():
    """Codex writes "info": null before any usage is known; .get('info', {}) returned None
    and every reader raised AttributeError."""
    from reveal.adapters.codex.analysis.overview import get_overview
    assert get_overview([_NULL_INFO, _REAL_INFO, _NULL_INFO], {})['tokens_used'] == 1234


def test_token_readers_survive_null_info():
    from reveal.adapters.codex.analysis.messages import get_grand_total_tokens, get_token_turns
    from reveal.adapters.codex.analysis.timeline import get_timeline
    assert get_grand_total_tokens([_REAL_INFO, _NULL_INFO]) == 1234
    turns = get_token_turns([_NULL_INFO, _REAL_INFO])
    assert [t.get('input_tokens') for t in turns] == [None, 10]
    assert len(get_timeline([_NULL_INFO, _REAL_INFO])) == 2



# ---------------------------------------------------------------------------
# Rollout fidelity, validated against all 138 real sessions (kinetic-nightmare-1001):
# shell commands in rollouts without exec_command_end, web/tool searches as tool calls,
# rolled-back turns, quoted search terms, config secrets, the memories pipeline DB.
# ---------------------------------------------------------------------------

from reveal.adapters.codex.analysis.normalize import mark_rolled_back, normalize_record  # noqa: E402
from reveal.adapters.codex.analysis.tools import (  # noqa: E402
    get_shell_commands, unrecorded_exec_scripts)
from reveal.adapters.codex.analysis.overview import get_overview  # noqa: E402
from reveal.adapters.codex.analysis.messages import get_exchanges, extract_messages  # noqa: E402


def _ri(ts, payload):
    return normalize_record({'timestamp': ts, 'type': 'response_item', 'payload': payload})


def _ev(ts, payload):
    return normalize_record({'timestamp': ts, 'type': 'event_msg', 'payload': payload})


def _call(ts, cid, name, args):
    return _ri(ts, {'type': 'function_call', 'call_id': cid, 'name': name, 'arguments': json.dumps(args)})


def _out(ts, cid, text):
    return _ri(ts, {'type': 'function_call_output', 'call_id': cid, 'output': text})


# A rollout that never wrote exec_command_end (78 of 138 real ones)
_NO_END = [
    _call('t1', 'c1', 'exec_command', {'cmd': 'false', 'workdir': '/w'}),
    _out('t1', 'c1', 'Chunk ID: a\nWall time: 0.5000 seconds\nProcess exited with code 2\n'
                     'Original token count: 1\nOutput:\nboom'),
    _call('t2', 'c2', 'exec_command', {'cmd': 'sleep 9'}),
    _out('t2', 'c2', 'Chunk ID: b\nWall time: 1.0000 seconds\nProcess running with session ID 77\nOutput:\n'),
    _call('t3', 'c3', 'write_stdin', {'session_id': 77, 'chars': ''}),
    _out('t3', 'c3', 'Chunk ID: c\nWall time: 8.0 seconds\nProcess exited with code 0\nOutput:\n'),
    _call('t4', 'c4', 'exec_command', {'cmd': 'tia search'}),
    _out('t4', 'c4', 'aborted by user after 3.0s'),
    _ri('t5', {'type': 'custom_tool_call', 'call_id': 'c5', 'name': 'exec', 'input': 'await tools.exec_command({})'}),
    _ri('t5', {'type': 'custom_tool_call_output', 'call_id': 'c5', 'output': 'Script completed'}),
]


class TestShellCommandsWithoutEndEvents:
    def test_rebuilt_from_exec_command_calls(self):
        cmds = get_shell_commands(_NO_END)
        assert [c['command'][2] for c in cmds] == ['false', 'sleep 9', 'tia search']
        assert [c['exit_code'] for c in cmds] == [2, 0, None]  # 0 from the write_stdin poll
        assert [c['status'] for c in cmds] == ['completed', 'completed', 'aborted']
        assert cmds[0]['duration'] == {'secs': 0, 'nanos': 500000000}
        assert cmds[0]['aggregated_output'] == 'boom'
        assert cmds[0]['cwd'] == '/w'

    def test_exec_scripts_are_counted_as_unrecorded(self):
        assert unrecorded_exec_scripts(_NO_END) == 1

    def test_recorded_end_events_win(self):
        recs = _NO_END + [_ev('t9', {'type': 'exec_command_end', 'call_id': 'e1', 'command': ['ls'], 'exit_code': 0})]
        assert [c['call_id'] for c in get_shell_commands(recs)] == ['e1']
        assert unrecorded_exec_scripts(recs) == 0

    def test_overview_counts_match_the_lists(self):
        ov = get_overview(_NO_END, {})
        assert ov['shell_calls'] == 3
        assert ov['tool_calls'] == 5  # exec_command x3, write_stdin, exec


class TestSearchesAreToolCalls:
    def test_web_and_tool_search(self):
        from reveal.adapters.codex.analysis.tools import get_tool_pairs
        recs = [
            _ri('t1', {'type': 'web_search_call', 'status': 'completed',
                       'action': {'type': 'search', 'query': 'codex rollout format'}}),
            _ri('t2', {'type': 'tool_search_call', 'call_id': 's1', 'arguments': {'query': 'x'}}),
            _ri('t2', {'type': 'tool_search_output', 'call_id': 's1', 'tools': []}),
        ]
        pairs = get_tool_pairs(recs)
        assert [p['call']['name'] for p in pairs] == ['web_search', 'tool_search']
        assert 'codex rollout format' in pairs[0]['call']['arguments']
        assert pairs[0]['output']['output'] == 'status: completed'
        assert pairs[1]['output'] is not None
        assert get_overview(recs, {})['tool_calls'] == 2


def test_rolled_back_turns_are_marked():
    recs = mark_rolled_back([
        _ev('t1', {'type': 'task_started'}), _ev('t1', {'type': 'user_message', 'message': 'a'}),
        _ev('t2', {'type': 'agent_message', 'message': 'A'}), _ev('t2', {'type': 'task_complete'}),
        _ev('t3', {'type': 'task_started'}), _ev('t3', {'type': 'user_message', 'message': 'b'}),
        _ev('t4', {'type': 'turn_aborted'}), _ev('t4', {'type': 'thread_rolled_back', 'num_turns': 1}),
        _ev('t5', {'type': 'task_started'}), _ev('t5', {'type': 'user_message', 'message': 'c'}),
    ])
    assert [(e['prompt'], e.get('rolled_back', False)) for e in get_exchanges(recs)] == \
        [('a', False), ('b', True), ('c', False)]
    assert [m.get('rolled_back', False) for m in extract_messages(recs)] == [False, False, True, False]


def test_search_finds_a_term_containing_a_quote(tmp_path):
    """The raw line stores '"' as '\\"'; matching the plain term on it found nothing."""
    from reveal.adapters.codex.handlers.sessions import search_sessions
    rollout = tmp_path / 'r.jsonl'
    rollout.write_text(json.dumps({'timestamp': 't', 'type': 'event_msg', 'payload': {
        'type': 'user_message', 'message': 'name it "awkwardly" named'}}) + '\n', encoding='utf-8')
    db = _make_sqlite_db(tmp_path, rollout)
    assert search_sessions(db, 'awkwardly" named')['total'] == 1
    assert search_sessions(db, 'awkwardly')['total'] == 1


_FAKE_CONFIG = '''
model = "gpt-5.5"
openai_api_key = "sk-FAKESECRET-toplevel-111111"
[mcp_servers.github]
command = "npx"
args = ["-y", "server-github", "--token", "ghp_FAKESECRET_in_args_222222", "--api-key=sk-FAKESECRET-inline-333333"]
[mcp_servers.github.env]
GITHUB_PERSONAL_ACCESS_TOKEN = "ghp_FAKESECRET_env_444444"
ANTHROPIC_KEY = "sk-ant-FAKESECRET-555555"
DATABASE_URL = "postgres://admin:FAKESECRETpw666666@db.example:5432/app"
[mcp_servers.remote]
url = "https://mcp.example/sse"
http_headers = { Authorization = "Bearer FAKESECRET-header-777777", "X-Api-Key" = "FAKESECRET-xapikey-888888" }
'''


class TestConfigSecrets:
    def test_no_secret_survives_anywhere_in_the_config(self, tmp_path):
        """Masking by key name alone printed 4 of these 8 in full."""
        from reveal.adapters.codex.handlers.system import get_config
        (tmp_path / 'config.toml').write_text(_FAKE_CONFIG, encoding='utf-8')
        out = json.dumps(get_config(tmp_path))
        assert out.count('FAKESECRET') == 0, out
        cfg = get_config(tmp_path)['config']
        assert cfg['model'] == 'gpt-5.5'
        assert cfg['mcp_servers']['github']['args'][:3] == ['-y', 'server-github', '--token']
        assert cfg['mcp_servers']['github']['env']['DATABASE_URL'] == 'postgres://admin:***@db.example:5432/app'
        assert cfg['mcp_servers']['remote']['url'] == 'https://mcp.example/sse'

    def test_key_drilldown_is_masked_too(self, tmp_path):
        from reveal.adapters.codex.handlers.system import get_config
        (tmp_path / 'config.toml').write_text(_FAKE_CONFIG, encoding='utf-8')
        assert 'FAKESECRET' not in json.dumps(get_config(tmp_path, {'key': 'mcp_servers.github.args'}))

    @pytest.mark.parametrize('obj', [
        {'keyboard_layout': 'us-intl-alt'}, {'note': 'see task-list-items'},
        {'url': 'https://example.com/path'}, {'args': ['--verbose', 'value-after-plain-flag']},
    ])
    def test_ordinary_values_are_left_alone(self, obj):
        from reveal.utils.secrets import redact_secrets
        assert redact_secrets(obj) == obj


def test_memories_pipeline_reads_memories_db(tmp_path):
    """Current Codex keeps stage1_outputs in memories_1.sqlite; the state DB has no such table."""
    conn = sqlite3.connect(str(tmp_path / 'memories_1.sqlite'))
    conn.execute('CREATE TABLE stage1_outputs (thread_id TEXT, source_updated_at INTEGER, rollout_slug TEXT, '
                 'generated_at INTEGER, selected_for_phase2 INTEGER, usage_count INTEGER, last_usage INTEGER)')
    conn.execute("INSERT INTO stage1_outputs VALUES ('t1', 1, 'slug', 1, 1, 0, NULL)")
    conn.commit()
    conn.close()
    adapter = _make_adapter('memories/pipeline', tmp_path, _write_fixture_jsonl(tmp_path))
    result = adapter.get_structure()
    assert 'error' not in result
    assert result['stage1_total'] == 1


def test_text_view_prints_meta_warnings(capsys):
    from reveal.adapters.codex.renderer import CodexRenderer
    CodexRenderer._render_text({'type': 'codex_shell', 'shell_calls': [], 'total': 0,
                                'meta': {'warnings': [{'type': 'unrecorded_commands', 'count': 2,
                                                       'message': '2 exec script call(s) ran shell commands'}]}})
    assert '2 exec script call(s) ran shell commands' in capsys.readouterr().out
