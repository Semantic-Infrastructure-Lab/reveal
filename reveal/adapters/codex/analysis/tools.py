"""Tool call and shell execution pairing for Codex sessions."""

import json
import re
from typing import Any, Dict, List, Optional

from ...agent_base import pair_tool_calls
from .normalize import text_of


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
    pairs = pair_tool_calls(items, 'function_call', 'function_call_output', 'call_id')
    for pair in pairs:
        call = pair.get('call') or {}
        # A web search records no output event; its status is the outcome.
        if pair.get('output') is None and call.get('original_type') == 'web_search_call' and call.get('status'):
            pair['output'] = {'type': 'function_call_output', 'call_id': call.get('call_id'),
                              'output': f"status: {call['status']}"}
    return pairs


_EXITED = re.compile(r'^Process exited with code (-?\d+)', re.M)
_RUNNING = re.compile(r'^Process running with session ID (\d+)', re.M)
_WALL = re.compile(r'^Wall time: ([\d.]+) seconds', re.M)


def _args(call: Dict[str, Any]) -> Dict[str, Any]:
    try:
        parsed = json.loads(call.get('arguments') or '{}')
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _commands_from_exec_calls(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """exec_command_end-shaped entries rebuilt from ``exec_command`` calls and their outputs.

    Many rollouts (78 of 138 measured) never wrote exec_command_end, so /shell and the
    overview's count read 0 for sessions that ran thousands of commands. The call holds the
    command; its output says ``Process exited with code N`` and ``Wall time``. A command still
    running when the call returned (``Process running with session ID S``) gets the exit code
    of the first later ``write_stdin`` poll of S that reports one.
    """
    pairs = get_tool_pairs(records)
    exit_by_session: Dict[str, int] = {}
    for pair in pairs:
        call, out = pair.get('call') or {}, pair.get('output') or {}
        if call.get('name') == 'write_stdin':
            sid = str(_args(call).get('session_id', ''))
            m = _EXITED.search(text_of(out.get('output')))
            if sid and m and sid not in exit_by_session:
                exit_by_session[sid] = int(m.group(1))
    commands: List[Dict[str, Any]] = []
    for pair in pairs:
        call, out = pair.get('call') or {}, pair.get('output') or {}
        if call.get('name') != 'exec_command':
            continue
        args = _args(call)
        text = text_of(out.get('output'))
        exit_code: Optional[int] = None
        m = _EXITED.search(text)
        if m:
            exit_code = int(m.group(1))
        else:
            running = _RUNNING.search(text)
            if running:
                exit_code = exit_by_session.get(running.group(1))
        if exit_code is not None:
            status = 'completed'
        elif text.startswith('aborted by user'):
            status = 'aborted'
        else:
            status = 'running'  # never reported an exit code before the session moved on
        wall = _WALL.search(text)
        secs = float(wall.group(1)) if wall else 0.0
        commands.append({
            'type': 'exec_command_end',
            'call_id': call.get('call_id'),
            'command': ['/bin/bash', '-lc', str(args.get('cmd', ''))],
            'cwd': args.get('workdir'),
            'exit_code': exit_code,
            'status': status,
            'duration': {'secs': int(secs), 'nanos': int(round((secs - int(secs)) * 1e9))},
            'aggregated_output': text.partition('Output:\n')[2] if 'Output:\n' in text else '',
            'source': 'exec_command_output',  # rebuilt from the call, not a recorded end event
            '_timestamp': call.get('_timestamp'),
        })
    return commands


def get_shell_commands(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every shell command the session ran, as exec_command_end-shaped dicts.

    Recorded exec_command_end events (and CommandExecution items, normalized to them) when
    the rollout has any; otherwise rebuilt from ``exec_command`` calls. Commands an ``exec``
    script ran are recorded one by one only in the item-era format; see
    :func:`unrecorded_exec_scripts`.
    """
    ended = _flatten_event_msg_payloads(records, 'exec_command_end')
    return ended if ended else _commands_from_exec_calls(records)


def unrecorded_exec_scripts(records: List[Dict[str, Any]]) -> int:
    """How many ``exec`` script calls ran commands this rollout never records one by one.

    An ``exec`` call is a script that can run several commands; only rollouts with
    exec_command_end/CommandExecution records list them. Elsewhere the script and its combined
    output are in /tools, and the count of commands is unknown, so callers disclose it rather
    than read it as zero.
    """
    if _flatten_event_msg_payloads(records, 'exec_command_end'):
        return 0
    return sum(1 for pair in get_tool_pairs(records) if (pair.get('call') or {}).get('name') == 'exec')
