"""Shared utilities for agent-style session adapters (claude://, codex://, etc.)."""

from typing import Any, Dict, List, Optional


def pair_tool_calls(
    records: List[Dict[str, Any]],
    call_type: str,
    output_type: str,
    call_id_field: str = 'call_id',
) -> List[Dict[str, Any]]:
    """Pair tool call records with their outputs by call_id.

    Args:
        records: list of dicts, each with a 'type' field
        call_type: type string for call records (e.g. 'function_call')
        output_type: type string for output records (e.g. 'function_call_output')
        call_id_field: field name for the call ID

    Returns:
        list of {'call': call_record, 'output': output_record_or_None}
    """
    outputs: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        if rec.get('type') == output_type:
            cid = rec.get(call_id_field)
            if cid is not None:
                outputs[cid] = rec

    pairs: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get('type') == call_type:
            cid = rec.get(call_id_field)
            pairs.append({
                'call': rec,
                'output': outputs.get(cid) if cid is not None else None,
            })

    return pairs
