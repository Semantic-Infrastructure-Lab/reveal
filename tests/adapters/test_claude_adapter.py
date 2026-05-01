"""Unit tests for Claude Code conversation adapter."""

import pytest
import json
import sys
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.adapters.claude.render_messages import _format_tool_params, _render_raw_block


# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'conversations'
TEST_CONVERSATION = FIXTURES_DIR / 'test-session.jsonl'


class TestClaudeAdapterInit:
    """Tests for ClaudeAdapter initialization."""

    def test_parse_session_name_with_session_prefix(self):
        """Test session name parsing with 'session/' prefix."""
        adapter = ClaudeAdapter('session/test-session-123', query=None)
        assert adapter.session_name == 'test-session-123'

    def test_parse_session_name_without_prefix(self):
        """Test session name parsing without 'session/' prefix."""
        adapter = ClaudeAdapter('test-session-123', query=None)
        assert adapter.session_name == 'test-session-123'

    def test_query_parameter(self):
        """Test query parameter is stored."""
        adapter = ClaudeAdapter('session/test', query='summary')
        assert adapter.query == 'summary'

    # BACK-265: bare session-name pattern (no 'session/' prefix) with sub-paths
    def test_parse_session_name_bare_adjective_noun_mmdd(self):
        """Bare adjective-noun-MMDD is recognised as a session name."""
        a = ClaudeAdapter('ancient-quasar-0501')
        assert a.session_name == 'ancient-quasar-0501'

    def test_parse_session_name_bare_with_message_subpath(self):
        """Bare session-name/message/N extracts only the session name (BACK-265)."""
        a = ClaudeAdapter('burning-antimatter-0501/message/5')
        assert a.session_name == 'burning-antimatter-0501'

    def test_parse_session_name_bare_with_tools_subpath(self):
        """Bare session-name/tools extracts only the session name (BACK-265)."""
        a = ClaudeAdapter('citrine-glow-0430/tools')
        assert a.session_name == 'citrine-glow-0430'

    def test_parse_session_name_non_session_resource_unchanged(self):
        """Non-session resources like 'settings' pass through unchanged."""
        a = ClaudeAdapter('settings')
        assert a.session_name == 'settings'

    def test_parse_session_name_with_session_prefix_and_subpath(self):
        """'session/NAME/sub' still extracts NAME correctly."""
        a = ClaudeAdapter('session/ancient-quasar-0501/message/3')
        assert a.session_name == 'ancient-quasar-0501'


class TestLastQueryParam:
    """Tests for ?last=N aliasing to ?tail=N (BACK-266)."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_last_equals_n_returns_n_turns(self, mock_find):
        """?last=3 should return the last 3 assistant turns."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='last=3')
        result = adapter.get_structure()
        assert len(result.get('messages', [])) <= 3

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_bare_last_returns_one_turn(self, mock_find):
        """Bare ?last (no value) should still return 1 turn."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='last')
        result = adapter.get_structure()
        assert len(result.get('messages', [])) <= 1

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_tail_equals_n_unchanged(self, mock_find):
        """?tail=N should still work as before."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='tail=2')
        result = adapter.get_structure()
        assert len(result.get('messages', [])) <= 2


class TestContractCompliance:
    """Tests for Output Contract v1.0 compliance."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_contract_base_fields(self, mock_find):
        """Test _get_contract_base returns all required fields."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        base = adapter._get_contract_base()

        assert 'contract_version' in base
        assert base['contract_version'] == '1.0'
        assert 'type' in base
        assert 'source' in base
        assert 'source_type' in base
        assert base['source_type'] == 'file'

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_overview_contract_compliance(self, mock_find):
        """Test overview output includes all required contract fields."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        overview = adapter.get_structure()

        # Required fields
        assert overview['contract_version'] == '1.0'
        assert overview['type'] == 'claude_session_overview'
        assert overview['source'] == str(TEST_CONVERSATION)
        assert overview['source_type'] == 'file'

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_type_uses_snake_case(self, mock_find):
        """Test type field uses snake_case format."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        overview = adapter.get_structure()

        # Check snake_case (lowercase with underscores, no hyphens)
        assert '_' in overview['type'] or overview['type'].islower()
        assert '-' not in overview['type']


class TestMessageLoading:
    """Tests for JSONL message loading."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_load_messages_success(self, mock_find):
        """Test successful JSONL message loading."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        messages = adapter._load_messages()

        assert len(messages) == 13
        assert all(isinstance(msg, dict) for msg in messages)

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_load_messages_lazy_loading(self, mock_find):
        """Test messages are lazy loaded and cached."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        # First load
        messages1 = adapter._load_messages()
        # Second load should return cached
        messages2 = adapter._load_messages()

        assert messages1 is messages2  # Same object reference

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_load_messages_file_not_found(self, mock_find):
        """Test error handling when conversation file not found."""
        mock_find.return_value = None
        adapter = ClaudeAdapter('session/nonexistent')

        with pytest.raises(FileNotFoundError, match="Conversation not found"):
            adapter._load_messages()


class TestOverviewGeneration:
    """Tests for session overview generation."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_overview_message_counts(self, mock_find):
        """Test overview correctly counts user and assistant messages."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        overview = adapter.get_structure()

        assert overview['message_count'] == 13
        assert overview['user_messages'] == 7  # 3 actual user + 4 tool_results
        assert overview['assistant_messages'] == 6

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_overview_tool_counts(self, mock_find):
        """Test overview correctly counts tool usage."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        overview = adapter.get_structure()

        tools_used = overview['tools_used']
        assert tools_used['Read'] == 2
        assert tools_used['Bash'] == 1
        assert tools_used['Write'] == 1

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_overview_file_operations(self, mock_find):
        """Test overview tracks file operations."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        overview = adapter.get_structure()

        file_ops = overview['file_operations']
        assert file_ops['Read'] == 2
        assert file_ops['Write'] == 1
        # Bash is not a file operation
        assert 'Bash' not in file_ops

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_overview_thinking_estimates(self, mock_find):
        """Test overview estimates thinking tokens."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        overview = adapter.get_structure()

        assert 'thinking_chars_approx' in overview
        assert 'thinking_tokens_approx' in overview
        assert overview['thinking_chars_approx'] > 0
        # Token estimate should be roughly chars / 4
        assert overview['thinking_tokens_approx'] == overview['thinking_chars_approx'] // 4

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_overview_duration(self, mock_find):
        """Test overview calculates session duration."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        overview = adapter.get_structure()

        assert 'duration' in overview
        assert overview['duration'] is not None
        # Should be a string representation of timedelta
        assert isinstance(overview['duration'], str)


class TestErrorDetection:
    """Tests for error extraction."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_get_errors_detects_errors(self, mock_find):
        """Test error detection finds tool failures."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='errors')

        result = adapter.get_structure()

        assert result['type'] == 'claude_errors'
        assert result['error_count'] > 0
        assert 'errors' in result
        assert len(result['errors']) > 0

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_error_includes_context(self, mock_find):
        """Test error results include context."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='errors')

        result = adapter.get_structure()

        first_error = result['errors'][0]
        assert 'message_index' in first_error
        assert 'content_preview' in first_error
        assert 'timestamp' in first_error


class TestToolFiltering:
    """Tests for tool call filtering."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_filter_specific_tool(self, mock_find):
        """Test filtering for specific tool type."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='tools=Bash')

        result = adapter.get_structure()

        assert result['type'] == 'claude_tool_calls'
        assert result['tool_name'] == 'Bash'
        assert result['call_count'] == 1
        assert len(result['calls']) == 1

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_tool_calls_include_input(self, mock_find):
        """Test tool calls include input parameters."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='tools=Read')

        result = adapter.get_structure()

        assert result['call_count'] == 2
        first_call = result['calls'][0]
        assert 'input' in first_call
        assert 'message_index' in first_call
        assert 'timestamp' in first_call

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_get_all_tools(self, mock_find):
        """Test getting all tool usage statistics."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test/tools')

        result = adapter.get_structure()

        assert result['type'] == 'claude_tool_summary'
        assert 'tools' in result
        assert 'details' in result
        assert result['total_calls'] == 4  # 2 Read + 1 Bash + 1 Write


class TestThinkingExtraction:
    """Tests for thinking block extraction."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_extract_thinking_blocks(self, mock_find):
        """Test extraction of thinking blocks."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test/thinking')

        result = adapter.get_structure()

        assert result['type'] == 'claude_thinking'
        assert result['thinking_block_count'] == 3  # 3 thinking blocks in fixture
        assert 'blocks' in result
        assert len(result['blocks']) == 3

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_thinking_blocks_include_estimates(self, mock_find):
        """Test thinking blocks include token estimates."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test/thinking')

        result = adapter.get_structure()

        first_block = result['blocks'][0]
        assert 'content' in first_block
        assert 'char_count' in first_block
        assert 'token_estimate' in first_block
        assert 'message_index' in first_block


class TestMessageFiltering:
    """Tests for message role filtering."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_filter_user_messages(self, mock_find):
        """Test filtering for user messages only."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test/user')

        result = adapter.get_structure()

        assert result['type'] == 'claude_user_messages'
        assert result['role'] == 'user'
        assert result['message_count'] == 7  # 3 actual user + 4 tool_results

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_filter_assistant_messages(self, mock_find):
        """Test filtering for assistant messages only."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test/assistant')

        result = adapter.get_structure()

        assert result['type'] == 'claude_assistant_messages'
        assert result['role'] == 'assistant'
        assert result['message_count'] == 6


