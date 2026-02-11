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
            key, value_str = part.split('=', 1)
            key = key.strip()
            value_str = value_str.strip()
            value: Union[bool, int, float, str] = coerce_value(value_str) if coerce else value_str
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
        value: Target value for comparison (str or coerced type)
    """
    field: str
    op: str
    value: Union[bool, int, float, str]

    VALID_OPERATORS = {'=', '>', '<', '>=', '<=', '!=', '~=', '!~', '..', '?', '!', '*', '=='}

    def __post_init__(self):
        # Normalize operators
        if self.op == '==':
            self.op = '='

        # Validate operator
        if self.op not in self.VALID_OPERATORS:
            raise ValueError(f"Invalid operator: {self.op}. Must be one of {sorted(self.VALID_OPERATORS)}")


def _try_parse_negation_filter(part: str) -> Optional[QueryFilter]:
    """Try to parse negation filter (!field).

    Args:
        part: Filter part to parse

    Returns:
        QueryFilter if negation found, None otherwise
    """
    if part.startswith('!'):
        field = part[1:].strip()
        if field:
            return QueryFilter(field, '!', '')
    return None


def _try_parse_two_char_operators(part: str, coerce_numeric: bool) -> Optional[QueryFilter]:
    """Try to parse two-character operators (>=, <=, !=, ~=, !~).

    Args:
        part: Filter part to parse
        coerce_numeric: Whether to coerce numeric values

    Returns:
        QueryFilter if operator matched, None otherwise
    """
    for op in ['>=', '<=', '!=', '~=', '!~']:
        if op in part:
            field, value_str = part.split(op, 1)
            field = field.strip()
            value_str = value_str.strip()

            value: Union[bool, int, float, str]
            if coerce_numeric and op not in ('~=', '!~'):
                value = coerce_value(value_str)
            else:
                value = value_str

            return QueryFilter(field, op, value)
    return None


def _parse_equals_special_cases(field: str, value: str) -> Optional[QueryFilter]:
    """Parse special cases for = operator (wildcards, ranges).

    Args:
        field: Field name
        value: Value to check for special patterns

    Returns:
        QueryFilter if special case matched, None otherwise
    """
    # Check for wildcard pattern (*value*)
    if '*' in value:
        return QueryFilter(field, '*', value)

    # Check for range pattern (value1..value2)
    if '..' in value:
        return QueryFilter(field, '..', value)

    return None


def _try_parse_single_char_operators(part: str, coerce_numeric: bool) -> Optional[QueryFilter]:
    """Try to parse single-character operators (>, <, =).

    Args:
        part: Filter part to parse
        coerce_numeric: Whether to coerce numeric values

    Returns:
        QueryFilter if operator matched, None otherwise
    """
    for op in ['>', '<', '=']:
        if op in part:
            field, value = part.split(op, 1)
            field = field.strip()
            value = value.strip()

            # Special handling for = operator
            if op == '=':
                special_filter = _parse_equals_special_cases(field, value)
                if special_filter:
                    return special_filter

            # Normal operator handling
            final_value: Union[bool, int, float, str]
            if coerce_numeric:
                final_value = coerce_value(value)
            else:
                final_value = value

            return QueryFilter(field, op, final_value)
    return None


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
    parts = query.split('&')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Try parsing in order of precedence
        parsed_filter = None

        # 1. Check for negation prefix (!field)
        if support_existence:
            parsed_filter = _try_parse_negation_filter(part)
            if parsed_filter:
                filters.append(parsed_filter)
                continue

        # 2. Try two-character operators
        parsed_filter = _try_parse_two_char_operators(part, coerce_numeric)
        if parsed_filter:
            filters.append(parsed_filter)
            continue

        # 3. Try single-character operators
        parsed_filter = _try_parse_single_char_operators(part, coerce_numeric)
        if parsed_filter:
            filters.append(parsed_filter)
            continue

        # 4. Fallback to existence check
        if support_existence:
            filters.append(QueryFilter(part, '?', ''))

    return filters


def _handle_range_operator(field_value: Any, target_value: Any, opts: dict) -> bool:
    """Handle range operator (..) comparison."""
    if not isinstance(target_value, str) or '..' not in str(target_value):
        return False

    try:
        parts = str(target_value).split('..', 1)
        min_val, max_val = parts[0].strip(), parts[1].strip()

        # Try numeric comparison first if coercion enabled
        if opts['coerce_numeric']:
            try:
                field_num = field_value if isinstance(field_value, (int, float)) else float(field_value)
                min_num = float(min_val) if min_val else float('-inf')
                max_num = float(max_val) if max_val else float('inf')
                return min_num <= field_num <= max_num
            except (ValueError, TypeError):
                pass

        # Fall back to string comparison
        return min_val <= str(field_value) <= max_val
    except (ValueError, TypeError, AttributeError):
        return False


def _handle_wildcard_operator(field_value: Any, target_value: Any, opts: dict) -> bool:
    """Handle wildcard operator (*) comparison."""
    pattern_str = str(target_value)
    # Escape special regex characters except *
    pattern_str = re.escape(pattern_str).replace(r'\*', '.*')
    try:
        pattern = re.compile(pattern_str, re.IGNORECASE if not opts['case_sensitive'] else 0)
        return bool(pattern.search(str(field_value)))
    except re.error:
        return False


def _handle_regex_operator(field_value: Any, operator: str, target_value: Any) -> bool:
    """Handle regex operators (~=, !~)."""
    try:
        pattern = re.compile(str(target_value))
        matches = bool(pattern.search(str(field_value)))
        return matches if operator == '~=' else not matches
    except re.error:
        return False if operator == '~=' else True


def _handle_equality_operator(field_value: Any, operator: str, target_value: Any, opts: dict) -> bool:
    """Handle equality operators (=, !=)."""
    # Special case: if value contains .., treat as range (backward compatibility)
    if operator == '=' and isinstance(target_value, str) and '..' in str(target_value):
        return _handle_range_operator(field_value, target_value, opts)

    # Try numeric comparison if enabled
    if opts['coerce_numeric']:
        try:
            field_num = field_value if isinstance(field_value, (int, float)) else float(field_value)
            target_num = float(target_value)
            numeric_equal = field_num == target_num
            return numeric_equal if operator == '=' else not numeric_equal
        except (ValueError, TypeError):
            pass

    # String comparison
    field_str = str(field_value).lower() if not opts['case_sensitive'] else str(field_value)
    target_str = str(target_value).lower() if not opts['case_sensitive'] else str(target_value)
    strings_equal = field_str == target_str
    return strings_equal if operator == '=' else not strings_equal


def _handle_numeric_operator(field_value: Any, operator: str, target_value: Any, opts: dict) -> bool:
    """Handle numeric comparison operators (>, <, >=, <=)."""
    try:
        field_num = field_value if isinstance(field_value, (int, float)) else float(field_value)
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
            field_str = str(field_value)
            target_str = str(target_value)
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

    # Dispatch to specific operator handlers
    if operator == '..':
        return _handle_range_operator(field_value, target_value, opts)
    elif operator == '*':
        return _handle_wildcard_operator(field_value, target_value, opts)
    elif operator in ('~=', '!~'):
        return _handle_regex_operator(field_value, operator, target_value)
    elif operator in ('=', '!='):
        return _handle_equality_operator(field_value, operator, target_value, opts)
    elif operator in ('>', '<', '>=', '<='):
        return _handle_numeric_operator(field_value, operator, target_value, opts)

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


def _safe_numeric(v):
    """Convert value to numeric, returning None for non-numeric values."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _detect_value_types(items: List[Dict[str, Any]], field: str) -> tuple:
    """Detect if field values are numeric, string, or mixed.

    Returns:
        (has_numbers, has_strings) tuple
    """
    values = [item.get(field) for item in items]
    has_numbers = any(isinstance(v, (int, float)) and v is not None for v in values)
    has_strings = any(isinstance(v, str) for v in values)
    return has_numbers, has_strings


