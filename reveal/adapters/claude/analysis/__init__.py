"""Claude session analysis modules."""

from .tools import (
    extract_all_tool_results,
    get_tool_calls,
    get_all_tools,
    calculate_tool_success_rate,
    is_tool_error,
    get_files_touched,
    get_workflow,
    get_session_agents,
)
from .errors import get_errors, get_error_context
from .timeline import get_timeline
from .overview import get_overview, get_summary, analyze_message_sizes, get_context_changes, get_token_breakdown, _extract_session_title
from .messages import filter_by_role, get_message, get_thinking_blocks, search_messages, get_messages, get_message_range
from .search import search_sessions_for_term

__all__ = [
    # Tools
    'extract_all_tool_results',
    'get_tool_calls',
    'get_all_tools',
    'calculate_tool_success_rate',
    'is_tool_error',
    'get_files_touched',
    'get_workflow',
    'get_session_agents',
    # Errors
    'get_errors',
    'get_error_context',
    # Timeline
    'get_timeline',
    # Overview
    'get_overview',
    'get_summary',
    'analyze_message_sizes',
    'get_context_changes',
    'get_token_breakdown',
    '_extract_session_title',
    # Messages
    'filter_by_role',
    'get_message',
    'get_thinking_blocks',
    'search_messages',
    'get_messages',
    'get_message_range',
    # Cross-session search
    'search_sessions_for_term',
]