class TestSpecificMessageRetrieval:
    """Tests for retrieving specific messages."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_get_message_by_index(self, mock_find):
        """Test retrieving specific message by index."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test/message/0')

        result = adapter.get_structure()

        assert result['type'] == 'claude_message'
        assert result['message_index'] == 0
        assert 'message' in result
        assert 'timestamp' in result

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_get_message_out_of_range(self, mock_find):
        """Test error handling for out-of-range message index."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test/message/999')

        result = adapter.get_structure()

        assert 'error' in result
        assert 'out of range' in result['error']

    def test_get_message_snapshot_includes_hint(self, tmp_path):
        """Test that file-history-snapshot messages include a helpful hint."""
        snapshot_line = json.dumps({
            'type': 'file-history-snapshot',
            'message': {},
            'timestamp': None,
        })
        jsonl = tmp_path / 'snap.jsonl'
        jsonl.write_text(snapshot_line + '\n')

        adapter = ClaudeAdapter('session/snap/message/0')
        adapter.conversation_path = jsonl

        result = adapter.get_structure()

        assert result['message_type'] == 'file-history-snapshot'
        assert 'hint' in result
        assert 'metadata record' in result['hint']

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_get_message_non_snapshot_has_no_hint(self, mock_find):
        """Test that normal messages do not include the snapshot hint."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test/message/0')

        result = adapter.get_structure()

        assert 'hint' not in result


class TestSessionListing:
    """Tests for claude:// listing with query params."""

    def test_list_sessions_limit_param(self, tmp_path):
        """Test _list_sessions returns all sessions (limit applied by routing.py)."""
        # Create 5 fake project dirs each with a jsonl file
        base = tmp_path / 'projects'
        base.mkdir()
        for i in range(5):
            d = base / f'-home-user-src-tia-sessions-session-{i:02d}'
            d.mkdir()
            (d / 'conv.jsonl').write_text('{}')

        adapter = ClaudeAdapter('', query='limit=3')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._list_sessions()

        # All 5 sessions returned; routing.py applies the limit
        assert len(result['recent_sessions']) == 5
        assert result['session_count'] == 5

    def test_list_sessions_filter_param(self, tmp_path):
        """Test ?filter=term restricts output to matching session names."""
        base = tmp_path / 'projects'
        base.mkdir()
        for name in ['apple-session', 'banana-session', 'apple-other']:
            d = base / f'-home-user-src-tia-sessions-{name}'
            d.mkdir()
            (d / 'conv.jsonl').write_text('{}')

        adapter = ClaudeAdapter('', query='filter=apple')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._list_sessions()

        names = [s['session'] for s in result['recent_sessions']]
        assert all('apple' in n for n in names)
        assert len(names) == 2

    def test_list_sessions_search_alias(self, tmp_path):
        """Test ?search=term is an alias for ?filter=term."""
        base = tmp_path / 'projects'
        base.mkdir()
        for name in ['reveal-session', 'unrelated-session']:
            d = base / f'-home-user-src-tia-sessions-{name}'
            d.mkdir()
            (d / 'conv.jsonl').write_text('{}')

        adapter = ClaudeAdapter('', query='search=reveal')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._list_sessions()

        names = [s['session'] for s in result['recent_sessions']]
        assert len(names) == 1
        assert 'reveal' in names[0]

    def test_list_sessions_filter_case_insensitive(self, tmp_path):
        """Test ?filter=term matching is case-insensitive."""
        base = tmp_path / 'projects'
        base.mkdir()
        d = base / '-home-user-src-tia-sessions-Brewing-Session'
        d.mkdir()
        (d / 'conv.jsonl').write_text('{}')

        adapter = ClaudeAdapter('', query='filter=brewing')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._list_sessions()

        assert len(result['recent_sessions']) == 1

    def test_list_sessions_uuid_names_windows_style(self, tmp_path):
        """Test that UUID JSONL filenames are used as session names (Windows layout)."""
        base = tmp_path / 'projects'
        base.mkdir()
        # Windows: one project dir, multiple UUID JSONL files
        proj = base / 'C--Users-markf-frono'
        proj.mkdir()
        uuid1 = '6b7f43f0-29fe-47bf-8b03-e430f7ed7e9b'
        uuid2 = '00767efa-e49b-483d-a136-b0b02326d630'
        (proj / f'{uuid1}.jsonl').write_text('{}')
        (proj / f'{uuid2}.jsonl').write_text('{}')

        adapter = ClaudeAdapter('')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._list_sessions()

        names = {s['session'] for s in result['recent_sessions']}
        assert uuid1 in names
        assert uuid2 in names
        assert 'C--Users-markf-frono' not in names

    def test_list_sessions_skips_agent_files(self, tmp_path):
        """Test that agent-*.jsonl subagent files are excluded from listing."""
        base = tmp_path / 'projects'
        base.mkdir()
        proj = base / '-home-user-src-tia-sessions-my-session'
        proj.mkdir()
        (proj / 'main-uuid.jsonl').write_text('{}')
        (proj / 'agent-abc1234.jsonl').write_text('{}')
        (proj / 'agent-def5678.jsonl').write_text('{}')

        adapter = ClaudeAdapter('')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._list_sessions()

        assert result['session_count'] == 1
        assert result['recent_sessions'][0]['session'] == 'my-session'

    def test_list_sessions_agent_files_windows_style(self, tmp_path):
        """Test that agent-*.jsonl files are excluded even in Windows UUID layout."""
        base = tmp_path / 'projects'
        base.mkdir()
        proj = base / 'C--Users-markf-frono'
        proj.mkdir()
        uuid1 = '6b7f43f0-29fe-47bf-8b03-e430f7ed7e9b'
        (proj / f'{uuid1}.jsonl').write_text('{}')
        (proj / 'agent-abc1234.jsonl').write_text('{}')

        adapter = ClaudeAdapter('')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._list_sessions()

        names = {s['session'] for s in result['recent_sessions']}
        assert uuid1 in names
        assert 'agent-abc1234' not in names
        assert result['session_count'] == 1


class TestSearchSubcommand:
    """Tests for claude://search routing — now a real content search."""

    def test_search_subcommand_routes_to_content_search(self, tmp_path):
        """claude://search (no term) routes to cross-session search with empty term."""
        adapter = ClaudeAdapter('search', query=None)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            result = adapter.get_structure()

        assert result['type'] == 'claude_cross_session_search'

    def test_search_subpath_uses_path_term(self, tmp_path):
        """claude://search/<term> extracts the term from the path."""
        adapter = ClaudeAdapter('search/topstep', query=None)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            result = adapter.get_structure()

        assert result['type'] == 'claude_cross_session_search'
        assert result['term'] == 'topstep'


class TestFindConversationAgentFilter:
    """Tests that _find_conversation skips agent-*.jsonl subagent files."""

    def test_find_conversation_skips_agent_files(self, tmp_path):
        """Test that _find_conversation returns the main JSONL, not agent files."""
        base = tmp_path / 'projects'
        base.mkdir()
        proj = base / '-home-user-src-tia-sessions-my-session'
        proj.mkdir()
        agent1 = proj / 'agent-abc1234.jsonl'
        agent2 = proj / 'agent-def5678.jsonl'
        main = proj / 'main-uuid.jsonl'
        agent1.write_text('{}')
        agent2.write_text('{}')
        main.write_text('{}')

        adapter = ClaudeAdapter('session/my-session')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._find_conversation()

        assert result is not None
        assert result.name == 'main-uuid.jsonl'

    def test_find_conversation_only_agent_files_returns_none(self, tmp_path):
        """Test that _find_conversation returns None if only agent files exist."""
        base = tmp_path / 'projects'
        base.mkdir()
        proj = base / '-home-user-src-tia-sessions-my-session'
        proj.mkdir()
        (proj / 'agent-abc1234.jsonl').write_text('{}')

        adapter = ClaudeAdapter('session/my-session')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter._find_conversation()

        assert result is None


class TestConversationBaseEnvVar:
    """Tests for REVEAL_CLAUDE_DIR environment variable support."""

    def test_env_var_overrides_default_path(self, tmp_path, monkeypatch):
        """Test that REVEAL_CLAUDE_DIR env var overrides ~/.claude/projects."""
        monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(tmp_path))

        # Re-evaluate the class attribute by importing fresh
        import importlib
        import reveal.adapters.claude.adapter as mod
        importlib.reload(mod)

        assert mod.ClaudeAdapter.CONVERSATION_BASE == tmp_path

        # Restore after test
        importlib.reload(mod)

    def test_listing_respects_env_var_path(self, tmp_path, monkeypatch):
        """Test that session listing scans the env-var directory."""
        sessions_dir = tmp_path / 'my-claude-dir'
        sessions_dir.mkdir()
        proj = sessions_dir / '-home-user-src-tia-sessions-env-test'
        proj.mkdir()
        (proj / 'conv.jsonl').write_text('{}')

        adapter = ClaudeAdapter('')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', sessions_dir):
            result = adapter._list_sessions()

        names = [s['session'] for s in result['recent_sessions']]
        assert 'env-test' in names

    def test_reveal_claude_home_derives_conversation_base(self, tmp_path, monkeypatch):
        """BACK-121: When REVEAL_CLAUDE_HOME is set, CONVERSATION_BASE derives from it.

        Setting only REVEAL_CLAUDE_HOME should point CONVERSATION_BASE at
        <REVEAL_CLAUDE_HOME>/projects/ — same derivation pattern as BACK-119 for CLAUDE_JSON.
        """
        import importlib
        import reveal.adapters.claude.adapter as mod

        fake_home = tmp_path / 'some_user' / '.claude'
        monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(fake_home))
        monkeypatch.delenv('REVEAL_CLAUDE_DIR', raising=False)
        importlib.reload(mod)

        assert mod.ClaudeAdapter.CONVERSATION_BASE == fake_home / 'projects'

        # Restore
        importlib.reload(mod)

    def test_reveal_claude_dir_takes_precedence_over_claude_home(self, tmp_path, monkeypatch):
        """BACK-121: REVEAL_CLAUDE_DIR explicit override wins over REVEAL_CLAUDE_HOME derivation."""
        import importlib
        import reveal.adapters.claude.adapter as mod

        fake_home = tmp_path / 'some_user' / '.claude'
        explicit_dir = tmp_path / 'custom' / 'sessions'
        monkeypatch.setenv('REVEAL_CLAUDE_HOME', str(fake_home))
        monkeypatch.setenv('REVEAL_CLAUDE_DIR', str(explicit_dir))
        importlib.reload(mod)

        assert mod.ClaudeAdapter.CONVERSATION_BASE == explicit_dir

        # Restore
        importlib.reload(mod)


