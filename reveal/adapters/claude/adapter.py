"""Claude Code conversation adapter implementation."""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
from typing import Dict, List, Any, Optional
from datetime import datetime, date as _date
import json

from ..base import ResourceAdapter, register_adapter, register_renderer
from .renderer import ClaudeRenderer
from ...utils.query import parse_query_params
from .handlers.sessions import (
    list_sessions as _h_list_sessions,
    search_sessions as _h_search_sessions,
    track_file_sessions as _h_track_file_sessions,
    get_chain as _h_get_chain,
    _read_session_title,
)
from .handlers.system import (
    get_history as _h_get_history,
    get_settings as _h_get_settings,
    get_info as _h_get_info,
    get_config as _h_get_config,
)
from .handlers.workspace import (
    get_plans as _h_get_plans,
    get_memory as _h_get_memory,
    get_agents as _h_get_agents,
    get_hooks as _h_get_hooks,
)
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
    get_token_breakdown,
    search_sessions_for_term,
    get_session_agents,
    get_message_range,
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
    'tokens': {
        'type': 'flag',
        'description': 'Token usage breakdown by message role (input/output/cache)',
        'examples': ['?tokens']
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
    _make_output_type('claude_history', 'Prompt history from ~/.claude/history.jsonl', {
        'total_entries': {'type': 'integer'},
        'match_count': {'type': 'integer'},
        'entries': {'type': 'array'},
    }),
    _make_output_type('claude_info', 'Diagnostic dump of all resolved Claude Code data paths', {
        'paths': {'type': 'object'}, 'env': {'type': 'object'},
    }),
    _make_output_type('claude_settings', 'Claude Code settings from ~/.claude/settings.json', {
        'settings': {'type': 'object'},
    }),
    _make_output_type('claude_plans', 'List of plans from ~/.claude/plans/', {
        'plans': {'type': 'array'}, 'total': {'type': 'integer'},
    }),
    _make_output_type('claude_plan', 'Single plan content from ~/.claude/plans/', {
        'name': {'type': 'string'}, 'content': {'type': 'string'},
    }),
    _make_output_type('claude_config', 'Per-install config from ~/.claude.json (projects, MCP servers, flags)', {
        'projects_count': {'type': 'integer'}, 'projects': {'type': 'array'}, 'flags': {'type': 'object'},
    }),
    _make_output_type('claude_memory', 'Memory files from ~/.claude/projects/*/memory/', {
        'memories': {'type': 'array'}, 'total': {'type': 'integer'},
    }),
    _make_output_type('claude_agents', 'List of agent definitions from ~/.claude/agents/', {
        'agents': {'type': 'array'}, 'total': {'type': 'integer'},
    }),
    _make_output_type('claude_agent', 'Single agent definition from ~/.claude/agents/', {
        'name': {'type': 'string'}, 'content': {'type': 'string'},
    }),
    _make_output_type('claude_hooks', 'Hook scripts from ~/.claude/hooks/', {
        'hooks': {'type': 'array'}, 'total': {'type': 'integer'},
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
    {'uri': 'claude://history', 'description': 'Recent prompt history — last 50 prompts across all projects', 'output_type': 'claude_history'},
    {'uri': "claude://history?search=validate_token", 'description': 'Find prompts mentioning a term', 'query_param': '?search=<term>', 'output_type': 'claude_history'},
    {'uri': "claude://history?project=frono&since=2026-03-28", 'description': 'Prompts in a specific project since a date', 'query_param': '?project=<path>&since=<date>', 'output_type': 'claude_history'},
    {'uri': 'claude://info', 'description': 'Diagnostic dump of all resolved data paths', 'output_type': 'claude_info'},
    {'uri': 'claude://settings', 'description': 'Claude Code settings (model, permissions, hooks)', 'output_type': 'claude_settings'},
    {'uri': "claude://settings?key=model", 'description': 'Extract a specific settings value (dot-notation)', 'query_param': '?key=<dotpath>', 'output_type': 'claude_settings'},
    {'uri': "claude://settings?key=permissions.additionalDirectories", 'description': 'Extract nested settings value', 'query_param': '?key=<dotpath>', 'output_type': 'claude_settings'},
    {'uri': 'claude://plans', 'description': 'List all saved implementation plans', 'output_type': 'claude_plans'},
    {'uri': 'claude://plans/gentle-foraging-candy', 'description': 'Read a specific plan by name', 'output_type': 'claude_plan'},
    {'uri': "claude://plans?search=token", 'description': 'Search across plan content', 'query_param': '?search=<term>', 'output_type': 'claude_plans'},
    {'uri': 'claude://config', 'description': 'Per-install config: project count, MCP servers, feature flags', 'output_type': 'claude_config'},
    {'uri': "claude://config?key=projects./path/to/proj.mcpServers", 'description': 'Extract a specific config value (dot-notation)', 'query_param': '?key=<dotpath>', 'output_type': 'claude_config'},
    {'uri': 'claude://memory', 'description': 'All memory files across all projects', 'output_type': 'claude_memory'},
    {'uri': 'claude://memory/my-project', 'description': 'Memory files for a specific project', 'output_type': 'claude_memory'},
    {'uri': "claude://memory?search=feedback", 'description': 'Search memory file content', 'query_param': '?search=<term>', 'output_type': 'claude_memory'},
    {'uri': 'claude://agents', 'description': 'List all agent definitions', 'output_type': 'claude_agents'},
    {'uri': 'claude://agents/reveal-codereview', 'description': 'Read a specific agent definition', 'output_type': 'claude_agent'},
    {'uri': 'claude://hooks', 'description': 'List all hook event types and scripts', 'output_type': 'claude_hooks'},
    {'uri': 'claude://hooks/PostToolUse', 'description': 'Read a specific hook event script or list scripts', 'output_type': 'claude_hooks'},
]

_SCHEMA_NOTES = [
    'Reads Claude Code conversation JSONL files from ~/.claude/projects/',
    'Supports composite queries (e.g., ?tools=Bash&errors)',
    'Workflow tracking shows tool operation sequences',
    'File tracking shows all Read/Write/Edit operations',
    'Tool success rates calculated from result vs error status',
    'Cross-session search: claude://sessions/?search=term scans all JSONL files (parallel grep + snippet extraction). Default 20 results; use --all for full scan. ?since=DATE narrows corpus.',
]


def _resolve_claude_home_dir() -> Path:
    """Return the ~/.claude config directory, checking platform-specific locations.

    Search order:
    1. ``~/.claude`` (standard on Linux, macOS, and Windows)
    2. ``%APPDATA%\\Claude`` (Windows fallback for non-standard installs)

    Returns the primary path even when it doesn't exist so callers get a
    consistent, actionable path in error messages.
    """
    primary = Path.home() / '.claude'
    if primary.exists():
        return primary
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', '')
        if appdata:
            alt = Path(appdata) / 'Claude'
            if alt.exists():
                return alt
    return primary


def _resolve_claude_projects_dir() -> Path:
    """Return the Claude sessions directory, checking platform-specific locations.

    Search order:
    1. ``~/.claude/projects`` (standard on Linux, macOS, and Windows)
    2. ``%APPDATA%\\Claude\\projects`` (Windows fallback for non-standard installs)

    Returns the primary path even when it doesn't exist so callers get a
    consistent, actionable path in error messages.
    """
    primary = _resolve_claude_home_dir() / 'projects'
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

    # ~/.claude/ config directory — all non-session resources (settings, plans, history, etc.)
    # Override with REVEAL_CLAUDE_HOME env var.
    CLAUDE_HOME: Path = Path(os.environ['REVEAL_CLAUDE_HOME']) if os.environ.get('REVEAL_CLAUDE_HOME') else _resolve_claude_home_dir()

    # ~/.claude.json — per-install config file (MCP servers, feature flags).
    # Separate from CLAUDE_HOME; lives in the user's home directory on all platforms.
    # When REVEAL_CLAUDE_HOME is set, derives from its parent directory automatically
    # so a single override covers the whole user's Claude install (common for SSH).
    # Override explicitly with REVEAL_CLAUDE_JSON for non-standard layouts.
    CLAUDE_JSON: Path = (
        Path(os.environ['REVEAL_CLAUDE_JSON']) if os.environ.get('REVEAL_CLAUDE_JSON')
        else CLAUDE_HOME.parent / '.claude.json' if os.environ.get('REVEAL_CLAUDE_HOME')
        else Path.home() / '.claude.json'
    )

    # ~/.claude/projects/ — session JSONL files, one subdirectory per project.
    # When REVEAL_CLAUDE_HOME is set, derives from it automatically (CLAUDE_HOME / 'projects')
    # so a single override covers the whole install (common for SSH).
    # Override explicitly with REVEAL_CLAUDE_DIR for non-standard layouts.
    CONVERSATION_BASE: Path = (
        Path(os.environ['REVEAL_CLAUDE_DIR']) if os.environ.get('REVEAL_CLAUDE_DIR')
        else CLAUDE_HOME / 'projects' if os.environ.get('REVEAL_CLAUDE_HOME')
        else _resolve_claude_projects_dir()
    )

    # ~/.claude/plans/ — saved implementation plans (markdown files).
    PLANS_DIR: Path = CLAUDE_HOME / 'plans'

    # ~/.claude/agents/ — custom agent definitions (markdown files).
    AGENTS_DIR: Path = CLAUDE_HOME / 'agents'

    # ~/.claude/hooks/ — hook scripts keyed by event type.
    HOOKS_DIR: Path = CLAUDE_HOME / 'hooks'

    # Named session directories with README frontmatter (chain traversal via ?chain).
    # Set REVEAL_SESSIONS_DIR env var to enable; not required for standard usage.
    SESSIONS_DIR: Optional[Path] = Path(os.environ.get('REVEAL_SESSIONS_DIR', '')) if os.environ.get('REVEAL_SESSIONS_DIR') else None

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
        """Update all Claude install paths derived from the given projects directory.

        Called when --base-path is provided after initial construction. Derives
        CLAUDE_HOME and CLAUDE_JSON from path.parent so that a single flag covers
        the entire Claude install (history, config, plans, hooks, sessions).

        Derivation:
            CONVERSATION_BASE = path                     (~/.claude/projects/)
            CLAUDE_HOME       = path.parent              (~/.claude/)
            CLAUDE_JSON       = path.parent.parent / '.claude.json'  (~/.claude.json)
            PLANS_DIR         = path.parent / 'plans'
            AGENTS_DIR        = path.parent / 'agents'
            HOOKS_DIR         = path.parent / 'hooks'
        """
        self.CONVERSATION_BASE = path
        self.CLAUDE_HOME = path.parent
        self.CLAUDE_JSON = path.parent.parent / '.claude.json'
        self.PLANS_DIR = path.parent / 'plans'
        self.AGENTS_DIR = path.parent / 'agents'
        self.HOOKS_DIR = path.parent / 'hooks'
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
        1. Session name matches project directory suffix (named sessions)
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

    def _get_chain(self) -> Dict[str, Any]:
        return _h_get_chain(self.resource, self.session_name, self.SESSIONS_DIR, self._get_contract_base())

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
        if self.query == 'tokens':
            return get_token_breakdown(messages, self.session_name, contract_base)
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
            include_patches = self.query_params.get('patches') == 'true'
            return get_files_touched(messages, self.session_name, contract_base, include_patches=include_patches)
        if '/workflow' in self.resource:
            return get_workflow(messages, self.session_name, contract_base)
        if '/agents' in self.resource:
            return get_session_agents(messages, self.session_name, contract_base)
        if '/context' in self.resource:
            return get_context_changes(messages, self.session_name, contract_base)
        if '/user' in self.resource:
            return filter_by_role(messages, 'user', self.session_name, contract_base)
        if '/assistant' in self.resource:
            result = filter_by_role(messages, 'assistant', self.session_name, contract_base)
            result['full'] = 'full' in self.query_params
            return result
        if '/message/' in self.resource:
            msg_id = int(self.resource.split('/message/')[1])
            if msg_id < 0:
                msg_id = len(messages) + msg_id
            return get_message(messages, msg_id, self.session_name, contract_base)
        if self.resource.endswith('/message'):
            result = get_message_range(messages, self.session_name, contract_base)
            result['full'] = 'full' in self.query_params
            return result
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

        # claude://history — prompt history from ~/.claude/history.jsonl.
        if self.resource == 'history' or self.resource.startswith('history'):
            return self._get_history()

        # claude://info — diagnostic path dump.
        if self.resource == 'info':
            return self._get_info()

        # claude://settings — ~/.claude/settings.json.
        if self.resource == 'settings':
            return self._get_settings()

        # claude://plans[/<name>] — list or read ~/.claude/plans/.
        if self.resource == 'plans' or self.resource.startswith('plans/'):
            return self._get_plans()

        # claude://config — ~/.claude.json per-install config.
        if self.resource == 'config':
            return self._get_config()

        # claude://memory[/<project>] — memory files from ~/.claude/projects/*/memory/.
        if self.resource == 'memory' or self.resource.startswith('memory/'):
            return self._get_memory()

        # claude://agents[/<name>] — list or read ~/.claude/agents/.
        if self.resource == 'agents' or self.resource.startswith('agents/'):
            return self._get_agents()

        # claude://hooks[/<event>] — list or read ~/.claude/hooks/.
        if self.resource == 'hooks' or self.resource.startswith('hooks/'):
            return self._get_hooks()

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

    def _list_sessions(self) -> Dict[str, Any]:
        return _h_list_sessions(self.CONVERSATION_BASE, self.query_params)

    def _search_sessions(self) -> Dict[str, Any]:
        return _h_search_sessions(self.CONVERSATION_BASE, self.query_params)

    def _track_file_sessions(self) -> Dict[str, Any]:
        return _h_track_file_sessions(self.CONVERSATION_BASE, self.resource, self.query_params)

    def _get_history(self) -> Dict[str, Any]:
        return _h_get_history(self.CLAUDE_HOME, self.query_params)

    def _get_info(self) -> Dict[str, Any]:
        return _h_get_info(self.CLAUDE_HOME, self.CONVERSATION_BASE, self.PLANS_DIR, self.CLAUDE_JSON, self.SESSIONS_DIR)

    def _get_settings(self) -> Dict[str, Any]:
        return _h_get_settings(self.CLAUDE_HOME, self.query_params)

    def _get_plans(self) -> Dict[str, Any]:
        return _h_get_plans(self.PLANS_DIR, self.resource, self.query_params)

    _SECRET_PATTERNS = ('api_key', 'apikey', 'api-key', 'secret', 'token', 'password', 'credential', 'auth')

    def _mask_secrets(self, obj: Any, depth: int = 0) -> Any:
        """Recursively mask secret-looking string values in a config dict."""
        if depth > 6:
            return obj
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                k_lower = k.lower()
                if any(p in k_lower for p in self._SECRET_PATTERNS) and isinstance(v, str) and len(v) > 8:
                    result[k] = v[:4] + '***'
                else:
                    result[k] = self._mask_secrets(v, depth + 1)
            return result
        if isinstance(obj, list):
            return [self._mask_secrets(i, depth + 1) for i in obj]
        return obj

    def _get_config(self) -> Dict[str, Any]:
        return _h_get_config(self.CLAUDE_JSON, self.query_params)

    def _get_memory(self) -> Dict[str, Any]:
        return _h_get_memory(self.CONVERSATION_BASE, self.resource, self.query_params)

    def _get_agents(self) -> Dict[str, Any]:
        return _h_get_agents(self.AGENTS_DIR, self.resource, self.query_params)

    def _get_hooks(self) -> Dict[str, Any]:
        return _h_get_hooks(self.HOOKS_DIR, self.resource)

    # Static aliases — delegate to handlers/sessions.py; kept for test compatibility
    from .handlers.sessions import (  # type: ignore[misc]
        _extract_project_from_dir,
        _collect_sessions_from_dir,
        _read_session_title,
        _extract_text_from_content,
        _parse_jsonl_line_for_title,
        _find_session_readme,
        _parse_readme_frontmatter,
    )
    _extract_project_from_dir = staticmethod(_extract_project_from_dir)  # type: ignore[assignment]
    _collect_sessions_from_dir = staticmethod(_collect_sessions_from_dir)  # type: ignore[assignment]
    _read_session_title = staticmethod(_read_session_title)  # type: ignore[assignment]
    _extract_text_from_content = staticmethod(_extract_text_from_content)  # type: ignore[assignment]
    _parse_jsonl_line_for_title = staticmethod(_parse_jsonl_line_for_title)  # type: ignore[assignment]
    _find_session_readme = staticmethod(_find_session_readme)  # type: ignore[assignment]
    _parse_readme_frontmatter = staticmethod(_parse_readme_frontmatter)  # type: ignore[assignment]

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
            {
                'uri': 'claude://info',
                'description': 'Diagnostic: where are all my Claude Code data files?'
            },
            {
                'uri': 'claude://settings',
                'description': 'Claude Code settings: model, permissions, timeout, hooks'
            },
            {
                'uri': "claude://settings?key=permissions.additionalDirectories",
                'description': 'Extract a specific nested settings value'
            },
            {
                'uri': 'claude://history',
                'description': 'Recent prompt history — last 50 prompts across all projects'
            },
            {
                'uri': "claude://history?search=validate_token",
                'description': 'Find prompts mentioning a term'
            },
            {
                'uri': 'claude://plans',
                'description': 'List all saved implementation plans (~/.claude/plans/)'
            },
            {
                'uri': 'claude://plans/gentle-foraging-candy',
                'description': 'Read a specific plan by name'
            },
            {
                'uri': "claude://plans?search=token",
                'description': 'Search across all plan content for a term'
            },
            {
                'uri': 'claude://config',
                'description': 'Per-install config: project count, MCP servers, feature flags'
            },
            {
                'uri': "claude://config?key=installMethod",
                'description': 'Extract a specific config value (dot-notation path)'
            },
            {
                'uri': 'claude://memory',
                'description': 'All memory files across projects (~/.claude/projects/*/memory/)'
            },
            {
                'uri': "claude://memory?search=feedback",
                'description': 'Search memory file content across all projects'
            },
            {
                'uri': 'claude://agents',
                'description': 'List all agent definitions (~/.claude/agents/)'
            },
            {
                'uri': 'claude://agents/reveal-codereview',
                'description': 'Read a specific agent definition'
            },
            {
                'uri': 'claude://hooks',
                'description': 'List all hook event types and scripts (~/.claude/hooks/)'
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
            },
            {
                'name': 'Browse Claude Setup',
                'scenario': 'Audit your Claude Code install: MCP servers, agents, hooks, memory',
                'steps': [
                    'reveal claude://info',
                    'reveal claude://config',
                    'reveal claude://agents',
                    'reveal claude://hooks',
                    'reveal claude://memory',
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
        elif result_type == 'claude_message_range':
            self._post_process_message_range(result, args)
        elif result_type == 'claude_cross_session_search':
            self._post_process_search_results(result, args)
        elif result_type == 'claude_history':
            self._post_process_history(result, args)

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
    def _post_process_history(result: Dict[str, Any], args: Any) -> None:
        """Apply --search, --since, --head/--all filters to claude_history results."""
        entries = result.get('entries')
        if entries is None:
            return

        search_term = getattr(args, 'search', None)
        if search_term:
            lower = search_term.lower()
            entries = [e for e in entries if lower in e.get('prompt', '').lower()]

        since = getattr(args, 'since', None)
        if since:
            if since == 'today':
                from datetime import date
                since = date.today().isoformat()
            entries = [e for e in entries if e.get('timestamp', '') >= since]

        if not getattr(args, 'all', False):
            head = getattr(args, 'head', None)
            entries = entries[:head if head else 50]

        result['entries'] = entries
        result['displayed_count'] = len(entries)

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
                s['title'] = _read_session_title(Path(s['path']))

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
    def _post_process_message_range(result: Dict[str, Any], args: Any) -> None:
        """Apply --head/--tail/--range slicing to claude_message_range results."""
        msgs = result.get('messages')
        if msgs is None:
            return
        total_before = len(msgs)
        msgs = ClaudeAdapter._slice_list(msgs, args)
        result['messages'] = msgs
        result['displayed'] = len(msgs)
        if len(msgs) < total_before:
            result['filtered_from'] = total_before

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for claude:// adapter.

        Returns:
            Dictionary with help information (name, description, syntax, examples, etc.)
        """
        return {
            'name': 'claude',
            'description': 'Navigate and analyze Claude Code conversations - progressive session exploration',
            'syntax': (
                'claude://                                          # list all sessions\n'
                'claude://?search=<term>                            # search across sessions\n'
                'claude://session/{name}[/resource][?query]        # session-scoped access\n'
                'claude://info                                      # install overview\n'
                'claude://config[?key=<name>]                      # config flags and MCP registrations\n'
                'claude://history[?search=<term>]                  # prompt history\n'
                'claude://plans[/{name}]                           # saved plans\n'
                'claude://memory                                    # memory files\n'
                'claude://agents                                    # agent definitions\n'
                'claude://hooks                                     # hook configurations'
            ),
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
                'reveal claude://info                               # install overview',
                'reveal claude://config                            # config flags and MCP registrations',
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
                'SSH / multi-user: --base-path /path/to/.claude/projects points all resources at that install',
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [
                'reveal json:// - Navigate JSONL structure directly',
                'reveal help://adapters - All available adapters',
            ]
        }
