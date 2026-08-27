"""Git query filtering and comparison logic."""

from typing import Any, Optional, Union, Dict

from ...utils.query import compare_values


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
        if not compare(field_value, qf.op, qf.value, field_name=qf.field):
            return False

    return True
