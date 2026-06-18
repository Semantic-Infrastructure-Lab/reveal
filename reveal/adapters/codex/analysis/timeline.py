"""Full event timeline for Codex sessions."""

from typing import Any, Callable, Dict, List


def _cmd(payload: Dict[str, Any]) -> str:
    cmd = payload.get('command', [])
    if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1] == '-lc':
        return f"$ {cmd[2][:60]}"
    return '$ ' + ' '.join(str(c) for c in cmd[:3])


def _tok(payload: Dict[str, Any]) -> str:
    info = payload.get('info', {})
    total = (info.get('total_token_usage') or {}).get('total_tokens')
    return f"tokens total={total}" if total is not None else 'token_count'


def _msg80(payload: Dict[str, Any]) -> str:
    return (payload.get('message') or '')[:80]


def _response_msg(payload: Dict[str, Any]) -> str:
    content = payload.get('content') or ''
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get('type') == 'input_text':
                return str(block.get('text', ''))[:60]
        return f"[{len(content)} content block(s)]"
    return str(content)[:60]


_EVENT_MSG_HANDLERS: Dict[str, Callable[[Dict[str, Any]], str]] = {
    'user_message': _msg80,
    'agent_message': _msg80,
    'exec_command_end': _cmd,
    'token_count': _tok,
    'error': _msg80,
    'warning': _msg80,
    'task_complete': lambda p: f"task complete ({p.get('duration_ms', '?')}ms)",
    'task_started': lambda _: 'task started',
    'request_permissions': lambda _: 'request_permissions',
}

_RESPONSE_ITEM_HANDLERS: Dict[str, Callable[[Dict[str, Any]], str]] = {
    'function_call': lambda p: f"{p.get('name', '?')}({(p.get('arguments') or '')[:40]})",
    'function_call_output': lambda p: f"→ {str(p.get('output', ''))[:60]}",
    'reasoning': lambda _: 'reasoning (encrypted)',
    'message': _response_msg,
}


def _summarize(rtype: str, payload: Dict[str, Any]) -> str:
    ptype = payload.get('type', '')
    if rtype == 'event_msg':
        handler = _EVENT_MSG_HANDLERS.get(ptype)
        return handler(payload) if handler else ptype or rtype
    if rtype == 'response_item':
        handler = _RESPONSE_ITEM_HANDLERS.get(ptype)
        return handler(payload) if handler else ptype or rtype
    if rtype == 'session_meta':
        sid = (payload.get('session_id') or '')[:8]
        return f"session {sid} model={payload.get('model', '?')}"
    if rtype == 'turn_context':
        return f"cwd={payload.get('cwd', '?')}"
    if rtype == 'compacted':
        return 'compacted'
    return rtype


def get_timeline(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return all events in chronological order with brief summaries."""
    events: List[Dict[str, Any]] = []
    for i, rec in enumerate(records):
        ts = rec.get('timestamp')
        rtype = rec.get('type', 'unknown')
        payload = rec.get('payload', {})
        if not isinstance(payload, dict):
            payload = {}
        ptype = payload.get('type', '')
        events.append({
            'index': i,
            'timestamp': ts,
            'event_type': rtype,
            'payload_type': ptype,
            'summary': _summarize(rtype, payload),
        })
    events.sort(key=lambda e: (e['timestamp'] is None, e['timestamp'] or '', e['index']))
    return events
