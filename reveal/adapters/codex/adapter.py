"""OpenAI Codex CLI session adapter implementation."""

import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..base import ResourceAdapter, register_adapter, register_renderer
from .renderer import CodexRenderer
from ...utils.query import parse_query_params
from .handlers.sessions import (
    list_sessions as _h_list_sessions,
    search_sessions as _h_search_sessions,
    content_search_sessions as _h_content_search,
)
from .handlers.system import (
    get_info as _h_get_info,
    get_history as _h_get_history,
    get_config as _h_get_config,
    get_memories as _h_get_memories,
    get_rules as _h_get_rules,
    get_memories_pipeline as _h_get_memories_pipeline,
)
from .handlers.goals import get_goal as _h_get_goal
from .analysis.messages import extract_messages, get_last_agent_message, get_token_turns, get_grand_total_tokens
from .analysis.tools import get_tool_pairs, get_shell_commands
from .analysis.errors import get_errors as _analysis_get_errors
from .analysis.overview import get_overview as _analysis_get_overview
from .analysis.workflow import get_workflow as _analysis_get_workflow
from .analysis.timeline import get_timeline as _analysis_get_timeline

logger = logging.getLogger(__name__)

# UUID detection: full UUID or 7+ hex prefix
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    r'|^[0-9a-f]{7,}$'
)

_USER_FILTER = "(thread_source IS NULL OR thread_source = 'user') AND archived = 0"


def _resolve_codex_home() -> Path:
    return Path.home() / '.codex'


