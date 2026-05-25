"""Session overview/metrics generation for Codex sessions."""

from typing import Any, Dict, List, Optional


def _payload_type(rec: Dict[str, Any]) -> str:
    return str(rec.get('payload', {}).get('type', ''))


def get_overview(records: List[Dict[str, Any]], session_row: Dict[str, Any]) -> Dict[str, Any]:
    """Compute overview metrics from JSONL records + SQLite session_row.

    Returns a dict with:
      title, model, model_provider, reasoning_effort,
      user_turns, agent_turns, tool_calls, shell_calls,
      total_tokens, duration_ms, first_timestamp, last_timestamp,
      reasoning_blocks (count only — content is opaque)
    """
    user_turns = 0
    agent_turns = 0
    tool_calls = 0
    shell_begins = 0
    total_tokens: Optional[int] = None
    duration_ms: Optional[int] = None
    reasoning_blocks = 0
    first_ts: Optional[str] = None
    last_ts: Optional[str] = None

    for rec in records:
        ts = rec.get('timestamp')
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts

        rtype = rec.get('type', '')
        payload = rec.get('payload', {})
        ptype = payload.get('type', '')

        if rtype == 'event_msg':
            if ptype == 'user_message':
                user_turns += 1
            elif ptype == 'agent_message':
                agent_turns += 1
            elif ptype == 'exec_command_end':
                shell_begins += 1
            elif ptype == 'task_complete':
                dm = payload.get('duration_ms')
                if dm is not None:
                    duration_ms = dm
            elif ptype == 'token_count':
                # real format: payload.info.total_token_usage.total_tokens
                info = payload.get('info', {})
                tu = info.get('total_token_usage', {})
                tt = tu.get('total_tokens') or payload.get('total_tokens')
                if tt is not None:
                    total_tokens = tt
        elif rtype == 'response_item':
            if ptype == 'function_call':
                tool_calls += 1
            elif ptype == 'reasoning':
                reasoning_blocks += 1

    return {
        'title': session_row.get('title', ''),
        'model': session_row.get('model'),
        'model_provider': session_row.get('model_provider'),
        'reasoning_effort': session_row.get('reasoning_effort'),
        'tokens_used': session_row.get('tokens_used') if session_row.get('tokens_used') is not None else total_tokens,
        'cwd': session_row.get('cwd'),
        'approval_mode': session_row.get('approval_mode'),
        'cli_version': session_row.get('cli_version'),
        'git_branch': session_row.get('git_branch'),
        'user_turns': user_turns,
        'agent_turns': agent_turns,
        'tool_calls': tool_calls,
        'shell_calls': shell_begins,
        'reasoning_blocks': reasoning_blocks,
        'duration_ms': duration_ms,
        'first_timestamp': first_ts,
        'last_timestamp': last_ts,
    }
