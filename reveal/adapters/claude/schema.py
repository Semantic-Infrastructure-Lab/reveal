"""Schema constants for the claude:// adapter — query params, elements, output types, examples."""

_SCHEMA_QUERY_PARAMS = {
    'summary': {'type': 'flag', 'description': 'Session summary (overview + key events)'},
    'errors': {'type': 'flag', 'description': 'Filter for messages containing errors'},
    'tools': {'type': 'string', 'description': 'Filter for specific tool usage (comma-separated for multiple)', 'examples': ['?tools=Bash', '?tools=Edit', '?tools=Bash,Read']},
    'contains': {'type': 'string', 'description': 'Filter messages containing text', 'examples': ['?contains=reveal', '?contains=error']},
    'role': {'type': 'string', 'description': 'Filter by message role', 'values': ['user', 'assistant'], 'examples': ['?role=user']},
    'search': {
        'type': 'string',
        'description': 'Search all message content (text, thinking, tool inputs) for a term (case-insensitive). On claude://sessions/ performs cross-session search.',
        'examples': ['?search=path traversal', '?search=FileNotFoundError', '?search=validate_token']
    },
    'since': {
        'type': 'string',
        'description': 'Filter by date — ISO 8601 date string or "today". On sessions/: narrows corpus before scanning. On history: filters by prompt timestamp.',
        'examples': ['?since=2026-03-01', '?since=today']
    },
    'until': {
        'type': 'string',
        'description': 'Upper bound date filter — ISO 8601 date string. Pairs with ?since= for date range queries. Applies to session listings and cross-session search.',
        'examples': ['?since=2026-06-10&until=2026-06-12', '?until=2026-06-01']
    },
    'word': {
        'type': 'flag',
        'description': 'Whole-word match for ?search= (cross-session search only). Prevents substring matches.',
        'examples': ['?search=auth&word']
    },
    'snippet': {
        'type': 'integer',
        'description': 'Characters of context around search match (cross-session search only). Default 120, range 60–500.',
        'examples': ['?search=term&snippet=300', '?search=term&snippet=250']
    },
    'filter': {
        'type': 'string',
        'description': 'Filter session list by name substring (claude://sessions/ list mode). Alias of ?search= for list filtering.',
        'examples': ['?filter=auth-refactor']
    },
    'project': {
        'type': 'string',
        'description': 'Filter by project name (claude://history only). Scopes results to sessions in the specified project directory.',
        'examples': ['?project=my-project']
    },
    'key': {
        'type': 'string',
        'description': 'Dot-path key lookup for claude://settings and claude://config. Returns the value at that path.',
        'examples': ['?key=theme', '?key=env.ANTHROPIC_API_KEY']
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
    'patches': {
        'type': 'boolean',
        'description': 'Include file patch/diff content in the files-touched view (?patches=true)',
        'examples': ['?patches=true']
    },
    'digest': {
        'type': 'flag',
        'description': 'Composed readable view: overview + human prompts + assistant narrative in one call (path alias: /digest)',
        'examples': ['?digest']
    },
}

_SCHEMA_CLI_FLAGS = {
    '--all': {
        'description': 'Return all results (cross-session search: disable default 20-result cap)',
        'applies_to': ['claude://sessions/?search='],
    },
    '--base-path': {
        'description': 'Override the sessions base directory. Required when sessions live outside ~/.claude/projects/ (e.g. ~/src/tia/sessions/ for TIA).',
        'applies_to': ['claude://sessions/', 'claude://session/<name>'],
        'examples': ["reveal 'claude://sessions/?search=term' --base-path ~/src/tia/sessions"],
    },
}

_SCHEMA_ELEMENTS = {
    'workflow': 'Chronological sequence of tool operations',
    'files': 'All files read, written, or edited',
    'tools': 'All tool usage with success rates',
    'thinking': 'All thinking blocks with content previews and token estimates',
    'errors': 'All errors and exceptions (path alias for ?errors)',
    'timeline': 'Chronological message timeline (path alias for ?timeline)',
    'summary': 'Session summary with key events (path alias for ?summary)',
    'tokens': 'Token usage breakdown (path alias for ?tokens)',
    'context': 'Context window changes over session',
    'messages': 'All assistant narrative turns (text only, no tool calls) — best for reading what was said',
    'prompts': 'Human-typed prompts only — excludes tool-result wrapper turns. Prefer this over /user for reading intent.',
    'user': 'User messages: initial prompt full text + tool-result turn summaries. WARNING: the Claude API encodes tool-result turns as role: user too, so this mixes them in — prefer /prompts unless you specifically need tool-result turn boundaries. Response includes a `hint` field when tool-result-only turns are present.',
    'assistant': 'Assistant messages: text blocks only (skips thinking/tool_use)',
    'message/<n>': 'Single message by zero-based index over raw JSONL records (or negative: message/-1 = last message). NOTE: this is a different counting scheme than /message --range, which is 1-based over conversation turns — the response includes a `turn` field to cross-reference.',
    'digest': 'Composed readable view: overview + human prompts + assistant narrative in one call (path alias for ?digest) — removes the need for 3 separate calls to get a readable picture of a session.',
    'exchanges': 'Each real human prompt paired with the assistant\'s final text answer to it (skips thinking/tool-only turns in between) — for "what did I ask, what did it finally say back," one pair at a time. Distinct from /digest, which composes whole-session sections rather than joining prompt to answer.',
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
    _make_output_type('claude_user_messages', 'User messages: initial prompt + tool-result turn summaries. May include a `hint` field pointing at /prompts when tool-result-only turns are present.', {
        'messages': {'type': 'array'}, 'hint': {'type': 'string'}
    }),
    _make_output_type('claude_user_prompts', 'Human-typed prompts only — excludes tool-result wrapper messages (use /prompts)', {'messages': {'type': 'array'}}),
    _make_output_type('claude_assistant_messages', 'Assistant messages: text responses (thinking/tool blocks excluded)', {'messages': {'type': 'array'}}),
    _make_output_type('claude_thinking', 'All thinking blocks with content previews and token estimates', {
        'blocks': {'type': 'array'}, 'total_tokens': {'type': 'integer'}
    }),
    _make_output_type('claude_message', 'Single message by zero-based JSONL index with full content', {
        # Corrected to match get_message()'s actual returned keys (was declaring
        # index/role/content, which never matched the real output — BACK-513).
        'message_index': {'type': 'integer'},
        'message_type': {'type': 'string', 'enum': ['user', 'assistant']},
        'message': {'type': 'object'},
        'text': {'type': 'string'},
        'turn': {'type': 'integer', 'description': '1-based conversation turn number, for cross-referencing with /message --range (present only for user/assistant messages)'},
        'hint': {'type': 'string'},
    }),
    _make_output_type('claude_messages', 'Assistant narrative turns (text only, no tool calls) — used by /messages, ?tail=N, ?last', {'messages': {'type': 'array'}, 'total_turns': {'type': 'integer'}}),
    _make_output_type('claude_digest', 'Composed readable view: overview + human prompts + assistant narrative in one call (path alias /digest, or ?digest)', {
        'title': {'type': 'string'}, 'duration': {'type': 'string'},
        'message_count': {'type': 'integer'}, 'files_touched_count': {'type': 'integer'},
        'prompt_count': {'type': 'integer'}, 'prompts': {'type': 'array'},
        'narrative_turn_count': {'type': 'integer'}, 'assistant_narrative': {'type': 'array'},
    }),
    _make_output_type('claude_exchanges', 'Each real human prompt paired with the assistant\'s final text answer to it', {
        'exchange_count': {'type': 'integer'},
        'exchanges': {'type': 'array', 'description': 'Each entry: message_index, timestamp, prompt, answer_message_index, answer_timestamp, answer (null if no text answer was found before the next prompt)'},
    }),
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
    {'uri': 'claude://session/2627362f-6f72-45e1-b7bb-d5a61519a388', 'description': 'Session overview (messages, tools, duration) — session name is the UUID directory name, or a friendly name if using a session-naming layer', 'output_type': 'claude_overview'},
    {'uri': 'claude://session/infernal-earth-0118/workflow', 'description': 'Chronological sequence of tool operations', 'element': 'workflow', 'output_type': 'claude_workflow'},
    {'uri': 'claude://session/infernal-earth-0118/files', 'description': 'All files read, written, or edited', 'element': 'files', 'output_type': 'claude_files'},
    {'uri': 'claude://session/infernal-earth-0118/tools', 'description': 'All tool usage with success rates', 'element': 'tools', 'output_type': 'claude_tools'},
    {'uri': 'claude://session/infernal-earth-0118/errors', 'description': 'All errors and exceptions', 'element': 'errors', 'output_type': 'claude_errors'},
    {'uri': 'claude://session/infernal-earth-0118?tools=Bash', 'description': 'Filter for Bash tool usage', 'query_param': '?tools=Bash', 'output_type': 'claude_overview'},
    {'uri': 'claude://session/infernal-earth-0118?errors', 'description': 'Filter for error messages', 'query_param': '?errors', 'output_type': 'claude_overview'},
    {'uri': 'claude://session/infernal-earth-0118?summary', 'description': 'Session summary with key events', 'query_param': '?summary', 'output_type': 'claude_overview'},
    {'uri': 'claude://session/infernal-earth-0118/digest', 'description': 'Composed readable view: overview + human prompts + assistant narrative in one call — start here for "what happened in this session"', 'element': 'digest', 'output_type': 'claude_digest'},
    {'uri': 'claude://session/infernal-earth-0118/exchanges', 'description': 'Each human prompt paired with the assistant\'s final answer to it — use when you need "what was asked, what did it finally say" per turn, not a whole-session dump', 'element': 'exchanges', 'output_type': 'claude_exchanges'},
    {'uri': 'claude://session/infernal-earth-0118/messages', 'description': 'All assistant narrative turns (text only) — best resource for reading what was said', 'element': 'messages', 'output_type': 'claude_messages'},
    {'uri': 'claude://session/infernal-earth-0118/user', 'description': 'User messages: initial prompt + tool-result turn summaries — prefer /prompts for reading intent, this mixes in tool-result turns', 'element': 'user', 'output_type': 'claude_user_messages'},
    {'uri': 'claude://session/infernal-earth-0118/assistant', 'description': 'Assistant messages: text responses (thinking/tools hidden)', 'element': 'assistant', 'output_type': 'claude_assistant_messages'},
    {'uri': 'claude://session/infernal-earth-0118/thinking', 'description': 'All thinking blocks with content and token estimates', 'element': 'thinking', 'output_type': 'claude_thinking'},
    {'uri': 'claude://session/infernal-earth-0118/message/5', 'description': 'Read a specific message by zero-based JSONL index — response includes a `turn` field (1-based) for cross-referencing with /message --range', 'element': 'message/<n>', 'output_type': 'claude_message'},
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
    'Two message-indexing schemes coexist by design: /message/<n> is 0-based over raw JSONL records (Python-style negative indexing supported, e.g. -1 = last); /message --range is 1-based over conversation turns (matches reveal\'s system-wide --range/--head/--tail convention). /message/<n> responses include a `turn` field and /message --range responses include a `message_index` field so either number can be converted to the other without a second call.',
]
