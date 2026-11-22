"""Front-matter value comparison for markdown adapter (the where terms parse with the shared filter parser)."""

from typing import Any

from ...utils.query import compare_values


def compare(field_value: Any, operator: str, target_value: bool | int | float | str) -> bool:
    """Compare field value against target using operator.

    Uses unified compare_values() from query.py to eliminate duplication.

    Args:
        field_value: Value from frontmatter field
        operator: Comparison operator (>, <, >=, <=, ==, !=, ~=, .., !~)
        target_value: Target value to compare against

    Returns:
        True if comparison matches
    """
    return compare_values(
        field_value,
        operator,
        target_value,
        options={
            'allow_list_any': True,
            'case_sensitive': False,
            'coerce_numeric': True,
            'none_matches_not_equal': True
        }
    )
