"""Git query filtering and comparison logic."""

import re
from datetime import datetime
from functools import lru_cache
from typing import Any, Optional, Union, Dict

from ...utils.query import compare_values
from ...utils.query_eval import presence_matches

# A bound written as a year, a month or a day, no time: `date>2026`, `date>2026-02`,
# `date>2026-02-01`.
_PERIOD = re.compile(r'\d{4}(-\d{2}(-\d{2})?)?')
# A timestamp written with 'T' between the day and the time: `2026-02-01T12:00:00`.
_T_SEPARATED = re.compile(r'(\d{4}-\d{2}-\d{2})T(\d)')
# A timestamp with a zone: `2026-02-01T12:00:00Z`, `2026-02-01 12:00+02:00`, `...12:00:00-1200`.
_ZONED = re.compile(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?) ?(Z|[+-]\d{2}:?\d{2})',
                    re.IGNORECASE)


def _at_bound_precision(commit_date: str, bound: str) -> str:
    """The commit date at the bound's precision: its year, month or day when the bound is one
    (BACK-2277, months BACK-2300, years BACK-2309).

    A period bound names the whole period, so `date>P` is after the end of P, `date<P` before
    its start, `date>=P`/`date<=P` include all of it, and `date=P` is any time in it.
    Compared as the full 'YYYY-MM-DD HH:MM:SS' string, a commit in P sorts after 'P', so
    `date<=P` lost P, `date>P` kept it and `date=P` matched nothing. A timestamp bound
    compares the timestamp.
    """
    return commit_date[:len(bound)] if _PERIOD.fullmatch(bound) else commit_date


def _local_time(zoned: 're.Match[str]') -> str:
    """A zoned timestamp as the local wall-clock time the commit dates are written in.

    ``format_commit`` writes ``date`` with ``datetime.fromtimestamp``: the local time of the
    machine running reveal, with no zone. So `date>2026-02-01T12:00:00Z` compared the digits
    '12:00:00' with local times (BACK-2309); converted, it names the same instant. One hour a
    year is ambiguous: in the hour a DST change repeats, two instants print the same local
    time, in the commit dates and in the converted bound alike.
    """
    day, clock, zone = zoned.groups()
    zone = '+00:00' if zone.upper() == 'Z' else f'{zone[:3]}:{zone[-2:]}'
    try:
        moment = datetime.fromisoformat(f'{day}T{clock}{zone}').astimezone()
    # Not a calendar time (month 13), or outside what the platform's localtime converts.
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError(f"date bound {zoned.group(0)!r} is not a time reveal can convert to "
                         f"local time: {error}") from error
    fraction = f'.{moment.microsecond:06d}' if moment.microsecond else ''
    return moment.strftime('%Y-%m-%d %H:%M:%S') + fraction


@lru_cache(maxsize=256)
def _date_bound(text: str) -> str:
    """A bound as the commit dates are written: a zoned timestamp in local time (BACK-2309), and
    a 'T' between day and time as the space (BACK-2300), since ' ' sorts before 'T' and
    `date>DTHH:MM:SS` lost the commits of day D. Cached: every commit compares the same bound."""
    text = text.strip()
    zoned = _ZONED.fullmatch(text)
    if zoned:
        return _local_time(zoned)
    return _T_SEPARATED.sub(r'\1 \2', text, count=1)


def _compare_date(commit_date: str, operator: str, target: str) -> Optional[bool]:
    """A date bound, equality or range compared at the bound's precision; None for any other
    operator (`~=`, `!~`)."""
    if operator == '..' and '..' in target:
        low, high = (_date_bound(part) for part in target.split('..', 1))
        return ((not low or _at_bound_precision(commit_date, low) >= low)
                and (not high or _at_bound_precision(commit_date, high) <= high))
    target = _date_bound(target)
    if operator in ('>', '<', '>=', '<='):
        return compare_values(_at_bound_precision(commit_date, target), operator, target,
                              options={'coerce_numeric': False})
    if operator in ('=', '!='):
        same = _at_bound_precision(commit_date, target) == target
        return same if operator == '=' else not same
    return None


def compare(
    field_value: Any, operator: str, target_value: Union[bool, int, float, str],
    field_name: Optional[str] = None,
) -> bool:
    """Compare field value against target using operator.

    Uses unified compare_values() from query.py to eliminate duplication.

    Args:
        field_value: Value from commit dict
        operator: Comparison operator (=, >, <, >=, <=, !=, ~=, ..)
        target_value: Target value to compare against
        field_name: Name of the field being compared (BACK-1192) -- see
            coerce_numeric note below.

    Returns:
        True if comparison passes, False otherwise
    """
    # BACK-1192: commit_dict['date'] is a FORMATTED STRING ('2026-01-01
    # 15:30:00', see _format_commit()), not the numeric 'timestamp' field.
    # coerce_numeric=True made every ordered comparison (>, <, >=, <=)
    # against 'date' silently return False for every commit: float(field_
    # value) raises on a date string, and _handle_numeric_operator's string
    # fallback only triggers when coerce_numeric is False -- so date>=/
    # date<=/?since=/?until= filters matched nothing, ever, regardless of
    # the actual dates (confirmed live: date>=2026-01-01 against a commit
    # dated 2026-08-26 returned no match). ISO-formatted date strings
    # ('YYYY-MM-DD[ HH:MM:SS]') sort correctly under plain lexical string
    # comparison, so disabling numeric coercion specifically for 'date'
    # restores correct behavior without touching the shared compare_values()
    # utility other adapters rely on for genuinely numeric fields.
    coerce_numeric = field_name != 'date'
    # A year bound parses as a number (`date>2026` is 2026): it is a period all the same.
    if field_name == 'date' and isinstance(field_value, str) and isinstance(target_value, (str, int)):
        day_aware = _compare_date(field_value, operator, str(target_value))
        if day_aware is not None:
            return day_aware
    return compare_values(
        field_value,
        operator,
        target_value,
        options={
            'allow_list_any': False,  # Git commits don't have list fields
            'case_sensitive': False,  # Author/email/message searches case-insensitive
            'coerce_numeric': coerce_numeric,
            'none_matches_not_equal': True
        }
    )


def matches_all_filters(commit_dict: Dict[str, Any], query_filters: list) -> bool:
    """Check if commit matches all query filters.

    Args:
        commit_dict: Formatted commit dict from _format_commit()
        query_filters: List of query filter objects

    Returns:
        True if matches all filters, False otherwise
    """
    if not query_filters:
        return True

    for qf in query_filters:
        # Get field value from commit dict
        field_value = commit_dict.get(qf.field)
        # A bare key (`?author`) is the presence filter, as on json:// and ast:// (BACK-2300).
        matched = presence_matches(qf.op, field_value)
        if matched is None:
            matched = compare(field_value, qf.op, qf.value, field_name=qf.field)
        if not matched:
            return False

    return True
