"""Claude Code conversation adapter implementation."""

import os
import sys
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
    search_messages,
    get_messages,
    calculate_tool_success_rate,
    get_files_touched,
    get_workflow,
    get_context_changes,
    search_sessions_for_term,
)


_SCHEMA_QUERY_PARAMS = {
    'summary': {'type': 'flag', 'description': 'Session summary (overview + key events)'},
    'errors': {'type': 'flag', 'description': 'Filter for messages containing errors'},
    'tools': {'type': 'string', 'description': 'Filter for specific tool usage', 'examples': ['?tools=Bash', '?tools=Edit']},
    'contains': {'type': 'string', 'description': 'Filter messages containing text', 'examples': ['?contains=reveal', '?contains=error']},
    'role': {'type': 'string', 'description': 'Filter by message role', 'values': ['user', 'assistant'], 'examples': ['?role=user']},
    'search': {
        'type': 'string',
        'description': 'Search all message content (text, thinking, tool inputs) for a term (case-insensitive)',
        'examples': ['?search=path traversal', '?search=FileNotFoundError']
    },
    'tail': {
        'type': 'integer',
        'description': 'Show last N assistant turns — fast session recovery ("where did it stop?")',
        'examples': ['?tail=3', '?tail=1']
    },
    'last': {
        'type': 'flag',
        'description': 'Show last assistant turn (shorthand for ?tail=1)',
        'examples': ['?last']
    },
}

_SCHEMA_ELEMENTS = {
    'workflow': 'Chronological sequence of tool operations',
    'files': 'All files read, written, or edited',
    'tools': 'All tool usage with success rates',
    'thinking': 'All thinking blocks with content previews and token estimates',
    'errors': 'All errors and exceptions',
    'timeline': 'Chronological message timeline',
    'context': 'Context window changes over session',
    'user': 'User messages: initial prompt full text + tool-result turn summaries',
    'assistant': 'Assistant messages: text blocks only (skips thinking/tool_use)',
    'message/<n>': 'Single message by zero-based index (or negative: message/-1 = last message)'
}

def _make_output_type(type_name: str, description: str, extra_props: dict) -> dict:
    """Build a standard claude output_type schema entry."""
    props = {
        'contract_version': {'type': 'string'},
        'type': {'type': 'string', 'const': type_name},
        'source': {'type': 'string'},
        'source_type': {'type': 'string'},
        'session_name': {'type': 'string'},
    }
    props.update(extra_props)
    return {'type': type_name, 'description': description, 'schema': {'type': 'object', 'properties': props}}

_SCHEMA_OUTPUT_TYPES = [
    _make_output_type('claude_overview', 'Session overview with message counts and tool usage', {
        'message_count': {'type': 'integer'}, 'tool_calls': {'type': 'integer'},
        'duration': {'type': 'string'}, 'tool_summary': {'type': 'array'}
    }),
    _make_output_type('claude_workflow', 'Chronological tool operation sequence', {'operations': {'type': 'array'}}),
    _make_output_type('claude_files', 'Files touched during session', {'files': {'type': 'array'}}),
    _make_output_type('claude_tools', 'Tool usage statistics', {
        'tools': {'type': 'array'}, 'success_rate': {'type': 'number'}
    }),
    _make_output_type('claude_errors', 'All errors and exceptions in session', {
        'errors': {'type': 'array'}, 'count': {'type': 'integer'}
    }),
    _make_output_type('claude_user_messages', 'User messages: initial prompt + tool-result turn summaries', {'messages': {'type': 'array'}}),
    _make_output_type('claude_assistant_messages', 'Assistant messages: text responses (thinking/tool blocks excluded)', {'messages': {'type': 'array'}}),
    _make_output_type('claude_thinking', 'All thinking blocks with content previews and token estimates', {
        'blocks': {'type': 'array'}, 'total_tokens': {'type': 'integer'}
    }),
    {
        'type': 'claude_message',
        'description': 'Single message by zero-based index with full content',
        'schema': {'type': 'object', 'properties': {
            'contract_version': {'type': 'string'},
            'type': {'type': 'string', 'const': 'claude_message'},
            'session_name': {'type': 'string'},
            'index': {'type': 'integer'},
            'role': {'type': 'string', 'enum': ['user', 'assistant']},
            'content': {'type': 'array'}
        }}
    },
    _make_output_type('claude_messages', 'Assistant narrative turns (text only, no tool calls) — used by /messages, ?tail=N, ?last', {'messages': {'type': 'array'}, 'total_turns': {'type': 'integer'}}),
    _make_output_type('claude_timeline', 'Chronological message timeline with timestamps and turn types', {'events': {'type': 'array'}}),
    _make_output_type('claude_context', 'Context window usage and changes over the session', {
        'snapshots': {'type': 'array'}, 'peak_tokens': {'type': 'integer'}
    }),
    _make_output_type('claude_search_results', 'Search results across all session content (text, thinking, tool inputs)', {
        'query': {'type': 'string'}, 'matches': {'type': 'array'}, 'total': {'type': 'integer'}
    }),
    _make_output_type('claude_cross_session_search', 'Cross-session content search results (one snippet per matching session)', {
        'term': {'type': 'string'},
        'since': {'type': 'string'},
        'sessions_scanned': {'type': 'integer'},
        'match_count': {'type': 'integer'},
        'displayed_count': {'type': 'integer'},
        'matches': {'type': 'array'},
    }),
    _make_output_type('claude_session_list', 'List of all Claude sessions with metadata', {
        'sessions': {'type': 'array'}, 'total': {'type': 'integer'}
    }),
    _make_output_type('claude_file_sessions', 'Sessions that touched a specific file', {
        'file': {'type': 'string'}, 'sessions': {'type': 'array'}, 'total': {'type': 'integer'}
    }),
    _make_output_type('claude_chain', 'Session continuation chain traversal via README continuing_from: links', {
        'session': {'type': 'string'},
        'chain': {'type': 'array'},
        'chain_length': {'type': 'integer'},
        'sessions_dir': {'type': 'string'},
    }),
]

