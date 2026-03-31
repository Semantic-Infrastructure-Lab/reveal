"""Tests for BACK-035/036/037: claude:// session listing enhancements.

BACK-035: README presence indicator (✓/✗) in session listing.
BACK-036: Project column derived from encoded project directory name.
BACK-037: --since=today support (converts 'today' to ISO date before comparison).
"""

import json
import pytest
from io import StringIO
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from reveal.adapters.claude.adapter import ClaudeAdapter
from reveal.adapters.claude.renderer import ClaudeRenderer


# ─── BACK-036: _extract_project_from_dir ──────────────────────────────────────

class TestExtractProjectFromDir:
    def test_tia_sessions_dir(self):
        assert ClaudeAdapter._extract_project_from_dir(
            '-home-scottsen-src-tia-sessions-hosefobe-0314'
        ) == 'tia'

    def test_reveal_project_dir(self):
        result = ClaudeAdapter._extract_project_from_dir(
            '-home-scottsen-src-projects-reveal-external-git'
        )
        assert result == 'reveal'

    def test_sdms_sessions_dir(self):
        assert ClaudeAdapter._extract_project_from_dir(
            '-home-scottsen-src-projects-sdms-platform-sessions-foo-0301'
        ) == 'platform'

    def test_squaroids_project(self):
        result = ClaudeAdapter._extract_project_from_dir(
            '-home-scottsen-src-projects-games-squaroids'
        )
        assert result == 'squaroids'

    def test_no_sessions_marker(self):
        result = ClaudeAdapter._extract_project_from_dir(
            '-home-scottsen-src-tia'
        )
        assert result == 'tia'

    def test_empty_dir_name(self):
        result = ClaudeAdapter._extract_project_from_dir('')
        assert result == ''

    def test_all_skip_words(self):
        result = ClaudeAdapter._extract_project_from_dir('-home-src-projects-external')
        assert result == ''


# ─── BACK-035/036: _collect_sessions_from_dir fields ─────────────────────────

class TestCollectSessionsDirFields:
    def test_readme_present_true(self, tmp_path):
        project_dir = tmp_path / '-home-user-src-tia-sessions-foo-0301'
        project_dir.mkdir()
        (project_dir / 'README.md').write_text('# Session')
        (project_dir / 'session.jsonl').write_text(
            json.dumps({'type': 'user', 'message': {'content': 'hi'}}) + '\n'
        )
        sessions = ClaudeAdapter._collect_sessions_from_dir(project_dir)
        assert len(sessions) == 1
        assert sessions[0]['readme_present'] is True

    def test_readme_present_false(self, tmp_path):
        project_dir = tmp_path / '-home-user-src-tia-sessions-bar-0302'
        project_dir.mkdir()
        (project_dir / 'session.jsonl').write_text(
            json.dumps({'type': 'user', 'message': {'content': 'hi'}}) + '\n'
        )
        sessions = ClaudeAdapter._collect_sessions_from_dir(project_dir)
        assert len(sessions) == 1
        assert sessions[0]['readme_present'] is False

    def test_readme_present_readme_with_suffix(self, tmp_path):
        project_dir = tmp_path / '-home-user-src-myapp'
        project_dir.mkdir()
        (project_dir / 'README_v2.md').write_text('# Session')
        (project_dir / 'session.jsonl').write_text(
            json.dumps({'type': 'user', 'message': {'content': 'hi'}}) + '\n'
        )
        sessions = ClaudeAdapter._collect_sessions_from_dir(project_dir)
        assert sessions[0]['readme_present'] is True

    def test_project_field_present(self, tmp_path):
        project_dir = tmp_path / '-home-scottsen-src-tia-sessions-baz-0303'
        project_dir.mkdir()
        (project_dir / 'session.jsonl').write_text(
            json.dumps({'type': 'user', 'message': {'content': 'hi'}}) + '\n'
        )
        sessions = ClaudeAdapter._collect_sessions_from_dir(project_dir)
        assert sessions[0]['project'] == 'tia'

    def test_all_sessions_share_same_readme_and_project(self, tmp_path):
        """All JSONL files in one dir share the same readme_present and project."""
        project_dir = tmp_path / '-home-scottsen-src-tia-sessions-multi-0303'
        project_dir.mkdir()
        (project_dir / 'README.md').write_text('# Session')
        for i in range(3):
            (project_dir / f'session{i}.jsonl').write_text(
                json.dumps({'type': 'user', 'message': {'content': 'hi'}}) + '\n'
            )
        sessions = ClaudeAdapter._collect_sessions_from_dir(project_dir)
        assert len(sessions) == 3
        assert all(s['readme_present'] is True for s in sessions)
        assert all(s['project'] == 'tia' for s in sessions)

    def test_agent_jsonl_skipped(self, tmp_path):
        project_dir = tmp_path / '-home-user-src-app'
        project_dir.mkdir()
        (project_dir / 'agent-abc.jsonl').write_text('{"type": "user"}\n')
        (project_dir / 'real-session.jsonl').write_text('{"type": "user"}\n')
        sessions = ClaudeAdapter._collect_sessions_from_dir(project_dir)
        assert len(sessions) == 1
        assert sessions[0]['session'] == '-home-user-src-app'