def _create_sort_key(field: str, has_mixed_types: bool, sort_descending: bool):
    """Create sort key function for given field and type context.

    Args:
        field: Field name to sort by
        has_mixed_types: Whether field has mixed numeric/string types
        sort_descending: Sort direction

    Returns:
        Sort key function
    """
    def sort_key(item):
        value = item.get(field)

        # Apply type conversion if we have mixed types
        if has_mixed_types:
            value = _safe_numeric(value)

        # Handle None values (sort to end)
        if value is None:
            return float('inf') if not sort_descending else float('-inf')

        return value

    return sort_key


def _apply_sorting(items: List[Dict[str, Any]], field: str, descending: bool) -> List[Dict[str, Any]]:
    """Apply sorting to items with mixed-type handling and fallback."""
    has_numbers, has_strings = _detect_value_types(items, field)
    has_mixed = has_numbers and has_strings

    sort_key = _create_sort_key(field, has_mixed, descending)

    try:
        items.sort(key=sort_key, reverse=descending)
    except TypeError:
        # Fallback to string comparison if sorting fails
        items.sort(key=lambda item: str(item.get(field) or ''), reverse=descending)

    return items


def _apply_offset_and_limit(items: List[Dict[str, Any]], offset: int, limit: Optional[int]) -> List[Dict[str, Any]]:
    """Apply offset and limit to items list."""
    if offset > 0:
        items = items[offset:]
    if limit is not None:
        items = items[:limit]
    return items


