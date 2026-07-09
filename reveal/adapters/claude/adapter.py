"""Claude Code conversation adapter implementation."""

import logging
import os
import re
import sys
from pathlib import Path

# Matches the adjective-noun-MMDD pattern used for named TIA/Claude sessions.
_SESSION_NAME_RE = re.compile(r'^([a-z]+-[a-z]+-\d{4})(?:/|$)')
# Matches UUID session names (Windows / standard Claude Code layout).
_UUID_SESSION_RE = re.compile(r'^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:/|$)', re.IGNORECASE)
# Matches the 8-char hex prefix shown in session listings (truncated UUID, BACK-350).
_SHORT_UUID_RE = re.compile(r'^([0-9a-f]{8})(?:/|$)', re.IGNORECASE)


def _parse_session_identifier(resource: str):
    """Parse a session URI resource into (session_name, sub_path).

    Single source of truth for all recognized session identifier shapes — keeps
    _parse_session_name and _find_conversation in sync (BACK-358).

    Recognized forms:
    - 'session/NAME[/sub-path]'          explicit prefix
    - 'adjective-noun-MMDD[/sub-path]'   named TIA/Claude session
    - 'full-uuid[/sub-path]'             32-hex UUID (Windows layout)
    - '8hexchars[/sub-path]'             truncated UUID prefix from listings

    Returns:
        (session_name, sub_path) — sub_path is '' when absent.
    """
    if resource.startswith('session/'):
        parts = resource.split('/', 2)
        name = parts[1] if len(parts) > 1 else ''
        sub = parts[2] if len(parts) > 2 else ''
        return name, sub
    for regex in (_SESSION_NAME_RE, _UUID_SESSION_RE, _SHORT_UUID_RE):
        m = regex.match(resource)
        if m:
            name = m.group(1)
            sub = resource[len(name):].lstrip('/')
            return name, sub
    return resource, ''

logger = logging.getLogger(__name__)
from typing import Dict, List, Any, Optional
import json

from ..base import ResourceAdapter, register_adapter, register_renderer
from .renderer import ClaudeRenderer
from ...utils.query import parse_query_params
from .handlers.sessions import (
    list_sessions as _h_list_sessions,
    search_sessions as _h_search_sessions,
    track_file_sessions as _h_track_file_sessions,
    get_chain as _h_get_chain,
)
from .handlers.post_process import (
    _post_process_workflow,
    _post_process_search_results,
    _post_process_history,
    _post_process_session_list,
    _post_process_messages,
    _post_process_message_range,
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
    get_human_prompts,
    get_message,
    get_thinking_blocks,
    search_messages,
    get_messages,
    calculate_tool_success_rate,
    get_files_touched,
    get_workflow,
    get_context_changes,
    get_token_breakdown,
    get_session_agents,
    get_message_range,
    get_digest,
    get_exchanges,
)


