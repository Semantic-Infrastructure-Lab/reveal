"""Tests for BACK-027 (title extraction), BACK-030 (analytics renderer), BACK-034 (duration format)."""

import json
import pytest
from io import StringIO
from unittest.mock import patch

from reveal.adapters.claude.analysis.overview import (
    _calculate_session_duration,
    _extract_session_title,
    _extract_badge_from_messages,
)
from reveal.adapters.claude.renderer import ClaudeRenderer


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_user_msg(text):
    return {'type': 'user', 'message': {'content': text}}


def _make_assistant_msg(content_blocks):
    return {'type': 'assistant', 'message': {'content': content_blocks}}


def _make_bash_call(cmd):
    return {'type': 'tool_use', 'name': 'Bash', 'input': {'command': cmd}}


def _make_ts_msg(ts):
    return {'type': 'user', 'message': {'content': 'hi'}, 'timestamp': ts}


# ─── BACK-034: Duration format ────────────────────────────────────────────────

class TestDurationFormat:
    def _make_messages(self, ts1, ts2):
        return [
            {'type': 'user', 'message': {'content': 'hi'}, 'timestamp': ts1},
            {'type': 'user', 'message': {'content': 'bye'}, 'timestamp': ts2},
        ]

    def test_minutes_and_seconds(self):
        msgs = self._make_messages('2026-03-14T10:00:00Z', '2026-03-14T10:31:55Z')
        assert _calculate_session_duration(msgs) == '31m 55s'

    def test_zero_minutes(self):
        msgs = self._make_messages('2026-03-14T10:00:00Z', '2026-03-14T10:00:45Z')
        assert _calculate_session_duration(msgs) == '0m 45s'

    def test_hours_included(self):
        msgs = self._make_messages('2026-03-14T10:00:00Z', '2026-03-14T11:15:30Z')
        assert _calculate_session_duration(msgs) == '1h 15m 30s'

    def test_no_microseconds_in_output(self):
        msgs = self._make_messages('2026-03-14T10:00:00Z', '2026-03-14T10:31:55.617000Z')
        result = _calculate_session_duration(msgs)
        assert '.' not in result
        assert result == '31m 55s'

    def test_single_message_returns_none(self):
        msgs = [{'type': 'user', 'message': {'content': 'hi'}, 'timestamp': '2026-03-14T10:00:00Z'}]
        assert _calculate_session_duration(msgs) is None

    def test_no_timestamps_returns_none(self):
        msgs = [_make_user_msg('hi'), _make_user_msg('bye')]
        assert _calculate_session_duration(msgs) is None


# ─── BACK-027: Title extraction ───────────────────────────────────────────────

class TestTitleExtraction:
    def test_badge_takes_priority_over_everything(self):
        msgs = [
            _make_user_msg('# Session Continuation Context\n\n---\n\nboot.'),
            _make_assistant_msg([_make_bash_call('tia session badge "coverage + backlog triage"')]),
            _make_user_msg('work on Reveal'),
        ]
        assert _extract_session_title(msgs) == 'coverage + backlog triage'

    def test_badge_extracted_from_later_message(self):
        msgs = [
            _make_user_msg('work on Reveal'),
            _make_user_msg('more work'),
            _make_assistant_msg([_make_bash_call('tia session badge "refactor auth layer"')]),
        ]
        assert _extract_session_title(msgs) == 'refactor auth layer'

    def test_skips_session_continuation_boilerplate(self):
        msgs = [
            _make_user_msg('# Session Continuation Context\n\nHere is the README...\n---\n\nwork on Reveal, diligently'),
        ]
        assert _extract_session_title(msgs) == 'work on Reveal, diligently'

    def test_extracts_inline_topic_after_separator(self):
        msgs = [
            _make_user_msg('# Session Continuation Context\n\nLong readme...\n---\n\nfix the auth bug'),
        ]
        result = _extract_session_title(msgs)
        assert result == 'fix the auth bug'

    def test_skips_bare_boot(self):
        msgs = [
            _make_user_msg('boot'),
            _make_user_msg('fix the login page'),
        ]
        assert _extract_session_title(msgs) == 'fix the login page'

    def test_returns_first_real_user_message(self):
        msgs = [
            _make_user_msg('add dark mode to the dashboard'),
        ]
        assert _extract_session_title(msgs) == 'add dark mode to the dashboard'

    def test_truncates_to_100_chars(self):
        msgs = [_make_user_msg('x' * 150)]
        result = _extract_session_title(msgs)
        assert len(result) == 100

    def test_returns_none_when_all_boilerplate(self):
        msgs = [
            _make_user_msg('# Session Continuation Context\n\nREADME text'),
            _make_user_msg('boot'),
        ]
        assert _extract_session_title(msgs) is None

    def test_no_messages_returns_none(self):
        assert _extract_session_title([]) is None


