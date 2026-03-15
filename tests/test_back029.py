"""Tests for BACK-029: cross-session content search via claude://?search=term.

Architecture:
  Phase 1 — grep_files() parallel byte-scan pre-filters the JSONL corpus.
  Phase 2 — _extract_first_snippet() parses only matching files for excerpts.
  Routing — bare claude://?search=term triggers _search_sessions(), not name filter.
"""

import json
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.adapters.claude.analysis.search import (
    search_sessions_for_term,
    _extract_first_snippet,
)
from reveal.adapters.claude.renderer import ClaudeRenderer


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _write_session(directory: Path, session_name: str, messages: list) -> Path:
    """Write a JSONL session file under directory/session_name/."""
    project_dir = directory / f'-home-user-sessions-{session_name}'
    project_dir.mkdir(parents=True, exist_ok=True)
    jsonl = project_dir / f'{session_name}.jsonl'
    with open(jsonl, 'w') as fh:
        for msg in messages:
            fh.write(json.dumps(msg) + '\n')
    return jsonl


def _user_msg(text: str, ts: str = '2026-03-14T10:00:00') -> dict:
    return {
        'type': 'user',
        'timestamp': ts,
        'message': {'role': 'user', 'content': text},
    }


def _assistant_msg(text: str, ts: str = '2026-03-14T10:01:00') -> dict:
    return {
        'type': 'assistant',
        'timestamp': ts,
        'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]},
    }


# ─── _extract_first_snippet ──────────────────────────────────────────────────

class TestExtractFirstSnippet:

    def test_finds_user_message(self, tmp_path):
        jsonl = tmp_path / 'sess.jsonl'
        jsonl.write_text(
            json.dumps(_user_msg('working on topstep MES bot today')) + '\n'
        )
        result = _extract_first_snippet(jsonl, 'topstep')
        assert 'topstep' in result['excerpt'].lower()
        assert result['role'] == 'user'

    def test_finds_assistant_message(self, tmp_path):
        jsonl = tmp_path / 'sess.jsonl'
        jsonl.write_text(
            json.dumps(_assistant_msg('The TopStep combine limit is 3000')) + '\n'
        )
        result = _extract_first_snippet(jsonl, 'topstep')
        assert result['excerpt']
        assert result['role'] == 'assistant'

    def test_case_insensitive(self, tmp_path):
        jsonl = tmp_path / 'sess.jsonl'
        jsonl.write_text(json.dumps(_user_msg('TOPSTEP is the platform')) + '\n')
        result = _extract_first_snippet(jsonl, 'topstep')
        assert result['excerpt']

    def test_skips_non_matching_lines(self, tmp_path):
        jsonl = tmp_path / 'sess.jsonl'
        lines = [
            json.dumps(_user_msg('completely unrelated content')),
            json.dumps(_user_msg('also irrelevant')),
            json.dumps(_user_msg('finally: topstep mention here')),
        ]
        jsonl.write_text('\n'.join(lines) + '\n')
        result = _extract_first_snippet(jsonl, 'topstep')
        assert 'topstep' in result['excerpt'].lower()

    def test_returns_empty_dict_on_no_match(self, tmp_path):
        jsonl = tmp_path / 'sess.jsonl'
        jsonl.write_text(json.dumps(_user_msg('nothing relevant')) + '\n')
        result = _extract_first_snippet(jsonl, 'kubernetes')
        assert result['excerpt'] == ''
        assert result['role'] == ''
        assert result['timestamp'] == ''

    def test_handles_missing_file_gracefully(self, tmp_path):
        result = _extract_first_snippet(tmp_path / 'nonexistent.jsonl', 'term')
        assert result == {'excerpt': '', 'role': '', 'timestamp': ''}

    def test_skips_tool_result_lines_without_text(self, tmp_path):
        jsonl = tmp_path / 'sess.jsonl'
        # A tool_result line that mentions the term in result data
        tool_line = {
            'type': 'user',
            'timestamp': '2026-03-14T10:00:00',
            'message': {
                'role': 'user',
                'content': [{'type': 'tool_result', 'content': 'topstep data here'}],
            },
        }
        # Followed by a proper text message
        user_line = _user_msg('the topstep combine setup')
        jsonl.write_text(
            json.dumps(tool_line) + '\n' + json.dumps(user_line) + '\n'
        )
        result = _extract_first_snippet(jsonl, 'topstep')
        # Should find the text message
        assert result['role'] in ('user', 'assistant')


# ─── search_sessions_for_term ─────────────────────────────────────────────────

