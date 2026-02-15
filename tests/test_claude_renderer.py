"""Tests for reveal.adapters.claude.renderer module."""

import pytest
import sys
from io import StringIO


class TestClaudeRenderer:
    """Tests for ClaudeRenderer class."""

    def test_render_session_overview_basic(self, capsys):
        """Test rendering basic session overview."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'message_count': 10,
            'user_messages': 5,
            'assistant_messages': 5,
            'conversation_file': '/path/to/conversation.jsonl'
        }

        ClaudeRenderer._render_claude_session_overview(result)
        captured = capsys.readouterr()

        assert 'test-session-001' in captured.out
        assert 'Messages: 10' in captured.out
        assert 'User: 5' in captured.out
        assert 'Assistant: 5' in captured.out
        assert '/path/to/conversation.jsonl' in captured.out

    def test_render_session_overview_with_duration(self, capsys):
        """Test session overview with duration field."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'message_count': 10,
            'user_messages': 5,
            'assistant_messages': 5,
            'duration': '2h 15m',
            'conversation_file': '/path/to/conversation.jsonl'
        }

        ClaudeRenderer._render_claude_session_overview(result)
        captured = capsys.readouterr()

        assert 'Duration: 2h 15m' in captured.out

    def test_render_session_overview_with_tools(self, capsys):
        """Test session overview with tools used."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'message_count': 10,
            'user_messages': 5,
            'assistant_messages': 5,
            'tools_used': {'Bash': 10, 'Read': 5, 'Write': 3},
            'conversation_file': '/path/to/conversation.jsonl'
        }

        ClaudeRenderer._render_claude_session_overview(result)
        captured = capsys.readouterr()

        assert 'Tools Used:' in captured.out
        assert 'Bash: 10' in captured.out
        assert 'Read: 5' in captured.out
        assert 'Write: 3' in captured.out

    def test_render_tool_calls_bash(self, capsys):
        """Test rendering Bash tool calls."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'tool_name': 'Bash',
            'call_count': 2,
            'session': 'test-session-001',
            'calls': [
                {'input': {'command': 'ls -la', 'description': 'List files'}},
                {'input': {'command': 'cat file.txt'}},
            ]
        }

        ClaudeRenderer._render_claude_tool_calls(result)
        captured = capsys.readouterr()

        assert 'Tool: Bash (2 calls)' in captured.out
        assert 'List files' in captured.out
        assert '$ ls -la' in captured.out
        assert '$ cat file.txt' in captured.out

    def test_render_tool_calls_bash_long_command(self, capsys):
        """Test rendering Bash tool call with long command."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        long_cmd = 'echo ' + 'x' * 150

        result = {
            'tool_name': 'Bash',
            'call_count': 1,
            'session': 'test-session-001',
            'calls': [
                {'input': {'command': long_cmd}},
            ]
        }

        ClaudeRenderer._render_claude_tool_calls(result)
        captured = capsys.readouterr()

        assert '... (' in captured.out  # Truncation indicator
        assert '155 chars' in captured.out  # "echo " + 150 x's = 155 total

    def test_render_tool_calls_read(self, capsys):
        """Test rendering Read tool calls."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'tool_name': 'Read',
            'call_count': 2,
            'session': 'test-session-001',
            'calls': [
                {'input': {'file_path': '/path/to/file1.txt'}},
                {'input': {'file_path': '/path/to/file2.txt'}},
            ]
        }

        ClaudeRenderer._render_claude_tool_calls(result)
        captured = capsys.readouterr()

        assert 'Tool: Read (2 calls)' in captured.out
        assert '/path/to/file1.txt' in captured.out
        assert '/path/to/file2.txt' in captured.out

    def test_render_tool_calls_edit(self, capsys):
        """Test rendering Edit tool calls."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'tool_name': 'Edit',
            'call_count': 1,
            'session': 'test-session-001',
            'calls': [
                {'input': {'file_path': '/path/to/edit.txt'}},
            ]
        }

        ClaudeRenderer._render_claude_tool_calls(result)
        captured = capsys.readouterr()

        assert 'Tool: Edit (1 calls)' in captured.out
        assert '/path/to/edit.txt' in captured.out

    def test_render_tool_calls_write(self, capsys):
        """Test rendering Write tool calls."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'tool_name': 'Write',
            'call_count': 1,
            'session': 'test-session-001',
            'calls': [
                {'input': {'file_path': '/path/to/write.txt'}},
            ]
        }

        ClaudeRenderer._render_claude_tool_calls(result)
        captured = capsys.readouterr()

        assert 'Tool: Write (1 calls)' in captured.out
        assert '/path/to/write.txt' in captured.out

    def test_render_tool_calls_grep(self, capsys):
        """Test rendering Grep tool calls."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'tool_name': 'Grep',
            'call_count': 1,
            'session': 'test-session-001',
            'calls': [
                {'input': {'pattern': 'def.*test', 'path': '/src'}},
            ]
        }

        ClaudeRenderer._render_claude_tool_calls(result)
        captured = capsys.readouterr()

        assert 'Tool: Grep (1 calls)' in captured.out
        assert "'def.*test'" in captured.out
        assert '/src' in captured.out

    def test_render_tool_calls_glob(self, capsys):
        """Test rendering Glob tool calls."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'tool_name': 'Glob',
            'call_count': 1,
            'session': 'test-session-001',
            'calls': [
                {'input': {'pattern': '**/*.py'}},
            ]
        }

        ClaudeRenderer._render_claude_tool_calls(result)
        captured = capsys.readouterr()

        assert 'Tool: Glob (1 calls)' in captured.out
        assert '**/*.py' in captured.out

    def test_render_tool_calls_generic(self, capsys):
        """Test rendering generic tool calls."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'tool_name': 'CustomTool',
            'call_count': 1,
            'session': 'test-session-001',
            'calls': [
                {'input': {'param1': 'value1', 'param2': 'value2'}},
            ]
        }

        ClaudeRenderer._render_claude_tool_calls(result)
        captured = capsys.readouterr()

        assert 'Tool: CustomTool (1 calls)' in captured.out
        assert 'param1=value1' in captured.out

    def test_render_tool_summary(self, capsys):
        """Test rendering tool summary."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'total_calls': 20,
            'tools': {
                'Bash': {'count': 10, 'success_rate': '95%'},
                'Read': {'count': 8, 'success_rate': '100%'},
                'Write': {'count': 2, 'success_rate': '100%'},
            }
        }

        ClaudeRenderer._render_claude_tool_summary(result)
        captured = capsys.readouterr()

        assert 'Tool Summary: test-session-001' in captured.out
        assert 'Total Calls: 20' in captured.out
        assert 'Bash: 10 calls (95% success)' in captured.out
        assert 'Read: 8 calls (100% success)' in captured.out

    def test_render_errors_basic(self, capsys):
        """Test rendering error summary."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'error_count': 2,
            'errors': [
                {
                    'message_index': 5,
                    'error_type': 'FileNotFoundError',
                    'content_preview': 'File not found: /path/to/file.txt',
                    'context': {'tool_name': 'Read'}
                },
                {
                    'message_index': 7,
                    'error_type': 'PermissionError',
                    'content_preview': 'Permission denied',
                    'context': {'tool_name': 'Write'}
                },
            ]
        }

        ClaudeRenderer._render_claude_errors(result)
        captured = capsys.readouterr()

        assert 'Errors: test-session-001' in captured.out
        assert 'Total: 2' in captured.out
        assert 'FileNotFoundError' in captured.out
        assert 'PermissionError' in captured.out

    def test_render_errors_with_tool_input(self, capsys):
        """Test rendering errors with tool input preview."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'error_count': 1,
            'errors': [
                {
                    'message_index': 5,
                    'error_type': 'FileNotFoundError',
                    'content_preview': 'File not found',
                    'context': {
                        'tool_name': 'Read',
                        'tool_input_preview': '/path/to/missing.txt'
                    }
                },
            ]
        }

        ClaudeRenderer._render_claude_errors(result)
        captured = capsys.readouterr()

        assert 'Input: /path/to/missing.txt' in captured.out

    def test_render_errors_truncation(self, capsys):
        """Test rendering errors with long previews."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        long_input = 'x' * 100
        long_error = 'Error message: ' + 'y' * 80

        result = {
            'session': 'test-session-001',
            'error_count': 1,
            'errors': [
                {
                    'message_index': 5,
                    'error_type': 'Error',
                    'content_preview': long_error,
                    'context': {
                        'tool_name': 'Read',
                        'tool_input_preview': long_input
                    }
                },
            ]
        }

        ClaudeRenderer._render_claude_errors(result)
        captured = capsys.readouterr()

        assert '...' in captured.out  # Truncation

    def test_render_errors_many(self, capsys):
        """Test rendering many errors (truncated to 20)."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        errors = [
            {
                'message_index': i,
                'error_type': 'Error',
                'content_preview': f'Error {i}',
                'context': {'tool_name': 'Tool'}
            }
            for i in range(25)
        ]

        result = {
            'session': 'test-session-001',
            'error_count': 25,
            'errors': errors
        }

        ClaudeRenderer._render_claude_errors(result)
        captured = capsys.readouterr()

        assert 'Total: 25' in captured.out
        assert '... and 5 more errors' in captured.out

    def test_render_files_all_operations(self, capsys):
        """Test rendering files touched with all operations."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'total_operations': 10,
            'unique_files': 5,
            'by_operation': {
                'Read': {'/path/to/file1.txt': 5, '/path/to/file2.txt': 2},
                'Write': {'/path/to/output.txt': 2},
                'Edit': {'/path/to/edit.txt': 1},
            }
        }

        ClaudeRenderer._render_claude_files(result)
        captured = capsys.readouterr()

        assert 'Files Touched: test-session-001' in captured.out
        assert 'Total Operations: 10' in captured.out
        assert 'Unique Files: 5' in captured.out
        assert 'Read:' in captured.out
        assert '5x /path/to/file1.txt' in captured.out
        assert 'Write:' in captured.out
        assert 'Edit:' in captured.out

    def test_render_files_long_paths(self, capsys):
        """Test rendering files with long paths."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        long_path = '/very/long/path/' + 'x' * 80 + '/file.txt'

        result = {
            'session': 'test-session-001',
            'total_operations': 1,
            'unique_files': 1,
            'by_operation': {
                'Read': {long_path: 1},
            }
        }

        ClaudeRenderer._render_claude_files(result)
        captured = capsys.readouterr()

        assert '...' in captured.out  # Path truncation

    def test_render_files_many(self, capsys):
        """Test rendering many files (truncated to 15)."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        files = {f'/path/to/file{i}.txt': 1 for i in range(20)}

        result = {
            'session': 'test-session-001',
            'total_operations': 20,
            'unique_files': 20,
            'by_operation': {
                'Read': files,
            }
        }

        ClaudeRenderer._render_claude_files(result)
        captured = capsys.readouterr()

        assert '... and 5 more files' in captured.out

    def test_render_workflow(self, capsys):
        """Test rendering workflow sequence."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'total_steps': 5,
            'workflow': [
                {'step': 1, 'tool': 'Read', 'detail': '/path/to/file.txt'},
                {'step': 2, 'tool': 'Edit', 'detail': 'Change line 42'},
                {'step': 3, 'tool': 'Bash', 'detail': 'run tests'},
                {'step': 4, 'tool': 'Write', 'detail': '/path/to/output.txt'},
                {'step': 5, 'tool': 'Bash', 'detail': 'commit changes'},
            ]
        }

        ClaudeRenderer._render_claude_workflow(result)
        captured = capsys.readouterr()

        assert 'Workflow: test-session-001' in captured.out
        assert 'Total Steps: 5' in captured.out
        assert '[  1] Read' in captured.out
        assert '[  2] Edit' in captured.out

    def test_render_workflow_long_detail(self, capsys):
        """Test rendering workflow with long detail."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        long_detail = 'x' * 100

        result = {
            'session': 'test-session-001',
            'total_steps': 1,
            'workflow': [
                {'step': 1, 'tool': 'Bash', 'detail': long_detail},
            ]
        }

        ClaudeRenderer._render_claude_workflow(result)
        captured = capsys.readouterr()

        assert '...' in captured.out  # Detail truncation

    def test_render_workflow_many_steps(self, capsys):
        """Test rendering many workflow steps (truncated to 50)."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        workflow = [{'step': i, 'tool': 'Tool', 'detail': f'step {i}'} for i in range(60)]

        result = {
            'session': 'test-session-001',
            'total_steps': 60,
            'workflow': workflow
        }

        ClaudeRenderer._render_claude_workflow(result)
        captured = capsys.readouterr()

        assert '... and 10 more steps' in captured.out

    def test_render_context_changes(self, capsys):
        """Test rendering context changes."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'total_changes': 3,
            'final_cwd': '/home/user/project',
            'final_branch': 'feature-branch',
            'changes': [
                {'message_index': 5, 'type': 'cwd', 'value': '/home/user/project'},
                {'message_index': 10, 'type': 'branch', 'value': 'feature-branch'},
            ]
        }

        ClaudeRenderer._render_claude_context(result)
        captured = capsys.readouterr()

        assert 'Context Changes: test-session-001' in captured.out
        assert 'Total Changes: 3' in captured.out
        assert 'Final Directory: /home/user/project' in captured.out
        assert 'Final Branch: feature-branch' in captured.out
        assert 'Changed directory' in captured.out
        assert 'Switched branch' in captured.out

    def test_render_context_long_paths(self, capsys):
        """Test rendering context with long paths."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        long_path = '/very/long/path/' + 'x' * 100

        result = {
            'session': 'test-session-001',
            'total_changes': 1,
            'changes': [
                {'message_index': 5, 'type': 'cwd', 'value': long_path},
            ]
        }

        ClaudeRenderer._render_claude_context(result)
        captured = capsys.readouterr()

        assert '...' in captured.out  # Path truncation

    def test_render_filtered_results(self, capsys):
        """Test rendering filtered results."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'session': 'test-session-001',
            'query': 'error messages',
            'filters_applied': ['tool=Bash', 'status=error'],
            'result_count': 3,
            'results': [
                {'message_index': 5, 'tool_name': 'Bash', 'is_error': True, 'content': 'Command failed'},
                {'message_index': 10, 'tool_name': 'Bash', 'is_error': True, 'content': 'Exit code 1'},
                {'message_index': 15, 'tool_name': 'Read', 'is_error': False, 'content': 'File read'},
            ]
        }

        ClaudeRenderer._render_claude_filtered_results(result)
        captured = capsys.readouterr()

        assert 'Filtered Results: test-session-001' in captured.out
        assert 'Query: error messages' in captured.out
        assert 'Filters: tool=Bash, status=error' in captured.out
        assert 'Matches: 3' in captured.out
        assert '❌' in captured.out  # Error indicator
        assert '✓' in captured.out   # Success indicator

    def test_render_filtered_results_many(self, capsys):
        """Test rendering many filtered results (truncated to 25)."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        results = [
            {'message_index': i, 'tool_name': 'Tool', 'is_error': False, 'content': f'Result {i}'}
            for i in range(30)
        ]

        result = {
            'session': 'test-session-001',
            'query': 'test',
            'filters_applied': [],
            'result_count': 30,
            'results': results
        }

        ClaudeRenderer._render_claude_filtered_results(result)
        captured = capsys.readouterr()

        assert '... and 5 more results' in captured.out

    def test_render_text_dispatches(self, capsys):
        """Test _render_text dispatches to correct method."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'type': 'claude_session_overview',
            'session': 'test-session-001',
            'message_count': 10,
            'user_messages': 5,
            'assistant_messages': 5,
            'conversation_file': '/path/to/conversation.jsonl'
        }

        ClaudeRenderer._render_text(result)
        captured = capsys.readouterr()

        assert 'test-session-001' in captured.out

    def test_render_text_fallback(self, capsys):
        """Test _render_text falls back for unknown types."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'type': 'unknown_type',
            'session': 'test-session-001',
            'custom_field': 'value'
        }

        ClaudeRenderer._render_text(result)
        captured = capsys.readouterr()

        assert 'Type: unknown_type' in captured.out
        assert 'Session: test-session-001' in captured.out
        assert 'custom_field: value' in captured.out

    def test_render_fallback_with_large_collections(self, capsys):
        """Test fallback rendering with large lists/dicts."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'type': 'unknown_type',
            'session': 'test-session-001',
            'large_list': ['x' * 50 for _ in range(10)],
            'large_dict': {f'key{i}': f'value{i}' for i in range(10)}
        }

        ClaudeRenderer._render_fallback(result)
        captured = capsys.readouterr()

        assert '[list with 10 items]' in captured.out
        assert '[dict with 10 items]' in captured.out

    def test_render_element_with_content(self, capsys):
        """Test render_element with content field."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'content': 'This is the main content'
        }

        ClaudeRenderer.render_element(result, format='text')
        captured = capsys.readouterr()

        assert 'This is the main content' in captured.out

    def test_render_element_without_content(self, capsys):
        """Test render_element without content field."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'field1': 'value1',
            'field2': 'value2',
            'adapter': 'claude',  # Should be skipped
            'uri': 'claude://test',  # Should be skipped
            'timestamp': '2024-01-01'  # Should be skipped
        }

        ClaudeRenderer.render_element(result, format='text')
        captured = capsys.readouterr()

        assert 'field1: value1' in captured.out
        assert 'field2: value2' in captured.out
        assert 'adapter' not in captured.out
        assert 'uri' not in captured.out
        assert 'timestamp' not in captured.out

    def test_render_element_json_format(self, capsys):
        """Test render_element with JSON format."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        result = {
            'field1': 'value1',
            'field2': 'value2'
        }

        ClaudeRenderer.render_element(result, format='json')
        captured = capsys.readouterr()

        # Should render as JSON
        assert 'field1' in captured.out
        assert 'field2' in captured.out

    def test_render_error(self, capsys):
        """Test render_error outputs to stderr."""
        from reveal.adapters.claude.renderer import ClaudeRenderer

        error = ValueError('Test error message')
        ClaudeRenderer.render_error(error)
        captured = capsys.readouterr()

        assert 'Error: Test error message' in captured.err


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
