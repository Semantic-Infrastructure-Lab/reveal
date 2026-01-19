"""Claude Code conversation adapter implementation."""

from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime
import json
import sys

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.json_utils import safe_json_dumps


class ClaudeRenderer:
    """Renderer for Claude adapter results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render Claude conversation structure."""
        if format == 'json':
            print(safe_json_dumps(result))
            return

        # Text format - overview
        if 'messages' in result:
            print(f"Claude Session: {result.get('session', 'unknown')}")
            print(f"Messages: {result.get('message_count', len(result['messages']))}")
            if 'duration' in result:
                print(f"Duration: {result['duration']}")
            print()
            for msg in result.get('messages', [])[:10]:
                role = msg.get('role', 'unknown')
                preview = str(msg.get('content', ''))[:80]
                print(f"  [{role}] {preview}...")
            if len(result.get('messages', [])) > 10:
                print(f"  ... and {len(result['messages']) - 10} more messages")
        else:
            # Fallback: just dump structure
            for key, value in result.items():
                if key not in ('adapter', 'uri', 'timestamp'):
                    print(f"{key}: {value}")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render specific Claude element (message, tool call, etc.)."""
        if format == 'json':
            print(safe_json_dumps(result))
            return

        # Text format
        if 'content' in result:
            print(result['content'])
        else:
            for key, value in result.items():
                if key not in ('adapter', 'uri', 'timestamp'):
                    print(f"{key}: {value}")

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error: {error}", file=sys.stderr)


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
        """
        self.resource = resource
        self.query = query
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
        messages = self._load_messages()

        # Route based on resource path and query
        if self.query == 'summary':
            return self._get_summary(messages)
        elif self.query == 'timeline':
            return self._get_timeline(messages)
        elif self.query == 'errors':
            return self._get_errors(messages)
        elif self.query and self.query.startswith('tools='):
            tool_name = self.query.split('=')[1]
            return self._get_tool_calls(messages, tool_name)
        elif '/thinking' in self.resource:
            return self._get_thinking_blocks(messages)
        elif '/tools' in self.resource:
            return self._get_all_tools(messages)
        elif '/user' in self.resource:
            return self._filter_by_role(messages, 'user')
        elif '/assistant' in self.resource:
            return self._filter_by_role(messages, 'assistant')
        elif '/message/' in self.resource:
            msg_id = int(self.resource.split('/message/')[1])
            return self._get_message(messages, msg_id)
        else:
            return self._get_overview(messages)

    def _get_overview(self, messages: List[Dict]) -> Dict[str, Any]:
        """Generate session overview with key metrics.

        Args:
            messages: List of message dictionaries

        Returns:
            Overview dictionary with:
            - Message counts
            - Tool usage statistics
            - File operations
            - Thinking token estimates
            - Session duration
        """
        base = self._get_contract_base()
        base['type'] = 'claude_session_overview'

        tools_used = defaultdict(int)
        thinking_chars = 0
        user_messages = 0
        assistant_messages = 0
        file_operations = defaultdict(int)

        for msg in messages:
            msg_type = msg.get('type')

            if msg_type == 'user':
                user_messages += 1
            elif msg_type == 'assistant':
                assistant_messages += 1

                # Parse content blocks
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'tool_use':
                        tool_name = content.get('name')
                        tools_used[tool_name] += 1

                        # Track file operations
                        if tool_name in ('Read', 'Write', 'Edit'):
                            file_operations[tool_name] += 1

                    elif content.get('type') == 'thinking':
                        thinking_chars += len(content.get('thinking', ''))

        # Calculate duration
        timestamps = [msg.get('timestamp') for msg in messages if msg.get('timestamp')]
        duration = None
        if len(timestamps) >= 2:
            try:
                start = datetime.fromisoformat(timestamps[0].replace('Z', '+00:00'))
                end = datetime.fromisoformat(timestamps[-1].replace('Z', '+00:00'))
                duration = str(end - start)
            except (ValueError, AttributeError):
                pass

        base.update({
            'session': self.session_name,
            'message_count': len(messages),
            'user_messages': user_messages,
            'assistant_messages': assistant_messages,
            'tools_used': dict(tools_used),
            'file_operations': dict(file_operations),
            'thinking_chars_approx': thinking_chars,
            'thinking_tokens_approx': thinking_chars // 4,  # Rough estimate
            'duration': duration,
            'conversation_file': str(self.conversation_path)
        })

        return base

    def _get_summary(self, messages: List[Dict]) -> Dict[str, Any]:
        """Generate detailed analytics summary.

        Args:
            messages: List of message dictionaries

        Returns:
            Summary with detailed analytics (tool success rates, message sizes, etc.)
        """
        overview = self._get_overview(messages)
        overview['type'] = 'claude_analytics'

        # Add detailed analytics
        tool_success_rate = self._calculate_tool_success_rate(messages)
        message_sizes = self._analyze_message_sizes(messages)

        overview.update({
            'tool_success_rate': tool_success_rate,
            'avg_message_size': message_sizes['avg'],
            'max_message_size': message_sizes['max'],
            'thinking_blocks': message_sizes['thinking_blocks']
        })

        return overview

    def _get_timeline(self, messages: List[Dict]) -> Dict[str, Any]:
        """Generate chronological timeline of conversation.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary with timeline events (user messages, tool calls, tool results)
        """
        base = self._get_contract_base()
        base['type'] = 'claude_timeline'

        timeline = []
        for i, msg in enumerate(messages):
            timestamp = msg.get('timestamp', 'Unknown')
            msg_type = msg.get('type')

            if msg_type == 'user':
                # Extract user message text
                content_blocks = msg.get('message', {}).get('content', [])
                text_parts = [c.get('text', '') for c in content_blocks
                              if c.get('type') == 'text']
                text = ' '.join(text_parts)
                if text:
                    timeline.append({
                        'index': i,
                        'timestamp': timestamp,
                        'event_type': 'user_message',
                        'content_preview': text[:100]
                    })

            elif msg_type == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    content_type = content.get('type')

                    if content_type == 'text':
                        text = content.get('text', '')
                        if text:
                            timeline.append({
                                'index': i,
                                'timestamp': timestamp,
                                'event_type': 'assistant_message',
                                'content_preview': text[:100]
                            })

                    elif content_type == 'tool_use':
                        timeline.append({
                            'index': i,
                            'timestamp': timestamp,
                            'event_type': 'tool_call',
                            'tool_name': content.get('name'),
                            'tool_id': content.get('id')
                        })

                    elif content_type == 'tool_result':
                        is_error = content.get('is_error', False)
                        result_content = str(content.get('content', ''))
                        has_error = is_error or 'error' in result_content.lower()

                        timeline.append({
                            'index': i,
                            'timestamp': timestamp,
                            'event_type': 'tool_result',
                            'tool_id': content.get('tool_use_id'),
                            'status': 'error' if has_error else 'success',
                            'content_preview': result_content[:100]
                        })

                    elif content_type == 'thinking':
                        thinking_text = content.get('thinking', '')
                        timeline.append({
                            'index': i,
                            'timestamp': timestamp,
                            'event_type': 'thinking',
                            'tokens_approx': len(thinking_text) // 4,
                            'content_preview': thinking_text[:100]
                        })

        base.update({
            'session': self.session_name,
            'event_count': len(timeline),
            'timeline': timeline
        })

        return base

    def _get_errors(self, messages: List[Dict]) -> Dict[str, Any]:
        """Extract all errors with context.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary with error count and list of errors
        """
        base = self._get_contract_base()
        base['type'] = 'claude_errors'

        errors = []

        for i, msg in enumerate(messages):
            # Check tool results for errors
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'tool_result':
                        result_content = content.get('content', '')
                        if 'error' in result_content.lower() or 'failed' in result_content.lower():
                            errors.append({
                                'message_index': i,
                                'tool_use_id': content.get('tool_use_id'),
                                'content_preview': result_content[:200],
                                'timestamp': msg.get('timestamp')
                            })

        base.update({
            'session': self.session_name,
            'error_count': len(errors),
            'errors': errors
        })

        return base

    def _get_tool_calls(self, messages: List[Dict], tool_name: str) -> Dict[str, Any]:
        """Extract all calls to specific tool.

        Args:
            messages: List of message dictionaries
            tool_name: Name of tool to filter (e.g., 'Bash', 'Read')

        Returns:
            Dictionary with tool call count and list of calls
        """
        base = self._get_contract_base()
        base['type'] = 'claude_tool_calls'

        tool_calls = []

        for i, msg in enumerate(messages):
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'tool_use' and content.get('name') == tool_name:
                        tool_calls.append({
                            'message_index': i,
                            'tool_use_id': content.get('id'),
                            'input': content.get('input'),
                            'timestamp': msg.get('timestamp')
                        })

        base.update({
            'session': self.session_name,
            'tool_name': tool_name,
            'call_count': len(tool_calls),
            'calls': tool_calls
        })

        return base

    def _get_thinking_blocks(self, messages: List[Dict]) -> Dict[str, Any]:
        """Extract all thinking blocks.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary with thinking block count and list of blocks
        """
        base = self._get_contract_base()
        base['type'] = 'claude_thinking'

        thinking_blocks = []

        for i, msg in enumerate(messages):
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'thinking':
                        thinking = content.get('thinking', '')
                        thinking_blocks.append({
                            'message_index': i,
                            'content': thinking,
                            'char_count': len(thinking),
                            'token_estimate': len(thinking) // 4,
                            'timestamp': msg.get('timestamp')
                        })

        base.update({
            'session': self.session_name,
            'thinking_block_count': len(thinking_blocks),
            'total_chars': sum(b['char_count'] for b in thinking_blocks),
            'total_tokens_estimate': sum(b['token_estimate'] for b in thinking_blocks),
            'blocks': thinking_blocks
        })

        return base

    def _get_all_tools(self, messages: List[Dict]) -> Dict[str, Any]:
        """Get all tool calls across all types.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary with tool usage statistics
        """
        base = self._get_contract_base()
        base['type'] = 'claude_tool_summary'

        tools = defaultdict(list)

        for i, msg in enumerate(messages):
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'tool_use':
                        tool_name = content.get('name')
                        tools[tool_name].append({
                            'message_index': i,
                            'tool_use_id': content.get('id'),
                            'timestamp': msg.get('timestamp')
                        })

        base.update({
            'session': self.session_name,
            'tool_count': sum(len(calls) for calls in tools.values()),
            'tools': {name: len(calls) for name, calls in tools.items()},
            'details': dict(tools)
        })

        return base

    def _filter_by_role(self, messages: List[Dict], role: str) -> Dict[str, Any]:
        """Filter messages by role (user or assistant).

        Args:
            messages: List of message dictionaries
            role: Role to filter ('user' or 'assistant')

        Returns:
            Dictionary with filtered messages
        """
        base = self._get_contract_base()
        base['type'] = f'claude_{role}_messages'

        filtered = []

        for i, msg in enumerate(messages):
            if msg.get('type') == role:
                filtered.append({
                    'message_index': i,
                    'timestamp': msg.get('timestamp'),
                    'content': msg.get('message', {}).get('content', [])
                })

        base.update({
            'session': self.session_name,
            'role': role,
            'message_count': len(filtered),
            'messages': filtered
        })

        return base

    def _get_message(self, messages: List[Dict], msg_id: int) -> Dict[str, Any]:
        """Get specific message by index.

        Args:
            messages: List of message dictionaries
            msg_id: Message index (0-based)

        Returns:
            Dictionary with message details
        """
        base = self._get_contract_base()
        base['type'] = 'claude_message'

        if msg_id < 0 or msg_id >= len(messages):
            base.update({
                'session': self.session_name,
                'error': f'Message index {msg_id} out of range (0-{len(messages)-1})'
            })
            return base

        msg = messages[msg_id]

        base.update({
            'session': self.session_name,
            'message_index': msg_id,
            'timestamp': msg.get('timestamp'),
            'message_type': msg.get('type'),  # Changed from 'type' to 'message_type'
            'message': msg.get('message', {})
        })

        return base

    def _calculate_tool_success_rate(self, messages: List[Dict]) -> Dict[str, Dict[str, Any]]:
        """Calculate success rate per tool.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary mapping tool names to success/failure stats
        """
        from collections import defaultdict

        # Build mapping of tool_use_id to tool name
        tool_use_map = self._collect_tool_use_ids(messages)

        # Track success/failure per tool
        tool_stats = defaultdict(lambda: {'success': 0, 'failure': 0, 'total': 0})
        self._track_tool_results(messages, tool_use_map, tool_stats)

        # Calculate final success rates
        return self._build_success_rate_report(tool_stats)

    def _collect_tool_use_ids(self, messages: List[Dict]) -> Dict[str, str]:
        """Extract mapping of tool_use_id to tool name from messages.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary mapping tool_use_id to tool name
        """
        tool_use_map = {}
        for msg in messages:
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'tool_use':
                        tool_id = content.get('id')
                        tool_name = content.get('name')
                        if tool_id and tool_name:
                            tool_use_map[tool_id] = tool_name
        return tool_use_map

    def _track_tool_results(self, messages: List[Dict], tool_use_map: Dict[str, str],
                           tool_stats: Dict[str, Dict[str, int]]) -> None:
        """Track success/failure for each tool based on results.

        Args:
            messages: List of message dictionaries
            tool_use_map: Mapping of tool_use_id to tool name
            tool_stats: Dictionary to update with success/failure counts
        """
        for msg in messages:
            if msg.get('type') != 'assistant':
                continue

            for content in msg.get('message', {}).get('content', []):
                if content.get('type') != 'tool_result':
                    continue

                tool_id = content.get('tool_use_id')
                if tool_id not in tool_use_map:
                    continue

                tool_name = tool_use_map[tool_id]
                tool_stats[tool_name]['total'] += 1

                if self._is_tool_error(content):
                    tool_stats[tool_name]['failure'] += 1
                else:
                    tool_stats[tool_name]['success'] += 1

    def _is_tool_error(self, content: Dict) -> bool:
        """Check if a tool result indicates an error.

        Args:
            content: Tool result content dictionary

        Returns:
            True if the result indicates an error
        """
        is_error = content.get('is_error', False)
        result_content = str(content.get('content', ''))
        has_error_text = ('error' in result_content.lower() or
                          'failed' in result_content.lower())
        return is_error or has_error_text

    def _build_success_rate_report(self, tool_stats: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, Any]]:
        """Build final success rate report from stats.

        Args:
            tool_stats: Dictionary of tool statistics

        Returns:
            Dictionary mapping tool names to success rate reports
        """
        result = {}
        for tool_name, stats in tool_stats.items():
            if stats['total'] > 0:
                success_rate = (stats['success'] / stats['total']) * 100
                result[tool_name] = {
                    'success': stats['success'],
                    'failure': stats['failure'],
                    'total': stats['total'],
                    'success_rate': round(success_rate, 1)
                }
        return result

    def _analyze_message_sizes(self, messages: List[Dict]) -> Dict[str, Any]:
        """Analyze message size distribution.

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary with average, max, and thinking block count
        """
        sizes = []
        thinking_blocks = 0

        for msg in messages:
            if msg.get('type') == 'assistant':
                msg_size = 0
                for content in msg.get('message', {}).get('content', []):
                    if content.get('type') == 'text':
                        msg_size += len(content.get('text', ''))
                    elif content.get('type') == 'thinking':
                        msg_size += len(content.get('thinking', ''))
                        thinking_blocks += 1
                sizes.append(msg_size)

        return {
            'avg': sum(sizes) // len(sizes) if sizes else 0,
            'max': max(sizes) if sizes else 0,
            'thinking_blocks': thinking_blocks
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
                    'uri': 'claude://session/infernal-earth-0118/thinking',
                    'description': 'Extract all thinking blocks with token estimates'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?tools=Bash',
                    'description': 'All Bash tool calls'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118?errors',
                    'description': 'Find errors and tool failures'
                },
                {
                    'uri': 'claude://session/infernal-earth-0118/tools',
                    'description': 'All tool usage statistics'
                }
            ],
            'features': [
                'Progressive disclosure (overview → details → specifics)',
                'Tool usage analytics and filtering',
                'Token usage estimates and optimization insights',
                'Error detection with context',
                'Thinking block extraction and analysis',
                'File operation tracking'
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