class TestSearchSessionsForTerm:

    def _make_sessions(self, base: Path, specs: list) -> list:
        """Build session dicts for specs = [(name, messages, modified_date)]."""
        sessions = []
        for name, messages, modified in specs:
            jsonl = _write_session(base, name, messages)
            sessions.append({
                'session': name,
                'path': str(jsonl),
                'modified': f'{modified}T12:00:00',
                'project': 'test',
                'size_kb': 1,
                'readme_present': False,
            })
        return sessions

    def test_finds_matching_sessions(self, tmp_path):
        sessions = self._make_sessions(tmp_path, [
            ('alpha', [_user_msg('working on topstep today')], '2026-03-14'),
            ('beta',  [_user_msg('unrelated content here')],   '2026-03-14'),
            ('gamma', [_user_msg('more topstep combine work')], '2026-03-13'),
        ])
        results = search_sessions_for_term(sessions, 'topstep')
        names = {r['session'] for r in results}
        assert 'alpha' in names
        assert 'gamma' in names
        assert 'beta' not in names

    def test_returns_empty_for_no_matches(self, tmp_path):
        sessions = self._make_sessions(tmp_path, [
            ('alpha', [_user_msg('completely different')], '2026-03-14'),
        ])
        results = search_sessions_for_term(sessions, 'kubernetes')
        assert results == []

    def test_results_sorted_most_recent_first(self, tmp_path):
        sessions = self._make_sessions(tmp_path, [
            ('older',  [_user_msg('topstep stuff')], '2026-03-10'),
            ('newer',  [_user_msg('topstep work')],  '2026-03-14'),
            ('middle', [_user_msg('topstep here')],  '2026-03-12'),
        ])
        results = search_sessions_for_term(sessions, 'topstep')
        assert len(results) == 3
        dates = [r['modified'] for r in results]
        assert dates == sorted(dates, reverse=True)

    def test_result_has_required_fields(self, tmp_path):
        sessions = self._make_sessions(tmp_path, [
            ('my-session', [_user_msg('topstep combine limits')], '2026-03-14'),
        ])
        results = search_sessions_for_term(sessions, 'topstep')
        assert len(results) == 1
        r = results[0]
        assert r['session'] == 'my-session'
        assert r['modified']
        assert r['project'] == 'test'
        assert 'excerpt' in r
        assert 'role' in r
        assert 'timestamp' in r

    def test_excerpt_contains_context(self, tmp_path):
        sessions = self._make_sessions(tmp_path, [
            ('my-sess', [_user_msg('checking topstep position limits today')], '2026-03-14'),
        ])
        results = search_sessions_for_term(sessions, 'topstep')
        assert results[0]['excerpt']

    def test_empty_sessions_returns_empty(self, tmp_path):
        assert search_sessions_for_term([], 'topstep') == []

    def test_empty_term_returns_empty(self, tmp_path):
        sessions = self._make_sessions(tmp_path, [
            ('s', [_user_msg('content')], '2026-03-14'),
        ])
        assert search_sessions_for_term(sessions, '') == []

    def test_case_insensitive_matching(self, tmp_path):
        sessions = self._make_sessions(tmp_path, [
            ('s1', [_user_msg('TOPSTEP is the platform')], '2026-03-14'),
        ])
        results_lower = search_sessions_for_term(sessions, 'topstep')
        results_upper = search_sessions_for_term(sessions, 'TOPSTEP')
        assert len(results_lower) == 1
        assert len(results_upper) == 1


# ─── Routing: claude://?search= triggers _search_sessions ────────────────────

