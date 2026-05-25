"""Error and warning event extraction for Codex sessions."""

from typing import Any, Dict, List

_ERROR_TYPES = {'error', 'warning', 'guardian_warning'}


def get_errors(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract error/warning events from JSONL records.

    Returns a list of dicts with keys: timestamp, severity, message
    """
    errors: List[Dict[str, Any]] = []
    for rec in records:
        if rec.get('type') != 'event_msg':
            continue
        payload = rec.get('payload', {})
        ptype = payload.get('type', '')
        if ptype in _ERROR_TYPES:
            errors.append({
                'timestamp': rec.get('timestamp'),
                'severity': ptype,
                'message': payload.get('message', ''),
            })
    return errors
