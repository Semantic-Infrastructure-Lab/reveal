"""Tool call and shell execution pairing for Codex sessions."""

from typing import Any, Dict, List

from ...agent_base import pair_tool_calls


def _flatten_response_item_payloads(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract payload dicts from response_item records, annotating with timestamp."""
    flat: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get('type') != 'response_item':
            continue
        payload = rec.get('payload', {})
        if not isinstance(payload, dict):
            continue
        entry = dict(payload)
        entry['_timestamp'] = rec.get('timestamp')
        flat.append(entry)
    return flat


def _flatten_event_msg_payloads(records: List[Dict[str, Any]], *ptypes: str) -> List[Dict[str, Any]]:
    """Extract payload dicts from event_msg records matching given payload types."""
    flat: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get('type') != 'event_msg':
            continue
        payload = rec.get('payload', {})
        if not isinstance(payload, dict):
            continue
        if payload.get('type') in ptypes:
            entry = dict(payload)
            entry['_timestamp'] = rec.get('timestamp')
            flat.append(entry)
    return flat


def get_tool_pairs(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return paired function_call + function_call_output records.

    Each pair: {'call': payload_dict, 'output': payload_dict_or_None}
    """
    items = _flatten_response_item_payloads(records)
    return pair_tool_calls(items, 'function_call', 'function_call_output', 'call_id')


def get_shell_commands(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return exec_command_end records from event_msg records.

    Codex emits exec_command_end with full command info (command list, exit_code,
    aggregated_output, duration, call_id). No separate begin event is needed.
    """
    return _flatten_event_msg_payloads(records, 'exec_command_end')
