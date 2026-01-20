"""Unit tests for Claude Code conversation adapter."""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from reveal.adapters.claude.adapter import ClaudeAdapter


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
        assert result['tool_count'] == 4  # 2 Read + 1 Bash + 1 Write


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


# Run tests with pytest
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
