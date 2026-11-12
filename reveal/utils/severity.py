"""Shared severity vocabulary and filtering for dict-shaped check/issue results.

Owns the rank for Detection objects and dictionary findings (BACK-1205).
Check-only gate helpers keep the unfiltered census independent of display rows;
network adapters retain their existing health verdicts.
"""

from typing import Any, Dict, List, Optional

from .results import AnalysisCompleteness, ExecutionFacts, FailureCause, execution_exit_code

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


CHECK_GATES = ('none', 'low', 'medium', 'high', 'findings')


def check_fail_on(args: Any) -> str:
    """Check's severity policy, distinct from analytical nouns' boolean gate."""
    return getattr(args, 'fail_on', None) or 'high'


def severity_counts(detections: list) -> Dict[str, int]:
    counts = dict.fromkeys(SEVERITY_ORDER, 0)
    for detection in detections:
        counts[detection.severity.value.lower()] += 1
    return counts


def check_gate_count(counts: Dict[str, int], displayed: int, policy: str) -> int:
    """Gates use all findings before presentation filters or cuts."""
    if policy == 'none':
        return 0
    if policy == 'findings':
        return displayed
    if policy not in CHECK_GATES:
        raise ValueError('unsupported Check findings gate')
    minimum = SEVERITY_ORDER.index(policy)
    return sum(counts.get(level, 0) for level in SEVERITY_ORDER[minimum:])


def filter_detections_by_severity(detections: list, severity: Optional[str]) -> list:
    """Display Detection objects using the same rank as dictionary findings."""
    level = severity.lower() if severity else ''
    if level not in SEVERITY_ORDER:
        return detections
    minimum = SEVERITY_ORDER.index(level)
    return [d for d in detections if SEVERITY_ORDER.index(d.severity.value.lower()) >= minimum]


def check_exit_code(
    total_issues: int, files_errored: int = 0, files_degraded: int = 0,
    exit_zero: bool = False, *, scan_incomplete: bool = False,
    fail_on: str = 'findings', output_failed: bool = False,
) -> int:
    """Compute `reveal check`'s process exit code (BACK-1099's contract).

    0 = clean: ran to completion, zero issues, every file parsed and every
        rule ran without raising.
    1 = issues found: ran to completion, no degraded/errored files, but at
        least one rule violation was reported.
    3 = incomplete scan: one or more files could not be checked at all
        (files_errored -- analyzer/parse pipeline raised) or were checked
        against a degraded/error-recovery parse (files_degraded) or a rule
        itself raised, or a rule-wide scan was capped/skipped. Takes priority over 1 even when issues were also
        found, because a degraded scan means the issue *count* itself may
        be wrong or incomplete.

    fail_on (BACK-2051, D6): ``findings`` (the default) keeps 1 for issues; ``none``
    reports them without failing but never hides lost or degraded analysis (3).
    It is mutually exclusive with exit_zero at the CLI (usage error, 2).

    output_failed (BACK-1939, D6): a requested artifact (``--also-json``) could not be
    written. Required output failure is 3 over findings (1) and over exit_zero, like the
    declared nouns (``execution_exit_code``).

    (2 is reserved for usage/invocation errors -- bad args, unsupported
    path -- raised directly by the CLI layer before a scan starts, not
    computed here.)

    exit_zero (BACK-1186): once the scan itself completed (this function
    was reached at all -- a real usage error still exits 2 upstream of
    here), always return 0 regardless of findings or degraded files. "Were
    there issues" stays fully recorded in the JSON/text summary; this only
    changes the process exit code, matching how every other reveal adapter
    (overview://, hotspots://, ...) already behaves -- makes `check` safe
    to drop into a `set -e` / CI pipeline without the caller needing to
    know this one adapter's special exit-code convention.
    """
    if fail_on not in CHECK_GATES:
        raise ValueError('unsupported Check findings gate')
    incomplete = bool(files_errored or files_degraded or scan_incomplete)
    facts = ExecutionFacts(AnalysisCompleteness.INCOMPLETE if incomplete else AnalysisCompleteness.COMPLETE,
                           findings=total_issues > 0,
                           failures=frozenset({FailureCause.OUTPUT}) if output_failed else frozenset())
    return execution_exit_code(facts, fail_on='none' if fail_on == 'none' else 'findings',
                               legacy_scan_override=exit_zero)
