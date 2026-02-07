"""Claude Code conversation adapter implementation."""

from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import json

from ..base import ResourceAdapter, register_adapter, register_renderer
from .renderer import ClaudeRenderer
from ...utils.query import parse_query_params
from .analysis import (
    extract_all_tool_results,
    get_tool_calls,
    get_all_tools,
    get_errors,
    get_timeline,
    get_overview,
    get_summary,
    filter_by_role,
    get_message,
    get_thinking_blocks,
    calculate_tool_success_rate,
    get_files_touched,
    get_workflow,
    get_context_changes,
)


@register_adapter('claude')
@register_renderer(ClaudeRenderer)
class ClaudeAdapter(ResourceAdapter):
    """Adapter for Claude Code conversation analysis.

    Provides progressive disclosure for Claude Code sessions:
    - Session overview with metrics
    - Message filtering (user/assistant/thinking/tools)
    - Tool usage analytics
    - Error detection
    - Token usage estimates
    """

    CONVERSATION_BASE = Path.home() / '.claude' / 'projects'

    def __init__(self, resource: str, query: str = None):
        """Initialize Claude adapter.

        Args:
            resource: Resource path (e.g., 'session/infernal-earth-0118')
            query: Optional query string (e.g., 'summary', 'errors', 'tools=Bash')

        Supports composite queries:
            - ?tools=Bash&errors - Bash tool calls that resulted in errors
            - ?tools=Bash&contains=reveal - Bash calls containing 'reveal'
            - ?errors&contains=traceback - Errors containing 'traceback'
        """
        if resource is None or not isinstance(resource, str):
            raise TypeError(f"resource must be a string, got {type(resource).__name__}")
        self.resource = resource
        self.query = query
        self.query_params = parse_query_params(query)
        self.session_name = self._parse_session_name(resource)
        self.conversation_path = self._find_conversation()
        self.messages = None  # Lazy load

    def _get_contract_base(self) -> Dict[str, Any]:
        """Get Output Contract v1.0 base fields.

        Returns:
            Dictionary with required contract fields:
            - contract_version: '1.0'
            - type: (to be set by caller)
            - source: Path to conversation file
            - source_type: 'file'
        """
        return {
            'contract_version': '1.0',
            'type': '',  # Set by caller
            'source': str(self.conversation_path) if self.conversation_path else '',
            'source_type': 'file'  # JSONL file
        }

    def _parse_session_name(self, resource: str) -> str:
        """Extract session name from URI.

        Args:
            resource: Resource string (e.g., 'session/infernal-earth-0118')

        Returns:
            Session name (e.g., 'infernal-earth-0118')
        """
        if resource.startswith('session/'):
            parts = resource.split('/')
            return parts[1] if len(parts) > 1 else None
        return resource

    def _find_conversation(self) -> Optional[Path]:
        """Find conversation JSONL file for session.

        Uses two strategies:
        1. Direct lookup in TIA-style project directory
        2. Fuzzy search across all project directories

        Returns:
            Path to conversation JSONL file, or None if not found
        """
        if not self.session_name:
            return None

        # Strategy 1: Check TIA-style project directory
        tia_prefix = "-home-scottsen-src-tia-sessions-"
        session_dir = self.CONVERSATION_BASE / f"{tia_prefix}{self.session_name}"
        if session_dir.exists():
            jsonl_files = list(session_dir.glob('*.jsonl'))
            if jsonl_files:
                return jsonl_files[0]

        # Strategy 2: Fuzzy search across all project dirs
        if self.CONVERSATION_BASE.exists():
            for project_dir in self.CONVERSATION_BASE.iterdir():
                if not project_dir.is_dir():
                    continue
                if self.session_name in project_dir.name:
                    jsonl_files = list(project_dir.glob('*.jsonl'))
                    if jsonl_files:
                        return jsonl_files[0]

        return None

    def _load_messages(self) -> List[Dict]:
        """Load and parse conversation JSONL.

        Returns:
            List of message dictionaries

        Raises:
            FileNotFoundError: If conversation file not found
        """
        if self.messages is not None:
            return self.messages

        if not self.conversation_path or not self.conversation_path.exists():
            raise FileNotFoundError(
                f"Conversation not found for session: {self.session_name}"
            )

        messages = []
        with open(self.conversation_path, 'r') as f:
            for line in f:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # Skip malformed lines

        self.messages = messages
        return messages

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Return session structure based on query.

        Routes to appropriate handler based on resource path and query.
        Supports composite queries for filtering (e.g., ?tools=Bash&errors&contains=reveal).

        Args:
            **kwargs: Additional parameters (unused)

        Returns:
            Dictionary with session data (Output Contract v1.0 compliant)
            All outputs include via _get_contract_base():
                'contract_version': '1.0'
                'type': adapter-specific type
                'source': conversation file path
                'source_type': 'file'
        """
        # Handle bare claude:// - list available sessions
        if not self.resource or self.resource in ('.', ''):
            return self._list_sessions()

        messages = self._load_messages()
        contract_base = self._get_contract_base()
        conversation_path_str = str(self.conversation_path) if self.conversation_path else ''

        # Check for composite query (multiple filters)
        if self._is_composite_query():
            return self._handle_composite_query(messages)

        # Route based on resource path and query (legacy single-query behavior)
        if self.query == 'summary':
            return get_summary(messages, self.session_name, conversation_path_str, contract_base)
        elif self.query == 'timeline':
            return get_timeline(messages, self.session_name, contract_base)
        elif self.query == 'errors':
            return get_errors(messages, self.session_name, contract_base)
        elif self.query and self.query.startswith('tools='):
            tool_name = self.query.split('=')[1]
            return get_tool_calls(messages, tool_name, self.session_name, contract_base)
        elif '/thinking' in self.resource:
            return get_thinking_blocks(messages, self.session_name, contract_base)
        elif '/tools' in self.resource:
            return get_all_tools(messages, self.session_name, contract_base)
        elif '/files' in self.resource:
            return get_files_touched(messages, self.session_name, contract_base)
        elif '/workflow' in self.resource:
            return get_workflow(messages, self.session_name, contract_base)
        elif '/context' in self.resource:
            return get_context_changes(messages, self.session_name, contract_base)
        elif '/user' in self.resource:
            return filter_by_role(messages, 'user', self.session_name, contract_base)
        elif '/assistant' in self.resource:
            return filter_by_role(messages, 'assistant', self.session_name, contract_base)
        elif '/message/' in self.resource:
            msg_id = int(self.resource.split('/message/')[1])
            return get_message(messages, msg_id, self.session_name, contract_base)
        else:
            return get_overview(messages, self.session_name, conversation_path_str, contract_base)

    def _is_composite_query(self) -> bool:
        """Check if query has multiple filter parameters.

        Returns:
            True if query combines multiple filters (e.g., tools + errors + contains)
        """
        if not self.query_params:
            return False

        # Composite if we have multiple filter-type params
        filter_params = {'tools', 'errors', 'contains'}
        active_filters = filter_params & set(self.query_params.keys())
        return len(active_filters) > 1

    def _handle_composite_query(self, messages: List[Dict]) -> Dict[str, Any]:
        """Handle composite queries with multiple filters.

        Supports combinations like:
            - ?tools=Bash&errors - Bash calls that errored
            - ?tools=Read&contains=config - Read calls containing 'config'
            - ?errors&contains=traceback - Errors with tracebacks

        Args:
            messages: List of message dictionaries

        Returns:
            Filtered results matching all criteria
        """
        base = self._get_contract_base()
        base['type'] = 'claude_filtered_results'

        # Start with all tool results
        results = extract_all_tool_results(messages)

        # Apply filters progressively
        if 'tools' in self.query_params:
            tool_name = self.query_params['tools']
            results = [r for r in results if r.get('tool_name') == tool_name]

        if 'errors' in self.query_params:
            results = [r for r in results if r.get('is_error')]

        if 'contains' in self.query_params:
            pattern = self.query_params['contains'].lower()
            results = [r for r in results if pattern in r.get('content', '').lower()]

        base.update({
            'session': self.session_name,
            'query': self.query,
            'filters_applied': list(self.query_params.keys()),
            'result_count': len(results),
            'results': results
        })

        return base

    def _list_sessions(self) -> Dict[str, Any]:
        """List available Claude Code sessions.

        Scans the Claude projects directory for sessions and returns
        recent ones with basic metadata.

        Returns:
            Dictionary with session list and usage help
        """
        base = {
            'contract_version': '1.0',
            'type': 'claude_session_list',
            'source': str(self.CONVERSATION_BASE),
            'source_type': 'directory'
        }

        sessions = []
        try:
            for project_dir in self.CONVERSATION_BASE.iterdir():
                if not project_dir.is_dir():
                    continue

                # Find JSONL files in project dir
                for jsonl_file in project_dir.glob('*.jsonl'):
                    # Try to extract session name from path
                    # TIA sessions: -home-scottsen-src-tia-sessions-SESSION_NAME
                    dir_name = project_dir.name
                    if '-sessions-' in dir_name:
                        session_name = dir_name.split('-sessions-')[-1]
                    else:
                        session_name = dir_name

                    stat = jsonl_file.stat()
                    sessions.append({
                        'session': session_name,
                        'path': str(jsonl_file),
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'size_kb': stat.st_size // 1024
                    })

            # Sort by modified time, most recent first
            sessions.sort(key=lambda x: x['modified'], reverse=True)

        except Exception as e:
            base['error'] = str(e)

        base.update({
            'session_count': len(sessions),
            'recent_sessions': sessions[:20],  # Show 20 most recent
            'usage': {
                'overview': 'reveal claude://session/<name>',
                'workflow': 'reveal claude://session/<name>/workflow',
                'files': 'reveal claude://session/<name>/files',
                'tools': 'reveal claude://session/<name>/tools',
                'errors': 'reveal claude://session/<name>?errors',
                'context': 'reveal claude://session/<name>/context',
                'specific_tool': 'reveal claude://session/<name>?tools=Bash',
                'composite': 'reveal claude://session/<name>?tools=Bash&errors',
                'thinking': 'reveal claude://session/<name>/thinking',
                'message': 'reveal claude://session/<name>/message/42'
            }
        })

        return base

    # Wrapper methods for backward compatibility with tests
    def _get_overview(self, messages: List[Dict]) -> Dict[str, Any]:
        """Wrapper for backward compatibility."""
        conversation_path_str = str(self.conversation_path) if self.conversation_path else ''
        return get_overview(messages, self.session_name, conversation_path_str, self._get_contract_base())

    def _get_summary(self, messages: List[Dict]) -> Dict[str, Any]:
        """Wrapper for backward compatibility."""
        conversation_path_str = str(self.conversation_path) if self.conversation_path else ''
        return get_summary(messages, self.session_name, conversation_path_str, self._get_contract_base())

    def _calculate_tool_success_rate(self, messages: List[Dict]) -> Dict[str, Dict[str, Any]]:
        """Wrapper for backward compatibility."""
        return calculate_tool_success_rate(messages)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for claude:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'claude',
            'description': 'Claude Code conversation analysis with tool usage, workflow tracking, and error detection',
            'uri_syntax': 'claude://session/{name}[/resource][?query]',
            'query_params': {
                'summary': {
                    'type': 'flag',
                    'description': 'Session summary (overview + key events)'
                },
                'errors': {
                    'type': 'flag',
                    'description': 'Filter for messages containing errors'
                },
                'tools': {
                    'type': 'string',
                    'description': 'Filter for specific tool usage',
                    'examples': ['?tools=Bash', '?tools=Edit']
                },
                'contains': {
                    'type': 'string',
                    'description': 'Filter messages containing text',
                    'examples': ['?contains=reveal', '?contains=error']
                },
                'role': {
                    'type': 'string',
                    'description': 'Filter by message role',
                    'values': ['user', 'assistant'],
                    'examples': ['?role=user']
                }
            },
            'elements': {
                'workflow': 'Chronological sequence of tool operations',
                'files': 'All files read, written, or edited',
                'tools': 'All tool usage with success rates',
                'thinking': 'All thinking blocks',
                'errors': 'All errors and exceptions',
                'timeline': 'Chronological message timeline',
                'context': 'Context window changes over session'
            },
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'claude_overview',
                    'description': 'Session overview with message counts and tool usage',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'claude_overview'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string', 'const': 'file'},
                            'session_name': {'type': 'string'},
                            'message_count': {'type': 'integer'},
                            'tool_calls': {'type': 'integer'},
                            'duration': {'type': 'string'},
                            'tool_summary': {'type': 'array'}
                        }
                    }
                },
                {
                    'type': 'claude_workflow',
                    'description': 'Chronological tool operation sequence',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'claude_workflow'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'session_name': {'type': 'string'},
                            'operations': {'type': 'array'}
                        }
                    }
                },
                {
                    'type': 'claude_files',
                    'description': 'Files touched during session',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'claude_files'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'session_name': {'type': 'string'},
                            'files': {'type': 'array'}
                        }
                    }
                },
                {
                    'type': 'claude_tools',
                    'description': 'Tool usage statistics',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'claude_tools'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'session_name': {'type': 'string'},
                            'tools': {'type': 'array'},
                            'success_rate': {'type': 'number'}
                        }
                    }
                },
                {
                    'type': 'claude_errors',
                    'description': 'All errors and exceptions in session',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'contract_version': {'type': 'string'},
                            'type': {'type': 'string', 'const': 'claude_errors'},
                            'source': {'type': 'string'},
                            'source_type': {'type': 'string'},
                            'session_name': {'type': 'string'},
                            'errors': {'type': 'array'},
                            'count': {'type': 'integer'}
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'claude://session/infernal-earth-0118',
                    'description': 'Session overview (messages, tools, duration)',
                    'output_type': 'claude_overview'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/workflow',
                    'description': 'Chronological sequence of tool operations',
                    'element': 'workflow',
                    'output_type': 'claude_workflow'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/files',
                    'description': 'All files read, written, or edited',
                    'element': 'files',
                    'output_type': 'claude_files'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/tools',
                    'description': 'All tool usage with success rates',
                    'element': 'tools',
                    'output_type': 'claude_tools'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/errors',
                    'description': 'All errors and exceptions',
                    'element': 'errors',
                    'output_type': 'claude_errors'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?tools=Bash',
                    'description': 'Filter for Bash tool usage',
                    'query_param': '?tools=Bash',
                    'output_type': 'claude_overview'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?errors',
                    'description': 'Filter for error messages',
                    'query_param': '?errors',
                    'output_type': 'claude_overview'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?summary',
                    'description': 'Session summary with key events',
                    'query_param': '?summary',
                    'output_type': 'claude_overview'
                }
            ],
            'notes': [
                'Reads Claude Code conversation JSONL files from ~/.claude/projects/',
                'Supports composite queries (e.g., ?tools=Bash&errors)',
                'Workflow tracking shows tool operation sequences',
                'File tracking shows all Read/Write/Edit operations',
                'Tool success rates calculated from result vs error status'
            ]
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for claude:// adapter.

        Returns:
            Dictionary with help information (name, description, syntax, examples, etc.)
        """
        return {
            'name': 'claude',
            'description': 'Navigate and analyze Claude Code conversations - progressive session exploration',
            'syntax': 'claude://session/{name}[/resource][?query]',
            'examples': [
                {
                    'uri': 'claude://session/infernal-earth-0118',
                    'description': 'Session overview (messages, tools, duration)'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/workflow',
                    'description': 'Chronological sequence of tool operations'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/files',
                    'description': 'All files read, written, or edited'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/tools',
                    'description': 'All tool usage with success rates'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?errors',
                    'description': 'Find errors with context'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/context',
                    'description': 'Track directory and branch changes'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/thinking',
                    'description': 'Extract all thinking blocks with token estimates'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?tools=Bash',
                    'description': 'Filter to specific tool calls'
                }
            ],
            'features': [
                'Progressive disclosure (overview → details → specifics)',
                'Tool usage analytics with success rates',
                'File operation tracking (Read/Write/Edit)',
                'Workflow visualization (chronological tool sequence)',
                'Error detection with full context',
                'Directory and branch change tracking',
                'Thinking block extraction and analysis',
                'Token usage estimates and optimization insights'
            ],
            'workflows': [
                {
                    'name': 'Post-Session Review',
                    'scenario': 'Understand what happened in a completed session',
                    'steps': [
                        'reveal claude://session/session-name',
                        'reveal claude://session/session-name?summary',
                        'reveal claude://session/session-name/tools'
                    ]
                },
                {
                    'name': 'Debug Failed Session',
                    'scenario': 'Find why a session failed',
                    'steps': [
                        'reveal claude://session/failed-build?errors',
                        'reveal claude://session/failed-build/message/67',
                        'reveal claude://session/failed-build?tools=Bash'
                    ]
                },
                {
                    'name': 'Token Optimization',
                    'scenario': 'Identify token waste',
                    'steps': [
                        'reveal claude://session/current?summary',
                        'reveal claude://session/current/thinking',
                        'reveal claude://session/current?tools=Read'
                    ]
                }
            ],
            'try_now': [
                'reveal claude://session/$(basename $PWD)',
                'reveal claude://session/$(basename $PWD)?summary',
                'reveal claude://session/$(basename $PWD)/thinking'
            ],
            'notes': [
                'Conversation files stored in ~/.claude/projects/{project-dir}/',
                'Session names typically match directory names (e.g., infernal-earth-0118)',
                'Token estimates are approximate (chars / 4)',
                'Use --format=json for programmatic analysis with jq'
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal json:// - Navigate JSONL structure directly',
                'reveal help://adapters - All available adapters',
                'TIA session domain - High-level session operations'
            ]
        }
