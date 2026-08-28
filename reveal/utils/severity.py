"""Shared severity vocabulary and filtering for dict-shaped check/issue results.

Mirrors cli/file_checker.py's _SEVERITY_ORDER/_apply_severity_filter (used by the
bare-file --check path for Detection objects), extended to work on plain dicts
so the ssl://, domain://, and mysql:// health-check adapters can share it
(BACK-1205).
"""

from typing import Any, Dict, List, Optional

SEVERITY_ORDER = ['low', 'medium', 'high', 'critical']


def filter_by_severity(
    items: List[Dict[str, Any]],
    severity: Optional[str],
    key: str = 'severity',
) -> List[Dict[str, Any]]:
    """Filter dicts to those at or above the given minimum severity.

    An unrecognized `severity` value is a no-op (returns items unchanged) rather
    than raising, matching _apply_severity_filter's leniency. An item missing
    `key` or carrying an unrecognized value is treated as unranked and dropped
    by any real threshold -- consistent with only showing what can be confirmed
    to meet the bar.

    This only ever filters what gets returned/displayed. Callers must compute
    status/summary/exit_code from the unfiltered list first -- exit_code is the
    true health signal these adapters already keep independent of the (also
    display-only) `only_failures` filter; see e.g. ssl/adapter.py's
    _batch_check_domains "based on ALL results, not just filtered" comment.
    """
    if not severity:
        return items
    level = str(severity).lower()
    if level not in SEVERITY_ORDER:
        return items
    min_idx = SEVERITY_ORDER.index(level)

    def rank(item: Dict[str, Any]) -> int:
        value = str(item.get(key, '')).lower()
        return SEVERITY_ORDER.index(value) if value in SEVERITY_ORDER else -1

    return [item for item in items if rank(item) >= min_idx]
