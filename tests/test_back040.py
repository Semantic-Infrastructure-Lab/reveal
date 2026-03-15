"""Tests for BACK-040: cross-session file tracking via claude://files/<path>.

Architecture:
  Phase 1 — grep_files() parallel byte-scan pre-filters sessions containing the path.
  Phase 2 — get_files_touched() extracts per-session Read/Write/Edit counts.
  Routing — claude://files/<path> triggers _track_file_sessions().
"""

import json
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.claude.adapter import ClaudeAdapter
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


def _file_op_msg(op: str, file_path: str, ts: str = '2026-03-14T10:01:00') -> dict:
    """Assistant message that performs a file operation via tool_use."""
    return {
        'type': 'assistant',
        'timestamp': ts,
        'message': {
            'role': 'assistant',
            'content': [{
                'type': 'tool_use',
                'name': op,
                'input': {'file_path': file_path},
            }],
        },
    }


# ─── Routing ──────────────────────────────────────────────────────────────────

class TestFileSessionsRouting:

    def test_files_path_routes_to_track_file_sessions(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/adapter.py')
            result = adapter.get_structure()
        assert result['type'] == 'claude_file_sessions'

    def test_bare_files_routes_to_track_file_sessions(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files')
            result = adapter.get_structure()
        assert result['type'] == 'claude_file_sessions'

    def test_bare_files_with_no_path_returns_error(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files')
            result = adapter.get_structure()
        assert 'error' in result
        assert result['match_count'] == 0

    def test_files_does_not_interfere_with_search_route(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('', query='search=topstep')
            result = adapter.get_structure()
        assert result['type'] == 'claude_cross_session_search'

    def test_files_does_not_interfere_with_listing(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('')
            result = adapter.get_structure()
        assert result['type'] == 'claude_session_list'


# ─── Contract ─────────────────────────────────────────────────────────────────

class TestFileSessionsContract:

    def test_result_has_contract_fields(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/adapter.py')
            result = adapter.get_structure()
        assert result['contract_version'] == '1.0'
        assert result['type'] == 'claude_file_sessions'
        assert 'file_path' in result
        assert 'sessions_scanned' in result
        assert 'match_count' in result
        assert 'sessions' in result
        assert isinstance(result['sessions'], list)

    def test_file_path_in_result_matches_query(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/reveal/adapters/claude/adapter.py')
            result = adapter.get_structure()
        assert result['file_path'] == 'reveal/adapters/claude/adapter.py'

    def test_since_none_when_not_provided(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/adapter.py')
            result = adapter.get_structure()
        assert result['since'] is None

    def test_since_stored_in_result(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/adapter.py', query='since=2026-03-01')
            result = adapter.get_structure()
        assert result['since'] == '2026-03-01'


# ─── Integration ──────────────────────────────────────────────────────────────

class TestFileSessionsIntegration:

    def test_finds_session_with_read_op(self, tmp_path):
        """Session that Read the target file should appear in results."""
        _write_session(tmp_path, 'alpha-0314', [
            _user_msg('can you read the config?'),
            _file_op_msg('Read', '/home/user/project/config.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/config.py')
            result = adapter.get_structure()
        assert result['match_count'] == 1
        assert result['sessions'][0]['session'] == 'alpha-0314'

    def test_finds_session_with_edit_op(self, tmp_path):
        """Session that Edited the target file should appear in results."""
        _write_session(tmp_path, 'beta-0314', [
            _user_msg('edit the util'),
            _file_op_msg('Edit', '/home/user/src/util.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/util.py')
            result = adapter.get_structure()
        assert result['match_count'] == 1

    def test_finds_session_with_write_op(self, tmp_path):
        """Session that Wrote the target file should appear in results."""
        _write_session(tmp_path, 'gamma-0314', [
            _user_msg('create new.py'),
            _file_op_msg('Write', '/home/user/src/new.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/new.py')
            result = adapter.get_structure()
        assert result['match_count'] == 1

    def test_excludes_session_without_target_file(self, tmp_path):
        """Session that only touched other files should not appear."""
        _write_session(tmp_path, 'unrelated-0314', [
            _file_op_msg('Read', '/home/user/src/other.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/target.py')
            result = adapter.get_structure()
        assert result['match_count'] == 0

    def test_ops_counts_are_correct(self, tmp_path):
        """Read ×2, Edit ×3 on target file should be counted correctly."""
        _write_session(tmp_path, 'count-test', [
            _file_op_msg('Read', '/home/user/project/adapter.py'),
            _file_op_msg('Read', '/home/user/project/adapter.py'),
            _file_op_msg('Edit', '/home/user/project/adapter.py'),
            _file_op_msg('Edit', '/home/user/project/adapter.py'),
            _file_op_msg('Edit', '/home/user/project/adapter.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/adapter.py')
            result = adapter.get_structure()
        assert result['match_count'] == 1
        ops = result['sessions'][0]['ops']
        assert ops.get('Read') == 2
        assert ops.get('Edit') == 3
        assert result['sessions'][0]['total_ops'] == 5

    def test_multiple_sessions_multiple_files(self, tmp_path):
        """Only sessions touching target appear; others excluded."""
        _write_session(tmp_path, 'touch-target', [
            _file_op_msg('Edit', '/home/user/src/main.py'),
        ])
        _write_session(tmp_path, 'touch-other', [
            _file_op_msg('Read', '/home/user/src/utils.py'),
        ])
        _write_session(tmp_path, 'touch-both', [
            _file_op_msg('Read', '/home/user/src/main.py'),
            _file_op_msg('Edit', '/home/user/src/utils.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/main.py')
            result = adapter.get_structure()
        names = {s['session'] for s in result['sessions']}
        assert 'touch-target' in names
        assert 'touch-both' in names
        assert 'touch-other' not in names

    def test_results_sorted_newest_first(self, tmp_path):
        """Sessions should be returned newest-first."""
        import os, time
        for name, date_str in [('old-0310', '2026-03-10'), ('new-0314', '2026-03-14'), ('mid-0312', '2026-03-12')]:
            jsonl = _write_session(tmp_path, name, [
                _file_op_msg('Read', '/home/user/project/shared.py'),
            ])
            ts = time.mktime(time.strptime(date_str, '%Y-%m-%d'))
            os.utime(jsonl, (ts, ts))
            # Also set mtime on the parent dir's jsonl
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/shared.py')
            result = adapter.get_structure()
        assert result['match_count'] == 3
        dates = [s['modified'] for s in result['sessions']]
        assert dates == sorted(dates, reverse=True)

    def test_sessions_scanned_reflects_corpus(self, tmp_path):
        """sessions_scanned should count all sessions in the corpus."""
        for i in range(4):
            _write_session(tmp_path, f'sess-{i}', [
                _file_op_msg('Read', f'/home/user/project/file_{i}.py'),
            ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/file_0.py')
            result = adapter.get_structure()
        assert result['sessions_scanned'] == 4
        assert result['match_count'] == 1

    def test_partial_path_matching(self, tmp_path):
        """Fragment like 'adapter.py' should match absolute paths."""
        _write_session(tmp_path, 'partial-match', [
            _file_op_msg('Read', '/long/absolute/path/to/reveal/adapters/claude/adapter.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            # Short fragment matches the tail
            adapter = ClaudeAdapter('files/claude/adapter.py')
            result = adapter.get_structure()
        assert result['match_count'] == 1

    def test_since_today_keyword_works(self, tmp_path):
        """?since=today should use today's date."""
        import os, time as _time
        # Old session — mtime in January
        old_jsonl = _write_session(tmp_path, 'old-jan', [
            _file_op_msg('Read', '/home/user/project/target.py'),
        ])
        old_ts = _time.mktime(_time.strptime('2026-01-01', '%Y-%m-%d'))
        os.utime(old_jsonl, (old_ts, old_ts))

        # Recent session — mtime now
        _write_session(tmp_path, 'recent-today', [
            _file_op_msg('Edit', '/home/user/project/target.py'),
        ])

        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/target.py', query='since=today')
            result = adapter.get_structure()

        names = {s['session'] for s in result['sessions']}
        assert 'old-jan' not in names
        assert 'recent-today' in names

    def test_result_session_entry_has_required_fields(self, tmp_path):
        _write_session(tmp_path, 'my-session', [
            _file_op_msg('Read', '/home/user/project/module.py'),
        ])
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/module.py')
            result = adapter.get_structure()
        assert result['match_count'] == 1
        entry = result['sessions'][0]
        assert 'session' in entry
        assert 'project' in entry
        assert 'modified' in entry
        assert 'ops' in entry
        assert 'total_ops' in entry

    def test_empty_corpus_returns_zero_matches(self, tmp_path):
        with patch.object(ClaudeAdapter, 'CONVERSATION_BASE', tmp_path):
            adapter = ClaudeAdapter('files/anything.py')
            result = adapter.get_structure()
        assert result['sessions_scanned'] == 0
        assert result['match_count'] == 0
        assert result['sessions'] == []


# ─── Renderer ─────────────────────────────────────────────────────────────────

class TestFileSessionsRenderer:

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

    def _make_result(self, sessions=None, match_count=None, **kwargs) -> dict:
        sessions = sessions or []
        return {
            'type': 'claude_file_sessions',
            'file_path': 'reveal/adapters/claude/adapter.py',
            'sessions_scanned': 100,
            'match_count': match_count if match_count is not None else len(sessions),
            'since': None,
            'sessions': sessions,
            **kwargs,
        }

    def test_renders_header_with_file_path(self):
        result = self._make_result()
        output = self._render(result)
        assert 'adapter.py' in output

    def test_renders_scanned_count(self):
        result = self._make_result()
        output = self._render(result)
        assert '100' in output

    def test_renders_match_count(self):
        result = self._make_result(match_count=3)
        output = self._render(result)
        assert '3' in output

    def test_renders_since_in_header(self):
        result = self._make_result(since='2026-03-10')
        output = self._render(result)
        assert '2026-03-10' in output

    def test_renders_session_name(self):
        sessions = [{
            'session': 'neon-falcon-0314',
            'project': 'reveal',
            'modified': '2026-03-14T21:09:00',
            'ops': {'Read': 2, 'Edit': 3},
            'total_ops': 5,
        }]
        output = self._render(self._make_result(sessions=sessions))
        assert 'neon-falcon-0314' in output

    def test_renders_project_tag(self):
        sessions = [{
            'session': 'neon-falcon-0314',
            'project': 'reveal',
            'modified': '2026-03-14T21:09:00',
            'ops': {'Edit': 1},
            'total_ops': 1,
        }]
        output = self._render(self._make_result(sessions=sessions))
        assert 'reveal' in output

    def test_renders_op_counts(self):
        sessions = [{
            'session': 'alpha-0314',
            'project': 'tia',
            'modified': '2026-03-14T12:00:00',
            'ops': {'Read': 2, 'Edit': 5},
            'total_ops': 7,
        }]
        output = self._render(self._make_result(sessions=sessions))
        assert 'Read' in output
        assert 'Edit' in output
        assert '2' in output
        assert '5' in output

    def test_zero_matches_renders_gracefully(self):
        result = self._make_result(match_count=0)
        output = self._render(result)
        assert 'adapter.py' in output
        assert '0' in output

    def test_renders_error_message(self):
        result = self._make_result(error='Corpus directory not found')
        output = self._render(result)
        assert 'Corpus directory not found' in output

    def test_multiple_sessions_all_rendered(self):
        sessions = [
            {'session': f'sess-{i}', 'project': 'p', 'modified': f'2026-03-{14-i:02d}T10:00:00',
             'ops': {'Edit': 1}, 'total_ops': 1}
            for i in range(3)
        ]
        output = self._render(self._make_result(sessions=sessions))
        for i in range(3):
            assert f'sess-{i}' in output

    def test_write_op_rendered_correctly(self):
        sessions = [{
            'session': 'write-sess',
            'project': 'x',
            'modified': '2026-03-14T10:00:00',
            'ops': {'Write': 1},
            'total_ops': 1,
        }]
        output = self._render(self._make_result(sessions=sessions))
        assert 'Write' in output