from .schema import (
    _SCHEMA_QUERY_PARAMS,
    _SCHEMA_CLI_FLAGS,
    _SCHEMA_ELEMENTS,
    _make_output_type,
    _SCHEMA_OUTPUT_TYPES,
    _SCHEMA_EXAMPLE_QUERIES,
    _SCHEMA_NOTES,
)


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
        self._warn_unknown_query_params(self.query_params)  # BACK-507
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

        Raises:
            ValueError: If path looks like a session directory (contains .jsonl files
                directly) rather than the projects directory.
        """
        if path.exists():
            # Auto-detect: if path is a .claude home (has a projects/ subdir), configure from there.
            projects_subdir = path / 'projects'
            if projects_subdir.is_dir():
                path = projects_subdir
            elif next(path.glob('*.jsonl'), None) is not None:
                raise ValueError(
                    f"--base-path looks like a session directory (contains .jsonl files directly).\n"
                    f"If pointing to a .claude home, use REVEAL_CLAUDE_HOME instead:\n"
                    f"  REVEAL_CLAUDE_HOME={path.parent} reveal 'claude://...'  # .claude home\n"
                    f"  --base-path {path.parent}                               # projects/ parent"
                )
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
        """Extract session name from URI resource string.

        Delegates to the module-level _parse_session_identifier so that all
        recognized session shapes stay in one place (BACK-358).
        """
        return _parse_session_identifier(resource)[0]

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

        # Strategy 4: prefix match — truncated 8-char UUID appears at the START of full
        # UUID filenames (e.g. 'c318161b' matches 'c318161b-xxxx-....jsonl').  Only applied
        # when session_name looks like a short UUID to avoid over-broad matching (BACK-350).
        if _SHORT_UUID_RE.fullmatch(self.session_name):
            for project_dir in dirs:
                for jsonl_file in project_dir.glob('*.jsonl'):
                    if jsonl_file.stem.startswith(self.session_name):
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

    def _has_query_flag(self, name: str) -> bool:
        """True when query is bare ?name or has ?name=value."""
        return self.query == name or self.query_params.get(name) is not None

    def _resolve_tail_count(self) -> int:
        last_val = self.query_params.get('last')
        if last_val is not None:
            return int(last_val) if last_val else 1
        return int(self.query_params['tail'])

    def _route_by_query(self, messages: List[Dict], conversation_path_str: str,
                        contract_base: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Route to handler by query parameter. Returns None if no query matches."""
        if self._has_query_flag('summary'):
            return get_summary(messages, self.session_name, conversation_path_str, contract_base)
        if self._has_query_flag('digest'):
            return get_digest(messages, self.session_name, conversation_path_str, contract_base)
        if self._has_query_flag('timeline'):
            return get_timeline(messages, self.session_name, contract_base)
        if self._has_query_flag('errors'):
            return get_errors(messages, self.session_name, contract_base)
        if self._has_query_flag('tokens'):
            return get_token_breakdown(messages, self.session_name, contract_base)
        if self.query and self.query.startswith('tools='):
            return get_tool_calls(messages, self.query.split('=')[1], self.session_name, contract_base)
        if self.query and self.query.startswith('search='):
            return search_messages(messages, self.query.split('=', 1)[1], self.session_name, contract_base)
        role = self.query_params.get('role')
        if role in ('user', 'assistant'):
            result = filter_by_role(messages, role, self.session_name, contract_base)
            if role == 'assistant':
                result['full'] = 'full' in self.query_params
            return result
        # ?tail=N or ?last=N — last N turns; bare ?last — shorthand for ?tail=1
        if self.query_params.get('tail') is not None or self.query_params.get('last') is not None:
            tail = self._resolve_tail_count()
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
        # Structural sub-resources: distinct data shapes, not overview filters.
        # No query-param alias (?thinking, ?workflow, …) — by design (BACK-352).
        # Contrast with /errors, /summary, /timeline, /tokens below, which ARE
        # aliases for query-param views added in BACK-270.
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
        if '/prompts' in self.resource:
            return get_human_prompts(messages, self.session_name, contract_base)
        if '/exchanges' in self.resource:
            result = get_exchanges(messages, self.session_name, contract_base)
            result['full'] = 'full' in self.query_params
            return result
        # Path aliases for query-routed views (BACK-270): /errors, /summary, /timeline, /tokens, /digest
        if '/errors' in self.resource:
            return get_errors(messages, self.session_name, contract_base)
        if '/summary' in self.resource:
            return get_summary(messages, self.session_name, conversation_path_str, contract_base)
        if '/digest' in self.resource:
            return get_digest(messages, self.session_name, conversation_path_str, contract_base)
        if '/timeline' in self.resource:
            return get_timeline(messages, self.session_name, contract_base)
        if '/tokens' in self.resource:
            return get_token_breakdown(messages, self.session_name, contract_base)
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

    # Prefix → method-name table for simple resource routing.
    # Each entry matches `resource == prefix` OR `resource.startswith(prefix + '/')`.
    _RESOURCE_DISPATCH = [
        ('files',    '_track_file_sessions'),
        ('history',  '_get_history'),
        ('info',     '_get_info'),
        ('settings', '_get_settings'),
        ('plans',    '_get_plans'),
        ('config',   '_get_config'),
        ('memory',   '_get_memory'),
        ('agents',   '_get_agents'),
        ('hooks',    '_get_hooks'),
    ]

    def _is_session_list_resource(self) -> bool:
        return (
            not self.resource
            or self.resource in ('.', '', 'sessions', 'sessions/')
            or self.resource.startswith('sessions/')
        )

    def _inject_search_term(self) -> None:
        """Copy path component of search/<term> into query_params['search']."""
        parts = self.resource.split('/', 1)
        path_term = parts[1].strip() if len(parts) > 1 else ''
        if path_term and not self.query_params.get('search'):
            self.query_params['search'] = path_term

    def _resolve_resource_handler(self) -> Optional[Any]:
        """Return bound handler for the current resource prefix, or None."""
        for prefix, method_name in self._RESOURCE_DISPATCH:
            if self.resource == prefix or self.resource.startswith(prefix + '/'):
                return getattr(self, method_name)
        return None

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Return session structure based on resource path and query params."""
        # Bare claude://, sessions/, '.', '' → session list or cross-session search.
        if self._is_session_list_resource():
            return self._search_sessions() if self.query_params.get('search') else self._list_sessions()

        # search/<term> — path-based alias; copy term into query_params first.
        if self.resource == 'search' or self.resource.startswith('search/'):
            self._inject_search_term()
            return self._search_sessions()

        # /chain substring (not a simple prefix — appears mid-path).
        if '/chain' in self.resource:
            return self._get_chain()

        # Simple prefix dispatch (files/, history, plans/, memory/, …).
        handler = self._resolve_resource_handler()
        if handler is not None:
            return handler()

        # Session message routing — load messages then dispatch by query/resource.
        messages = self._load_messages()
        contract_base = self._get_contract_base()
        conversation_path_str = str(self.conversation_path) if self.conversation_path else ''
        if self._is_composite_query():
            return self._handle_composite_query(messages)
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
            tool_filter = self.query_params['tools']
            tool_names = {n.strip() for n in tool_filter.split(',') if n.strip()}
            results = [r for r in results if r.get('tool_name') in tool_names]

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

    def _get_config(self) -> Dict[str, Any]:
        return _h_get_config(self.CLAUDE_JSON, self.query_params)

    def _get_memory(self) -> Dict[str, Any]:
        return _h_get_memory(self.CONVERSATION_BASE, self.resource, self.query_params)

    def _get_agents(self) -> Dict[str, Any]:
        return _h_get_agents(self.AGENTS_DIR, self.resource, self.query_params)

    def _get_hooks(self) -> Dict[str, Any]:
        return _h_get_hooks(self.HOOKS_DIR, self.resource)

    # Static aliases — delegate to handlers/post_process.py; kept for test compatibility
    from .handlers.post_process import (  # type: ignore[misc]
        _slice_list,
        _post_process_workflow,
        _post_process_search_results,
        _post_process_history,
        _post_process_session_list,
        _post_process_messages,
        _post_process_message_range,
    )
    _slice_list = staticmethod(_slice_list)  # type: ignore[assignment]
    _post_process_workflow = staticmethod(_post_process_workflow)  # type: ignore[assignment]
    _post_process_search_results = staticmethod(_post_process_search_results)  # type: ignore[assignment]
    _post_process_history = staticmethod(_post_process_history)  # type: ignore[assignment]
    _post_process_session_list = staticmethod(_post_process_session_list)  # type: ignore[assignment]
    _post_process_messages = staticmethod(_post_process_messages)  # type: ignore[assignment]
    _post_process_message_range = staticmethod(_post_process_message_range)  # type: ignore[assignment]

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
            'cli_flags': _SCHEMA_CLI_FLAGS,
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
                'uri': 'claude://session/2627362f-6f72-45e1-b7bb-d5a61519a388',
                'description': 'Session overview (messages, tools, duration) — session name is the UUID directory name under ~/.claude/projects/<project>/ (or a friendly name if using a session-naming layer)'
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
                'uri': 'claude://session/infernal-earth-0118/messages',
                'description': 'All assistant narrative turns (text only) — best resource for reading what was said'
            },
            {
                'uri': 'claude://session/infernal-earth-0118/prompts',
                'description': 'Human-typed prompts only (excludes tool-result wrapper messages)'
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
                    'reveal claude://session/session-name/prompts',
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
            _post_process_workflow(result, args)
        elif result_type == 'claude_session_list':
            _post_process_session_list(result, args)
        elif result_type == 'claude_messages':
            _post_process_messages(result, args)
        elif result_type == 'claude_message_range':
            _post_process_message_range(result, args)
        elif result_type == 'claude_cross_session_search':
            _post_process_search_results(result, args)
        elif result_type == 'claude_history':
            _post_process_history(result, args)

        return result

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
