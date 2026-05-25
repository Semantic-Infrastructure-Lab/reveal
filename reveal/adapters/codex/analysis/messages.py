"""User/agent turn extraction for Codex sessions."""

from typing import Any, Dict, List, Optional


def _payload_type(rec: Dict[str, Any]) -> str:
    """Return the payload subtype of a record, or '' if unavailable."""
    return rec.get('payload', {}).get('type', '')


def extract_messages(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract user and agent message turns from JSONL records.

    Returns a list of dicts with keys:
      timestamp, role ('user'|'agent'), message, phase (agent only)
    """
    turns: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get('type') != 'event_msg':
            continue
        ptype = _payload_type(rec)
        payload = rec.get('payload', {})
        if ptype == 'user_message':
            turns.append({
                'timestamp': rec.get('timestamp'),
                'role': 'user',
                'message': payload.get('message', ''),
            })
        elif ptype == 'agent_message':
            turns.append({
                'timestamp': rec.get('timestamp'),
                'role': 'agent',
                'message': payload.get('message', ''),
                'phase': payload.get('phase'),
            })
    return turns


def _parse_token_usage(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract per-request token counts from a token_count payload.

    Handles both the real Codex format (payload.info.last_token_usage) and the
    simplified flat format used in tests (payload.input_tokens etc.).
    """
    info = payload.get('info', {})
    last = info.get('last_token_usage')
    if last:
        return last
    # flat/legacy format
    return {k: payload.get(k) for k in (
        'input_tokens', 'cached_input_tokens', 'output_tokens',
        'reasoning_output_tokens', 'total_tokens',
    ) if k in payload}


def get_token_turns(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return per-turn token usage from token_count events.

    Each entry: timestamp, turn (1-based index), input_tokens, cached_input_tokens,
    output_tokens, reasoning_output_tokens, total_tokens.
    """
    turns: List[Dict[str, Any]] = []
    n = 0
    for rec in records:
        if rec.get('type') != 'event_msg':
            continue
        if _payload_type(rec) != 'token_count':
            continue
        n += 1
        usage = _parse_token_usage(rec.get('payload', {}))
        turns.append({'turn': n, 'timestamp': rec.get('timestamp'), **usage})
    return turns


def get_last_agent_message(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the last agent_message record, or None if none found."""
    last = None
    for rec in records:
        if rec.get('type') == 'event_msg' and _payload_type(rec) == 'agent_message':
            last = rec
    return last
