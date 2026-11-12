"""Shared Claude session identifier parsing and canonical view names."""
import re

from ...utils.query_parser import peek_query_items

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

SESSION_VIEW_NAMES = ('overview', 'messages', 'prompts', 'thinking', 'tools', 'files',
                      'workflow', 'agents', 'context', 'timeline', 'errors', 'tokens',
                      'digest', 'exchanges', 'message', 'search', 'chain')


SESSION_VIEWS = frozenset(('', 'messages', 'prompts', 'thinking', 'tools', 'files', 'workflow',
                           'agents', 'context', 'timeline', 'errors', 'summary', 'tokens',
                           'digest', 'exchanges', 'message'))
QUERY_VIEWS = (('summary', 'claude_analytics'), ('digest', 'claude_digest'),
               ('timeline', 'claude_timeline'), ('errors', 'claude_errors'),
               ('tokens', 'claude_token_breakdown'), ('tools', 'claude_tool_calls'),
               ('search', 'claude_search_results'), ('tail', 'claude_messages'), ('last', 'claude_messages'))
RESOURCE_VIEWS = (('thinking', 'claude_thinking'), ('tools', 'claude_tool_summary'),
                  ('files', 'claude_files'), ('workflow', 'claude_workflow'),
                  ('agents', 'claude_session_agents'), ('context', 'claude_context'),
                  ('prompts', 'claude_user_prompts'), ('exchanges', 'claude_exchanges'),
                  ('errors', 'claude_errors'), ('summary', 'claude_analytics'),
                  ('digest', 'claude_digest'), ('timeline', 'claude_timeline'),
                  ('tokens', 'claude_token_breakdown'), ('messages', 'claude_messages'))


def _active(params):
    return {key for key, value in peek_query_items(params) if value is not None and value is not False}


def selected_type(resource, params):
    active = _active(params)
    if len(active.intersection(('tools', 'errors', 'contains'))) > 1:
        return 'claude_filtered_results'
    for key, kind in QUERY_VIEWS:
        if key in active:
            return kind
    for segment, kind in RESOURCE_VIEWS:
        if '/' + segment in resource:
            if 'raw' in active and segment in ('prompts', 'messages'):
                return 'claude_user_messages' if segment == 'prompts' else 'claude_assistant_messages'
            return kind
    if '/message/' in resource:
        return 'claude_message'
    if resource.endswith('/message'):
        return 'claude_message_range'
    return 'claude_session_overview'


NON_SESSION_NAMESPACES = ('files', 'history', 'info', 'settings', 'plans', 'config', 'memory',
                          'agents', 'hooks', 'sessions', 'search')
