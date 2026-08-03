"""User/agent turn extraction for Codex sessions."""

from typing import Any, Dict, List, Optional


def _payload_type(rec: Dict[str, Any]) -> str:
    """Return the payload subtype of a record, or '' if unavailable."""
    return str(rec.get('payload', {}).get('type', ''))


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
    last: Dict[str, Any] = info.get('last_token_usage') or {}
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


def get_grand_total_tokens(records: List[Dict[str, Any]]) -> Optional[int]:
    """Return the session's cumulative token total from the last token_count event.

    Uses payload.info.total_token_usage.total_tokens (cumulative), not the
    per-request last_token_usage delta used by get_token_turns().
    """
    last_total: Optional[int] = None
    for rec in records:
        if rec.get('type') != 'event_msg':
            continue
        if _payload_type(rec) != 'token_count':
            continue
        payload = rec.get('payload', {})
        info = payload.get('info', {})
        tu = info.get('total_token_usage', {})
        tt = tu.get('total_tokens') or payload.get('total_tokens')
        if tt is not None:
            last_total = tt
    return last_total


def get_last_agent_message(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the last agent_message record, or None if none found."""
    last = None
    for rec in records:
        if rec.get('type') == 'event_msg' and _payload_type(rec) == 'agent_message':
            last = rec
    return last


def get_exchanges(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pair each user prompt with the agent's final reply to it (BACK-943).

    Unlike claude:// (role=user records mixed with tool-result wrapper turns,
    requiring a parentUuid-chain walk to find the "real" answer), codex's
    event_msg/user_message and event_msg/agent_message are already narrative-
    only and strictly chronological — so pairing is a straight linear walk:
    each user turn pairs with the LAST agent turn before the following user
    turn (matching claude://'s "final answer, not first" semantics — an agent
    often narrates an initial "I'll start by..." before its real conclusion),
    or None if the session ends without any agent reply.
    """
    turns = extract_messages(records)
    exchanges: List[Dict[str, Any]] = []
    pending: Optional[Dict[str, Any]] = None
    for turn in turns:
        if turn['role'] == 'user':
            if pending is not None:
                exchanges.append(pending)
            pending = {
                'prompt': turn['message'],
                'prompt_timestamp': turn['timestamp'],
                'answer': None,
                'answer_timestamp': None,
            }
        elif turn['role'] == 'agent' and pending is not None:
            pending['answer'] = turn['message']
            pending['answer_timestamp'] = turn['timestamp']
    if pending is not None:
        exchanges.append(pending)
    return exchanges


def get_message_by_index(records: List[Dict[str, Any]], index: int) -> Optional[Dict[str, Any]]:
    """Return the raw JSONL record at `index` (0-based, Python-style negative

    indexing supported — e.g. -1 = last record). Indexes the full raw record
    stream, not just user/agent turns, matching claude://'s /message/<n>
    convention (bulk/forensic access, not narrative reading).
    """
    if not records:
        return None
    try:
        rec = records[index]
    except IndexError:
        return None
    resolved_index = index if index >= 0 else len(records) + index
    payload = rec.get('payload', {})
    return {
        'record_index': resolved_index,
        'record_type': rec.get('type', ''),
        'payload_type': payload.get('type', ''),
        'timestamp': rec.get('timestamp'),
        'record': rec,
    }