class TestExtractBadge:
    def test_extracts_quoted_badge(self):
        msgs = [_make_assistant_msg([_make_bash_call('tia session badge "my badge text"')])]
        assert _extract_badge_from_messages(msgs) == 'my badge text'

    def test_badge_with_spaces_and_special_chars(self):
        msgs = [_make_assistant_msg([_make_bash_call('tia session badge "BACK-025 + coverage [saved]"')])]
        assert _extract_badge_from_messages(msgs) == 'BACK-025 + coverage [saved]'

    def test_no_badge_returns_none(self):
        msgs = [_make_user_msg('hi'), _make_assistant_msg([{'type': 'text', 'text': 'hello'}])]
        assert _extract_badge_from_messages(msgs) is None

    def test_non_bash_tool_ignored(self):
        msgs = [_make_assistant_msg([{'type': 'tool_use', 'name': 'Read',
                                       'input': {'command': 'tia session badge "ignored"'}}])]
        assert _extract_badge_from_messages(msgs) is None

    def test_empty_messages_returns_none(self):
        assert _extract_badge_from_messages([]) is None


# ─── BACK-030: Analytics renderer ─────────────────────────────────────────────

class TestAnalyticsRenderer:
    def _render(self, result):
        output = StringIO()
        with patch('sys.stdout', output):
            ClaudeRenderer._render_claude_analytics(result)
        return output.getvalue()

    def _make_result(self, **kwargs):
        base = {
            'type': 'claude_analytics',
            'session': 'test-session-0314',
            'message_count': 42,
            'user_messages': 15,
            'assistant_messages': 27,
        }
        base.update(kwargs)
        return base

    def test_shows_session_name(self):
        out = self._render(self._make_result())
        assert 'test-session-0314' in out

    def test_shows_title_when_present(self):
        out = self._render(self._make_result(title='my session title'))
        assert 'my session title' in out

    def test_no_title_line_when_absent(self):
        out = self._render(self._make_result())
        assert 'Title:' not in out

    def test_shows_duration(self):
        out = self._render(self._make_result(duration='31m 55s'))
        assert '31m 55s' in out

    def test_shows_message_counts(self):
        out = self._render(self._make_result())
        assert '42' in out
        assert '15' in out
        assert '27' in out

    def test_renders_tool_success_rates(self):
        tool_success_rate = {
            'Bash': {'success': 45, 'failure': 3, 'total': 48, 'success_rate': 93.8},
            'Read': {'success': 20, 'failure': 0, 'total': 20, 'success_rate': 100.0},
        }
        out = self._render(self._make_result(tool_success_rate=tool_success_rate))
        assert 'Bash' in out
        assert '93.8%' in out
        assert '45/48' in out
        assert '3 failed' in out
        assert 'Read' in out
        assert '100.0%' in out

    def test_no_failed_shown_when_zero(self):
        tool_success_rate = {
            'Read': {'success': 10, 'failure': 0, 'total': 10, 'success_rate': 100.0},
        }
        out = self._render(self._make_result(tool_success_rate=tool_success_rate))
        assert 'failed' not in out

    def test_shows_message_size_stats(self):
        out = self._render(self._make_result(avg_message_size=1500, max_message_size=12000))
        assert '1,500' in out
        assert '12,000' in out

    def test_shows_thinking_blocks(self):
        out = self._render(self._make_result(thinking_blocks=8, thinking_tokens_approx=4200))
        assert '8 blocks' in out
        assert '4,200' in out

    def test_no_tool_success_section_when_empty(self):
        out = self._render(self._make_result(tool_success_rate={}))
        assert 'Tool Success' not in out

    def test_dispatched_via_type(self):
        """Ensure claude_analytics type routes to _render_claude_analytics."""
        result = self._make_result()
        output = StringIO()
        with patch('sys.stdout', output):
            ClaudeRenderer._render_text(result)
        out = output.getvalue()
        assert 'test-session-0314' in out
        assert '[dict' not in out  # regression: old fallback showed [dict with N items]
