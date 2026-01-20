"""Claude Code conversation adapter implementation."""

from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime
from urllib.parse import parse_qs
import json
import re
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

        Supports composite queries:
            - ?tools=Bash&errors - Bash tool calls that resulted in errors
            - ?tools=Bash&contains=reveal - Bash calls containing 'reveal'
            - ?errors&contains=traceback - Errors containing 'traceback'
        """
        if resource is None or not isinstance(resource, str):
            raise TypeError(f"resource must be a string, got {type(resource).__name__}")
        self.resource = resource
        self.query = query
        self.query_params = self._parse_query(query)
        self.session_name = self._parse_session_name(resource)
        self.conversation_path = self._find_conversation()
        self.messages = None  # Lazy load

    def _parse_query(self, query: str) -> Dict[str, Any]:
        """Parse query string into structured parameters.

        Supports:
            - 'errors' -> {'errors': True}
            - 'tools=Bash' -> {'tools': 'Bash'}
            - 'tools=Bash&errors' -> {'tools': 'Bash', 'errors': True}
            - 'contains=reveal' -> {'contains': 'reveal'}

        Args:
            query: Raw query string

        Returns:
            Dictionary of parsed parameters
        """
        if not query:
            return {}

        params = {}

        # Handle simple keywords and key=value pairs
        for part in query.split('&'):
            if '=' in part:
                key, value = part.split('=', 1)
                params[key] = value
            else:
                # Keywords like 'errors', 'summary', 'timeline'
                params[part] = True

        return params

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

        # Check for composite query (multiple filters)
        if self._is_composite_query():
            return self._handle_composite_query(messages)

        # Route based on resource path and query (legacy single-query behavior)
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
        results = self._extract_all_tool_results(messages)

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

    def _extract_all_tool_results(self, messages: List[Dict]) -> List[Dict]:
        """Extract all tool results with metadata for filtering.

        Args:
            messages: List of message dictionaries

        Returns:
            List of tool result dictionaries with:
            - message_index, tool_use_id, tool_name, content, is_error, timestamp
        """
        # First pass: collect tool_use_id -> tool_name mapping from assistant messages
        tool_use_map = {}
        for msg in messages:
            if msg.get('type') == 'assistant':
                for content in msg.get('message', {}).get('content', []):
                    if isinstance(content, dict) and content.get('type') == 'tool_use':
                        tool_id = content.get('id')
                        tool_name = content.get('name')
                        if tool_id and tool_name:
                            tool_use_map[tool_id] = tool_name

        # Second pass: extract tool results from user messages
        results = []
        for i, msg in enumerate(messages):
            if msg.get('type') == 'user':
                for content in msg.get('message', {}).get('content', []):
                    if not isinstance(content, dict):
                        continue
                    if content.get('type') == 'tool_result':
                        tool_id = content.get('tool_use_id')
                        tool_name = tool_use_map.get(tool_id, 'unknown')
                        result_content = str(content.get('content', ''))

                        results.append({
                            'message_index': i,
                            'tool_use_id': tool_id,
                            'tool_name': tool_name,
                            'content': result_content[:500],  # Truncate for display
                            'is_error': self._is_tool_error(content),
                            'timestamp': msg.get('timestamp')
                        })

        return results

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
                # Extract user message text and tool results
                content_blocks = msg.get('message', {}).get('content', [])

                # User text messages
                text_parts = [c.get('text', '') for c in content_blocks
                              if isinstance(c, dict) and c.get('type') == 'text']
                text = ' '.join(text_parts)
                if text:
                    timeline.append({
                        'index': i,
                        'timestamp': timestamp,
                        'event_type': 'user_message',
                        'content_preview': text[:100]
                    })

                # Tool results (returned from tool execution)
                for content in content_blocks:
                    if isinstance(content, dict) and content.get('type') == 'tool_result':
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

        Detects errors through multiple signals (in priority order):
        1. is_error: true in tool_result (definitive)
        2. Exit codes > 0 in Bash output (definitive)
        3. Traceback/Exception at start of line (strong signal)
        4. Common error patterns at start of content (moderate signal)

        Avoids false positives by NOT matching error keywords mid-content
        (e.g., documentation mentioning "error handling").

        Args:
            messages: List of message dictionaries

        Returns:
            Dictionary with error count and list of errors
        """
        import re
        base = self._get_contract_base()
        base['type'] = 'claude_errors'

        errors = []

        # Patterns that indicate errors when at start of line/content
        # Using MULTILINE so ^ matches start of any line
        strong_patterns = re.compile(
            r'^\s*(?:traceback|exception|error:|fatal:|panic:)',
            re.IGNORECASE | re.MULTILINE
        )

        # Exit code pattern - matches "Exit code N" where N > 0
        exit_code_pattern = re.compile(r'exit code (\d+)', re.IGNORECASE)

        for i, msg in enumerate(messages):
            # Tool results are in 'user' type messages (results returned to assistant)
            if msg.get('type') == 'user':
                for content in msg.get('message', {}).get('content', []):
                    # Skip non-dict content (plain text messages)
                    if not isinstance(content, dict):
                        continue
                    if content.get('type') == 'tool_result':
                        result_content = str(content.get('content', ''))

                        # Priority 1: Explicit is_error flag (definitive)
                        is_error = content.get('is_error', False)

                        # Priority 2: Exit code > 0 (definitive for Bash)
                        exit_match = exit_code_pattern.search(result_content)
                        has_exit_error = exit_match and int(exit_match.group(1)) > 0

                        # Priority 3: Strong error patterns at line start
                        has_strong_pattern = bool(strong_patterns.search(result_content))

                        error_type = None
                        if is_error:
                            error_type = 'is_error_flag'
                        elif has_exit_error:
                            error_type = 'exit_code'
                        elif has_strong_pattern:
                            error_type = 'pattern_match'

                        if error_type:
                            tool_use_id = content.get('tool_use_id')
                            context = self._get_error_context(messages, i, tool_use_id)

                            errors.append({
                                'message_index': i,
                                'tool_use_id': tool_use_id,
                                'error_type': error_type,
                                'content_preview': result_content[:300],
                                'timestamp': msg.get('timestamp'),
                                'context': context
                            })

        base.update({
            'session': self.session_name,
            'error_count': len(errors),
            'errors': errors
        })

        return base

    def _get_error_context(self, messages: List[Dict], error_msg_index: int,
                           tool_use_id: str) -> Dict[str, Any]:
        """Get context around an error for debugging.

        Looks backwards from the error to find:
        - The tool_use call that triggered the error
        - Any thinking before the tool call
        - The tool name and input

        Args:
            messages: List of message dictionaries
            error_msg_index: Index of the message containing the error
            tool_use_id: The tool_use_id that resulted in the error

        Returns:
            Context dictionary with tool_call, thinking, and prior_action
        """
        context = {
            'tool_name': None,
            'tool_input_preview': None,
            'thinking_preview': None,
            'prior_action': None
        }

        # Look backwards from the error message to find the tool_use
        for i in range(error_msg_index - 1, max(0, error_msg_index - 10), -1):
            msg = messages[i]
            if msg.get('type') != 'assistant':
                continue

            contents = msg.get('message', {}).get('content', [])
            for content in contents:
                if not isinstance(content, dict):
                    continue

                # Found the tool_use that led to this error
                if content.get('type') == 'tool_use' and content.get('id') == tool_use_id:
                    context['tool_name'] = content.get('name')
                    tool_input = content.get('input', {})
                    if isinstance(tool_input, dict):
                        # For Bash, show the command
                        if 'command' in tool_input:
                            context['tool_input_preview'] = tool_input['command'][:200]
                        # For Read/Edit, show the file path
                        elif 'file_path' in tool_input:
                            context['tool_input_preview'] = tool_input['file_path']
                        else:
                            # Generic: show first key-value
                            for k, v in tool_input.items():
                                context['tool_input_preview'] = f"{k}: {str(v)[:150]}"
                                break

                # Look for thinking in the same message
                if content.get('type') == 'thinking':
                    thinking = content.get('thinking', '')
                    # Get the last ~200 chars which is usually the decision
                    if len(thinking) > 200:
                        context['thinking_preview'] = '...' + thinking[-200:]
                    else:
                        context['thinking_preview'] = thinking

            # If we found the tool_use, we're done
            if context['tool_name']:
                break

        return context

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
                'errors': 'reveal claude://session/<name>?errors',
                'tools': 'reveal claude://session/<name>?tools=Bash',
                'composite': 'reveal claude://session/<name>?tools=Bash&errors&contains=reveal',
                'thinking': 'reveal claude://session/<name>/thinking',
                'message': 'reveal claude://session/<name>/message/42'
            }
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
            # Tool results are in 'user' type messages (results returned to assistant)
            if msg.get('type') != 'user':
                continue

            for content in msg.get('message', {}).get('content', []):
                if not isinstance(content, dict):
                    continue
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

        Uses multiple signals:
        - is_error flag (definitive)
        - Exit code > 0 (definitive for Bash)
        - Error patterns at line start (strong signal)

        Args:
            content: Tool result content dictionary

        Returns:
            True if the result indicates an error
        """
        import re

        # Check explicit is_error flag first (definitive)
        if content.get('is_error', False):
            return True

        result_content = str(content.get('content', ''))

        # Check for exit code > 0 (definitive for Bash)
        exit_match = re.search(r'exit code (\d+)', result_content, re.IGNORECASE)
        if exit_match and int(exit_match.group(1)) > 0:
            return True

        # Check for strong error patterns at line start
        strong_patterns = re.compile(
            r'^\s*(?:traceback|exception|error:|fatal:|panic:)',
            re.IGNORECASE | re.MULTILINE
        )
        if strong_patterns.search(result_content):
            return True

        return False

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