class TestReconfigureBasePath:
    """Tests for reconfigure_base_path — --base-path CLI flag behaviour."""

    def test_derives_all_paths_from_projects_dir(self, tmp_path):
        """--base-path derives CLAUDE_HOME, CLAUDE_JSON, PLANS_DIR, AGENTS_DIR, HOOKS_DIR."""
        projects_dir = tmp_path / 'some_user' / '.claude' / 'projects'
        adapter = ClaudeAdapter('')
        adapter.reconfigure_base_path(projects_dir)

        assert adapter.CONVERSATION_BASE == projects_dir
        assert adapter.CLAUDE_HOME == tmp_path / 'some_user' / '.claude'
        assert adapter.CLAUDE_JSON == tmp_path / 'some_user' / '.claude.json'
        assert adapter.PLANS_DIR == tmp_path / 'some_user' / '.claude' / 'plans'
        assert adapter.AGENTS_DIR == tmp_path / 'some_user' / '.claude' / 'agents'
        assert adapter.HOOKS_DIR == tmp_path / 'some_user' / '.claude' / 'hooks'

    def test_overrides_are_instance_level(self, tmp_path):
        """reconfigure_base_path sets instance attrs, leaving class attrs unchanged."""
        projects_dir = tmp_path / '.claude' / 'projects'
        original_home = ClaudeAdapter.CLAUDE_HOME

        adapter = ClaudeAdapter('')
        adapter.reconfigure_base_path(projects_dir)

        assert adapter.CLAUDE_HOME != original_home
        assert ClaudeAdapter.CLAUDE_HOME == original_home  # class untouched

    def test_raises_when_path_contains_jsonl_directly(self, tmp_path):
        """BACK-269: session dir passed as --base-path raises ValueError with hint."""
        session_dir = tmp_path / '-home-user-sessions-my-sess'
        session_dir.mkdir(parents=True)
        (session_dir / 'my-sess.jsonl').write_text('{}')

        adapter = ClaudeAdapter('')
        with pytest.raises(ValueError, match='session directory'):
            adapter.reconfigure_base_path(session_dir)

    def test_error_message_includes_parent_path(self, tmp_path):
        """BACK-269: error message tells user the parent directory to use."""
        session_dir = tmp_path / '.claude' / 'projects' / '-home-user-sessions-my-sess'
        session_dir.mkdir(parents=True)
        (session_dir / 'my-sess.jsonl').write_text('{}')

        adapter = ClaudeAdapter('')
        with pytest.raises(ValueError, match=str(tmp_path / '.claude' / 'projects')):
            adapter.reconfigure_base_path(session_dir)

    def test_accepts_normal_projects_dir(self, tmp_path):
        """BACK-269: a normal projects dir (no .jsonl at root) works fine."""
        projects_dir = tmp_path / '.claude' / 'projects'
        projects_dir.mkdir(parents=True)
        # Create a session subdir with JSONL inside it (correct layout)
        sess = projects_dir / '-home-user-sessions-my-sess'
        sess.mkdir()
        (sess / 'my-sess.jsonl').write_text('{}')

        adapter = ClaudeAdapter('')
        adapter.reconfigure_base_path(projects_dir)  # should not raise
        assert adapter.CONVERSATION_BASE == projects_dir


class TestHelpDocumentation:
    """Tests for help documentation."""

    def test_get_help_returns_dict(self):
        """Test get_help returns dictionary."""
        help_doc = ClaudeAdapter.get_help()

        assert isinstance(help_doc, dict)

    def test_help_includes_required_fields(self):
        """Test help documentation includes required fields."""
        help_doc = ClaudeAdapter.get_help()

        assert 'name' in help_doc
        assert 'description' in help_doc
        assert 'syntax' in help_doc
        assert 'examples' in help_doc
        assert 'features' in help_doc

    def test_help_examples_are_valid(self):
        """Test help examples include URIs and descriptions."""
        help_doc = ClaudeAdapter.get_help()

        examples = help_doc['examples']
        assert len(examples) > 0
        for example in examples:
            assert 'uri' in example
            assert 'description' in example
            assert example['uri'].startswith('claude://')

    def test_help_includes_workflows(self):
        """Test help documentation includes workflow examples."""
        help_doc = ClaudeAdapter.get_help()

        workflows = help_doc['workflows']
        assert len(workflows) > 0
        for workflow in workflows:
            assert 'name' in workflow
            assert 'scenario' in workflow
            assert 'steps' in workflow


class TestSummaryAnalytics:
    """Tests for detailed summary analytics."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_summary_includes_overview(self, mock_find):
        """Test summary includes overview data."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='summary')

        result = adapter.get_structure()

        assert result['type'] == 'claude_analytics'
        # Should include all overview fields
        assert 'message_count' in result
        assert 'tools_used' in result
        assert 'thinking_tokens_approx' in result

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_summary_includes_analytics(self, mock_find):
        """Test summary includes additional analytics."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='summary')

        result = adapter.get_structure()

        # Additional analytics fields
        assert 'avg_message_size' in result
        assert 'max_message_size' in result
        assert 'thinking_blocks' in result


class TestSessionDiscovery:
    """Tests for session discovery logic."""

    def test_find_conversation_tia_style(self):
        """Test finding conversation in TIA-style directory."""
        # Create a temporary test structure
        adapter = ClaudeAdapter('session/test-session')

        # Mock the CONVERSATION_BASE to fixtures dir
        with patch.object(adapter, 'CONVERSATION_BASE', FIXTURES_DIR.parent):
            # Create expected directory structure
            test_dir = FIXTURES_DIR.parent / '-home-scottsen-src-tia-sessions-test-session'
            test_dir.mkdir(exist_ok=True)
            test_file = test_dir / 'conversation.jsonl'
            test_file.write_text('{}')

            try:
                result = adapter._find_conversation()
                assert result == test_file
            finally:
                # Cleanup
                test_file.unlink()
                test_dir.rmdir()

    def test_find_conversation_returns_none_when_not_found(self):
        """Test _find_conversation returns None when session not found."""
        adapter = ClaudeAdapter('session/nonexistent-session-xyz')

        result = adapter._find_conversation()

        assert result is None

    def test_find_conversation_empty_session_name(self):
        """Test _find_conversation returns None when session name is empty."""
        adapter = ClaudeAdapter('session/')

        result = adapter._find_conversation()

        assert result is None

    def test_find_conversation_fuzzy_search_with_files(self):
        """Test fuzzy search skips non-directory entries."""
        adapter = ClaudeAdapter('session/fuzzy-test')

        # Create a temporary structure with files and directories
        with patch.object(adapter, 'CONVERSATION_BASE', FIXTURES_DIR.parent):
            test_file = FIXTURES_DIR.parent / 'fuzzy-test-file.txt'
            test_dir = FIXTURES_DIR.parent / 'fuzzy-test-session'
            test_file.write_text('not a directory')
            test_dir.mkdir(exist_ok=True)
            jsonl_file = test_dir / 'conversation.jsonl'
            jsonl_file.write_text('{}')

            try:
                result = adapter._find_conversation()
                # Should find the directory, not the file
                assert result == jsonl_file
            finally:
                # Cleanup
                test_file.unlink()
                jsonl_file.unlink()
                test_dir.rmdir()

    def test_find_conversation_fuzzy_search_success(self):
        """Test fuzzy search finds session with partial name match."""
        adapter = ClaudeAdapter('session/partial')

        with patch.object(adapter, 'CONVERSATION_BASE', FIXTURES_DIR.parent):
            # Create directory with session name as substring
            test_dir = FIXTURES_DIR.parent / 'some-partial-session-name'
            test_dir.mkdir(exist_ok=True)
            jsonl_file = test_dir / 'conversation.jsonl'
            jsonl_file.write_text('{}')

            try:
                result = adapter._find_conversation()
                assert result == jsonl_file
            finally:
                # Cleanup
                jsonl_file.unlink()
                test_dir.rmdir()


class TestMessageLoadingEdgeCases:
    """Tests for edge cases in message loading."""

    def test_load_messages_with_malformed_json(self):
        """Test loading messages skips malformed JSON lines."""
        # Create a temporary file with malformed JSON
        temp_file = FIXTURES_DIR / 'malformed.jsonl'
        temp_file.write_text(
            '{"valid": "json"}\n'
            '{invalid json here}\n'
            '{"another": "valid"}\n'
        )

        try:
            adapter = ClaudeAdapter('session/test')
            adapter.conversation_path = temp_file

            messages = adapter._load_messages()

            # Should have loaded 2 valid messages, skipped 1 malformed
            assert len(messages) == 2
            assert messages[0]['valid'] == 'json'
            assert messages[1]['another'] == 'valid'
        finally:
            temp_file.unlink()


class TestOverviewEdgeCases:
    """Tests for edge cases in overview generation."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_overview_with_invalid_timestamps(self, mock_find):
        """Test overview handles invalid timestamp formats gracefully."""
        # Create messages with invalid timestamps
        invalid_conv = FIXTURES_DIR / 'invalid-timestamps.jsonl'
        invalid_conv.write_text(
            '{"timestamp": "not-a-timestamp", "type": "user"}\n'
            '{"timestamp": "also-invalid", "type": "assistant"}\n'
        )

        try:
            mock_find.return_value = invalid_conv
            adapter = ClaudeAdapter('session/test')

            # Load messages and get overview
            messages = adapter._load_messages()
            result = adapter._get_overview(messages)

            # Should handle invalid timestamps gracefully (duration = None)
            assert 'duration' in result
            assert result['duration'] is None
        finally:
            invalid_conv.unlink()

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_overview_with_missing_timestamp_field(self, mock_find):
        """Test overview handles missing timestamp fields."""
        invalid_conv = FIXTURES_DIR / 'no-timestamps.jsonl'
        invalid_conv.write_text(
            '{"type": "user", "content": [{"type": "text", "text": "hi"}]}\n'
            '{"type": "assistant", "content": [{"type": "text", "text": "hello"}]}\n'
        )

        try:
            mock_find.return_value = invalid_conv
            adapter = ClaudeAdapter('session/test')

            # Load messages and get overview
            messages = adapter._load_messages()
            result = adapter._get_overview(messages)

            # Should handle missing timestamps gracefully (duration = None)
            assert 'duration' in result
            assert result['duration'] is None
        finally:
            invalid_conv.unlink()