_SCHEMA_EXAMPLE_QUERIES = [
    {'uri': 'claude://session/infernal-earth-0118', 'description': 'Session overview (messages, tools, duration)', 'output_type': 'claude_overview'},
    {'uri': 'claude://session/infernal-earth-0118/workflow', 'description': 'Chronological sequence of tool operations', 'element': 'workflow', 'output_type': 'claude_workflow'},
    {'uri': 'claude://session/infernal-earth-0118/files', 'description': 'All files read, written, or edited', 'element': 'files', 'output_type': 'claude_files'},
    {'uri': 'claude://session/infernal-earth-0118/tools', 'description': 'All tool usage with success rates', 'element': 'tools', 'output_type': 'claude_tools'},
    {'uri': 'claude://session/infernal-earth-0118/errors', 'description': 'All errors and exceptions', 'element': 'errors', 'output_type': 'claude_errors'},
    {'uri': 'claude://session/infernal-earth-0118?tools=Bash', 'description': 'Filter for Bash tool usage', 'query_param': '?tools=Bash', 'output_type': 'claude_overview'},
    {'uri': 'claude://session/infernal-earth-0118?errors', 'description': 'Filter for error messages', 'query_param': '?errors', 'output_type': 'claude_overview'},
    {'uri': 'claude://session/infernal-earth-0118?summary', 'description': 'Session summary with key events', 'query_param': '?summary', 'output_type': 'claude_overview'},
    {'uri': 'claude://session/infernal-earth-0118/user', 'description': 'User messages: initial prompt + tool-result turn summaries', 'element': 'user', 'output_type': 'claude_user_messages'},
    {'uri': 'claude://session/infernal-earth-0118/assistant', 'description': 'Assistant messages: text responses (thinking/tools hidden)', 'element': 'assistant', 'output_type': 'claude_assistant_messages'},
    {'uri': 'claude://session/infernal-earth-0118/thinking', 'description': 'All thinking blocks with content and token estimates', 'element': 'thinking', 'output_type': 'claude_thinking'},
    {'uri': 'claude://session/infernal-earth-0118/message/5', 'description': 'Read a specific message by zero-based index', 'element': 'message/<n>', 'output_type': 'claude_message'},
    {'uri': 'claude://session/infernal-earth-0118/timeline', 'description': 'Chronological message timeline with timestamps and turn types', 'element': 'timeline', 'output_type': 'claude_timeline'},
    {'uri': 'claude://session/infernal-earth-0118/context', 'description': 'Context window usage and changes over the session', 'element': 'context', 'output_type': 'claude_context'},
    {
        'uri': 'claude://session/infernal-earth-0118?search=path traversal',
        'description': 'Search all content (text, thinking, tool inputs) for a term',
        'query_param': '?search=<term>',
        'output_type': 'claude_search_results'
    },
    {'uri': 'claude://session/infernal-earth-0118?last', 'description': 'Last assistant turn — fast recovery ("where did it stop?")', 'query_param': '?last', 'output_type': 'claude_messages'},
    {'uri': 'claude://session/infernal-earth-0118?tail=3', 'description': 'Last 3 assistant turns', 'query_param': '?tail=N', 'output_type': 'claude_messages'},
    {'uri': 'claude://session/infernal-earth-0118/message/-1', 'description': 'Last message (negative index)', 'element': 'message/<n>', 'output_type': 'claude_message'},
    {'uri': "claude://sessions/?search=validate_token", 'description': 'Cross-session content search — sessions mentioning a term (20 results by default)', 'query_param': '?search=<term>', 'output_type': 'claude_cross_session_search'},
    {'uri': "claude://sessions/?search=auth&since=2026-03-01", 'description': 'Cross-session search scoped to recent sessions', 'query_param': '?search=<term>&since=<date>', 'output_type': 'claude_cross_session_search'},
    {'uri': "claude://search/validate_token", 'description': 'Path-based alias for cross-session search', 'output_type': 'claude_cross_session_search'},
]