class TestCrossSessionSearchRouting:

    def test_search_param_routes_to_content_search(self, tmp_path):
        """claude://?search=term should invoke _search_sessions, not _list_sessions."""
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=topstep')
            result = adapter.get_structure()
        assert result['type'] == 'claude_cross_session_search'
        assert result['term'] == 'topstep'

    def test_no_search_param_routes_to_list(self, tmp_path):
        """claude:// without ?search= should remain a session listing."""
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query=None)
            result = adapter.get_structure()
        assert result['type'] == 'claude_session_list'

    def test_filter_param_still_routes_to_list(self, tmp_path):
        """claude://?filter=myproject should still return a session listing."""
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='filter=myproject')
            result = adapter.get_structure()
        assert result['type'] == 'claude_session_list'

    def test_sessions_prefix_with_search_routes_to_content_search(self, tmp_path):
        """claude://sessions?search=term should also hit _search_sessions."""
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('sessions', query='search=topstep')
            result = adapter.get_structure()
        assert result['type'] == 'claude_cross_session_search'

    def test_result_has_contract_fields(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=anything')
            result = adapter.get_structure()
        assert result.get('contract_version') == '1.0'
        assert 'sessions_scanned' in result
        assert 'match_count' in result
        assert 'matches' in result

    def test_since_param_scopes_corpus(self, tmp_path):
        """Sessions older than --since should be excluded from the scan."""
        # Create one old session that contains the term
        old_dir = tmp_path / '-home-user-sessions-old-sess'
        old_dir.mkdir(parents=True)
        old_jsonl = old_dir / 'old-sess.jsonl'
        old_jsonl.write_text(json.dumps(_user_msg('topstep data here')) + '\n')
        # Force old mtime
        import os, time
        old_time = time.mktime(time.strptime('2026-01-01', '%Y-%m-%d'))
        os.utime(old_jsonl, (old_time, old_time))

        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=topstep&since=2026-03-01')
            result = adapter.get_structure()

        # Old session should NOT appear — filtered out by since before grep
        sessions_found = {m['session'] for m in result['matches']}
        assert 'old-sess' not in sessions_found

    def test_empty_search_term_returns_zero_matches(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=')
            # Empty ?search= should not route to content search
            # (falls back to _list_sessions since query_params.get('search') is falsy)
            result = adapter.get_structure()
        assert result['type'] == 'claude_session_list'


# ─── Integration: real corpus in tmp_path ─────────────────────────────────────

class TestCrossSessionSearchIntegration:

    def test_finds_sessions_in_real_corpus(self, tmp_path):
        _write_session(tmp_path, 'alpha-0310',
                       [_user_msg('working on topstep combine limits')])
        _write_session(tmp_path, 'beta-0311',
                       [_user_msg('unrelated kubernetes deploy work')])
        _write_session(tmp_path, 'gamma-0312',
                       [_user_msg('more topstep MES bot debugging')])

        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=topstep')
            result = adapter.get_structure()

        assert result['type'] == 'claude_cross_session_search'
        assert result['match_count'] == 2
        names = {m['session'] for m in result['matches']}
        assert 'alpha-0310' in names
        assert 'gamma-0312' in names
        assert 'beta-0311' not in names

    def test_scanned_count_reflects_corpus_size(self, tmp_path):
        for i in range(5):
            _write_session(tmp_path, f'sess-{i}', [_user_msg(f'content {i}')])

        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=content')
            result = adapter.get_structure()

        assert result['sessions_scanned'] == 5
        assert result['match_count'] == 5


# ─── Renderer ─────────────────────────────────────────────────────────────────

class TestCrossSessionSearchRenderer:

    def _render(self, result: dict) -> str:
        buf = StringIO()
        import sys
        old = sys.stdout
        sys.stdout = buf
        try:
            ClaudeRenderer._render_text(result)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_renders_header(self):
        result = {
            'type': 'claude_cross_session_search',
            'term': 'topstep',
            'sessions_scanned': 100,
            'match_count': 3,
            'since': None,
            'matches': [],
        }
        output = self._render(result)
        assert 'topstep' in output
        assert '100' in output
        assert '3' in output

    def test_renders_match_entries(self):
        result = {
            'type': 'claude_cross_session_search',
            'term': 'topstep',
            'sessions_scanned': 10,
            'match_count': 1,
            'since': None,
            'matches': [{
                'session': 'alpha-0314',
                'modified': '2026-03-14T18:45:00',
                'project': 'tia',
                'role': 'user',
                'excerpt': '...checking topstep combine data...',
                'timestamp': '2026-03-14 18:44',
                'readme_present': True,
                'size_kb': 50,
            }],
        }
        output = self._render(result)
        assert 'alpha-0314' in output
        assert 'tia' in output
        assert 'topstep' in output

    def test_renders_since_in_header(self):
        result = {
            'type': 'claude_cross_session_search',
            'term': 'deploy',
            'sessions_scanned': 50,
            'match_count': 0,
            'since': '2026-03-10',
            'matches': [],
        }
        output = self._render(result)
        assert '2026-03-10' in output

    def test_renders_zero_matches_gracefully(self):
        result = {
            'type': 'claude_cross_session_search',
            'term': 'xyzzy',
            'sessions_scanned': 200,
            'match_count': 0,
            'since': None,
            'matches': [],
        }
        output = self._render(result)
        assert 'xyzzy' in output
        assert '0' in output