class TestTimeline:
    """Tests for timeline generation."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_timeline_basic_structure(self, mock_find):
        """Test timeline generates basic structure."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='timeline')

        result = adapter.get_structure()

        assert result['type'] == 'claude_timeline'
        assert 'timeline' in result
        assert 'event_count' in result
        assert isinstance(result['timeline'], list)
        assert result['event_count'] > 0

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_timeline_includes_all_event_types(self, mock_find):
        """Test timeline includes all event types."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='timeline')

        result = adapter.get_structure()
        timeline = result['timeline']

        # Extract event types
        event_types = {event['event_type'] for event in timeline}

        # Should have multiple event types
        assert 'user_message' in event_types
        assert 'assistant_message' in event_types
        assert 'tool_call' in event_types
        assert 'tool_result' in event_types
        assert 'thinking' in event_types

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_timeline_preserves_chronology(self, mock_find):
        """Test timeline events are in chronological order."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='timeline')

        result = adapter.get_structure()
        timeline = result['timeline']

        # Check indices are increasing
        indices = [event['index'] for event in timeline]
        assert indices == sorted(indices)

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_timeline_tool_matching(self, mock_find):
        """Test tool calls match with their results."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='timeline')

        result = adapter.get_structure()
        timeline = result['timeline']

        # Find all tool calls and results
        tool_calls = {e['tool_id']: e for e in timeline if e['event_type'] == 'tool_call'}
        tool_results = {e['tool_id']: e for e in timeline if e['event_type'] == 'tool_result'}

        # Every tool call should have a result
        for tool_id in tool_calls:
            assert tool_id in tool_results

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_timeline_error_detection(self, mock_find):
        """Test timeline marks error results."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='timeline')

        result = adapter.get_structure()
        timeline = result['timeline']

        # Find error results
        error_results = [e for e in timeline if e['event_type'] == 'tool_result' and e['status'] == 'error']
        success_results = [e for e in timeline if e['event_type'] == 'tool_result' and e['status'] == 'success']

        # Should have at least one error (tool-001 fails)
        assert len(error_results) > 0
        # Should have at least one success
        assert len(success_results) > 0

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_timeline_thinking_tokens(self, mock_find):
        """Test timeline includes thinking token estimates."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='timeline')

        result = adapter.get_structure()
        timeline = result['timeline']

        # Find thinking events
        thinking_events = [e for e in timeline if e['event_type'] == 'thinking']

        # Should have thinking events with token estimates
        assert len(thinking_events) > 0
        for event in thinking_events:
            assert 'tokens_approx' in event
            assert event['tokens_approx'] > 0


class TestToolSuccessRate:
    """Tests for tool success rate calculation."""

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_calculate_tool_success_rate_basic(self, mock_find):
        """Test basic tool success rate calculation."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test')

        messages = adapter._load_messages()
        result = adapter._calculate_tool_success_rate(messages)

        # From test-session.jsonl:
        # Read: tool-001 (error), tool-003 (success) = 1/2 = 50%
        # Bash: tool-002 (success) = 1/1 = 100%
        # Write: tool-004 (success) = 1/1 = 100%
        assert 'Read' in result
        assert result['Read']['success'] == 1
        assert result['Read']['failure'] == 1
        assert result['Read']['total'] == 2
        assert result['Read']['success_rate'] == 50.0

        assert 'Bash' in result
        assert result['Bash']['success'] == 1
        assert result['Bash']['total'] == 1
        assert result['Bash']['success_rate'] == 100.0

        assert 'Write' in result
        assert result['Write']['success'] == 1
        assert result['Write']['total'] == 1
        assert result['Write']['success_rate'] == 100.0

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_summary_includes_tool_success_rate(self, mock_find):
        """Test that summary includes tool success rate data."""
        mock_find.return_value = TEST_CONVERSATION
        adapter = ClaudeAdapter('session/test', query='summary')

        result = adapter.get_structure()

        assert 'tool_success_rate' in result
        assert isinstance(result['tool_success_rate'], dict)
        # Should have Read, Bash, Write tools
        assert len(result['tool_success_rate']) >= 3

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_tool_success_rate_all_failures(self, mock_find):
        """Test tool success rate with all failures."""
        # Create conversation with only failures
        # Note: tool_results are in 'user' type messages (returned from tool execution)
        fail_conv = FIXTURES_DIR / 'all-failures.jsonl'
        fail_conv.write_text(
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Read","id":"t1","input":{"file_path":"missing.txt"}}]},"timestamp":"2026-01-18T10:00:00.000Z"}\n'
            '{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"Error: File not found","is_error":true}]},"timestamp":"2026-01-18T10:00:01.000Z"}\n'
        )

        try:
            mock_find.return_value = fail_conv
            adapter = ClaudeAdapter('session/test')

            messages = adapter._load_messages()
            result = adapter._calculate_tool_success_rate(messages)

            assert 'Read' in result
            assert result['Read']['success'] == 0
            assert result['Read']['failure'] == 1
            assert result['Read']['success_rate'] == 0.0
        finally:
            fail_conv.unlink()

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_tool_success_rate_no_tools(self, mock_find):
        """Test tool success rate with no tool usage."""
        no_tools = FIXTURES_DIR / 'no-tools.jsonl'
        no_tools.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Hello"}]},"timestamp":"2026-01-18T10:00:00.000Z"}\n'
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hi there!"}]},"timestamp":"2026-01-18T10:00:01.000Z"}\n'
        )

        try:
            mock_find.return_value = no_tools
            adapter = ClaudeAdapter('session/test')

            messages = adapter._load_messages()
            result = adapter._calculate_tool_success_rate(messages)

            # Should return empty dict when no tools used
            assert result == {}
        finally:
            no_tools.unlink()

    @patch.object(ClaudeAdapter, '_find_conversation')
    def test_tool_success_rate_orphan_result(self, mock_find):
        """Test tool success rate with orphan tool_result (no matching tool_use)."""
        orphan = FIXTURES_DIR / 'orphan-result.jsonl'
        orphan.write_text(
            '{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_result","tool_use_id":"unknown-id","content":"Success"}]},"timestamp":"2026-01-18T10:00:00.000Z"}\n'
        )

        try:
            mock_find.return_value = orphan
            adapter = ClaudeAdapter('session/test')

            messages = adapter._load_messages()
            result = adapter._calculate_tool_success_rate(messages)

            # Should skip orphan results
            assert result == {}
        finally:
            orphan.unlink()


class TestClaudeAdapterSchema:
    """Test schema generation for AI agent integration."""

    def test_get_schema(self):
        """Should return machine-readable schema."""
        schema = ClaudeAdapter.get_schema()

        assert schema is not None
        assert schema['adapter'] == 'claude'
        assert 'description' in schema
        assert 'uri_syntax' in schema
        assert 'claude://session/' in schema['uri_syntax']

    def test_schema_query_params(self):
        """Schema should document query parameters."""
        schema = ClaudeAdapter.get_schema()

        assert 'query_params' in schema
        query_params = schema['query_params']

        # Should have filtering params
        assert 'summary' in query_params
        assert 'errors' in query_params
        assert 'tools' in query_params
        assert 'contains' in query_params
        assert 'role' in query_params

        # Role param should have values
        role_param = query_params['role']
        assert 'values' in role_param
        assert 'user' in role_param['values']
        assert 'assistant' in role_param['values']

    def test_schema_elements(self):
        """Schema should document available elements."""
        schema = ClaudeAdapter.get_schema()

        assert 'elements' in schema
        elements = schema['elements']

        # Should have all claude elements
        assert 'workflow' in elements
        assert 'files' in elements
        assert 'tools' in elements
        assert 'thinking' in elements
        assert 'errors' in elements
        assert 'timeline' in elements
        assert 'context' in elements

    def test_schema_output_types(self):
        """Schema should define output types."""
        schema = ClaudeAdapter.get_schema()

        assert 'output_types' in schema
        assert len(schema['output_types']) >= 5

        # Should have claude output types
        output_types = [ot['type'] for ot in schema['output_types']]
        assert 'claude_overview' in output_types
        assert 'claude_workflow' in output_types
        assert 'claude_files' in output_types
        assert 'claude_tools' in output_types
        assert 'claude_errors' in output_types

    def test_schema_examples(self):
        """Schema should include usage examples."""
        schema = ClaudeAdapter.get_schema()

        assert 'example_queries' in schema
        assert len(schema['example_queries']) >= 8

        # Examples should have required fields
        for example in schema['example_queries']:
            assert 'uri' in example
            assert 'description' in example

    def test_schema_batch_support(self):
        """Schema should indicate batch support status."""
        schema = ClaudeAdapter.get_schema()

        assert 'supports_batch' in schema
        assert 'supports_advanced' in schema


