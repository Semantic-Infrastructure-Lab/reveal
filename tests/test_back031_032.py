"""Tests for BACK-031 (session overview enrichment) and BACK-032 (workflow run collapse).

BACK-031: claude:// session overview adds files_touched, readme_present, last_assistant_snippet.
BACK-032: claude:// /workflow collapses consecutive identical tool+detail runs.
"""

import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from reveal.adapters.claude.analysis.overview import (
    _collect_files_touched,
    _get_last_assistant_snippet,
    _check_readme_present,
    get_overview,
)
from reveal.adapters.claude.analysis.tools import (
    _collapse_workflow_runs,
    get_workflow,
)
from reveal.adapters.claude.renderer import ClaudeRenderer


def _capture_render(fn, *args, **kwargs):
    from unittest.mock import patch
    from io import StringIO
    buf = StringIO()
    with patch('sys.stdout', buf):
        fn(*args, **kwargs)
    return buf.getvalue()


def _make_msg(role, content_blocks):
    return {'type': role, 'message': {'content': content_blocks}}


def _tool_use(name, **inp):
    return {'type': 'tool_use', 'name': name, 'input': inp, 'id': f'tu_{name}'}


def _text_block(text):
    return {'type': 'text', 'text': text}


def _thinking_block(text):
    return {'type': 'thinking', 'thinking': text}


# ─── _collect_files_touched ───────────────────────────────────────────────────

class TestCollectFilesTouched:
    def test_collects_edit_write_read(self):
        messages = [
            _make_msg('assistant', [
                _tool_use('Edit', file_path='a.py'),
                _tool_use('Write', file_path='b.py'),
                _tool_use('Read', file_path='c.py'),
            ])
        ]
        result = _collect_files_touched(messages)
        assert result == ['a.py', 'b.py', 'c.py']

    def test_deduplicates_paths(self):
        messages = [
            _make_msg('assistant', [
                _tool_use('Edit', file_path='a.py'),
                _tool_use('Edit', file_path='a.py'),
                _tool_use('Edit', file_path='b.py'),
            ])
        ]
        result = _collect_files_touched(messages)
        assert result == ['a.py', 'b.py']

    def test_ignores_non_file_tools(self):
        messages = [
            _make_msg('assistant', [
                _tool_use('Bash', command='ls'),
                _tool_use('Grep', pattern='foo', path='.'),
            ])
        ]
        result = _collect_files_touched(messages)
        assert result == []

    def test_ignores_user_messages(self):
        messages = [
            {'type': 'user', 'message': {'content': [
                _tool_use('Edit', file_path='should_not_appear.py')
            ]}}
        ]
        result = _collect_files_touched(messages)
        assert result == []

    def test_empty_messages(self):
        assert _collect_files_touched([]) == []

    def test_preserves_first_occurrence_order(self):
        messages = [
            _make_msg('assistant', [
                _tool_use('Edit', file_path='z.py'),
                _tool_use('Edit', file_path='a.py'),
                _tool_use('Edit', file_path='m.py'),
            ])
        ]
        result = _collect_files_touched(messages)
        assert result == ['z.py', 'a.py', 'm.py']


# ─── _get_last_assistant_snippet ─────────────────────────────────────────────

class TestGetLastAssistantSnippet:
    def test_returns_last_text_block(self):
        messages = [
            _make_msg('assistant', [_text_block('first response')]),
            _make_msg('user', [{'type': 'text', 'text': 'ok'}]),
            _make_msg('assistant', [_text_block('final answer here')]),
        ]
        result = _get_last_assistant_snippet(messages)
        assert result == 'final answer here'

    def test_truncates_at_100_chars_with_ellipsis(self):
        long_text = 'x' * 150
        messages = [_make_msg('assistant', [_text_block(long_text)])]
        result = _get_last_assistant_snippet(messages)
        assert len(result) == 101  # 100 chars + ellipsis char
        assert result.endswith('…')

    def test_exactly_100_chars_no_ellipsis(self):
        text = 'y' * 100
        messages = [_make_msg('assistant', [_text_block(text)])]
        result = _get_last_assistant_snippet(messages)
        assert result == text
        assert not result.endswith('…')

    def test_skips_non_text_blocks(self):
        messages = [
            _make_msg('assistant', [
                _thinking_block('internal thought'),
                _tool_use('Edit', file_path='x.py'),
                _text_block('visible text'),
            ])
        ]
        result = _get_last_assistant_snippet(messages)
        assert result == 'visible text'

    def test_no_assistant_messages_returns_none(self):
        messages = [{'type': 'user', 'message': {'content': [{'type': 'text', 'text': 'hello'}]}}]
        result = _get_last_assistant_snippet(messages)
        assert result is None

    def test_empty_messages_returns_none(self):
        assert _get_last_assistant_snippet([]) is None

    def test_skips_empty_text_blocks(self):
        messages = [
            _make_msg('assistant', [
                _text_block(''),
                _text_block('   '),
                _text_block('real content'),
            ])
        ]
        result = _get_last_assistant_snippet(messages)
        assert result == 'real content'


