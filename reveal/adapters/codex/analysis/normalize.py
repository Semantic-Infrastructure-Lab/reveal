"""One reading of Codex rollout records across its two event shapes (BACK-1566).

Codex CLI before 2026-08-09 wrote a turn as ``event_msg`` / ``user_message`` /
``agent_message`` / ``exec_command_end``. Later versions write one
``event_msg`` / ``item_completed`` per item, its kind in ``payload.item.type``
(``UserMessage``, ``AgentMessage``, ``CommandExecution``, ...), with text in
``content`` blocks. Every reader here keys on the old names, so every current
session read as 0 turns and 0 shell calls while its token count still parsed.

:func:`normalize_record` maps the new shape onto the old one, once, where records
are read; the item itself stays under ``payload['item']``. No rollout mixes the
two shapes (measured over 135 files), so nothing is counted twice. Tool calls
written as ``custom_tool_call`` (both eras) read as ``function_call``, which the
tool readers already pair by ``call_id``; the original kind stays under
``payload['original_type']``.
"""

import json
from typing import Any, Dict, List


def text_of(content: Any) -> str:
    """The text of a list of content blocks ('text' / 'Text' / 'input_text' ...)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ''
    parts: List[str] = []
    for block in content:
        if isinstance(block, dict) and isinstance(block.get('text'), str):
            parts.append(block['text'])
    return '\n'.join(parts)


def _from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """The legacy event_msg payload for one item_completed item, or {} for none."""
    kind = item.get('type')
    if kind == 'UserMessage':
        return {'type': 'user_message', 'message': text_of(item.get('content')), 'item': item}
    if kind == 'AgentMessage':
        return {'type': 'agent_message', 'message': text_of(item.get('content')),
                'phase': item.get('phase'), 'item': item}
    if kind == 'CommandExecution':
        # Same fields as exec_command_end, keyed by the item id instead of call_id.
        payload = {k: v for k, v in item.items() if k not in ('type', 'id')}
        return {**payload, 'type': 'exec_command_end', 'call_id': item.get('id'), 'item': item}
    return {}


def normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """*record* ({timestamp, type, payload}) in the legacy shape the readers know."""
    payload = record.get('payload')
    if not isinstance(payload, dict):
        return record
    rtype, ptype = record.get('type'), payload.get('type')
    if rtype == 'event_msg' and ptype == 'item_completed' and isinstance(payload.get('item'), dict):
        legacy = _from_item(payload['item'])
        return {**record, 'payload': legacy} if legacy else record
    if rtype == 'response_item' and ptype == 'custom_tool_call':
        return {**record, 'payload': {**payload, 'type': 'function_call',
                                      'arguments': payload.get('input', ''),
                                      'original_type': ptype}}
    if rtype == 'response_item' and ptype == 'web_search_call':
        # A tool call too (113 across 15 sessions); without this /tools, /workflow and the
        # overview's tool count left every web search out. No call_id and no output record:
        # the action carries the query and the payload its status.
        action = payload.get('action') if isinstance(payload.get('action'), dict) else {}
        return {**record, 'payload': {**payload, 'type': 'function_call', 'name': 'web_search',
                                      'arguments': json.dumps(action),
                                      'call_id': payload.get('id') or f"web_search@{record.get('timestamp')}",
                                      'original_type': ptype}}
    if rtype == 'response_item' and ptype == 'tool_search_call':
        return {**record, 'payload': {**payload, 'type': 'function_call', 'name': 'tool_search',
                                      'arguments': json.dumps(payload.get('arguments') or {}),
                                      'original_type': ptype}}
    if rtype == 'response_item' and ptype == 'tool_search_output':
        return {**record, 'payload': {**payload, 'type': 'function_call_output',
                                      'output': json.dumps(payload.get('tools') or []),
                                      'original_type': ptype}}
    if rtype == 'response_item' and ptype == 'custom_tool_call_output':
        return {**record, 'payload': {**payload, 'type': 'function_call_output',
                                      'output': text_of(payload.get('output')) or payload.get('output'),
                                      'original_type': ptype}}
    return record


def mark_rolled_back(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flag the records of turns a ``thread_rolled_back`` event undid (``_rolled_back``).

    Codex leaves an undone turn in the rollout and appends ``thread_rolled_back
    {num_turns: N}``; the last N turns (each opened by ``task_started``) before it are no
    longer part of the conversation. Readers kept them as live prompts and answers (4 of 5
    measured rollbacks undid a real prompt the session then continued past).
    """
    for i, rec in enumerate(records):
        payload = rec.get('payload')
        if rec.get('type') != 'event_msg' or not isinstance(payload, dict) \
                or payload.get('type') != 'thread_rolled_back':
            continue
        remaining = int(payload.get('num_turns') or 1)
        start = i
        for j in range(i - 1, -1, -1):
            p = records[j].get('payload')
            if isinstance(p, dict) and p.get('type') == 'task_started':
                start = j
                remaining -= 1
                if remaining == 0:
                    break
        for j in range(start, i):
            records[j]['_rolled_back'] = True
    return records