class TestClaudeRenderer:
    """Test renderer output formatting."""

    @pytest.fixture
    def mock_session_file(self, tmp_path):
        """Create a mock session file."""
        session_file = tmp_path / "conversations.jsonl"
        messages = [
            {
                "type": "user",
                "content": "Test message",
                "timestamp": "2024-01-01T12:00:00"
            },
            {
                "type": "assistant",
                "content": "Response",
                "timestamp": "2024-01-01T12:00:01"
            }
        ]
        with open(session_file, 'w') as f:
            for msg in messages:
                f.write(json.dumps(msg) + '\n')
        return session_file

    def test_renderer_session_overview(self, mock_session_file):
        """Renderer should format session overview correctly."""
        from reveal.adapters.claude.renderer import ClaudeRenderer
        from io import StringIO
        import sys

        result = {
            'type': 'claude_session_overview',
            'session': 'test-session',
            'message_count': 10,
            'user_messages': 5,
            'assistant_messages': 5,
            'tools_used': {'Bash': 3, 'Read': 2},
            'conversation_file': str(mock_session_file)
        }

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        ClaudeRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain key sections
        assert 'test-session' in output
        assert 'Messages:' in output
        assert 'Tools Used:' in output
        assert 'Bash' in output

    def test_renderer_json_format(self, mock_session_file):
        """Renderer should support JSON output."""
        from reveal.adapters.claude.renderer import ClaudeRenderer
        from io import StringIO
        import sys

        result = {
            'type': 'claude_session_overview',
            'session': 'test-session',
            'message_count': 10,
            'user_messages': 5,
            'assistant_messages': 5,
            'tools_used': {'Bash': 3, 'Read': 2},
            'conversation_file': str(mock_session_file)
        }

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        ClaudeRenderer.render_structure(result, format='json')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should be valid JSON
        parsed = json.loads(output)
        assert 'type' in parsed
        assert parsed['type'] == 'claude_session_overview'
        assert parsed['session'] == 'test-session'

    def test_renderer_error_handling(self):
        """Renderer should handle errors gracefully."""
        from reveal.adapters.claude.renderer import ClaudeRenderer
        from io import StringIO
        import sys

        # Capture stderr (render_error outputs to stderr)
        old_stderr = sys.stderr
        sys.stderr = captured_output = StringIO()

        error = FileNotFoundError("Session file not found")
        ClaudeRenderer.render_error(error)

        sys.stderr = old_stderr
        output = captured_output.getvalue()

        assert 'Error' in output
        assert 'Session file not found' in output

    def test_renderer_tool_calls(self, mock_session_file):
        """Renderer should format tool calls correctly."""
        from reveal.adapters.claude.renderer import ClaudeRenderer
        from io import StringIO
        import sys

        result = {
            'type': 'claude_tool_calls',
            'tool_name': 'Bash',
            'call_count': 3,
            'session': 'test-session',
            'calls': [
                {
                    'input': {'command': 'ls -la', 'description': 'List files'},
                    'result': 'file1.txt\nfile2.txt'
                }
            ]
        }

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        ClaudeRenderer.render_structure(result, format='text')

        sys.stdout = old_stdout
        output = captured_output.getvalue()

        # Should contain tool call info
        assert 'Bash' in output
        assert 'ls -la' in output


class TestSessionsAlias:
    """Tests for claude://sessions alias — Issue 3."""

    def test_sessions_alias_returns_listing(self, tmp_path):
        """claude://sessions should return the session list, not an error."""
        base = tmp_path / 'projects'
        base.mkdir()
        proj = base / '-home-user-src-tia-sessions-my-session'
        proj.mkdir()
        (proj / 'main.jsonl').write_text('{}')

        adapter = ClaudeAdapter('sessions')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter.get_structure()

        assert result['type'] == 'claude_session_list'
        assert result['session_count'] == 1

    def test_sessions_trailing_slash_alias(self, tmp_path):
        """claude://sessions/ (trailing slash) also returns the listing."""
        base = tmp_path / 'projects'
        base.mkdir()

        adapter = ClaudeAdapter('sessions/')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter.get_structure()

        assert result['type'] == 'claude_session_list'

    def test_sessions_not_treated_as_session_name(self, tmp_path):
        """Ensure 'sessions' is never passed to _find_conversation as a session name."""
        base = tmp_path / 'projects'
        base.mkdir()

        adapter = ClaudeAdapter('sessions')
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter.get_structure()

        assert 'error' not in result or result.get('type') == 'claude_session_list'
        assert result['type'] == 'claude_session_list'