# ─── BACK-037: --since=today ──────────────────────────────────────────────────

class TestSinceToday:
    def _make_result(self, sessions):
        return {
            'type': 'claude_session_list',
            'recent_sessions': sessions,
            'session_count': len(sessions),
        }

    def test_since_today_filters_old_sessions(self):
        today = date.today().isoformat()
        sessions = [
            {'session': 'old', 'modified': '2020-01-01T00:00:00', 'size_kb': 1},
            {'session': 'new', 'modified': f'{today}T12:00:00', 'size_kb': 1},
        ]
        result = self._make_result(sessions)
        args = SimpleNamespace(search=None, since='today', all=True, head=None)
        with patch.object(ClaudeAdapter, '_read_session_title', return_value=None):
            ClaudeAdapter._post_process_session_list(result, args)
        names = [s['session'] for s in result['recent_sessions']]
        assert 'new' in names
        assert 'old' not in names

    def test_since_today_keeps_today_sessions(self):
        today = date.today().isoformat()
        sessions = [
            {'session': 'morning', 'modified': f'{today}T08:00:00', 'size_kb': 1},
            {'session': 'evening', 'modified': f'{today}T22:00:00', 'size_kb': 1},
        ]
        result = self._make_result(sessions)
        args = SimpleNamespace(search=None, since='today', all=True, head=None)
        with patch.object(ClaudeAdapter, '_read_session_title', return_value=None):
            ClaudeAdapter._post_process_session_list(result, args)
        assert len(result['recent_sessions']) == 2

    def test_since_date_string_works(self):
        sessions = [
            {'session': 'before', 'modified': '2026-03-13T00:00:00', 'size_kb': 1},
            {'session': 'after', 'modified': '2026-03-14T10:00:00', 'size_kb': 1},
        ]
        result = self._make_result(sessions)
        args = SimpleNamespace(search=None, since='2026-03-14', all=True, head=None)
        with patch.object(ClaudeAdapter, '_read_session_title', return_value=None):
            ClaudeAdapter._post_process_session_list(result, args)
        names = [s['session'] for s in result['recent_sessions']]
        assert 'after' in names
        assert 'before' not in names

    def test_since_none_no_filter(self):
        sessions = [
            {'session': 'old', 'modified': '2020-01-01T00:00:00', 'size_kb': 1},
            {'session': 'new', 'modified': '2026-03-14T00:00:00', 'size_kb': 1},
        ]
        result = self._make_result(sessions)
        args = SimpleNamespace(search=None, since=None, all=True, head=None)
        with patch.object(ClaudeAdapter, '_read_session_title', return_value=None):
            ClaudeAdapter._post_process_session_list(result, args)
        assert len(result['recent_sessions']) == 2


# ─── BACK-035/036: Renderer shows README + PROJECT columns ───────────────────

def _render_list(sessions, total=None):
    """Run _render_claude_session_list and capture stdout."""
    result = {
        'type': 'claude_session_list',
        'session_count': total if total is not None else len(sessions),
        'recent_sessions': sessions,
        'displayed_count': len(sessions),
        'usage': {},
    }
    buf = StringIO()
    with patch('sys.stdout', buf):
        ClaudeRenderer._render_claude_session_list(result)
    return buf.getvalue()


class TestRendererListColumns:
    def test_readme_present_shows_checkmark(self):
        sessions = [{'session': 'foo-0314', 'modified': '2026-03-14T10:00:00',
                     'size_kb': 10, 'readme_present': True, 'project': 'tia', 'title': 'Test'}]
        out = _render_list(sessions)
        assert '✓' in out

    def test_readme_absent_shows_x(self):
        sessions = [{'session': 'bar-0314', 'modified': '2026-03-14T10:00:00',
                     'size_kb': 10, 'readme_present': False, 'project': 'tia', 'title': 'Test'}]
        out = _render_list(sessions)
        assert '✗' in out

    def test_project_column_shown(self):
        sessions = [{'session': 'baz-0314', 'modified': '2026-03-14T10:00:00',
                     'size_kb': 5, 'readme_present': False, 'project': 'reveal', 'title': ''}]
        out = _render_list(sessions)
        assert 'reveal' in out

    def test_header_has_r_and_project(self):
        sessions = []
        out = _render_list(sessions)
        assert 'PROJECT' in out
        assert 'R' in out

    def test_long_project_truncated(self):
        sessions = [{'session': 'foo-0314', 'modified': '2026-03-14T10:00:00',
                     'size_kb': 5, 'readme_present': False,
                     'project': 'superlongprojectname', 'title': ''}]
        out = _render_list(sessions)
        assert 'superlongproject' not in out  # truncated to 12

    def test_readme_column_missing_field_shows_x(self):
        """Sessions without readme_present field → ✗ (falsy default)."""
        sessions = [{'session': 'old-session', 'modified': '2026-03-10T00:00:00',
                     'size_kb': 3, 'title': None}]
        out = _render_list(sessions)
        assert '✗' in out

    def test_since_hint_in_header(self):
        out = _render_list([])
        assert 'today' in out