# ─── _check_readme_present ───────────────────────────────────────────────────

class TestCheckReadmePresent:
    def test_readme_found(self, tmp_path):
        session_dir = tmp_path / 'my-session'
        session_dir.mkdir()
        conv = session_dir / 'abc123.jsonl'
        conv.write_text('{}')
        readme = session_dir / 'README.md'
        readme.write_text('# Session')
        assert _check_readme_present(str(conv)) is True

    def test_readme_absent(self, tmp_path):
        session_dir = tmp_path / 'my-session'
        session_dir.mkdir()
        conv = session_dir / 'abc123.jsonl'
        conv.write_text('{}')
        assert _check_readme_present(str(conv)) is False

    def test_readme_variant_name(self, tmp_path):
        session_dir = tmp_path / 'my-session'
        session_dir.mkdir()
        conv = session_dir / 'abc123.jsonl'
        conv.write_text('{}')
        (session_dir / 'README_FULL.md').write_text('# Full')
        assert _check_readme_present(str(conv)) is True

    def test_exception_returns_false(self):
        result = _check_readme_present('/nonexistent/path/conv.jsonl')
        assert result is False


# ─── get_overview: new fields ────────────────────────────────────────────────

class TestGetOverviewNewFields:
    def _run_overview(self, messages, conv_path='/fake/session/x.jsonl'):
        return get_overview(messages, 'test-session', conv_path, {'source': 'test'})

    def test_files_touched_in_result(self):
        messages = [
            _make_msg('assistant', [
                _tool_use('Edit', file_path='main.py'),
                _tool_use('Write', file_path='utils.py'),
            ])
        ]
        result = self._run_overview(messages)
        assert result['files_touched'] == ['main.py', 'utils.py']
        assert result['files_touched_count'] == 2

    def test_last_assistant_snippet_in_result(self):
        messages = [
            _make_msg('assistant', [_text_block('done!')])
        ]
        result = self._run_overview(messages)
        assert result['last_assistant_snippet'] == 'done!'

    def test_readme_present_field_exists(self):
        result = self._run_overview([])
        assert 'readme_present' in result


# ─── _collapse_workflow_runs ─────────────────────────────────────────────────