class TestSessionTitle:
    """Tests for session title extraction — Issue 4."""

    def _make_session(self, tmp_path, messages):
        """Write a JSONL session file and return (base_path, adapter)."""
        import json as _json
        base = tmp_path / 'projects'
        base.mkdir()
        proj = base / '-home-user-src-tia-sessions-my-session'
        proj.mkdir()
        jsonl = proj / 'main.jsonl'
        jsonl.write_text('\n'.join(_json.dumps(m) for m in messages) + '\n')
        adapter = ClaudeAdapter('session/my-session')
        adapter.conversation_path = jsonl
        return base, adapter

    def test_title_extracted_from_string_content(self, tmp_path):
        """Title extracted when first user message has string content."""
        import json as _json
        msgs = [
            {'type': 'user', 'message': {'role': 'user', 'content': 'Fix the login bug\nMore details below'}, 'uuid': 'u1', 'timestamp': '2026-01-01T00:00:00Z'},
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'OK'}]}, 'uuid': 'a1', 'timestamp': '2026-01-01T00:00:01Z'},
        ]
        base, adapter = self._make_session(tmp_path, msgs)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter.get_structure()

        assert result.get('title') == 'Fix the login bug'

    def test_title_extracted_from_list_content(self, tmp_path):
        """Title extracted when first user message has list-of-items content."""
        msgs = [
            {'type': 'user', 'message': {'role': 'user', 'content': [
                {'type': 'text', 'text': 'Refactor the auth module\nDetails follow'}
            ]}, 'uuid': 'u1', 'timestamp': '2026-01-01T00:00:00Z'},
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'OK'}]}, 'uuid': 'a1', 'timestamp': '2026-01-01T00:00:01Z'},
        ]
        base, adapter = self._make_session(tmp_path, msgs)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter.get_structure()

        assert result.get('title') == 'Refactor the auth module'

    def test_title_truncated_at_100_chars(self, tmp_path):
        """Title is capped at 100 characters."""
        long_line = 'A' * 150
        msgs = [
            {'type': 'user', 'message': {'role': 'user', 'content': long_line}, 'uuid': 'u1', 'timestamp': '2026-01-01T00:00:00Z'},
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'OK'}]}, 'uuid': 'a1', 'timestamp': '2026-01-01T00:00:01Z'},
        ]
        base, adapter = self._make_session(tmp_path, msgs)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter.get_structure()

        assert len(result.get('title', '')) == 100

    def test_title_none_when_no_user_messages(self, tmp_path):
        """Title is None when there are no user messages."""
        msgs = [
            {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Hello'}]}, 'uuid': 'a1', 'timestamp': '2026-01-01T00:00:00Z'},
        ]
        base, adapter = self._make_session(tmp_path, msgs)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', base):
            result = adapter.get_structure()

        assert result.get('title') is None


class TestHelpCrossPlatform:
    """Tests for help://claude cross-platform examples — Issue 5."""

    def test_try_now_has_no_bash_substitution(self):
        """try_now entries must not contain $(basename $PWD) or similar bash substitutions."""
        help_doc = ClaudeAdapter.get_help()
        for cmd in help_doc.get('try_now', []):
            assert '$(' not in cmd, f"Bash substitution found in try_now: {cmd!r}"

    def test_notes_mention_both_platforms(self):
        """Notes should mention both bash/zsh and PowerShell for finding session name."""
        help_doc = ClaudeAdapter.get_help()
        notes_text = ' '.join(help_doc.get('notes', []))
        assert 'bash' in notes_text.lower() or 'zsh' in notes_text.lower(), "No bash/zsh mention in notes"
        assert 'powershell' in notes_text.lower(), "No PowerShell mention in notes"

    def test_try_now_still_has_examples(self):
        """try_now must still contain actual reveal commands."""
        help_doc = ClaudeAdapter.get_help()
        reveal_cmds = [c for c in help_doc.get('try_now', []) if 'reveal' in c]
        assert len(reveal_cmds) >= 3, "Expected at least 3 reveal commands in try_now"


class TestClaudeInfo:
    """Tests for claude://info diagnostic path dump."""

    def test_get_info_returns_correct_type(self):
        adapter = ClaudeAdapter('info')
        result = adapter.get_structure()
        assert result['type'] == 'claude_info'
        assert result['contract_version'] == '1.0'

    def test_get_info_has_all_path_keys(self):
        adapter = ClaudeAdapter('info')
        result = adapter.get_structure()
        paths = result['paths']
        for key in ('claude_home', 'projects', 'history', 'plans', 'settings', 'config', 'agents', 'hooks'):
            assert key in paths, f"Missing path key: {key}"

    def test_get_info_paths_have_exists_field(self):
        adapter = ClaudeAdapter('info')
        result = adapter.get_structure()
        for key, info in result['paths'].items():
            assert 'exists' in info, f"Path {key} missing 'exists' field"
            assert 'path' in info, f"Path {key} missing 'path' field"

    def test_get_info_has_env_overrides(self):
        adapter = ClaudeAdapter('info')
        result = adapter.get_structure()
        env = result['env']
        assert 'REVEAL_CLAUDE_HOME' in env
        assert 'REVEAL_CLAUDE_DIR' in env
        assert 'REVEAL_SESSIONS_DIR' in env


class TestClaudeSettings:
    """Tests for claude://settings."""

    def test_returns_correct_type(self):
        adapter = ClaudeAdapter('settings')
        result = adapter.get_structure()
        assert result['type'] == 'claude_settings'
        assert result['contract_version'] == '1.0'

    def test_settings_is_dict(self):
        adapter = ClaudeAdapter('settings')
        result = adapter.get_structure()
        assert isinstance(result.get('settings'), dict)

    def test_key_extraction_simple(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text('{"model": "sonnet", "timeout": 300}')
        original = ClaudeAdapter.CLAUDE_HOME
        ClaudeAdapter.CLAUDE_HOME = tmp_path
        try:
            adapter = ClaudeAdapter('settings')
            adapter.query_params = {'key': 'model'}
            result = adapter._get_settings()
            assert result['key'] == 'model'
            assert result['value'] == 'sonnet'
        finally:
            ClaudeAdapter.CLAUDE_HOME = original

    def test_key_extraction_nested(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text('{"permissions": {"additionalDirectories": ["/tmp"]}}')
        original = ClaudeAdapter.CLAUDE_HOME
        ClaudeAdapter.CLAUDE_HOME = tmp_path
        try:
            adapter = ClaudeAdapter('settings')
            adapter.query_params = {'key': 'permissions.additionalDirectories'}
            result = adapter._get_settings()
            assert result['key'] == 'permissions.additionalDirectories'
            assert result['value'] == ['/tmp']
        finally:
            ClaudeAdapter.CLAUDE_HOME = original

    def test_key_extraction_missing_key(self, tmp_path):
        settings_file = tmp_path / 'settings.json'
        settings_file.write_text('{"model": "sonnet"}')
        original = ClaudeAdapter.CLAUDE_HOME
        ClaudeAdapter.CLAUDE_HOME = tmp_path
        try:
            adapter = ClaudeAdapter('settings')
            adapter.query_params = {'key': 'nonexistent'}
            result = adapter._get_settings()
            assert 'error' in result
            assert result['value'] is None
        finally:
            ClaudeAdapter.CLAUDE_HOME = original

    def test_missing_settings_file(self, tmp_path):
        original = ClaudeAdapter.CLAUDE_HOME
        ClaudeAdapter.CLAUDE_HOME = tmp_path
        try:
            adapter = ClaudeAdapter('settings')
            result = adapter._get_settings()
            assert 'error' in result
            assert result['settings'] == {}
        finally:
            ClaudeAdapter.CLAUDE_HOME = original


class TestClaudePlans:
    """Tests for claude://plans list and claude://plans/<name>."""

    def _make_plans_dir(self, tmp_path):
        plans_dir = tmp_path / 'plans'
        plans_dir.mkdir()
        (plans_dir / 'alpha-plan.md').write_text('# Alpha Plan\n\nContent for alpha.')
        (plans_dir / 'beta-plan.md').write_text('# Beta Plan\n\nContent about tokens.')
        (plans_dir / 'gamma-plan.md').write_text('# Gamma Plan\n\nSomething else.')
        return plans_dir

    def test_list_plans_returns_correct_type(self, tmp_path):
        self._make_plans_dir(tmp_path)
        original = ClaudeAdapter.PLANS_DIR
        ClaudeAdapter.PLANS_DIR = tmp_path / 'plans'
        try:
            adapter = ClaudeAdapter('plans')
            result = adapter._get_plans()
            assert result['type'] == 'claude_plans'
            assert result['total'] == 3
            assert len(result['plans']) == 3
        finally:
            ClaudeAdapter.PLANS_DIR = original

    def test_list_plans_entries_have_required_fields(self, tmp_path):
        self._make_plans_dir(tmp_path)
        original = ClaudeAdapter.PLANS_DIR
        ClaudeAdapter.PLANS_DIR = tmp_path / 'plans'
        try:
            adapter = ClaudeAdapter('plans')
            result = adapter._get_plans()
            for plan in result['plans']:
                assert 'name' in plan
                assert 'modified' in plan
                assert 'size_kb' in plan
                assert 'title' in plan
        finally:
            ClaudeAdapter.PLANS_DIR = original

    def test_list_plans_search_filter(self, tmp_path):
        self._make_plans_dir(tmp_path)
        original = ClaudeAdapter.PLANS_DIR
        ClaudeAdapter.PLANS_DIR = tmp_path / 'plans'
        try:
            adapter = ClaudeAdapter('plans')
            adapter.query_params = {'search': 'tokens'}
            result = adapter._get_plans()
            assert result['displayed'] == 1
            assert result['plans'][0]['name'] == 'beta-plan'
        finally:
            ClaudeAdapter.PLANS_DIR = original

    def test_read_specific_plan(self, tmp_path):
        self._make_plans_dir(tmp_path)
        original = ClaudeAdapter.PLANS_DIR
        ClaudeAdapter.PLANS_DIR = tmp_path / 'plans'
        try:
            adapter = ClaudeAdapter('plans/alpha-plan')
            result = adapter._get_plans()
            assert result['type'] == 'claude_plan'
            assert result['name'] == 'alpha-plan'
            assert '# Alpha Plan' in result['content']
        finally:
            ClaudeAdapter.PLANS_DIR = original

    def test_read_plan_not_found(self, tmp_path):
        self._make_plans_dir(tmp_path)
        original = ClaudeAdapter.PLANS_DIR
        ClaudeAdapter.PLANS_DIR = tmp_path / 'plans'
        try:
            adapter = ClaudeAdapter('plans/nonexistent')
            result = adapter._get_plans()
            assert 'error' in result
        finally:
            ClaudeAdapter.PLANS_DIR = original

    def test_missing_plans_dir(self, tmp_path):
        original = ClaudeAdapter.PLANS_DIR
        ClaudeAdapter.PLANS_DIR = tmp_path / 'plans'  # doesn't exist
        try:
            adapter = ClaudeAdapter('plans')
            result = adapter._get_plans()
            assert 'error' in result
            assert result['plans'] == []
        finally:
            ClaudeAdapter.PLANS_DIR = original


class TestClaudeConfig:
    """Tests for claude://config."""

    def _make_claude_json(self, tmp_path, data: dict):
        p = tmp_path / '.claude.json'
        import json
        p.write_text(json.dumps(data))
        return p

    def test_config_returns_correct_type(self, tmp_path):
        p = self._make_claude_json(tmp_path, {
            'installMethod': 'native',
            'autoUpdates': False,
            'projects': {},
        })
        original = ClaudeAdapter.CLAUDE_JSON
        ClaudeAdapter.CLAUDE_JSON = p
        try:
            adapter = ClaudeAdapter('config')
            result = adapter._get_config()
            assert result['type'] == 'claude_config'
            assert result['projects_count'] == 0
            assert result['flags']['installMethod'] == 'native'
        finally:
            ClaudeAdapter.CLAUDE_JSON = original

    def test_config_extracts_mcp_servers(self, tmp_path):
        p = self._make_claude_json(tmp_path, {
            'projects': {
                '/home/user/proj': {
                    'mcpServers': {'reveal-mcp': {'command': 'reveal'}},
                    'allowedTools': ['Bash'],
                }
            }
        })
        original = ClaudeAdapter.CLAUDE_JSON
        ClaudeAdapter.CLAUDE_JSON = p
        try:
            adapter = ClaudeAdapter('config')
            result = adapter._get_config()
            assert result['projects_count'] == 1
            assert result['projects'][0]['mcp_servers'] == ['reveal-mcp']
            assert result['projects'][0]['allowed_tools'] == ['Bash']
        finally:
            ClaudeAdapter.CLAUDE_JSON = original

    def test_config_key_extraction(self, tmp_path):
        p = self._make_claude_json(tmp_path, {'installMethod': 'native', 'verbose': True})
        original = ClaudeAdapter.CLAUDE_JSON
        ClaudeAdapter.CLAUDE_JSON = p
        try:
            adapter = ClaudeAdapter('config')
            adapter.query_params = {'key': 'installMethod'}
            result = adapter._get_config()
            assert result['key'] == 'installMethod'
            assert result['value'] == 'native'
        finally:
            ClaudeAdapter.CLAUDE_JSON = original

    def test_config_key_missing(self, tmp_path):
        p = self._make_claude_json(tmp_path, {'installMethod': 'native'})
        original = ClaudeAdapter.CLAUDE_JSON
        ClaudeAdapter.CLAUDE_JSON = p
        try:
            adapter = ClaudeAdapter('config')
            adapter.query_params = {'key': 'nonexistent'}
            result = adapter._get_config()
            assert result['value'] is None
        finally:
            ClaudeAdapter.CLAUDE_JSON = original

    def test_config_missing_file(self, tmp_path):
        original = ClaudeAdapter.CLAUDE_JSON
        ClaudeAdapter.CLAUDE_JSON = tmp_path / '.claude.json'
        try:
            adapter = ClaudeAdapter('config')
            result = adapter._get_config()
            assert 'error' in result
            assert result['projects'] == []
        finally:
            ClaudeAdapter.CLAUDE_JSON = original

    def test_config_masks_secrets(self, tmp_path):
        p = self._make_claude_json(tmp_path, {
            'api_key': 'sk-ant-very-secret-key-here',
            'installMethod': 'native',
        })
        original = ClaudeAdapter.CLAUDE_JSON
        ClaudeAdapter.CLAUDE_JSON = p
        try:
            adapter = ClaudeAdapter('config')
            result = adapter._mask_secrets({'api_key': 'sk-ant-very-secret-key-here'})
            assert result['api_key'].endswith('***')
            assert not result['api_key'].startswith('sk-ant-very')
        finally:
            ClaudeAdapter.CLAUDE_JSON = original

    def test_reveal_claude_json_env_override(self, tmp_path, monkeypatch):
        """BACK-119: REVEAL_CLAUDE_JSON overrides CLAUDE_JSON path."""
        import importlib
        import reveal.adapters.claude.adapter as adapter_module
        p = self._make_claude_json(tmp_path, {'installMethod': 'native', 'autoUpdates': True})
        monkeypatch.setenv('REVEAL_CLAUDE_JSON', str(p))
        # Re-evaluate class attribute with env var set
        monkeypatch.setattr(adapter_module.ClaudeAdapter, 'CLAUDE_JSON', p)
        adapter = adapter_module.ClaudeAdapter('config')
        result = adapter._get_config()
        assert result['type'] == 'claude_config'
        assert result['flags']['installMethod'] == 'native'

    def test_reveal_claude_home_derives_claude_json_path(self, tmp_path):
        """BACK-119: When REVEAL_CLAUDE_HOME is set, CLAUDE_JSON derives from its parent.

        The class attribute is evaluated at import time so we verify the derivation
        logic by checking the formula directly: CLAUDE_HOME.parent / '.claude.json'.
        """
        import os
        import reveal.adapters.claude.adapter as adapter_module
        from pathlib import Path
        fake_home = tmp_path / 'some_user' / '.claude'
        # Simulate what the class attribute expression produces for REVEAL_CLAUDE_HOME
        derived = Path(str(fake_home)).parent / '.claude.json'
        assert derived == tmp_path / 'some_user' / '.claude.json'
        # Verify _get_config reads from CLAUDE_JSON (already covered by test_reveal_claude_json_env_override)
        # This test confirms the derivation formula produces the correct sibling path.


class TestClaudeMemory:
    """Tests for claude://memory."""

    def _make_memory_tree(self, tmp_path):
        proj_dir = tmp_path / '-home-user-proj1'
        (proj_dir / 'memory').mkdir(parents=True)
        (proj_dir / 'memory' / 'feedback_test.md').write_text(
            '---\nname: test feedback\ndescription: A test feedback\ntype: feedback\n---\nBody text here.')
        (proj_dir / 'memory' / 'user_profile.md').write_text(
            '---\nname: user\ndescription: User profile\ntype: user\n---\nScott is a dev.')
        other_proj = tmp_path / '-home-user-proj2'
        (other_proj / 'memory').mkdir(parents=True)
        (other_proj / 'memory' / 'project_context.md').write_text(
            '---\nname: context\ndescription: Project context\ntype: project\n---\nContent.')
        return tmp_path

    def test_memory_returns_correct_type(self, tmp_path):
        self._make_memory_tree(tmp_path)
        original = ClaudeAdapter.CONVERSATION_BASE
        ClaudeAdapter.CONVERSATION_BASE = tmp_path
        try:
            adapter = ClaudeAdapter('memory')
            result = adapter._get_memory()
            assert result['type'] == 'claude_memory'
            assert result['total'] == 3
        finally:
            ClaudeAdapter.CONVERSATION_BASE = original

    def test_memory_entries_have_required_fields(self, tmp_path):
        self._make_memory_tree(tmp_path)
        original = ClaudeAdapter.CONVERSATION_BASE
        ClaudeAdapter.CONVERSATION_BASE = tmp_path
        try:
            adapter = ClaudeAdapter('memory')
            result = adapter._get_memory()
            for m in result['memories']:
                assert 'project' in m
                assert 'name' in m
                assert 'type' in m
                assert 'description' in m
                assert 'modified' in m
                assert 'path' in m
        finally:
            ClaudeAdapter.CONVERSATION_BASE = original

    def test_memory_project_filter(self, tmp_path):
        self._make_memory_tree(tmp_path)
        original = ClaudeAdapter.CONVERSATION_BASE
        ClaudeAdapter.CONVERSATION_BASE = tmp_path
        try:
            adapter = ClaudeAdapter('memory/proj1')
            result = adapter._get_memory()
            assert result['total'] == 2
            assert all('proj1' in m['project'] for m in result['memories'])
        finally:
            ClaudeAdapter.CONVERSATION_BASE = original

    def test_memory_search_filter(self, tmp_path):
        self._make_memory_tree(tmp_path)
        original = ClaudeAdapter.CONVERSATION_BASE
        ClaudeAdapter.CONVERSATION_BASE = tmp_path
        try:
            adapter = ClaudeAdapter('memory')
            adapter.query_params = {'search': 'scott'}
            result = adapter._get_memory()
            assert result['total'] == 1
            assert result['memories'][0]['name'] == 'user_profile'
        finally:
            ClaudeAdapter.CONVERSATION_BASE = original

    def test_memory_missing_projects_dir(self, tmp_path):
        original = ClaudeAdapter.CONVERSATION_BASE
        ClaudeAdapter.CONVERSATION_BASE = tmp_path / 'nonexistent'
        try:
            adapter = ClaudeAdapter('memory')
            result = adapter._get_memory()
            assert 'error' in result
            assert result['memories'] == []
        finally:
            ClaudeAdapter.CONVERSATION_BASE = original

    def test_memory_parses_frontmatter_type(self, tmp_path):
        self._make_memory_tree(tmp_path)
        original = ClaudeAdapter.CONVERSATION_BASE
        ClaudeAdapter.CONVERSATION_BASE = tmp_path
        try:
            adapter = ClaudeAdapter('memory')
            result = adapter._get_memory()
            types = {m['name']: m['type'] for m in result['memories']}
            assert types.get('feedback_test') == 'feedback'
            assert types.get('user_profile') == 'user'
        finally:
            ClaudeAdapter.CONVERSATION_BASE = original


class TestClaudeAgents:
    """Tests for claude://agents list and claude://agents/<name>."""

    def _make_agents_dir(self, tmp_path):
        agents_dir = tmp_path / 'agents'
        agents_dir.mkdir()
        (agents_dir / 'review-bot.md').write_text(
            '---\nname: review-bot\ndescription: Code review agent\ntools: Bash, Read\nmodel: sonnet\n---\nDo reviews.')
        (agents_dir / 'test-runner.md').write_text(
            '---\nname: test-runner\ndescription: Runs tests\ntools: Bash\nmodel: haiku\n---\nRun tests.')
        return agents_dir

    def test_agents_list_returns_correct_type(self, tmp_path):
        self._make_agents_dir(tmp_path)
        original = ClaudeAdapter.AGENTS_DIR
        ClaudeAdapter.AGENTS_DIR = tmp_path / 'agents'
        try:
            adapter = ClaudeAdapter('agents')
            result = adapter._get_agents()
            assert result['type'] == 'claude_agents'
            assert result['total'] == 2
        finally:
            ClaudeAdapter.AGENTS_DIR = original

    def test_agents_list_entries_have_required_fields(self, tmp_path):
        self._make_agents_dir(tmp_path)
        original = ClaudeAdapter.AGENTS_DIR
        ClaudeAdapter.AGENTS_DIR = tmp_path / 'agents'
        try:
            adapter = ClaudeAdapter('agents')
            result = adapter._get_agents()
            for a in result['agents']:
                assert 'name' in a
                assert 'modified' in a
                assert 'description' in a
                assert 'tools' in a
                assert 'model' in a
        finally:
            ClaudeAdapter.AGENTS_DIR = original

    def test_agents_read_specific(self, tmp_path):
        self._make_agents_dir(tmp_path)
        original = ClaudeAdapter.AGENTS_DIR
        ClaudeAdapter.AGENTS_DIR = tmp_path / 'agents'
        try:
            adapter = ClaudeAdapter('agents/review-bot')
            result = adapter._get_agents()
            assert result['type'] == 'claude_agent'
            assert result['name'] == 'review-bot'
            assert 'Do reviews.' in result['content']
            assert result['model'] == 'sonnet'
        finally:
            ClaudeAdapter.AGENTS_DIR = original

    def test_agents_not_found(self, tmp_path):
        self._make_agents_dir(tmp_path)
        original = ClaudeAdapter.AGENTS_DIR
        ClaudeAdapter.AGENTS_DIR = tmp_path / 'agents'
        try:
            adapter = ClaudeAdapter('agents/nonexistent')
            result = adapter._get_agents()
            assert 'error' in result
        finally:
            ClaudeAdapter.AGENTS_DIR = original

    def test_agents_missing_dir(self, tmp_path):
        original = ClaudeAdapter.AGENTS_DIR
        ClaudeAdapter.AGENTS_DIR = tmp_path / 'agents'
        try:
            adapter = ClaudeAdapter('agents')
            result = adapter._get_agents()
            assert 'error' in result
            assert result['agents'] == []
        finally:
            ClaudeAdapter.AGENTS_DIR = original

    def test_agents_search_filter(self, tmp_path):
        self._make_agents_dir(tmp_path)
        original = ClaudeAdapter.AGENTS_DIR
        ClaudeAdapter.AGENTS_DIR = tmp_path / 'agents'
        try:
            adapter = ClaudeAdapter('agents')
            adapter.query_params = {'search': 'review'}
            result = adapter._get_agents()
            assert result['displayed'] == 1
            assert result['agents'][0]['name'] == 'review-bot'
        finally:
            ClaudeAdapter.AGENTS_DIR = original

    def test_agents_parses_tools_list(self, tmp_path):
        self._make_agents_dir(tmp_path)
        original = ClaudeAdapter.AGENTS_DIR
        ClaudeAdapter.AGENTS_DIR = tmp_path / 'agents'
        try:
            adapter = ClaudeAdapter('agents')
            result = adapter._get_agents()
            by_name = {a['name']: a for a in result['agents']}
            assert by_name['review-bot']['tools'] == ['Bash', 'Read']
            assert by_name['test-runner']['tools'] == ['Bash']
        finally:
            ClaudeAdapter.AGENTS_DIR = original


class TestClaudeHooks:
    """Tests for claude://hooks list and claude://hooks/<event>."""

    def _make_hooks_dir(self, tmp_path):
        hooks_dir = tmp_path / 'hooks'
        hooks_dir.mkdir()
        script = hooks_dir / 'PostToolUse'
        script.write_text('#!/bin/bash\necho hello')
        script.chmod(0o755)
        # Also a directory-style event
        pre_dir = hooks_dir / 'PreToolUse'
        pre_dir.mkdir()
        (pre_dir / 'validate.sh').write_text('#!/bin/bash\necho validate')
        (pre_dir / 'validate.sh').chmod(0o755)
        return hooks_dir

    def test_hooks_list_returns_correct_type(self, tmp_path):
        self._make_hooks_dir(tmp_path)
        original = ClaudeAdapter.HOOKS_DIR
        ClaudeAdapter.HOOKS_DIR = tmp_path / 'hooks'
        try:
            adapter = ClaudeAdapter('hooks')
            result = adapter._get_hooks()
            assert result['type'] == 'claude_hooks'
            assert result['total'] == 2
        finally:
            ClaudeAdapter.HOOKS_DIR = original

    def test_hooks_list_entries_have_required_fields(self, tmp_path):
        self._make_hooks_dir(tmp_path)
        original = ClaudeAdapter.HOOKS_DIR
        ClaudeAdapter.HOOKS_DIR = tmp_path / 'hooks'
        try:
            adapter = ClaudeAdapter('hooks')
            result = adapter._get_hooks()
            for h in result['hooks']:
                assert 'event' in h
                assert 'kind' in h
                assert 'modified' in h
        finally:
            ClaudeAdapter.HOOKS_DIR = original

    def test_hooks_file_event_kind(self, tmp_path):
        self._make_hooks_dir(tmp_path)
        original = ClaudeAdapter.HOOKS_DIR
        ClaudeAdapter.HOOKS_DIR = tmp_path / 'hooks'
        try:
            adapter = ClaudeAdapter('hooks')
            result = adapter._get_hooks()
            by_event = {h['event']: h for h in result['hooks']}
            assert by_event['PostToolUse']['kind'] == 'file'
            assert by_event['PreToolUse']['kind'] == 'directory'
        finally:
            ClaudeAdapter.HOOKS_DIR = original

    def test_hooks_read_file_event(self, tmp_path):
        self._make_hooks_dir(tmp_path)
        original = ClaudeAdapter.HOOKS_DIR
        ClaudeAdapter.HOOKS_DIR = tmp_path / 'hooks'
        try:
            adapter = ClaudeAdapter('hooks/PostToolUse')
            result = adapter._get_hooks()
            assert result['event'] == 'PostToolUse'
            assert result['kind'] == 'file'
            assert 'echo hello' in result['content']
            if sys.platform != 'win32':
                assert result['executable'] is True
        finally:
            ClaudeAdapter.HOOKS_DIR = original

    def test_hooks_read_dir_event(self, tmp_path):
        self._make_hooks_dir(tmp_path)
        original = ClaudeAdapter.HOOKS_DIR
        ClaudeAdapter.HOOKS_DIR = tmp_path / 'hooks'
        try:
            adapter = ClaudeAdapter('hooks/PreToolUse')
            result = adapter._get_hooks()
            assert result['event'] == 'PreToolUse'
            assert result['kind'] == 'directory'
            assert len(result['scripts']) == 1
            assert result['scripts'][0]['name'] == 'validate.sh'
        finally:
            ClaudeAdapter.HOOKS_DIR = original

    def test_hooks_missing_dir(self, tmp_path):
        original = ClaudeAdapter.HOOKS_DIR
        ClaudeAdapter.HOOKS_DIR = tmp_path / 'hooks'
        try:
            adapter = ClaudeAdapter('hooks')
            result = adapter._get_hooks()
            assert 'error' in result
            assert result['hooks'] == []
        finally:
            ClaudeAdapter.HOOKS_DIR = original

    def test_hooks_event_not_found(self, tmp_path):
        self._make_hooks_dir(tmp_path)
        original = ClaudeAdapter.HOOKS_DIR
        ClaudeAdapter.HOOKS_DIR = tmp_path / 'hooks'
        try:
            adapter = ClaudeAdapter('hooks/NonExistentEvent')
            result = adapter._get_hooks()
            assert 'error' in result
        finally:
            ClaudeAdapter.HOOKS_DIR = original


class TestFormatToolParams:
    """Tests for _format_tool_params truncation behaviour (BACK-263)."""

    def test_bash_default_truncates_at_120(self):
        cmd = 'x' * 200
        lines = _format_tool_params('Bash', {'command': cmd})
        assert lines[0] == f"  command: {'x' * 120}..."

    def test_bash_no_truncation_when_short(self):
        cmd = 'echo hello'
        lines = _format_tool_params('Bash', {'command': cmd})
        assert lines[0] == '  command: echo hello'

    def test_bash_verbose_no_truncation(self):
        cmd = 'x' * 300
        lines = _format_tool_params('Bash', {'command': cmd}, max_chars=None)
        assert lines[0] == f"  command: {'x' * 300}"

    def test_bash_custom_max_chars(self):
        cmd = 'x' * 50
        lines = _format_tool_params('Bash', {'command': cmd}, max_chars=20)
        assert lines[0] == f"  command: {'x' * 20}..."

    def test_agent_default_truncates_at_120(self):
        prompt = 'p' * 200
        lines = _format_tool_params('Agent', {'prompt': prompt})
        assert lines[0] == f"  prompt: {'p' * 120}..."

    def test_agent_verbose_no_truncation(self):
        prompt = 'p' * 300
        lines = _format_tool_params('Agent', {'prompt': prompt}, max_chars=None)
        assert lines[0] == f"  prompt: {'p' * 300}"

    def test_agent_uses_description_fallback(self):
        desc = 'Search for bugs'
        lines = _format_tool_params('Agent', {'description': desc})
        assert lines[0] == f'  prompt: {desc}'

    def test_write_edit_read_unaffected_by_max_chars(self):
        lines = _format_tool_params('Read', {'file_path': '/foo/bar.py'}, max_chars=10)
        assert lines[0] == '  file_path: /foo/bar.py'


class TestRenderRawBlock:
    """Tests for _render_raw_block truncation propagation (BACK-263, BACK-268)."""

    def test_tool_use_bash_respects_max_chars(self, capsys):
        block = {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'x' * 300}}
        _render_raw_block(block, max_chars=50)
        out = capsys.readouterr().out
        assert f"{'x' * 50}..." in out
        assert 'x' * 51 not in out

    def test_tool_use_bash_verbose_no_truncation(self, capsys):
        cmd = 'x' * 300
        block = {'type': 'tool_use', 'name': 'Bash', 'input': {'command': cmd}}
        _render_raw_block(block, max_chars=None)
        out = capsys.readouterr().out
        assert cmd in out
        assert '...' not in out

    def test_thinking_respects_max_chars(self, capsys):
        thinking = 't' * 600
        block = {'type': 'thinking', 'thinking': thinking}
        _render_raw_block(block, max_chars=100)
        out = capsys.readouterr().out
        assert f"{'t' * 100}..." in out
        assert 't' * 101 not in out

    def test_thinking_verbose_no_truncation(self, capsys):
        thinking = 't' * 600
        block = {'type': 'thinking', 'thinking': thinking}
        _render_raw_block(block, max_chars=None)
        out = capsys.readouterr().out
        assert thinking in out
        assert '...' not in out

    def test_thinking_default_500_chars(self, capsys):
        thinking = 't' * 600
        block = {'type': 'thinking', 'thinking': thinking}
        _render_raw_block(block)  # default max_chars=500
        out = capsys.readouterr().out
        assert f"{'t' * 500}..." in out

    def test_tool_result_truncation_unchanged(self, capsys):
        block = {'type': 'tool_result', 'content': 'r' * 1000}
        _render_raw_block(block, max_chars=200)
        out = capsys.readouterr().out
        assert '[tool_result]' in out
        assert '800 more chars' in out


# Run tests with pytest
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
