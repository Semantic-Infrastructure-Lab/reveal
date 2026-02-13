"""Filtering logic for markdown adapter."""

import fnmatch
from typing import Dict, Any, Optional, List, Tuple

from . import query as query_module


def matches_filter(frontmatter: Optional[Dict[str, Any]],
                   field: str, operator: str, value: str) -> bool:
    """Check if frontmatter matches a single filter.

    Args:
        frontmatter: Parsed frontmatter dict (or None)
        field: Field name to check
        operator: '=' (match), '!' (missing), '*' (wildcard), '?' (exists)
        value: Value to match against

    Returns:
        True if matches
    """
    if operator == '!':
        # Missing field filter
        return frontmatter is None or field not in frontmatter

    if frontmatter is None:
        return False

    if operator == '?':
        # Exists filter
        return field in frontmatter

    if field not in frontmatter:
        return False

    fm_value = frontmatter[field]

    # Handle list values (match if any item matches)
    if isinstance(fm_value, list):
        if operator == '*':
            return any(fnmatch.fnmatch(str(item), value) for item in fm_value)
        else:
            return any(str(item) == value for item in fm_value)

    # Handle scalar values
    fm_str = str(fm_value)
    if operator == '*':
        return fnmatch.fnmatch(fm_str, value)
    else:
        return fm_str == value


def matches_all_filters(frontmatter: Optional[Dict[str, Any]],
                        filters: List[Tuple[str, str, str]],
                        query_filters: List[Any]) -> bool:
    """Check if frontmatter matches all filters (AND logic).

    Args:
        frontmatter: Parsed frontmatter dict (or None)
        filters: Legacy filters (field, operator, value) tuples
        query_filters: New query filters from unified syntax

    Returns:
        True if matches all filters
    """
    # Check legacy filters first (backward compatibility)
    if filters:
        if not all(
            matches_filter(frontmatter, field, op, value)
            for field, op, value in filters
        ):
            return False

    # Check new query filters (unified syntax)
    if query_filters:
        for qf in query_filters:
            if frontmatter is None:
                return False

            # Get field value from frontmatter
            field_value = frontmatter.get(qf.field)

            # Compare using operator
            if not query_module.compare(field_value, qf.op, qf.value):
                return False

    return True
