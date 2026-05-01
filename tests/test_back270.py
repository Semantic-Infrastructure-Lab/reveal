"""Tests for BACK-270: path aliases for query-routed views.

/errors, /summary, /timeline, /tokens are aliases for ?errors, ?summary,
?timeline, ?tokens — both forms should return the same result type.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.claude.adapter import ClaudeAdapter


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_session(tmp_path: Path, messages: list) -> Path:
    """Write session JSONL and return the projects directory."""
    projects = tmp_path / 'projects'
    proj = projects / '-home-user-tia-sessions-my-sess'
    proj.mkdir(parents=True, exist_ok=True)
    f = proj / 'my-sess.jsonl'
    with open(f, 'w') as fh:
        for m in messages:
            fh.write(json.dumps(m) + '\n')
    return projects


def _user_msg(text: str) -> dict:
    return {
        'type': 'user',
        'timestamp': '2026-03-14T10:00:00',
        'message': {'role': 'user', 'content': text},
    }


def _assistant_msg(text: str) -> dict:
    return {
        'type': 'assistant',
        'timestamp': '2026-03-14T10:01:00',
        'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': text}]},
    }


_MESSAGES = [_user_msg('hello'), _assistant_msg('world')]


# ─── Path alias tests ─────────────────────────────────────────────────────────

class TestPathAliases:
    """Each path-form alias returns the same result type as the query form."""

    def _get(self, tmp_path, resource, query=None):
        projects = _make_session(tmp_path, _MESSAGES)
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', projects):
            adapter = ClaudeAdapter(resource, query=query)
            return adapter.get_structure()

    def test_errors_path_alias(self, tmp_path):
        r = self._get(tmp_path, 'session/my-sess/errors')
        assert r['type'] == 'claude_errors'

    def test_errors_query_form_unchanged(self, tmp_path):
        r = self._get(tmp_path, 'session/my-sess', query='errors')
        assert r['type'] == 'claude_errors'

    def test_summary_path_alias(self, tmp_path):
        r = self._get(tmp_path, 'session/my-sess/summary')
        assert r['type'] == 'claude_analytics'

    def test_summary_query_form_unchanged(self, tmp_path):
        r = self._get(tmp_path, 'session/my-sess', query='summary')
        assert r['type'] == 'claude_analytics'

    def test_timeline_path_alias(self, tmp_path):
        r = self._get(tmp_path, 'session/my-sess/timeline')
        assert r['type'] == 'claude_timeline'

    def test_timeline_query_form_unchanged(self, tmp_path):
        r = self._get(tmp_path, 'session/my-sess', query='timeline')
        assert r['type'] == 'claude_timeline'

    def test_tokens_path_alias(self, tmp_path):
        r = self._get(tmp_path, 'session/my-sess/tokens')
        assert r['type'] == 'claude_token_breakdown'

    def test_tokens_query_form_unchanged(self, tmp_path):
        r = self._get(tmp_path, 'session/my-sess', query='tokens')
        assert r['type'] == 'claude_token_breakdown'

    def test_path_alias_and_query_form_return_same_type(self, tmp_path):
        """Both forms of each view return identical result types."""
        for path_seg, query_str, expected_type in [
            ('errors',   'errors',   'claude_errors'),
            ('timeline', 'timeline', 'claude_timeline'),
            ('tokens',   'tokens',   'claude_token_breakdown'),
            ('summary',  'summary',  'claude_analytics'),
        ]:
            rp = self._get(tmp_path, f'session/my-sess/{path_seg}')
            rq = self._get(tmp_path, 'session/my-sess', query=query_str)
            rp_type = rp['type']
            rq_type = rq['type']
            assert rp_type == expected_type, f'/{path_seg} returned {rp_type!r}'
            assert rq_type == expected_type, f'?{query_str} returned {rq_type!r}'
