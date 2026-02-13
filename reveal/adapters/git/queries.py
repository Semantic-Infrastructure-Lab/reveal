"""Git query filtering and comparison logic."""

from typing import Any, Union, Dict

from ...utils.query import compare_values


def compare(field_value: Any, operator: str, target_value: Union[bool, int, float, str]) -> bool:
    """Compare field value against target using operator.

    Uses unified compare_values() from query.py to eliminate duplication.

    Args:
        field_value: Value from commit dict
        operator: Comparison operator (=, >, <, >=, <=, !=, ~=, ..)
        target_value: Target value to compare against

    Returns:
        True if comparison passes, False otherwise
    """
    return compare_values(
        field_value,
        operator,
        target_value,
        options={
            'allow_list_any': False,  # Git commits don't have list fields
            'case_sensitive': False,  # Author/email/message searches case-insensitive
            'coerce_numeric': True,   # For timestamp comparisons
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
        if not compare(field_value, qf.op, qf.value):
            return False

    return True
