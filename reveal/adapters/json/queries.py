"""Query and filtering functions for JSON adapter."""

from typing import Any, List, Dict

from ...utils.query import compare_values, ResultControl


def get_field_value(obj: Any, field: str) -> Any:
    """Get field value from JSON object, supporting nested paths.

    Args:
        obj: JSON object (dict)
        field: Field name, supports dot notation (e.g., 'user.name')

    Returns:
        Field value or None if not found
    """
    if not isinstance(obj, dict):
        return None

    # Support nested field access with dot notation
    parts = field.split('.')
    current = obj

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None

    return current


def compare(field_value: Any, operator: str, target_value: Any) -> bool:
    """Compare field value against target using operator.

    Uses unified compare_values() from query.py to eliminate duplication.

    Args:
        field_value: Value from JSON object
        operator: Comparison operator (=, >, <, >=, <=, !=, ~=, ..)
        target_value: Target value to compare against (can be bool, int, float, or str)

    Returns:
        True if comparison passes, False otherwise
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


def matches_all_filters(obj: Any, query_filters: list, get_field_value_func, compare_func) -> bool:
    """Check if object matches all query filters.

    Args:
        obj: JSON object to test
        query_filters: List of query filter objects
        get_field_value_func: Function to extract field values
        compare_func: Function to compare values

    Returns:
        True if matches all filters, False otherwise
    """
    if not query_filters:
        return True

    for qf in query_filters:
        field_value = get_field_value_func(obj, qf.field)
        if not compare_func(field_value, qf.op, qf.value):
            return False

    return True


def filter_array(arr: List[Any], query_filters: list, get_field_value_func, compare_func) -> List[Any]:
    """Filter array elements based on query filters.

    Args:
        arr: Array to filter
        query_filters: List of query filter objects
        get_field_value_func: Function to extract field values
        compare_func: Function to compare values

    Returns:
        Filtered array
    """
    if not query_filters:
        return arr

    return [
        item for item in arr
        if matches_all_filters(item, query_filters, get_field_value_func, compare_func)
    ]


def apply_result_control(
    arr: List[Any],
    result_control: ResultControl,
    get_field_value_func
) -> tuple[List[Any], Dict[str, Any]]:
    """Apply result control (sort, limit, offset) to array.

    Args:
        arr: Array to control
        result_control: Result control configuration
        get_field_value_func: Function to extract field values for sorting

    Returns:
        Tuple of (controlled array, metadata dict)
    """
    metadata: Dict[str, Any] = {}
    total_matches = len(arr)
    controlled = arr

    # Sort
    if result_control.sort_field:
        try:
            field = result_control.sort_field
            reverse = result_control.sort_descending

            def sort_key(item):
                """Extract sort key from item."""
                value = get_field_value_func(item, field)
                # Handle None values (sort to end)
                if value is None:
                    return (1, '') if not reverse else (0, '')
                return (0, value)

            controlled = sorted(controlled, key=sort_key, reverse=reverse)
        except Exception:
            # If sorting fails, continue without sorting
            pass

    # Offset
    if result_control.offset is not None and result_control.offset > 0:
        controlled = controlled[result_control.offset:]

    # Limit
    if result_control.limit is not None:
        controlled = controlled[:result_control.limit]

    # Add truncation warning if results were limited
    displayed = len(controlled)
    if displayed < total_matches:
        metadata['warnings'] = [{
            'type': 'truncated',
            'message': f'Results truncated: showing {displayed} of {total_matches} total matches'
        }]
        metadata['displayed_results'] = displayed
        metadata['total_matches'] = total_matches

    return controlled, metadata


def navigate_to_path(data: Any, json_path: List[str | int], slice_spec: tuple | None) -> Any:
    """Navigate to the specified JSON path.

    Args:
        data: Root JSON data
        json_path: List of path components (keys and indices)
        slice_spec: Optional tuple of (start, end) for array slicing

    Returns:
        Value at the specified path

    Raises:
        KeyError: If key not found
        IndexError: If array index out of range
        TypeError: If cannot navigate into value type
    """
    current = data
    for key in json_path:
        if isinstance(current, dict):
            if str(key) not in current:
                raise KeyError(f"Key not found: {key}")
            current = current[str(key)]
        elif isinstance(current, list):
            if not isinstance(key, int):
                raise TypeError(f"Array index must be integer, got: {key}")
            if key >= len(current) or key < -len(current):
                raise IndexError(f"Array index out of range: {key}")
            current = current[key]
        else:
            raise TypeError(f"Cannot navigate into {type(current).__name__}")

    # Apply slice if specified
    if slice_spec and isinstance(current, list):
        start, end = slice_spec
        current = current[start:end]

    return current