@register_adapter('codex')
@register_renderer(CodexRenderer)
class CodexAdapter(ResourceAdapter):
    """Adapter for OpenAI Codex CLI session analysis.

    Reads from ~/.codex/state_5.sqlite (session index) and
    ~/.codex/sessions/**/*.jsonl (per-session JSONL files).
    """

    # Base paths — override with env vars for testing / SSH
    CODEX_HOME: Path = (
        Path(os.environ['REVEAL_CODEX_HOME'])
        if os.environ.get('REVEAL_CODEX_HOME')
        else _resolve_codex_home()
    )
    CODEX_DB: Path = (
        Path(os.environ['REVEAL_CODEX_DB'])
        if os.environ.get('REVEAL_CODEX_DB')
        else CODEX_HOME / 'state_5.sqlite'
    )

    def __init__(self, resource: str, query: Optional[str] = None):
        if resource is None or not isinstance(resource, str):
            raise TypeError(f'resource must be a string, got {type(resource).__name__}')
        self.resource = resource
        self.query = query
        self.query_params = parse_query_params(query or '')

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_contract_base(self) -> Dict[str, Any]:
        return {
            'contract_version': '1.0',
            'type': '',
            'source': str(self.CODEX_DB),
            'source_type': 'sqlite',
        }

    def _is_uuid(self, s: str) -> bool:
        """Return True if s looks like a Codex session UUID (or prefix)."""
        return bool(_UUID_RE.match(s))

    def _session_id_from_resource(self) -> Optional[str]:
        """Extract UUID prefix from resource (before any '/')."""
        parts = self.resource.split('/', 1)
        candidate = parts[0]
        if self._is_uuid(candidate):
            return candidate
        return None

    def _session_sub_path(self) -> str:
        """Return the sub-path after UUID/, e.g. 'messages', 'tools', ''."""
        parts = self.resource.split('/', 1)
        return parts[1] if len(parts) > 1 else ''

    # ------------------------------------------------------------------
    # SQLite helpers
    # ------------------------------------------------------------------

    def _find_session_row(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Look up a session row by full or prefix UUID."""
        if not self.CODEX_DB.exists():
            return None
        try:
            conn = sqlite3.connect(str(self.CODEX_DB))
            conn.row_factory = sqlite3.Row
            try:
                # Try exact match first
                row = conn.execute(
                    f'SELECT * FROM threads WHERE id = ? AND {_USER_FILTER}',
                    (session_id,)
                ).fetchone()
                if row is None and len(session_id) < 36:
                    # Prefix match
                    row = conn.execute(
                        f'SELECT * FROM threads WHERE id LIKE ? AND {_USER_FILTER} LIMIT 1',
                        (session_id + '%',)
                    ).fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        except sqlite3.Error:
            return None

    # ------------------------------------------------------------------
    # JSONL loading
    # ------------------------------------------------------------------

    def _load_records(self, jsonl_path: Path) -> List[Dict[str, Any]]:
        """Read a JSONL file, parse envelope, skip malformed lines.

        Each returned dict: {timestamp, type, payload}
        Legacy bare-JSON lines (no envelope) are treated as unknown.
        """
        records: List[Dict[str, Any]] = []
        try:
            with open(jsonl_path, 'r', encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    # Envelope format: must have 'type' at top level
                    if 'type' in obj:
                        records.append({
                            'timestamp': obj.get('timestamp'),
                            'type': obj.get('type'),
                            'payload': obj.get('payload', {}),
                        })
                    else:
                        # Legacy bare-JSON — keep as unknown
                        records.append({'timestamp': None, 'type': 'unknown', 'payload': obj})
        except OSError:
            pass
        return records

    def _find_jsonl_for_session(self, session_row: Dict[str, Any]) -> Optional[Path]:
        """Resolve the JSONL file path from the session row's rollout_path."""
        rollout_path = session_row.get('rollout_path')
        if rollout_path:
            p = Path(rollout_path)
            if p.exists():
                return p
        return None

    # ------------------------------------------------------------------
    # Resource routing
    # ------------------------------------------------------------------

    def _is_session_list_resource(self) -> bool:
        return (
            not self.resource
            or self.resource in ('.', '', 'sessions', 'sessions/')
            or self.resource.startswith('sessions/')
        )

    _NAMED_RESOURCES = {
        'info': '_get_info',
        'history': '_get_history',
        'config': '_get_config',
        'memories': '_get_memories',
        'rules': '_get_rules',
    }

    # memories/pipeline is a sub-path of memories — routed before generic memories
    _MEMORIES_PIPELINE = 'memories/pipeline'

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Route codex:// resource to the appropriate handler."""
        # Bare or sessions/ → list, search, or content search
        if self._is_session_list_resource():
            content = self.query_params.get('content')
            if content:
                return _h_content_search(self.CODEX_DB, content)
            search = self.query_params.get('search')
            if search:
                return _h_search_sessions(self.CODEX_DB, search)
            return _h_list_sessions(self.CODEX_DB)

        # memories/pipeline — check before generic memories
        if self.resource == self._MEMORIES_PIPELINE:
            return self._get_memories_pipeline()

        # Named resources: info, history, config, memories, rules
        for prefix, method_name in self._NAMED_RESOURCES.items():
            if self.resource == prefix or self.resource.startswith(prefix + '/'):
                handler: Callable[[], Dict[str, Any]] = getattr(self, method_name)
                return handler()

        # UUID → session analysis
        session_id = self._session_id_from_resource()
        if session_id:
            return self._handle_session(session_id)

        # Unknown resource
        base = self._get_contract_base()
        base['type'] = 'codex_error'
        base['error'] = f'Unknown codex:// resource: {self.resource!r}'
        return base

    def _handle_session(self, session_id: str) -> Dict[str, Any]:
        """Handle codex://<UUID>[/sub] requests."""
        if not self.CODEX_DB.exists():
            base = self._get_contract_base()
            base['type'] = 'codex_not_installed'
            base['error'] = f'Codex DB not found: {self.CODEX_DB}'
            return base

        session_row = self._find_session_row(session_id)
        if session_row is None:
            base = self._get_contract_base()
            base['type'] = 'codex_error'
            base['error'] = f'Session not found: {session_id}'
            return base

        jsonl_path = self._find_jsonl_for_session(session_row)
        records: List[Dict[str, Any]] = []
        if jsonl_path:
            records = self._load_records(jsonl_path)

        sub = self._session_sub_path()

        # ?last / ?tokens / ?goal → query-param routes
        if 'last' in self.query_params or self.query_params.get('last') is not None:
            return self._result_last(records, session_row)
        if 'tokens' in self.query_params or self.query_params.get('tokens') is not None:
            return self._result_tokens(records, session_row)
        if 'goal' in self.query_params or self.query_params.get('goal') is not None:
            return self._result_goal(session_row)

        if sub == 'messages':
            return self._result_messages(records, session_row)
        if sub == 'tools':
            return self._result_tools(records, session_row)
        if sub == 'errors':
            return self._result_errors(records, session_row)
        if sub == 'shell':
            return self._result_shell(records, session_row)
        if sub == 'workflow':
            return self._result_workflow(records, session_row)
        if sub == 'timeline':
            return self._result_timeline(records, session_row)

        # Default: overview
        return self._result_overview(records, session_row)

    # ------------------------------------------------------------------
    # Session sub-results
    # ------------------------------------------------------------------

    def _base(self, result_type: str, session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._get_contract_base()
        b['type'] = result_type
        b['session_id'] = session_row.get('id', '')
        return b

    def _result_overview(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_session_overview', session_row)
        metrics = _analysis_get_overview(records, session_row)
        b.update(metrics)
        return b

    def _result_last(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_messages', session_row)
        last_rec = get_last_agent_message(records)
        if last_rec:
            payload = last_rec.get('payload', {})
            b['messages'] = [{
                'timestamp': last_rec.get('timestamp'),
                'role': 'agent',
                'message': payload.get('message', ''),
                'phase': payload.get('phase'),
            }]
        else:
            b['messages'] = []
        b['total_turns'] = len(b['messages'])
        return b

    def _result_messages(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_messages', session_row)
        turns = extract_messages(records)
        b['messages'] = turns
        b['total_turns'] = len(turns)
        return b

    def _result_tools(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_tools', session_row)
        pairs = get_tool_pairs(records)
        b['tools'] = pairs
        b['total'] = len(pairs)
        return b

    def _result_errors(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_errors', session_row)
        errors = _analysis_get_errors(records)
        b['errors'] = errors
        b['total'] = len(errors)
        return b

    def _result_shell(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_shell', session_row)
        commands = get_shell_commands(records)
        b['shell_calls'] = commands
        b['total'] = len(commands)
        return b

    def _result_tokens(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_tokens', session_row)
        turns = get_token_turns(records)
        b['token_turns'] = turns
        b['total_turns'] = len(turns)
        b['grand_total'] = get_grand_total_tokens(records)
        return b

    def _result_workflow(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_workflow', session_row)
        events = _analysis_get_workflow(records)
        b['events'] = events
        b['total'] = len(events)
        return b

    def _result_timeline(self, records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
        b = self._base('codex_timeline', session_row)
        events = _analysis_get_timeline(records)
        b['events'] = events
        b['total'] = len(events)
        return b

    def _result_goal(self, session_row: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = session_row.get('id', '')
        result = _h_get_goal(self.CODEX_HOME, thread_id)
        # Merge session_id into result for contract consistency
        result['session_id'] = thread_id
        return result

    # ------------------------------------------------------------------
    # Named resource handlers
    # ------------------------------------------------------------------

    def _get_info(self) -> Dict[str, Any]:
        return _h_get_info(self.CODEX_HOME, self.CODEX_DB)

    def _get_history(self) -> Dict[str, Any]:
        return _h_get_history(self.CODEX_HOME, self.query_params)

    def _get_config(self) -> Dict[str, Any]:
        return _h_get_config(self.CODEX_HOME)

    def _get_memories(self) -> Dict[str, Any]:
        return _h_get_memories(self.CODEX_HOME)

    def _get_rules(self) -> Dict[str, Any]:
        return _h_get_rules(self.CODEX_HOME)

    def _get_memories_pipeline(self) -> Dict[str, Any]:
        return _h_get_memories_pipeline(self.CODEX_DB)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'codex',
            'description': 'OpenAI Codex CLI session analysis',
            'uri_syntax': 'codex://[sessions[/?search=term|?content=term] | <UUID>[/messages|tools|errors|shell|workflow|timeline][?last|?tokens|?goal] | info | history | config | memories[/pipeline] | rules]',
            'output_types': [
                'codex_session_list', 'codex_session_overview', 'codex_content_search',
                'codex_info', 'codex_history', 'codex_config', 'codex_memories',
                'codex_memories_pipeline', 'codex_rules',
                'codex_messages', 'codex_tools', 'codex_errors', 'codex_shell',
                'codex_tokens', 'codex_workflow', 'codex_timeline', 'codex_goal',
            ],
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'codex',
            'description': 'Navigate and analyze OpenAI Codex CLI sessions — SQLite-backed session index + per-session JSONL analysis',
            'syntax': (
                'codex://                                           # list all sessions\n'
                'codex://sessions/?search=<term>                   # metadata search (SQLite)\n'
                'codex://sessions/?content=<term>                  # JSONL content search\n'
                'codex://<UUID>                                     # session overview\n'
                'codex://<UUID>?last                                # last agent message\n'
                'codex://<UUID>?tokens                              # per-turn token breakdown\n'
                'codex://<UUID>?goal                                # thread goal (goals_1.sqlite)\n'
                'codex://<UUID>/messages                            # user + agent turns\n'
                'codex://<UUID>/tools                               # function_call pairs + success rates\n'
                'codex://<UUID>/shell                               # shell commands + exit codes\n'
                'codex://<UUID>/errors                              # error/warning events\n'
                'codex://<UUID>/workflow                            # tools + shell interleaved chronologically\n'
                'codex://<UUID>/timeline                            # all events in order\n'
                'codex://info                                       # install paths + DB stats\n'
                'codex://history                                    # ~/.codex/history.jsonl\n'
                'codex://config                                     # ~/.codex/config.toml (secrets masked)\n'
                'codex://memories                                   # ~/.codex/memories/\n'
                'codex://memories/pipeline                          # Stage1/Stage2 memory pipeline status\n'
                'codex://rules                                      # ~/.codex/rules/*.rules'
            ),
            'examples': [
                {'uri': 'codex://', 'description': 'List all sessions (newest first)'},
                {'uri': 'codex://sessions/?search=auth-refactor', 'description': 'Find sessions mentioning auth-refactor (SQLite metadata)'},
                {'uri': 'codex://sessions/?content=authentication', 'description': 'Full-text search across all session JSONL files'},
                {'uri': 'codex://019e5cc5', 'description': 'Session overview: turns, tool calls, tokens, duration'},
                {'uri': 'codex://019e5cc5?last', 'description': 'Last agent message only — fast recovery pattern'},
                {'uri': 'codex://019e5cc5?tokens', 'description': 'Per-turn token breakdown (input/output/cached/reasoning)'},
                {'uri': 'codex://019e5cc5?goal', 'description': 'Thread goal objective + token budget (goals_1.sqlite)'},
                {'uri': 'codex://019e5cc5/messages', 'description': 'All user and agent turns in order'},
                {'uri': 'codex://019e5cc5/tools', 'description': 'Paired function_call + output events'},
                {'uri': 'codex://019e5cc5/shell', 'description': 'Shell commands with exit codes and output'},
                {'uri': 'codex://019e5cc5/errors', 'description': 'Errors and warnings from the session'},
                {'uri': 'codex://019e5cc5/workflow', 'description': 'Tools + shell interleaved chronologically'},
                {'uri': 'codex://019e5cc5/timeline', 'description': 'Full chronological event stream'},
                {'uri': 'codex://info', 'description': 'Install paths and DB stats'},
                {'uri': 'codex://history', 'description': 'Prompt history from ~/.codex/history.jsonl'},
                {'uri': 'codex://config', 'description': 'Config TOML (secrets masked)'},
                {'uri': 'codex://memories/pipeline', 'description': 'Stage1/Stage2 memory pipeline status'},
            ],
            'features': [
                'SQLite-backed session listing (fast, no JSONL scan needed for list/search)',
                'UUID prefix lookup — type first 7+ hex chars instead of full UUID',
                'Per-turn token breakdown with input/output/reasoning/cached split',
                'Full-text JSONL content search across all sessions',
                'Shell command tracking with exit codes, output, and duration',
                'Tool call pairing (function_call + function_call_output)',
                'Chronological workflow view — tools + shell interleaved by timestamp',
                'Full timeline — all event types in session order',
                'Thread goal tracking (goals_1.sqlite) — objective + token budget',
                'Memory pipeline status — Stage1/Stage2 consolidation from stage1_outputs',
                'Reasoning block count (content encrypted — only count shown)',
                'Memory citations in agent_message turns',
                'Config TOML with secret masking',
            ],
            'notes': [
                'Sessions stored in ~/.codex/sessions/ as per-session JSONL files',
                'SQLite index at ~/.codex/state_5.sqlite — most queries start here',
                'UUID prefix: 7+ hex chars uniquely identify a session',
                'Subagent sessions filtered out — only user-visible threads shown',
                'Override paths: REVEAL_CODEX_HOME, REVEAL_CODEX_DB env vars',
                'token_count events give per-request token deltas from the API',
            ],
            'output_formats': ['text', 'json'],
            'see_also': [
                'reveal claude:// - Claude Code session analysis (sister adapter)',
                'reveal help://adapters - All available adapters',
            ],
        }
