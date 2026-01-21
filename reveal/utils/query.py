"""Query string parsing utilities.

Provides unified parsing for URI query strings used across adapters.
Supports simple key=value parameters and operator-based filters.

Examples:
    # Simple parameters (stats, claude adapters)
    parse_query_params("hotspots=true&min_lines=50", coerce=True)
    # -> {'hotspots': True, 'min_lines': 50}

    # Bare keywords become True
    parse_query_params("errors&tools=Bash")
    # -> {'errors': True, 'tools': 'Bash'}

    # Operator-based filters (ast adapter)
    parse_query_filters("lines>50&type=function")
    # -> [QueryFilter('lines', '>', 50), QueryFilter('type', '=', 'function')]

    # Existence/missing filters (markdown adapter)
    parse_query_filters("!draft&tags")
    # -> [QueryFilter('draft', '!', ''), QueryFilter('tags', '?', '')]
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


def coerce_value(value: str) -> Union[bool, int, float, str]:
    """Coerce string value to appropriate type.

    Args:
        value: String value to coerce

    Returns:
        Coerced value (bool, int, float, or original string)

    Examples:
        >>> coerce_value('true')
        True
        >>> coerce_value('42')
        42
        >>> coerce_value('3.14')
        3.14
        >>> coerce_value('hello')
        'hello'
    """
    # Boolean coercion
    if value.lower() in ('true', '1', 'yes'):
        return True
    if value.lower() in ('false', '0', 'no'):
        return False

    # Numeric coercion
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def parse_query_params(query: str, coerce: bool = False) -> Dict[str, Any]:
    """Parse query string into key-value parameters.

    Handles both key=value pairs and bare keywords (which become True).

    Args:
        query: Query string (e.g., "hotspots=true&min_lines=50&errors")
        coerce: If True, automatically coerce values to bool/int/float

    Returns:
        Dictionary of parameter names to values

    Examples:
        >>> parse_query_params("tools=Bash&errors")
        {'tools': 'Bash', 'errors': True}

        >>> parse_query_params("min_lines=50&active=true", coerce=True)
        {'min_lines': 50, 'active': True}
    """
    if not query:
        return {}

    params = {}
    for part in query.split('&'):
        part = part.strip()
        if not part:
            continue

        if '=' in part:
            key, value = part.split('=', 1)
            key = key.strip()
            value = value.strip()
            params[key] = coerce_value(value) if coerce else value
        else:
            # Bare keyword becomes True
            params[part] = True

    return params


@dataclass
class QueryFilter:
    """Structured query filter with field, operator, and value.

    Attributes:
        field: Field name to filter on
        op: Operator ('=', '>', '<', '>=', '<=', '!', '?', '*')
        value: Filter value (may be empty for existence operators)

    Operators:
        '='  - Equality match
        '>'  - Greater than (numeric)
        '<'  - Less than (numeric)
        '>=' - Greater than or equal (numeric)
        '<=' - Less than or equal (numeric)
        '!'  - Field must be missing/empty
        '?'  - Field must exist (presence check)
        '*'  - Wildcard pattern match
    """
    field: str
    op: str
    value: Any

    def __post_init__(self):
        """Validate operator."""
        valid_ops = {'=', '>', '<', '>=', '<=', '!', '?', '*'}
        if self.op not in valid_ops:
            raise ValueError(f"Invalid operator: {self.op}. Must be one of {valid_ops}")


# Operator precedence for parsing (longer operators first)
_COMPARISON_OPS = ['>=', '<=', '>', '<', '=']


def parse_query_filters(
    query: str,
    coerce_numeric: bool = True,
    support_existence: bool = True
) -> List[QueryFilter]:
    """Parse query string into structured filters with operators.

    Supports comparison operators (>, <, >=, <=, =) and existence
    operators (!, ? for missing/present).

    Args:
        query: Query string (e.g., "lines>50&type=function&!draft")
        coerce_numeric: If True, coerce comparison values to int
        support_existence: If True, support ! (missing) and bare field (exists)

    Returns:
        List of QueryFilter objects

    Examples:
        >>> parse_query_filters("lines>50&type=function")
        [QueryFilter('lines', '>', 50), QueryFilter('type', '=', 'function')]

        >>> parse_query_filters("!draft&tags")
        [QueryFilter('draft', '!', ''), QueryFilter('tags', '?', '')]
    """
    if not query:
        return []

    filters = []
    for part in query.split('&'):
        part = part.strip()
        if not part:
            continue

        # Check for missing field operator (!)
        if support_existence and part.startswith('!'):
            field = part[1:].strip()
            filters.append(QueryFilter(field, '!', ''))
            continue

        # Try comparison operators (order matters: >= before >)
        parsed = False
        for op in _COMPARISON_OPS:
            if op in part:
                key, value = part.split(op, 1)
                key = key.strip()
                value = value.strip()

                # Handle wildcard in value
                if '*' in value:
                    filters.append(QueryFilter(key, '*', value))
                else:
                    # Coerce to int for comparison operators
                    if coerce_numeric and op in {'>', '<', '>=', '<='}:
                        try:
                            value = int(value)
                        except ValueError:
                            pass
                    filters.append(QueryFilter(key, op, value))
                parsed = True
                break

        # If no operator found and existence checking enabled, treat as exists check
        if not parsed:
            if support_existence:
                filters.append(QueryFilter(part, '?', ''))
            # Otherwise skip unknown syntax

    return filters


def apply_filter(item: Dict[str, Any], filter: QueryFilter) -> bool:
    """Apply a single filter to an item.

    Args:
        item: Dictionary to check
        filter: QueryFilter to apply

    Returns:
        True if item matches filter, False otherwise
    """
    field_value = item.get(filter.field)

    if filter.op == '!':
        # Missing/empty check
        return field_value is None or field_value == ''

    if filter.op == '?':
        # Existence check
        return field_value is not None and field_value != ''

    if field_value is None:
        return False

    if filter.op == '=':
        return str(field_value) == str(filter.value)

    if filter.op == '*':
        # Wildcard match
        pattern = filter.value.replace('*', '')
        return pattern.lower() in str(field_value).lower()

    # Numeric comparisons
    try:
        num_value = float(field_value) if isinstance(field_value, str) else field_value
        filter_num = float(filter.value) if isinstance(filter.value, str) else filter.value

        if filter.op == '>':
            return num_value > filter_num
        if filter.op == '<':
            return num_value < filter_num
        if filter.op == '>=':
            return num_value >= filter_num
        if filter.op == '<=':
            return num_value <= filter_num
    except (ValueError, TypeError):
        return False

    return False


def apply_filters(item: Dict[str, Any], filters: List[QueryFilter]) -> bool:
    """Apply multiple filters to an item (all must match).

    Args:
        item: Dictionary to check
        filters: List of QueryFilter objects

    Returns:
        True if item matches ALL filters, False otherwise
    """
    return all(apply_filter(item, f) for f in filters)
