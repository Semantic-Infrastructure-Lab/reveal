"""Full event timeline for Codex sessions."""

from typing import Any, Dict, List


def _summarize(rtype: str, payload: Dict[str, Any]) -> str:
    ptype = payload.get('type', '')
    if rtype == 'event_msg':
        if ptype == 'user_message':
            return (payload.get('message') or '')[:80]
        if ptype == 'agent_message':
            return (payload.get('message') or '')[:80]
        if ptype == 'exec_command_end':
            cmd = payload.get('command', [])
            if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1] == '-lc':
                return f"$ {cmd[2][:60]}"
            return '$ ' + ' '.join(str(c) for c in cmd[:3])
        if ptype == 'token_count':
            info = payload.get('info', {})
            total = (info.get('total_token_usage') or {}).get('total_tokens')
            return f"tokens total={total}" if total is not None else 'token_count'
        if ptype in ('error', 'warning'):
            return (payload.get('message') or '')[:80]
        if ptype == 'task_complete':
            return f"task complete ({payload.get('duration_ms', '?')}ms)"
        if ptype == 'task_started':
            return 'task started'
        if ptype == 'request_permissions':
            return 'request_permissions'
        return ptype or rtype
    if rtype == 'response_item':
        if ptype == 'function_call':
            return f"{payload.get('name', '?')}({(payload.get('arguments') or '')[:40]})"
        if ptype == 'function_call_output':
            return f"→ {str(payload.get('output', ''))[:60]}"
        if ptype == 'reasoning':
            return 'reasoning (encrypted)'
        if ptype == 'message':
            content = payload.get('content') or ''
            if isinstance(content, list):
                # List of content blocks — extract text from first block
                for block in content:
                    if isinstance(block, dict) and block.get('type') == 'input_text':
                        return block.get('text', '')[:60]
                return f"[{len(content)} content block(s)]"
            return str(content)[:60]
        return ptype or rtype
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
