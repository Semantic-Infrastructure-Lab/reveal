"""The active-entry-point filter: one owner for architecture, overview and the diff.

``imports://?entrypoints`` lists every file nothing but tests imports (fan-in 0).
Most of those are not places execution starts, so the briefs report only the
*active* ones: fan_out > 0, not a test file, not an ``__init__.py``.
"""
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .path_utils import is_test_path_any_sep

ACTIVE_ENTRY_POINT_RULE = 'fan_out > 0, not a test file, not __init__.py'


def is_active_entry_point(entry: Dict[str, Any]) -> bool:
    """True for a fan-in-0 row that is an active entry point (see the module docstring)."""
    return (
        entry.get('fan_out', 0) > 0
        and not is_test_path_any_sep(entry['file'])
        and Path(entry['file']).name != '__init__.py'
    )


def active_entry_points(entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [e for e in entries if is_active_entry_point(e)]


def entry_point_filter(entries: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """How many fan-in-0 files there are, how many of them are active, and the rule between them."""
    rows = list(entries)
    return {
        'fan_in_zero': len(rows),
        'active': len(active_entry_points(rows)),
        'rule': ACTIVE_ENTRY_POINT_RULE,
    }


def entry_point_rule_line(indent: str = '') -> str:
    return f'{indent}active = {ACTIVE_ENTRY_POINT_RULE}'
