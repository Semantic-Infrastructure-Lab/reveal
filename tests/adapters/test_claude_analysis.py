"""Unit tests for Claude adapter analysis/messages.py functions.

Tests the content-normalization helpers and search/filter functions
added in violet-gem-0218:
  - _extract_text
  - _content_to_blocks
  - _find_excerpt
  - search_messages
  - filter_by_role (str-content normalization fix)
  - get_thinking_blocks
  - get_message
"""

from reveal.adapters.claude.analysis.messages import (
    _extract_text,
    _content_to_blocks,
    _find_excerpt,
    search_messages,
    filter_by_role,
    get_thinking_blocks,
    get_message,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _contract_base():
    return {
        'contract_version': '1.0',
        'type': '',
        'source': '/fake/path.jsonl',
        'source_type': 'file',
    }


def _user_msg(content, timestamp='2026-01-01T10:00:00.000Z', idx=None):
    """Build a user-type message dict."""
    m = {
        'type': 'user',
        'timestamp': timestamp,
        'message': {'role': 'user', 'content': content},
    }
    return m


def _assistant_msg(content, timestamp='2026-01-01T10:01:00.000Z'):
    return {
        'type': 'assistant',
        'timestamp': timestamp,
        'message': {'role': 'assistant', 'content': content},
    }


# ---------------------------------------------------------------------------
# _extract_text
# ---------------------------------------------------------------------------

class TestExtractText:

    def test_string_content_returned_as_is(self):
        assert _extract_text('hello world') == 'hello world'

    def test_empty_string(self):
        assert _extract_text('') == ''

    def test_list_single_text_block(self):
        content = [{'type': 'text', 'text': 'hello'}]
        assert _extract_text(content) == 'hello'

    def test_list_multiple_text_blocks(self):
        content = [
            {'type': 'text', 'text': 'line one'},
            {'type': 'text', 'text': 'line two'},
        ]
        result = _extract_text(content)
        assert 'line one' in result
        assert 'line two' in result

    def test_list_skips_non_text_blocks(self):
        content = [
            {'type': 'thinking', 'thinking': 'some thought'},
            {'type': 'text', 'text': 'visible text'},
            {'type': 'tool_use', 'name': 'Bash', 'input': {}},
        ]
        assert _extract_text(content) == 'visible text'

    def test_list_all_non_text_returns_empty(self):
        content = [
            {'type': 'thinking', 'thinking': 'thought'},
            {'type': 'tool_use', 'name': 'Read', 'input': {}},
        ]
        assert _extract_text(content) == ''

    def test_none_returns_empty(self):
        assert _extract_text(None) == ''

    def test_dict_returns_empty(self):
        """Non-str, non-list input returns empty string."""
        assert _extract_text({'type': 'text', 'text': 'x'}) == ''

    def test_list_with_malformed_block(self):
        """Malformed blocks (non-dicts) are skipped gracefully."""
        content = ['not a dict', {'type': 'text', 'text': 'good'}]
        assert _extract_text(content) == 'good'

    def test_text_block_missing_text_key(self):
        """Text block without 'text' key returns empty string for that block."""
        content = [{'type': 'text'}]
        assert _extract_text(content) == ''


# ---------------------------------------------------------------------------
# _content_to_blocks
# ---------------------------------------------------------------------------

class TestContentToBlocks:

    def test_string_becomes_single_text_block(self):
        result = _content_to_blocks('hello')
        assert result == [{'type': 'text', 'text': 'hello'}]

    def test_list_returned_as_is(self):
        blocks = [{'type': 'text', 'text': 'x'}]
        assert _content_to_blocks(blocks) is blocks

    def test_empty_string_becomes_text_block(self):
        result = _content_to_blocks('')
        assert result == [{'type': 'text', 'text': ''}]

    def test_empty_list_returned_as_is(self):
        assert _content_to_blocks([]) == []

    def test_none_returns_empty_list(self):
        assert _content_to_blocks(None) == []

    def test_dict_returns_empty_list(self):
        assert _content_to_blocks({'type': 'text'}) == []

    def test_int_returns_empty_list(self):
        assert _content_to_blocks(42) == []


# ---------------------------------------------------------------------------
# _find_excerpt
# ---------------------------------------------------------------------------

class TestFindExcerpt:

    def test_term_in_middle(self):
        text = 'a' * 60 + 'TARGET' + 'b' * 60
        excerpt = _find_excerpt(text, 'TARGET')
        assert 'TARGET' in excerpt

    def test_term_at_start(self):
        text = 'TARGET at the start of text'
        excerpt = _find_excerpt(text, 'TARGET')
        assert 'TARGET' in excerpt

    def test_term_at_end(self):
        text = 'text ends with TARGET'
        excerpt = _find_excerpt(text, 'TARGET')
        assert 'TARGET' in excerpt

    def test_term_not_found_returns_prefix(self):
        text = 'no match here at all'
        result = _find_excerpt(text, 'MISSING', window=10)
        assert result == text[:10]

    def test_ellipsis_prefix_when_start_truncated(self):
        text = 'x' * 200 + 'TERM' + 'y' * 200
        excerpt = _find_excerpt(text, 'TERM')
        assert excerpt.startswith('...')

    def test_ellipsis_suffix_when_end_truncated(self):
        text = 'x' * 200 + 'TERM' + 'y' * 200
        excerpt = _find_excerpt(text, 'TERM')
        assert excerpt.endswith('...')

    def test_no_ellipsis_for_short_text(self):
        text = 'short TERM text'
        excerpt = _find_excerpt(text, 'TERM')
        assert not excerpt.startswith('...')
        assert not excerpt.endswith('...')

    def test_case_insensitive_match(self):
        text = 'This has a Target word in it'
        excerpt = _find_excerpt(text, 'target')
        assert 'Target' in excerpt

    def test_custom_window(self):
        text = 'a' * 100 + 'X' + 'b' * 100
        excerpt = _find_excerpt(text, 'X', window=20)
        # Result should be shorter than default window=120
        assert len(excerpt.replace('...', '')) < 50


# ---------------------------------------------------------------------------
# search_messages
# ---------------------------------------------------------------------------

class TestSearchMessages:

    def _messages_with_text(self):
        return [
            _user_msg('Hello, this contains path traversal vulnerability'),
            _assistant_msg([
                {'type': 'text', 'text': 'I found a path traversal issue.'},
                {'type': 'thinking', 'thinking': 'Let me think about path traversal...'},
            ]),
        ]

    def test_finds_match_in_user_text(self):
        messages = [_user_msg('the quick brown fox')]
        result = search_messages(messages, 'fox', 'test', _contract_base())
        assert result['match_count'] == 1
        assert result['matches'][0]['role'] == 'user'
        assert result['matches'][0]['block_type'] == 'text'

    def test_finds_match_in_assistant_text(self):
        messages = [_assistant_msg([{'type': 'text', 'text': 'fox in the box'}])]
        result = search_messages(messages, 'fox', 'test', _contract_base())
        assert result['match_count'] == 1
        assert result['matches'][0]['role'] == 'assistant'

    def test_finds_match_in_thinking_block(self):
        messages = [_assistant_msg([
            {'type': 'thinking', 'thinking': 'the needle is here'},
        ])]
        result = search_messages(messages, 'needle', 'test', _contract_base())
        assert result['match_count'] == 1
        assert result['matches'][0]['block_type'] == 'thinking'

    def test_finds_match_in_tool_use_input(self):
        messages = [_assistant_msg([
            {'type': 'tool_use', 'name': 'Bash', 'id': 't1',
             'input': {'command': 'grep -r needle /src', 'description': 'search'}},
        ])]
        result = search_messages(messages, 'needle', 'test', _contract_base())
        assert result['match_count'] == 1
        assert 'tool_use' in result['matches'][0]['block_type']

    def test_finds_match_in_tool_use_name(self):
        messages = [_assistant_msg([
            {'type': 'tool_use', 'name': 'Bash', 'id': 't1', 'input': {'command': 'ls'}},
        ])]
        result = search_messages(messages, 'Bash', 'test', _contract_base())
        assert result['match_count'] == 1

    def test_case_insensitive(self):
        messages = [_user_msg('Hello World')]
        result = search_messages(messages, 'hello world', 'test', _contract_base())
        assert result['match_count'] == 1

    def test_no_matches(self):
        messages = [_user_msg('nothing here')]
        result = search_messages(messages, 'xyzzy', 'test', _contract_base())
        assert result['match_count'] == 0
        assert result['matches'] == []

    def test_empty_messages(self):
        result = search_messages([], 'term', 'test', _contract_base())
        assert result['match_count'] == 0

    def test_str_content_user_message_found(self):
        """User messages with bare string content (initial prompt) are searchable."""
        messages = [
            {'type': 'user', 'timestamp': '2026-01-01T10:00:00Z',
             'message': {'role': 'user', 'content': 'find the needle in this string'}},
        ]
        result = search_messages(messages, 'needle', 'test', _contract_base())
        assert result['match_count'] == 1

    def test_str_content_no_char_iteration_bug(self):
        """Bare string content must NOT produce one match per character."""
        messages = [
            {'type': 'user', 'timestamp': '2026-01-01T10:00:00Z',
             'message': {'role': 'user', 'content': 'aaaaaa'}},
        ]
        result = search_messages(messages, 'a', 'test', _contract_base())
        # Should find 1 text-block match, not 6 character matches
        assert result['match_count'] == 1

    def test_result_type(self):
        result = search_messages([], 'x', 'session', _contract_base())
        assert result['type'] == 'claude_search_results'

    def test_result_includes_term(self):
        result = search_messages([], 'myterm', 'session', _contract_base())
        assert result['term'] == 'myterm'

    def test_result_includes_session(self):
        result = search_messages([], 'x', 'my-session', _contract_base())
        assert result['session'] == 'my-session'

    def test_match_includes_excerpt(self):
        messages = [_user_msg('the quick brown fox jumps')]
        result = search_messages(messages, 'fox', 'test', _contract_base())
        match = result['matches'][0]
        assert 'excerpt' in match
        assert 'fox' in match['excerpt'].lower()

    def test_match_includes_timestamp(self):
        messages = [_user_msg('target word here', timestamp='2026-01-15T09:30:00.000Z')]
        result = search_messages(messages, 'target', 'test', _contract_base())
        match = result['matches'][0]
        assert 'timestamp' in match
        # Timestamp should be truncated to YYYY-MM-DD HH:MM
        assert '2026-01-15' in match['timestamp']

    def test_skips_non_role_messages(self):
        """Messages without user/assistant type (e.g., system) are skipped."""
        messages = [
            {'type': 'system', 'timestamp': '2026-01-01T10:00:00Z',
             'message': {'content': [{'type': 'text', 'text': 'needle'}]}},
        ]
        result = search_messages(messages, 'needle', 'test', _contract_base())
        assert result['match_count'] == 0

    def test_multiple_blocks_multiple_matches(self):
        messages = [_assistant_msg([
            {'type': 'text', 'text': 'needle in text'},
            {'type': 'thinking', 'thinking': 'also needle in thinking'},
        ])]
        result = search_messages(messages, 'needle', 'test', _contract_base())
        assert result['match_count'] == 2


# ---------------------------------------------------------------------------
# filter_by_role (str-content fix)
# ---------------------------------------------------------------------------

class TestFilterByRole:

    def test_str_content_normalized_to_block_list(self):
        """Bare string content must be wrapped in a text block, not iterated."""
        messages = [
            {'type': 'user', 'timestamp': '2026-01-01T10:00:00Z',
             'message': {'role': 'user', 'content': 'initial prompt text'}},
        ]
        result = filter_by_role(messages, 'user', 'session', _contract_base())
        assert result['message_count'] == 1
        msg = result['messages'][0]
        content = msg['content']
        # Must be a list
        assert isinstance(content, list)
        # Must have exactly one block (not 18 chars = 18 items)
        assert len(content) == 1
        assert content[0] == {'type': 'text', 'text': 'initial prompt text'}

    def test_filters_only_requested_role(self):
        messages = [
            _user_msg([{'type': 'text', 'text': 'hi'}]),
            _assistant_msg([{'type': 'text', 'text': 'hello'}]),
            _user_msg([{'type': 'text', 'text': 'follow up'}]),
        ]
        result = filter_by_role(messages, 'user', 'session', _contract_base())
        assert result['message_count'] == 2

    def test_result_type_user(self):
        result = filter_by_role([], 'user', 'session', _contract_base())
        assert result['type'] == 'claude_user_messages'

    def test_result_type_assistant(self):
        result = filter_by_role([], 'assistant', 'session', _contract_base())
        assert result['type'] == 'claude_assistant_messages'

    def test_empty_messages(self):
        result = filter_by_role([], 'user', 'session', _contract_base())
        assert result['message_count'] == 0
        assert result['messages'] == []

    def test_message_index_preserved(self):
        messages = [
            _user_msg([{'type': 'text', 'text': 'a'}]),
            _assistant_msg([{'type': 'text', 'text': 'b'}]),
            _user_msg([{'type': 'text', 'text': 'c'}]),
        ]
        result = filter_by_role(messages, 'user', 'session', _contract_base())
        indices = [m['message_index'] for m in result['messages']]
        assert indices == [0, 2]

    def test_list_content_passed_through(self):
        blocks = [{'type': 'text', 'text': 'hello'}, {'type': 'thinking', 'thinking': 'X'}]
        messages = [_assistant_msg(blocks)]
        result = filter_by_role(messages, 'assistant', 'session', _contract_base())
        assert result['messages'][0]['content'] == blocks


# ---------------------------------------------------------------------------
# get_thinking_blocks
# ---------------------------------------------------------------------------

class TestGetThinkingBlocks:

    def test_extracts_thinking_blocks(self):
        messages = [
            _assistant_msg([
                {'type': 'thinking', 'thinking': 'first thought'},
                {'type': 'text', 'text': 'response'},
            ]),
            _assistant_msg([
                {'type': 'thinking', 'thinking': 'second thought'},
            ]),
        ]
        result = get_thinking_blocks(messages, 'session', _contract_base())
        assert result['thinking_block_count'] == 2

    def test_content_and_char_count(self):
        text = 'this is the thinking content'
        messages = [_assistant_msg([{'type': 'thinking', 'thinking': text}])]
        result = get_thinking_blocks(messages, 'session', _contract_base())
        block = result['blocks'][0]
        assert block['content'] == text
        assert block['char_count'] == len(text)

    def test_token_estimate(self):
        text = 'a' * 400
        messages = [_assistant_msg([{'type': 'thinking', 'thinking': text}])]
        result = get_thinking_blocks(messages, 'session', _contract_base())
        assert result['blocks'][0]['token_estimate'] == 100  # 400 // 4

    def test_no_thinking_blocks(self):
        messages = [_user_msg('hi'), _assistant_msg([{'type': 'text', 'text': 'hello'}])]
        result = get_thinking_blocks(messages, 'session', _contract_base())
        assert result['thinking_block_count'] == 0
        assert result['blocks'] == []
        assert result['total_chars'] == 0

    def test_user_messages_skipped(self):
        """Thinking blocks only come from assistant messages."""
        messages = [
            {'type': 'user', 'timestamp': '2026-01-01T10:00:00Z',
             'message': {'role': 'user', 'content': [
                 {'type': 'thinking', 'thinking': 'should be skipped'}
             ]}},
        ]
        result = get_thinking_blocks(messages, 'session', _contract_base())
        assert result['thinking_block_count'] == 0

    def test_result_type(self):
        result = get_thinking_blocks([], 'session', _contract_base())
        assert result['type'] == 'claude_thinking'

    def test_total_chars_sum(self):
        messages = [
            _assistant_msg([{'type': 'thinking', 'thinking': 'aa'}]),
            _assistant_msg([{'type': 'thinking', 'thinking': 'bbbb'}]),
        ]
        result = get_thinking_blocks(messages, 'session', _contract_base())
        assert result['total_chars'] == 6

    def test_non_list_content_skipped(self):
        """Assistant messages with non-list content (edge case) don't crash."""
        messages = [
            {'type': 'assistant', 'timestamp': '2026-01-01T10:01:00Z',
             'message': {'role': 'assistant', 'content': 'bare string'}},
        ]
        result = get_thinking_blocks(messages, 'session', _contract_base())
        assert result['thinking_block_count'] == 0


# ---------------------------------------------------------------------------
# get_message
# ---------------------------------------------------------------------------

class TestGetMessage:

    def _sample_messages(self):
        return [
            _user_msg('first message', timestamp='2026-01-01T10:00:00.000Z'),
            _assistant_msg([{'type': 'text', 'text': 'response'}],
                           timestamp='2026-01-01T10:01:00.000Z'),
            _user_msg('follow up', timestamp='2026-01-01T10:02:00.000Z'),
        ]

    def test_get_first_message(self):
        messages = self._sample_messages()
        result = get_message(messages, 0, 'session', _contract_base())
        assert result['message_index'] == 0
        assert result['message_type'] == 'user'
        assert 'error' not in result

    def test_get_last_message(self):
        messages = self._sample_messages()
        result = get_message(messages, 2, 'session', _contract_base())
        assert result['message_index'] == 2

    def test_out_of_range_positive(self):
        messages = self._sample_messages()
        result = get_message(messages, 99, 'session', _contract_base())
        assert 'error' in result
        assert 'out of range' in result['error']

    def test_out_of_range_negative(self):
        messages = self._sample_messages()
        result = get_message(messages, -1, 'session', _contract_base())
        assert 'error' in result

    def test_text_extracted_for_user_str_content(self):
        messages = [
            {'type': 'user', 'timestamp': '2026-01-01T10:00:00Z',
             'message': {'role': 'user', 'content': 'plain string content'}},
        ]
        result = get_message(messages, 0, 'session', _contract_base())
        assert result['text'] == 'plain string content'

    def test_text_extracted_for_list_content(self):
        messages = [_assistant_msg([{'type': 'text', 'text': 'hello from assistant'}])]
        result = get_message(messages, 0, 'session', _contract_base())
        assert result['text'] == 'hello from assistant'

    def test_timestamp_included(self):
        messages = self._sample_messages()
        result = get_message(messages, 0, 'session', _contract_base())
        assert result['timestamp'] == '2026-01-01T10:00:00.000Z'

    def test_result_type(self):
        messages = self._sample_messages()
        result = get_message(messages, 0, 'session', _contract_base())
        assert result['type'] == 'claude_message'

    def test_empty_messages_out_of_range(self):
        result = get_message([], 0, 'session', _contract_base())
        assert 'error' in result