_SCHEMA_NOTES = [
    'Reads Claude Code conversation JSONL files from ~/.claude/projects/',
    'Supports composite queries (e.g., ?tools=Bash&errors)',
    'Workflow tracking shows tool operation sequences',
    'File tracking shows all Read/Write/Edit operations',
    'Tool success rates calculated from result vs error status',
    'Cross-session search: claude://sessions/?search=term scans all JSONL files (parallel grep + snippet extraction). Default 20 results; use --all for full scan. ?since=DATE narrows corpus.',
]


def _resolve_claude_projects_dir() -> Path:
    """Return the Claude sessions directory, checking platform-specific locations.

    Search order:
    1. ``~/.claude/projects`` (standard on Linux, macOS, and Windows)
    2. ``%APPDATA%\\Claude\\projects`` (Windows fallback for non-standard installs)

    Returns the primary path even when it doesn't exist so callers get a
    consistent, actionable path in error messages.
    """
    primary = Path.home() / '.claude' / 'projects'
    if primary.exists():
        return primary
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            alt = Path(appdata) / 'Claude' / 'projects'
            if alt.exists():
                return alt
    return primary


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

    BUDGET_LIST_FIELD = 'results'

    CONVERSATION_BASE = Path(os.environ.get('REVEAL_CLAUDE_DIR', '')) or _resolve_claude_projects_dir()
    SESSIONS_DIR = Path(os.environ.get('REVEAL_SESSIONS_DIR', '')) if os.environ.get('REVEAL_SESSIONS_DIR') else None

    def __init__(self, resource: str, query: Optional[str] = None):
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
        self.query_params = parse_query_params(query or "")
        self.session_name = self._parse_session_name(resource) or "unknown"
        self.conversation_path = self._find_conversation()
        self.messages: Optional[List[Dict]] = None  # Lazy load

    def reconfigure_base_path(self, path: Path) -> None:
        """Update the conversation base directory and re-resolve the conversation path.

        Called when --base-path is provided after initial construction, so the
        adapter can locate conversations under the overridden directory.
        """
        self.CONVERSATION_BASE = path
        self.conversation_path = self._find_conversation()

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
            return parts[1] if len(parts) > 1 else ""
        return resource

    def _find_conversation(self) -> Optional[Path]:
        """Find conversation JSONL file for session.

        Uses two strategies:
        1. Session name matches project directory suffix (named sessions, e.g. TIA-style)
        2. Session name is a UUID matching a JSONL filename inside any project directory

        Returns:
            Path to conversation JSONL file, or None if not found
        """
        if not self.session_name or not self.CONVERSATION_BASE.exists():
            return None

        dirs = [d for d in self.CONVERSATION_BASE.iterdir() if d.is_dir()]

        # Strategy 1 (priority): session name appears in project dir name (named sessions)
        for project_dir in dirs:
            if self.session_name in project_dir.name:
                jsonl_files = [f for f in project_dir.glob('*.jsonl')
                               if not f.stem.startswith('agent-')]
                if jsonl_files:
                    return jsonl_files[0]

        # Strategy 2 (fallback): session name is a UUID matching a JSONL filename
        for project_dir in dirs:
            jsonl_file = project_dir / f"{self.session_name}.jsonl"
            if jsonl_file.exists():
                return jsonl_file

        # Strategy 3: suffix match — handles truncated UUIDs from the session listing
        for project_dir in dirs:
            for jsonl_file in project_dir.glob('*.jsonl'):
                if jsonl_file.stem.endswith(self.session_name):
                    return jsonl_file

        return None

    @staticmethod
    def _find_session_readme(session_name: str, sessions_dir: Optional[Path]) -> Optional[Path]:
        """Find the most recent README for a session in the sessions directory.

        Args:
            session_name: Session identifier (e.g., 'emerald-shade-0315')
            sessions_dir: Root directory containing per-session subdirs

        Returns:
            Path to the most recent README*.md file, or None if not found
        """
        if not sessions_dir or not sessions_dir.exists():
            return None
        session_dir = sessions_dir / session_name
        if not session_dir.exists():
            return None
        readmes = sorted(session_dir.glob('README*.md'), reverse=True)
        return readmes[0] if readmes else None

    @staticmethod
    def _parse_readme_frontmatter(readme_path: Path) -> Dict[str, Any]:
        """Parse YAML frontmatter from a README file.

        Args:
            readme_path: Path to the README file

        Returns:
            Dict of frontmatter fields, empty dict if no frontmatter or parse error
        """
        import yaml
        try:
            text = readme_path.read_text(encoding='utf-8')
            if text.startswith('---'):
                end = text.find('\n---', 3)
                if end != -1:
                    frontmatter_text = text[3:end].strip()
                    return yaml.safe_load(frontmatter_text) or {}
        except Exception:
            pass
        return {}

    def _get_chain(self) -> Dict[str, Any]:
        """Traverse session continuation chain via README continuing_from: links.

        Reads REVEAL_SESSIONS_DIR/<session>/README*.md for each session,
        extracts YAML frontmatter, and follows continuing_from: until the
        chain ends or a cycle is detected (limit: 50 sessions).

        Returns:
            Output Contract v1.0 dict with type 'claude_chain' and chain list
        """
        contract_base = self._get_contract_base()
        sessions_dir = self.SESSIONS_DIR

        chain: List[Dict[str, Any]] = []
        seen: set = set()
        current_name: Optional[str] = self.session_name

        while current_name and current_name not in seen and len(chain) < 50:
            seen.add(current_name)
            readme_path = self._find_session_readme(current_name, sessions_dir)
            frontmatter = self._parse_readme_frontmatter(readme_path) if readme_path else {}

            entry: Dict[str, Any] = {
                'session': current_name,
                'readme': str(readme_path) if readme_path else None,
                'date': frontmatter.get('date') or frontmatter.get('session_date'),
                'badge': frontmatter.get('badge'),
                'continuing_from': frontmatter.get('continuing_from'),
                'tests_start': frontmatter.get('tests_start'),
                'tests_end': frontmatter.get('tests_end'),
                'commits': frontmatter.get('commits'),
            }
            chain.append(entry)
            current_name = frontmatter.get('continuing_from')

        return {
            **contract_base,
            'type': 'claude_chain',
            'session': self.session_name,
            'chain': chain,
            'chain_length': len(chain),
            'sessions_dir': str(sessions_dir) if sessions_dir else None,
        }

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
        with open(self.conversation_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # Skip malformed lines

        self.messages = messages
        return messages

    def _route_by_query(self, messages: List[Dict], conversation_path_str: str,
                        contract_base: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Route to handler by query parameter. Returns None if no query matches."""
        if self.query == 'summary':
            return get_summary(messages, self.session_name, conversation_path_str, contract_base)
        if self.query == 'timeline':
            return get_timeline(messages, self.session_name, contract_base)
        if self.query == 'errors':
            return get_errors(messages, self.session_name, contract_base)
        if self.query and self.query.startswith('tools='):
            return get_tool_calls(messages, self.query.split('=')[1], self.session_name, contract_base)
        if self.query and self.query.startswith('search='):
            return search_messages(messages, self.query.split('=', 1)[1], self.session_name, contract_base)
        # ?tail=N — last N assistant turns; ?last — shorthand for ?tail=1
        tail_str = self.query_params.get('tail')
        if tail_str is not None or 'last' in self.query_params:
            tail = 1 if 'last' in self.query_params else int(tail_str)
            result = get_messages(messages, self.session_name, contract_base)
            turns = result.get('messages', [])
            total = len(turns)
            result['messages'] = turns[-tail:] if 0 < tail < total else ([] if tail == 0 else turns)
            result['total_turns'] = total
            if tail < total:
                result['tail_of'] = total
            return result
        return None

    def _route_by_resource(self, messages: List[Dict], conversation_path_str: str,
                           contract_base: Dict[str, Any]) -> Dict[str, Any]:
        """Route to handler by resource path segment."""
        if '/thinking' in self.resource:
            return get_thinking_blocks(messages, self.session_name, contract_base)
        if '/tools' in self.resource:
            return get_all_tools(messages, self.session_name, contract_base)
        if '/files' in self.resource:
            return get_files_touched(messages, self.session_name, contract_base)
        if '/workflow' in self.resource:
            return get_workflow(messages, self.session_name, contract_base)
        if '/context' in self.resource:
            return get_context_changes(messages, self.session_name, contract_base)
        if '/user' in self.resource:
            return filter_by_role(messages, 'user', self.session_name, contract_base)
        if '/assistant' in self.resource:
            return filter_by_role(messages, 'assistant', self.session_name, contract_base)
        if '/message/' in self.resource:
            msg_id = int(self.resource.split('/message/')[1])
            if msg_id < 0:
                msg_id = len(messages) + msg_id
            return get_message(messages, msg_id, self.session_name, contract_base)
        if '/messages' in self.resource:
            search = self.query_params.get('search') or self.query_params.get('contains')
            return get_messages(messages, self.session_name, contract_base, search=search)
        return get_overview(messages, self.session_name, conversation_path_str, contract_base)

    def _route_query_handler(self, messages: List[Dict], conversation_path_str: str,
                             contract_base: Dict[str, Any]) -> Dict[str, Any]:
        """Route to appropriate handler based on resource path and query."""
        result = self._route_by_query(messages, conversation_path_str, contract_base)
        if result is not None:
            return result
        return self._route_by_resource(messages, conversation_path_str, contract_base)

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
        # Handle bare claude:// and sessions/ aliases.
        # ?search=term at this level means cross-session content search.
        # ?filter=term (or no ?search=) keeps the original session-name listing.
        is_session_list_resource = (
            not self.resource
            or self.resource in ('.', '', 'sessions', 'sessions/')
            or self.resource.startswith('sessions/')
        )
        if is_session_list_resource:
            if self.query_params.get('search'):
                return self._search_sessions()
            return self._list_sessions()

        # claude://search/<term> — path-based alias for cross-session content search.
        # Also handles bare claude://search (prompts for a term).
        if self.resource == 'search' or self.resource.startswith('search/'):
            parts = self.resource.split('/', 1)
            path_term = parts[1].strip() if len(parts) > 1 else ''
            if path_term and not self.query_params.get('search'):
                self.query_params['search'] = path_term
            return self._search_sessions()

        # claude://files/<path> — cross-session file tracking.
        if self.resource == 'files' or self.resource.startswith('files/'):
            return self._track_file_sessions()

        # claude://session/<id>/chain — session continuation chain traversal.
        if '/chain' in self.resource:
            return self._get_chain()

        messages = self._load_messages()
        contract_base = self._get_contract_base()
        conversation_path_str = str(self.conversation_path) if self.conversation_path else ''

        # Check for composite query (multiple filters)
        if self._is_composite_query():
            return self._handle_composite_query(messages)

        # Route to appropriate handler
        return self._route_query_handler(messages, conversation_path_str, contract_base)

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

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        """Extract plain text from a message content (str or list of content blocks)."""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get('type') == 'text':
                    return item.get('text', '').strip()
        return ''

    _BOILERPLATE_PREFIXES = ('# Session Continuation Context', '# TIA System Instructions')

    @staticmethod
    def _parse_jsonl_line_for_title(line: str) -> Optional[str]:
        """Parse one JSONL line and return user text as a title candidate, or None.

        Returns None to signal "skip this line, keep scanning" for boilerplate messages.
        Returns False to signal "stop scanning" (not currently used, but reserved).
        """
        import json as _json
        try:
            rec = _json.loads(line)
        except Exception:
            return None
        if rec.get('type') != 'user':
            return None
        content = rec.get('message', {}).get('content', '')
        text = ClaudeAdapter._extract_text_from_content(content)
        if not text:
            return None
        candidate = text.split('\n')[0].strip()
        # Skip auto-injected boilerplate preambles; try to extract real user text after ---
        if any(candidate.startswith(p) for p in ClaudeAdapter._BOILERPLATE_PREFIXES):
            sep_idx = text.rfind('\n---\n')
            if sep_idx >= 0:
                candidate = text[sep_idx + 5:].strip().split('\n')[0].strip()
            else:
                return None
        # Skip bare boot commands — the real task will be in a later message
        if candidate.lower() in ('boot.', 'boot'):
            return None
        return candidate[:80] or None

    @staticmethod
    def _scan_jsonl_for_title(jsonl_path: Path) -> Optional[str]:
        """Scan first 50 lines of JSONL file for a user text title."""
        with open(jsonl_path, 'r', errors='replace') as fh:
            for i, line in enumerate(fh):
                if i > 50:
                    break
                title = ClaudeAdapter._parse_jsonl_line_for_title(line)
                if title is not None:
                    return title
        return None

    @staticmethod
    def _read_session_title(jsonl_path: Path) -> Optional[str]:
        """Read first user text message from JSONL as a display title.

        Reads only the first 30 lines to avoid loading entire file.
        """
        try:
            return ClaudeAdapter._scan_jsonl_for_title(jsonl_path)
        except Exception:
            return None

    @staticmethod
    def _extract_project_from_dir(dir_name: str) -> str:
        """Derive a short project label from an encoded Claude project directory name.

        E.g. '-home-scottsen-src-tia-sessions-hosefobe-0314' → 'tia'
             '-home-scottsen-src-projects-reveal-external-git' → 'reveal'
        """
        _SKIP = {'home', 'scottsen', 'src', 'projects', 'external', 'internal', 'git'}
        prefix = dir_name.split('-sessions-')[0] if '-sessions-' in dir_name else dir_name
        parts = [p for p in prefix.lstrip('-').split('-') if p and p not in _SKIP]
        return parts[-1] if parts else ''

    @staticmethod
    def _collect_sessions_from_dir(project_dir: Path) -> List[Dict[str, Any]]:
        """Collect session entry dicts from one project directory."""
        sessions = []
        readme_present = bool(list(project_dir.glob('README*.md'))[:1])
        project = ClaudeAdapter._extract_project_from_dir(project_dir.name)
        for jsonl_file in project_dir.glob('*.jsonl'):
            if jsonl_file.stem.startswith('agent-'):
                continue
            dir_name = project_dir.name
            file_stem = jsonl_file.stem
            if '-sessions-' in dir_name:
                session_name = dir_name.split('-sessions-')[-1]
            elif len(file_stem) == 36 and file_stem.count('-') == 4:
                # UUID filename (Windows-style) — use the UUID as the session name
                session_name = file_stem
            else:
                session_name = dir_name
            stat = jsonl_file.stat()
            sessions.append({
                'session': session_name,
                'path': str(jsonl_file),
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'size_kb': stat.st_size // 1024,
                'readme_present': readme_present,
                'project': project,
            })
        return sessions

    def _list_sessions(self) -> Dict[str, Any]:
        """List available Claude Code sessions.

        Scans the Claude projects directory for sessions and returns
        all sessions sorted by recency.

        Supports query params when called from get_structure():
            ?filter=term  - filter session names by substring (case-insensitive)
            ?search=term  - alias for ?filter=term

        CLI flags (applied by routing.py):
            --head N      - show N most recent (default: 20)
            --all         - show all sessions
            --since DATE  - filter by modified date (e.g. 2026-02-27)
            --search TERM - filter session names (overrides ?filter=)

        Returns:
            Dictionary with full session list (routing.py applies display limits)
        """
        base: Dict[str, Any] = {
            'contract_version': '1.0',
            'type': 'claude_session_list',
            'source': str(self.CONVERSATION_BASE),
            'source_type': 'directory'
        }

        name_filter = (self.query_params.get('filter') or self.query_params.get('search', '')).lower()

        sessions = []
        try:
            for project_dir in self.CONVERSATION_BASE.iterdir():
                if not project_dir.is_dir():
                    continue
                sessions.extend(self._collect_sessions_from_dir(project_dir))
            sessions.sort(key=lambda x: x['modified'], reverse=True)  # type: ignore[arg-type, return-value]
        except Exception as e:
            base['error'] = str(e)

        # Apply name filter if provided
        if name_filter:
            sessions = [s for s in sessions if name_filter in str(s['session']).lower()]

        base.update({
            'session_count': len(sessions),
            'recent_sessions': sessions,  # routing.py applies head/since limits
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

    def _search_sessions(self) -> Dict[str, Any]:
        """Cross-session content search using ``?search=term``.

        Scans all session JSONL files for the search term using parallel
        byte-level pre-filtering, then extracts one representative snippet per
        matching session.

        Supports ``?since=DATE`` (e.g. ``2026-03-01`` or ``today``) to scope
        the corpus before scanning — highly recommended for large session stores.

        Returns:
            Dict of type ``claude_cross_session_search`` with ``matches`` list.
        """
        term = self.query_params.get('search', '')
        since = self.query_params.get('since', '')

        if since == 'today':
            from datetime import date as _date
            since = _date.today().isoformat()

        # Collect all sessions across all project directories.
        all_sessions: List[Dict[str, Any]] = []
        try:
            for project_dir in self.CONVERSATION_BASE.iterdir():
                if project_dir.is_dir():
                    all_sessions.extend(self._collect_sessions_from_dir(project_dir))
        except Exception as e:
            return {
                'contract_version': '1.0',
                'type': 'claude_cross_session_search',
                'source': str(self.CONVERSATION_BASE),
                'source_type': 'directory',
                'term': term,
                'error': str(e),
                'sessions_scanned': 0,
                'match_count': 0,
                'matches': [],
            }

        # Apply --since before grep to shrink the corpus.
        if since:
            all_sessions = [s for s in all_sessions if s.get('modified', '') >= since]

        matches = search_sessions_for_term(all_sessions, term)

        return {
            'contract_version': '1.0',
            'type': 'claude_cross_session_search',
            'source': str(self.CONVERSATION_BASE),
            'source_type': 'directory',
            'term': term,
            'since': since or None,
            'sessions_scanned': len(all_sessions),
            'match_count': len(matches),
            'matches': matches,
        }

    def _track_file_sessions(self) -> Dict[str, Any]:
        """Cross-session file tracking using ``claude://files/<path>``.

        Finds all sessions that touched a given file path using parallel
        byte-level pre-filtering, then extracts per-session operations
        (Read/Write/Edit counts).  Partial path matching is used so both
        absolute and relative path fragments work.

        Supports ``?since=DATE`` to scope the corpus before scanning.

        Returns:
            Dict of type ``claude_file_sessions`` with ``sessions`` list.
        """
        from ...utils.parallel import grep_files as _grep_files

        file_path = self.resource[len('files/'):].strip('/')
        since = self.query_params.get('since', '')

        if since == 'today':
            from datetime import date as _date
            since = _date.today().isoformat()

        _error_base: Dict[str, Any] = {
            'contract_version': '1.0',
            'type': 'claude_file_sessions',
            'source': str(self.CONVERSATION_BASE),
            'source_type': 'directory',
            'file_path': file_path,
            'since': since or None,
            'sessions_scanned': 0,
            'match_count': 0,
            'sessions': [],
        }

        if not file_path:
            return {**_error_base, 'error': 'No file path provided. Usage: claude://files/path/to/file.py'}

        all_sessions: List[Dict[str, Any]] = []
        try:
            for project_dir in self.CONVERSATION_BASE.iterdir():
                if project_dir.is_dir():
                    all_sessions.extend(self._collect_sessions_from_dir(project_dir))
        except Exception as e:
            return {**_error_base, 'error': str(e)}

        if since:
            all_sessions = [s for s in all_sessions if s.get('modified', '') >= since]

        # Parallel byte-scan pre-filter.
        matched_paths = _grep_files([Path(s['path']) for s in all_sessions], [file_path])
        matched_path_strs = {str(p) for p in matched_paths}
        candidates = [s for s in all_sessions if s['path'] in matched_path_strs]

        results = []
        for session in candidates:
            try:
                messages: List[Dict] = []
                with open(session['path'], 'r', encoding='utf-8') as fh:
                    for line in fh:
                        try:
                            messages.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                contract_base = {
                    'contract_version': '1.0',
                    'source': session['path'],
                    'source_type': 'file',
                }
                files_result = get_files_touched(messages, session['session'], contract_base)

                # Partial path match across all ops.
                ops_for_file: Dict[str, int] = {}
                for op, files_dict in files_result.get('by_operation', {}).items():
                    count = sum(v for k, v in files_dict.items() if file_path in k)
                    if count:
                        ops_for_file[op] = count

                if ops_for_file:
                    results.append({
                        'session': session['session'],
                        'project': session.get('project', ''),
                        'modified': session['modified'],
                        'ops': ops_for_file,
                        'total_ops': sum(ops_for_file.values()),
                    })
            except Exception:
                continue

        results.sort(key=lambda x: x['modified'], reverse=True)

        return {
            'contract_version': '1.0',
            'type': 'claude_file_sessions',
            'source': str(self.CONVERSATION_BASE),
            'source_type': 'directory',
            'file_path': file_path,
            'since': since or None,
            'sessions_scanned': len(all_sessions),
            'match_count': len(results),
            'sessions': results,
        }

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
            'query_params': _SCHEMA_QUERY_PARAMS,
            'elements': _SCHEMA_ELEMENTS,
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    @staticmethod
    def _get_help_examples() -> List[Dict[str, str]]:
        """Get example URIs for help documentation."""
        return [
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
            },
            {
                'uri': 'claude://session/infernal-earth-0118/user',
                'description': 'User messages: initial prompt + tool-result turns'
            },
            {
                'uri': 'claude://session/infernal-earth-0118/assistant',
                'description': 'Assistant messages: text responses only (skip thinking/tools)'
            },
            {
                'uri': 'claude://session/infernal-earth-0118/message/5',
                'description': 'Read a specific message by index'
            },
            {
                'uri': 'claude://session/infernal-earth-0118/message/-1',
                'description': 'Read the last message (negative index supported)'
            },
            {
                'uri': 'claude://session/infernal-earth-0118?last',
                'description': 'Show last assistant turn — fast session recovery'
            },
            {
                'uri': 'claude://session/infernal-earth-0118?tail=3',
                'description': 'Show last 3 assistant turns'
            },
            {
                'uri': 'claude://session/infernal-earth-0118?search=verify',
                'description': 'Search all content (text, thinking, tool inputs) for a term'
            },
            {
                'uri': "claude://sessions/?search=validate_token",
                'description': 'Cross-session content search — find sessions mentioning a term (20 by default)'
            },
            {
                'uri': "claude://sessions/?search=auth&since=2026-03-01",
                'description': 'Cross-session search scoped to recent sessions (?since= reduces scan time)'
            },
        ]

    @staticmethod
    def _get_help_workflows() -> List[Dict[str, Any]]:
        """Get workflow examples for help documentation."""
        return [
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
            },
            {
                'name': 'Read Session Content',
                'scenario': 'Extract the prompt and findings from a session',
                'steps': [
                    'reveal claude://session/session-name/user',
                    'reveal claude://session/session-name/assistant',
                    'reveal claude://session/session-name/thinking',
                ]
            },
            {
                'name': 'Prompt Comparison',
                'scenario': 'Compare what two sessions found on the same codebase',
                'steps': [
                    'reveal claude://session/session-a/user',
                    'reveal claude://session/session-b/user',
                    'reveal claude://session/session-a?search=<finding>',
                    'reveal claude://session/session-b?search=<finding>',
                ]
            }
        ]

    def post_process(self, result: Dict[str, Any], args: Any) -> Dict[str, Any]:
        """Apply display hints and claude-specific filtering after get_structure().

        Called by the router after get_structure() returns. Keeps all knowledge
        of claude result-type taxonomy inside the adapter layer.
        """
        if not isinstance(result, dict):
            return result

        result_type = result.get('type', '')
        if not result_type.startswith('claude_'):
            return result

        result['_display'] = {
            'max_snippet_chars': getattr(args, 'max_snippet_chars', None),
            'verbose': getattr(args, 'verbose', False),
            'head': getattr(args, 'head', None),
            'tail': getattr(args, 'tail', None),
            'range': getattr(args, 'range', None),
        }

        if result_type == 'claude_workflow':
            self._post_process_workflow(result, args)
        elif result_type == 'claude_session_list':
            self._post_process_session_list(result, args)
        elif result_type == 'claude_messages':
            self._post_process_messages(result, args)
        elif result_type == 'claude_cross_session_search':
            self._post_process_search_results(result, args)

        return result

    @staticmethod
    def _slice_list(items: list, args: Any) -> list:
        """Slice a list by --head, --tail, or --range args."""
        head = getattr(args, 'head', None)
        tail = getattr(args, 'tail', None)
        rng = getattr(args, 'range', None)
        if head is not None:
            return items[:head]
        if tail is not None:
            return items[-tail:]
        if rng is not None:
            start, end = rng
            return items[start - 1:end]
        return items

    @staticmethod
    def _post_process_workflow(result: Dict[str, Any], args: Any) -> None:
        """Apply --type, --search, and --head/--tail/--range to claude_workflow results."""
        workflow = result.get('workflow')
        if workflow is None:
            return
        total_before = len(workflow)

        type_filter = getattr(args, 'type', None)
        if type_filter:
            workflow = [s for s in workflow if (s.get('tool') or '').lower() == type_filter.lower()]

        search_term = getattr(args, 'search', None)
        if search_term:
            lower = search_term.lower()
            workflow = [
                s for s in workflow
                if lower in (s.get('detail') or '').lower()
                or lower in (s.get('tool') or '').lower()
            ]

        workflow = ClaudeAdapter._slice_list(workflow, args)
        result['workflow'] = workflow
        result['displayed_steps'] = len(workflow)
        if len(workflow) < total_before:
            result['filtered_from'] = total_before

    @staticmethod
    def _post_process_search_results(result: Dict[str, Any], args: Any) -> None:
        """Apply --head/--all display limits to claude_cross_session_search results."""
        matches = result.get('matches')
        if matches is None:
            return
        if not getattr(args, 'all', False):
            head = getattr(args, 'head', None)
            matches = matches[:head if head else 20]
        result['matches'] = matches
        result['displayed_count'] = len(matches)

    @staticmethod
    def _post_process_session_list(result: Dict[str, Any], args: Any) -> None:
        """Apply --search, --since, --head/--all filters to claude_session_list results."""
        sessions = result.get('recent_sessions')
        if sessions is None:
            return

        search_term = getattr(args, 'search', None)
        if search_term:
            lower = search_term.lower()
            sessions = [s for s in sessions if lower in s.get('session', '').lower()]

        since = getattr(args, 'since', None)
        if since:
            if since == 'today':
                from datetime import date
                since = date.today().isoformat()
            sessions = [s for s in sessions if s.get('modified', '') >= since]

        if not getattr(args, 'all', False):
            head = getattr(args, 'head', None)
            sessions = sessions[:head if head else 20]

        result['recent_sessions'] = sessions
        result['displayed_count'] = len(sessions)

        for s in sessions:
            if 'title' not in s and s.get('path'):
                s['title'] = ClaudeAdapter._read_session_title(Path(s['path']))

    @staticmethod
    def _post_process_messages(result: Dict[str, Any], args: Any) -> None:
        """Apply --head/--tail/--range slicing to claude_messages results."""
        msgs = result.get('messages')
        if msgs is None:
            return
        msgs = ClaudeAdapter._slice_list(msgs, args)
        result['messages'] = msgs
        result['total_turns'] = len(msgs)

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
            'examples': ClaudeAdapter._get_help_examples(),
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
            'workflows': ClaudeAdapter._get_help_workflows(),
            'try_now': [
                'reveal claude://                                   # list all sessions',
                'reveal claude://session/infernal-earth-0118',
                'reveal claude://session/infernal-earth-0118?summary',
                'reveal claude://session/infernal-earth-0118/thinking'
            ],
            'notes': [
                'Conversation files stored in ~/.claude/projects/{project-dir}/',
                'Session names typically match directory names (e.g., infernal-earth-0118)',
                'Token estimates are approximate (chars / 4)',
                'Use --format=json for programmatic analysis with jq',
                'Current session name — bash/zsh: basename $PWD | PowerShell: Split-Path -Leaf $PWD',
                'On Windows, UUID session names are shown in the listing (reveal claude://)',
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal json:// - Navigate JSONL structure directly',
                'reveal help://adapters - All available adapters',
                'TIA session domain - High-level session operations'
            ]
        }
