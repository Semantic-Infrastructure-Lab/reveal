"""Chronological tool+shell workflow for Codex sessions."""

from typing import Any, Dict, List

from .tools import get_tool_pairs, get_shell_commands


def get_workflow(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return tool calls and shell commands interleaved chronologically.

    Each entry has:
      - kind: 'tool_call' | 'shell'
      - timestamp
      - tool_call: name, call_id, arguments, output, success
      - shell: command, exit_code, duration_ms, aggregated_output, success
    """
    events: List[Dict[str, Any]] = []

    for pair in get_tool_pairs(records):
        call = pair.get('call', {})
        output = pair.get('output')
        events.append({
            'kind': 'tool_call',
            'timestamp': call.get('_timestamp'),
            'name': call.get('name', '?'),
            'call_id': call.get('call_id', ''),
            'arguments': call.get('arguments', ''),
            'output': output.get('output', '') if output else None,
            'success': output is not None,
        })

    for cmd in get_shell_commands(records):
        dur_obj = cmd.get('duration', {})
        secs = dur_obj.get('secs', 0) if isinstance(dur_obj, dict) else 0
        nanos = dur_obj.get('nanos', 0) if isinstance(dur_obj, dict) else 0
        events.append({
            'kind': 'shell',
            'timestamp': cmd.get('_timestamp'),
            'command': cmd.get('command', []),
            'exit_code': cmd.get('exit_code'),
            'duration_ms': secs * 1000 + nanos // 1_000_000,
            'aggregated_output': cmd.get('aggregated_output', ''),
            'success': cmd.get('exit_code') == 0,
        })

    events.sort(key=lambda e: (e['timestamp'] is None, e['timestamp'] or ''))
    return events