class TestCollapseWorkflowRuns:
    def _step(self, n, tool, detail, msg_idx=0):
        return {'step': n, 'tool': tool, 'detail': detail, 'message_index': msg_idx}

    def test_no_collapse_when_no_repeats(self):
        wf = [
            self._step(1, 'Edit', 'a.py'),
            self._step(2, 'Read', 'b.py'),
            self._step(3, 'Bash', 'make test'),
        ]
        result = _collapse_workflow_runs(wf, [])
        assert len(result) == 3
        assert all(s.get('run_count', 1) == 1 for s in result)

    def test_collapses_identical_consecutive_steps(self):
        wf = [
            self._step(1, 'Edit', 'README.md'),
            self._step(2, 'Edit', 'README.md'),
            self._step(3, 'Edit', 'README.md'),
            self._step(4, 'Edit', 'README.md'),
            self._step(5, 'Edit', 'README.md'),
        ]
        result = _collapse_workflow_runs(wf, [])
        assert len(result) == 1
        assert result[0]['run_count'] == 5
        assert result[0]['step'] == 1

    def test_non_consecutive_not_collapsed(self):
        wf = [
            self._step(1, 'Edit', 'a.py'),
            self._step(2, 'Read', 'b.py'),
            self._step(3, 'Edit', 'a.py'),
        ]
        result = _collapse_workflow_runs(wf, [])
        assert len(result) == 3
        assert all(s.get('run_count', 1) == 1 for s in result)

    def test_different_detail_not_collapsed(self):
        wf = [
            self._step(1, 'Edit', 'a.py'),
            self._step(2, 'Edit', 'b.py'),
        ]
        result = _collapse_workflow_runs(wf, [])
        assert len(result) == 2

    def test_steps_renumbered(self):
        wf = [
            self._step(1, 'Edit', 'a.py'),
            self._step(2, 'Edit', 'a.py'),
            self._step(3, 'Read', 'b.py'),
        ]
        result = _collapse_workflow_runs(wf, [])
        assert [s['step'] for s in result] == [1, 2]

    def test_thinking_hint_extracted(self):
        messages = [
            _make_msg('assistant', [
                _thinking_block('Planning the edit sequence'),
                _tool_use('Edit', file_path='x.py'),
            ])
        ]
        wf = [
            {'step': 1, 'tool': 'Edit', 'detail': 'x.py', 'message_index': 0},
            {'step': 2, 'tool': 'Edit', 'detail': 'x.py', 'message_index': 0},
        ]
        result = _collapse_workflow_runs(wf, messages)
        assert result[0].get('thinking_hint') == 'Planning the edit sequence'

    def test_no_thinking_hint_when_no_thinking(self):
        messages = [
            _make_msg('assistant', [_tool_use('Edit', file_path='x.py')])
        ]
        wf = [
            {'step': 1, 'tool': 'Edit', 'detail': 'x.py', 'message_index': 0},
            {'step': 2, 'tool': 'Edit', 'detail': 'x.py', 'message_index': 0},
        ]
        result = _collapse_workflow_runs(wf, messages)
        assert 'thinking_hint' not in result[0]

    def test_thinking_hint_truncated_to_60_chars(self):
        long_thought = 'I need to make a very long plan: ' + 'x' * 80
        messages = [_make_msg('assistant', [_thinking_block(long_thought)])]
        wf = [
            {'step': 1, 'tool': 'Edit', 'detail': 'x.py', 'message_index': 0},
            {'step': 2, 'tool': 'Edit', 'detail': 'x.py', 'message_index': 0},
        ]
        result = _collapse_workflow_runs(wf, messages)
        assert len(result[0].get('thinking_hint', '')) <= 60

    def test_empty_workflow_returns_empty(self):
        assert _collapse_workflow_runs([], []) == []

    def test_single_step_no_collapse(self):
        wf = [self._step(1, 'Edit', 'a.py')]
        result = _collapse_workflow_runs(wf, [])
        assert len(result) == 1
        assert result[0].get('run_count', 1) == 1

    def test_multiple_runs_collapsed_separately(self):
        wf = [
            self._step(1, 'Edit', 'a.py'),
            self._step(2, 'Edit', 'a.py'),
            self._step(3, 'Read', 'b.py'),
            self._step(4, 'Read', 'b.py'),
            self._step(5, 'Read', 'b.py'),
        ]
        result = _collapse_workflow_runs(wf, [])
        assert len(result) == 2
        assert result[0]['run_count'] == 2
        assert result[1]['run_count'] == 3


# ─── get_workflow: collapsed_steps field ─────────────────────────────────────

class TestGetWorkflowCollapsedSteps:
    def test_collapsed_steps_present(self):
        messages = [
            _make_msg('assistant', [
                _tool_use('Edit', file_path='a.py'),
                _tool_use('Edit', file_path='a.py'),
                _tool_use('Edit', file_path='a.py'),
            ])
        ]
        result = get_workflow(messages, 'test', {})
        assert result['total_steps'] == 3
        assert result['collapsed_steps'] == 1

    def test_no_collapse_when_all_different(self):
        messages = [
            _make_msg('assistant', [
                _tool_use('Edit', file_path='a.py'),
                _tool_use('Edit', file_path='b.py'),
                _tool_use('Edit', file_path='c.py'),
            ])
        ]
        result = get_workflow(messages, 'test', {})
        assert result['total_steps'] == 3
        assert result['collapsed_steps'] == 3


# ─── renderer: overview with new fields ──────────────────────────────────────

