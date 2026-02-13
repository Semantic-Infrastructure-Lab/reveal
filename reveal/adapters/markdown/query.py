"""Query parsing and comparison for markdown adapter."""

from typing import Any, List, Tuple

from ...utils.query import compare_values


def parse_query(query: str) -> List[Tuple[str, str, str]]:
    """Parse query string into filter tuples.

    Args:
        query: Query string (e.g., 'field=value&!other')

    Returns:
        List of (field, operator, value) tuples
        Operators: '=' (match), '!' (missing), '*' (wildcard)
    """
    filters: List[tuple] = []
    if not query:
        return filters

    # Split on & for multiple filters
    parts = query.split('&')
    for part in parts:
        part = part.strip()
        if not part:
            continue

        if part.startswith('!'):
            # Missing field filter: !field
            field = part[1:]
            filters.append((field, '!', ''))
        elif '=' in part:
            # Value filter: field=value or field=*pattern*
            field, value = part.split('=', 1)
            if '*' in value:
                filters.append((field, '*', value))
            else:
                filters.append((field, '=', value))
        else:
            # Treat as existence check: field (exists)
            filters.append((part, '?', ''))

    return filters


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