def apply_result_control(items: List[Dict[str, Any]], control: ResultControl) -> List[Dict[str, Any]]:
    """Apply result control to a list of items.

    Args:
        items: List of items (dicts)
        control: ResultControl with sort/limit/offset

    Returns:
        Processed list of items
    """
    result = items[:]

    if control.sort_field:
        result = _apply_sorting(result, control.sort_field, control.sort_descending)

    result = _apply_offset_and_limit(result, control.offset, control.limit)

    return result


def apply_budget_limits(
    items: List[Dict[str, Any]],
    max_items: Optional[int] = None,
    max_bytes: Optional[int] = None,
    max_depth: Optional[int] = None,
    truncate_strings: Optional[int] = None
) -> Dict[str, Any]:
    """Apply budget constraints to results and track truncation.

    Args:
        items: List of result items
        max_items: Stop after N items
        max_bytes: Stop after N bytes (approximate token budget)
        max_depth: Limit nested dict/list depth (not implemented yet)
        truncate_strings: Truncate long string values to N characters

    Returns:
        Dictionary with 'items' and 'meta' keys containing truncation metadata

    Example:
        >>> items = [{'name': 'a'}, {'name': 'b'}, {'name': 'c'}]
        >>> result = apply_budget_limits(items, max_items=2)
        >>> result['meta']['truncated']
        True
        >>> len(result['items'])
        2
    """
    import json

    truncated = False
    truncation_reason = None
    total_available = len(items)
    result_items = items.copy()

    # Apply max_items constraint
    if max_items is not None and len(result_items) > max_items:
        result_items = result_items[:max_items]
        truncated = True
        truncation_reason = 'max_items_exceeded'

    # Apply max_bytes constraint (approximate)
    if max_bytes is not None and not truncated:
        accumulated_bytes = 0
        truncated_at = len(result_items)

        for i, item in enumerate(result_items):
            # Approximate size by JSON serialization
            item_json = json.dumps(item, default=str)
            accumulated_bytes += len(item_json.encode('utf-8'))

            if accumulated_bytes > max_bytes:
                truncated_at = i
                truncated = True
                truncation_reason = 'max_bytes_exceeded'
                break

        if truncated:
            result_items = result_items[:truncated_at]

    # Apply string truncation (to each item's string values)
    if truncate_strings is not None:
        result_items = _truncate_string_values(result_items, truncate_strings)

    # Build metadata
    meta = {
        'truncated': truncated,
        'reason': truncation_reason,
        'total_available': total_available,
        'returned': len(result_items)
    }

    # Add pagination hint if truncated
    if truncated:
        meta['next_cursor'] = f'offset={len(result_items)}'

    return {
        'items': result_items,
        'meta': meta
    }


def _truncate_string_values(items: List[Dict[str, Any]], max_length: int) -> List[Dict[str, Any]]:
    """Truncate long string values in items.

    Args:
        items: List of dictionaries
        max_length: Maximum string length

    Returns:
        List with truncated strings
    """
    result = []
    for item in items:
        truncated_item: Dict[str, Any] = {}
        for key, value in item.items():
            if isinstance(value, str) and len(value) > max_length:
                truncated_item[key] = value[:max_length] + '...'
            elif isinstance(value, dict):
                truncated_item[key] = _truncate_dict_strings(value, max_length)
            elif isinstance(value, list):
                truncated_item[key] = [
                    _truncate_dict_strings(v, max_length) if isinstance(v, dict)
                    else v[:max_length] + '...' if isinstance(v, str) and len(v) > max_length
                    else v
                    for v in value
                ]
            else:
                truncated_item[key] = value
        result.append(truncated_item)
    return result


def _truncate_dict_strings(d: Dict[str, Any], max_length: int) -> Dict[str, Any]:
    """Recursively truncate strings in a dictionary.

    Args:
        d: Dictionary to process
        max_length: Maximum string length

    Returns:
        Dictionary with truncated strings
    """
    result: Dict[str, Any] = {}
    for key, value in d.items():
        if isinstance(value, str) and len(value) > max_length:
            result[key] = value[:max_length] + '...'
        elif isinstance(value, dict):
            result[key] = _truncate_dict_strings(value, max_length)
        elif isinstance(value, list):
            result[key] = [
                _truncate_dict_strings(v, max_length) if isinstance(v, dict)
                else v[:max_length] + '...' if isinstance(v, str) and len(v) > max_length
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result
