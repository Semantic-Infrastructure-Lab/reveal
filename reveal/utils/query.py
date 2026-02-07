"""Query parsing and filtering utilities for Reveal adapters.

Provides unified query syntax parsing and comparison logic used across all adapters.
This eliminates code duplication and ensures consistent behavior.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union


def coerce_value(value: str) -> Union[bool, int, float, str]:
    """Coerce a string value to its appropriate type.

    Args:
        value: String value to coerce

    Returns:
        Value coerced to bool, int, float, or left as string
    """
    if not isinstance(value, str):
        return value

    # Boolean (including numeric representations: '1'=True, '0'=False)
    if value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
        return value.lower() in ('true', 'yes', '1')

    # Try numeric
    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def parse_query_params(query: str, coerce: bool = False) -> Dict[str, Any]:
    """Parse URL query string into parameter dictionary.

    Args:
        query: Query string (e.g., "key1=value1&key2=value2")
        coerce: Whether to coerce values to their appropriate types

    Returns:
        Dictionary of query parameters
    """
    if not query:
        return {}

    params = {}
    for part in query.split('&'):
        part = part.strip()
        if not part:  # Skip empty parts
            continue

        if '=' in part:
            key, value = part.split('=', 1)
            key = key.strip()
            value = value.strip()
            if coerce:
                value = coerce_value(value)
            params[key] = value
        else:
            params[part] = True

    return params


@dataclass
class QueryFilter:
    """Represents a single filter condition.

    Attributes:
        field: Field name to filter on
        op: Operator (>, <, >=, <=, =, !=, ~=, .., ?, !, *)
        value: Target value for comparison
    """
    field: str
    op: str
    value: str

    VALID_OPERATORS = {'=', '>', '<', '>=', '<=', '!=', '~=', '!~', '..', '?', '!', '*', '=='}

    def __post_init__(self):
        # Normalize operators
        if self.op == '==':
            self.op = '='

        # Validate operator
        if self.op not in self.VALID_OPERATORS:
            raise ValueError(f"Invalid operator: {self.op}. Must be one of {sorted(self.VALID_OPERATORS)}")


def parse_query_filters(
    query: str,
    coerce_numeric: bool = True,
    support_existence: bool = True
) -> List[QueryFilter]:
    """Parse query string into list of QueryFilter objects.

    Supports operators: >, <, >=, <=, =, ==, !=, ~=, .., ?, !

    Args:
        query: Query string with filters (e.g., "age>25&status=active")
        coerce_numeric: Try to coerce numeric values
        support_existence: Support ? and ! existence checks

    Returns:
        List of QueryFilter objects
    """
    if not query:
        return []

    filters = []

    # Split by & to get individual filters
    parts = query.split('&')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        matched = False

        # Check for negation prefix (!field)
        if support_existence and part.startswith('!'):
            field = part[1:].strip()
            if field:  # Make sure there's a field name after !
                filters.append(QueryFilter(field, '!', ''))
                matched = True
                continue

        # Try to match operators (order matters for precedence)
        # Two-character operators (except ..)
        for op in ['>=', '<=', '!=', '~=', '!~']:
            if op in part:
                field, value = part.split(op, 1)
                field = field.strip()
                value = value.strip()

                if coerce_numeric and op not in ('~=', '!~'):
                    value = coerce_value(value)

                filters.append(QueryFilter(field, op, value))
                matched = True
                break

        if matched:
            continue

        # Single-character operators (>, <, =)
        for op in ['>', '<', '=']:
            if op in part:
                field, value = part.split(op, 1)
                field = field.strip()
                value = value.strip()

                # Special handling for = operator
                if op == '=':
                    # Check for wildcard pattern (*value*)
                    if '*' in value:
                        filters.append(QueryFilter(field, '*', value))
                        matched = True
                        break

                    # Check for range pattern (value1..value2)
                    if '..' in value:
                        filters.append(QueryFilter(field, '..', value))
                        matched = True
                        break

                # Normal operator handling
                if coerce_numeric:
                    value = coerce_value(value)

                filters.append(QueryFilter(field, op, value))
                matched = True
                break

        if matched:
            continue

        # If no operator found, treat as existence check (if supported)
        if support_existence:
            filters.append(QueryFilter(part, '?', ''))

    return filters


def compare_values(
    field_value: Any,
    operator: str,
    target_value: Any,
    options: Optional[Dict[str, bool]] = None
) -> bool:
    """Universal comparison function for all adapters.

    This is the single source of truth for comparison logic, eliminating
    ~300 lines of duplicate code across adapters.

    Args:
        field_value: The value to compare (from data)
        operator: Comparison operator (=, !=, >, <, >=, <=, ~=, .., ==, !~)
        target_value: The target value to compare against
        options: Optional behavior flags:
            - allow_list_any: Check if any list element matches (default: True)
            - case_sensitive: Case-sensitive string comparison (default: False)
            - coerce_numeric: Try numeric comparison first (default: True)
            - none_matches_not_equal: None matches != operator (default: True)

    Returns:
        True if comparison passes, False otherwise

    Examples:
        >>> compare_values(25, '>', 20)
        True
        >>> compare_values('active', '=', 'active')
        True
        >>> compare_values('test', '~=', '^te')
        True
        >>> compare_values(None, '!=', 'something')
        True
    """
    # Default options
    opts = {
        'allow_list_any': True,
        'case_sensitive': False,
        'coerce_numeric': True,
        'none_matches_not_equal': True
    }
    if options:
        opts.update(options)

    # Normalize operator
    if operator == '==':
        operator = '='

    # Handle None/null values
    if field_value is None:
        if opts['none_matches_not_equal'] and operator in ('!=', '!~'):
            return True
        if operator == '=' and isinstance(target_value, str) and target_value.lower() == 'null':
            return True
        return False

    # Handle list fields - check if any element matches
    if opts['allow_list_any'] and isinstance(field_value, list):
        return any(compare_values(item, operator, target_value, options) for item in field_value)

    # Convert to string for string operations
    field_str = str(field_value)
    target_str = str(target_value)

    # Case sensitivity
    if not opts['case_sensitive']:
        field_str_lower = field_str.lower()
        target_str_lower = target_str.lower()
    else:
        field_str_lower = field_str
        target_str_lower = target_str

    # Handle range operator (..)
    if operator == '..':
        if not isinstance(target_value, str) or '..' not in str(target_value):
            return False

        try:
            parts = str(target_value).split('..', 1)
            min_val, max_val = parts[0].strip(), parts[1].strip()

            # Try numeric comparison first if coercion enabled
            if opts['coerce_numeric']:
                try:
                    if isinstance(field_value, (int, float)):
                        field_num = field_value
                    else:
                        field_num = float(field_value)

                    min_num = float(min_val) if min_val else float('-inf')
                    max_num = float(max_val) if max_val else float('inf')

                    return min_num <= field_num <= max_num
                except (ValueError, TypeError):
                    pass

            # Fall back to string comparison
            return min_val <= field_str <= max_val
        except (ValueError, TypeError, AttributeError):
            return False

    # Handle wildcard operator (*)
    if operator == '*':
        # Convert shell-style wildcards (*) to regex
        # *test* -> .*test.*
        # test* -> test.*
        # *test -> .*test
        pattern_str = str(target_value)
        # Escape special regex characters except *
        pattern_str = re.escape(pattern_str).replace(r'\*', '.*')
        try:
            pattern = re.compile(pattern_str, re.IGNORECASE if not opts['case_sensitive'] else 0)
            return bool(pattern.search(field_str))
        except re.error:
            return False

    # Handle regex operators (~=, !~)
    if operator in ('~=', '!~'):
        try:
            pattern = re.compile(str(target_value))
            matches = bool(pattern.search(field_str))
            return matches if operator == '~=' else not matches
        except re.error:
            return False if operator == '~=' else True

    # Handle equality operators (=, !=)
    if operator in ('=', '!='):
        # Special case: if value contains .., treat as range (for backward compatibility)
        # This handles queries like "age=25..30" which parse as op='=' with value='25..30'
        if operator == '=' and isinstance(target_value, str) and '..' in str(target_value):
            # Delegate to range handling
            return compare_values(field_value, '..', target_value, options)

        # Try numeric comparison if enabled
        if opts['coerce_numeric']:
            try:
                if isinstance(field_value, (int, float)):
                    field_num = field_value
                else:
                    field_num = float(field_value)

                target_num = float(target_value)
                numeric_equal = field_num == target_num
                return numeric_equal if operator == '=' else not numeric_equal
            except (ValueError, TypeError):
                pass

        # String comparison
        strings_equal = field_str_lower == target_str_lower
        return strings_equal if operator == '=' else not strings_equal

    # Handle numeric comparison operators (>, <, >=, <=)
    if operator in ('>', '<', '>=', '<='):
        try:
            # Get numeric value
            if isinstance(field_value, (int, float)):
                field_num = field_value
            else:
                field_num = float(field_value)

            target_num = float(target_value)

            if operator == '>':
                return field_num > target_num
            elif operator == '<':
                return field_num < target_num
            elif operator == '>=':
                return field_num >= target_num
            elif operator == '<=':
                return field_num <= target_num
        except (ValueError, TypeError):
            # Fall back to string comparison if coercion disabled or failed
            if not opts['coerce_numeric']:
                if operator == '>':
                    return field_str > target_str
                elif operator == '<':
                    return field_str < target_str
                elif operator == '>=':
                    return field_str >= target_str
                elif operator == '<=':
                    return field_str <= target_str
            return False

    return False


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

    # Use unified comparison logic
    return compare_values(field_value, filter.op, filter.value)


def apply_filters(item: Dict[str, Any], filters: List[QueryFilter]) -> bool:
    """Apply multiple filters to an item (AND logic).

    Args:
        item: Dictionary to check
        filters: List of QueryFilter objects

    Returns:
        True if item matches all filters, False otherwise
    """
    return all(apply_filter(item, f) for f in filters)


@dataclass
class ResultControl:
    """Control parameters for result formatting.

    Attributes:
        sort_field: Field to sort by (None = no sorting)
        sort_descending: Sort in descending order
        limit: Maximum number of results (None = no limit)
        offset: Number of results to skip (default: 0)
    """
    sort_field: Optional[str] = None
    sort_descending: bool = False
    limit: Optional[int] = None
    offset: int = 0


def parse_result_control(query: str) -> Tuple[str, ResultControl]:
    """Parse result control parameters from query string.

    Extracts sort=field, sort=-field, limit=N, offset=M parameters.

    Args:
        query: Query string

    Returns:
        Tuple of (cleaned_query, ResultControl)
        - cleaned_query: Query string with control params removed
        - ResultControl: Parsed control parameters
    """
    if not query:
        return '', ResultControl()

    control = ResultControl()
    remaining_parts = []

    for part in query.split('&'):
        part = part.strip()
        if not part:
            continue

        # Check for control parameters
        if part.startswith('sort='):
            sort_field = part[5:]  # Remove "sort="
            if sort_field.startswith('-'):
                control.sort_descending = True
                control.sort_field = sort_field[1:]
            else:
                control.sort_descending = False
                control.sort_field = sort_field

        elif part.startswith('limit='):
            try:
                control.limit = int(part[6:])
            except ValueError:
                pass

        elif part.startswith('offset='):
            try:
                control.offset = int(part[7:])
            except ValueError:
                pass

        else:
            # Not a control parameter, keep it
            remaining_parts.append(part)

    # Reconstruct query without control parameters
    cleaned_query = '&'.join(remaining_parts)

    return cleaned_query, control


def apply_result_control(items: List[Dict[str, Any]], control: ResultControl) -> List[Dict[str, Any]]:
    """Apply result control to a list of items.

    Args:
        items: List of items (dicts)
        control: ResultControl with sort/limit/offset

    Returns:
        Processed list of items
    """
    result = items[:]

    # Apply sorting
    if control.sort_field:
        def sort_key(item):
            value = item.get(control.sort_field)
            # Handle None values (sort to end)
            if value is None:
                return (1, '') if not control.sort_descending else (0, '')
            return (0, value)

        result.sort(key=sort_key, reverse=control.sort_descending)

    # Apply offset
    if control.offset > 0:
        result = result[control.offset:]

    # Apply limit
    if control.limit is not None:
        result = result[:control.limit]

    return result