class TestRendererOverviewNewFields:
    def test_files_section_shown(self):
        result = {
            'type': 'claude_session_overview',
            'session': 'test-0314',
            'message_count': 5,
            'user_messages': 2,
            'assistant_messages': 3,
            'files_touched': ['main.py', 'utils.py', 'config.py', 'extra.py'],
            'files_touched_count': 4,
            'readme_present': True,
            'last_assistant_snippet': 'All done.',
            'tools_used': {'Edit': 3},
            'conversation_file': '/path/to/conv.jsonl',
        }
        out = _capture_render(ClaudeRenderer._render_claude_session_overview, result)
        assert 'Files: 4' in out
        assert 'main.py' in out
        assert '+1 more' in out

    def test_readme_present_shown(self):
        result = {
            'type': 'claude_session_overview',
            'session': 's', 'message_count': 1,
            'user_messages': 1, 'assistant_messages': 0,
            'files_touched': [], 'files_touched_count': 0,
            'readme_present': True,
            'last_assistant_snippet': None,
            'tools_used': {},
            'conversation_file': '/x',
        }
        out = _capture_render(ClaudeRenderer._render_claude_session_overview, result)
        assert '✓' in out
        assert 'present' in out

    def test_readme_absent_shown(self):
        result = {
            'type': 'claude_session_overview',
            'session': 's', 'message_count': 1,
            'user_messages': 1, 'assistant_messages': 0,
            'files_touched': [], 'files_touched_count': 0,
            'readme_present': False,
            'last_assistant_snippet': None,
            'tools_used': {},
            'conversation_file': '/x',
        }
        out = _capture_render(ClaudeRenderer._render_claude_session_overview, result)
        assert '✗' in out
        assert 'absent' in out

    def test_last_snippet_shown(self):
        result = {
            'type': 'claude_session_overview',
            'session': 's', 'message_count': 1,
            'user_messages': 1, 'assistant_messages': 0,
            'files_touched': [], 'files_touched_count': 0,
            'readme_present': None,
            'last_assistant_snippet': 'Task complete.',
            'tools_used': {},
            'conversation_file': '/x',
        }
        out = _capture_render(ClaudeRenderer._render_claude_session_overview, result)
        assert 'Task complete.' in out

    def test_no_files_section_when_empty(self):
        result = {
            'type': 'claude_session_overview',
            'session': 's', 'message_count': 1,
            'user_messages': 1, 'assistant_messages': 0,
            'files_touched': [], 'files_touched_count': 0,
            'readme_present': None,
            'last_assistant_snippet': None,
            'tools_used': {},
            'conversation_file': '/x',
        }
        out = _capture_render(ClaudeRenderer._render_claude_session_overview, result)
        assert 'Files:' not in out


# ─── renderer: workflow with run_count ───────────────────────────────────────

class TestRendererWorkflowCollapsed:
    def test_run_count_shown_as_times_n(self):
        result = {
            'type': 'claude_workflow',
            'session': 'test',
            'total_steps': 5,
            'collapsed_steps': 1,
            'displayed_steps': None,
            'filtered_from': None,
            '_display': {},
            'workflow': [
                {'step': 1, 'tool': 'Edit', 'detail': 'README.md', 'run_count': 5},
            ],
        }
        out = _capture_render(ClaudeRenderer._render_claude_workflow, result)
        assert '×5' in out
        assert 'README.md' in out

    def test_collapsed_steps_in_header(self):
        result = {
            'type': 'claude_workflow',
            'session': 'test',
            'total_steps': 10,
            'collapsed_steps': 4,
            'displayed_steps': None,
            'filtered_from': None,
            '_display': {},
            'workflow': [],
        }
        out = _capture_render(ClaudeRenderer._render_claude_workflow, result)
        assert 'collapsing runs' in out
        assert '4' in out

    def test_thinking_hint_shown(self):
        result = {
            'type': 'claude_workflow',
            'session': 'test',
            'total_steps': 3,
            'collapsed_steps': 1,
            'displayed_steps': None,
            'filtered_from': None,
            '_display': {},
            'workflow': [
                {
                    'step': 1, 'tool': 'Edit', 'detail': 'x.py',
                    'run_count': 3, 'thinking_hint': 'Planning the refactor',
                },
            ],
        }
        out = _capture_render(ClaudeRenderer._render_claude_workflow, result)
        assert 'Planning the refactor' in out
        assert '→' in out

    def test_no_thinking_hint_when_absent(self):
        result = {
            'type': 'claude_workflow',
            'session': 'test',
            'total_steps': 1,
            'collapsed_steps': 1,
            'displayed_steps': None,
            'filtered_from': None,
            '_display': {},
            'workflow': [
                {'step': 1, 'tool': 'Edit', 'detail': 'a.py', 'run_count': 1},
            ],
        }
        out = _capture_render(ClaudeRenderer._render_claude_workflow, result)
        assert '→' not in out

    def test_no_collapsed_header_when_equal(self):
        """When collapsed_steps == total_steps, no 'collapsing runs' line."""
        result = {
            'type': 'claude_workflow',
            'session': 'test',
            'total_steps': 3,
            'collapsed_steps': 3,
            'displayed_steps': None,
            'filtered_from': None,
            '_display': {},
            'workflow': [],
        }
        out = _capture_render(ClaudeRenderer._render_claude_workflow, result)
        assert 'collapsing' not in out
