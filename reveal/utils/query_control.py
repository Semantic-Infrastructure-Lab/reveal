"""Result control: sorting, pagination, budget limits — ResultControl dataclass."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


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


def _apply_sort_param(control: ResultControl, sort_field: str) -> None:
    """Apply a sort=field or sort=-field value to the control object."""
    if sort_field.startswith('-'):
        control.sort_descending = True
        control.sort_field = sort_field[1:]
    else:
        control.sort_descending = False
        control.sort_field = sort_field


def _apply_control_param(control: ResultControl, part: str) -> bool:
    """Apply one query control parameter to control object. Returns True if consumed."""
    if part.startswith('sort='):
        _apply_sort_param(control, part[5:])
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
        return False
    return True


def parse_result_control(query: str) -> Tuple[str, ResultControl]:
    """Parse result control parameters from query string.

    Extracts sort=field, sort=-field, limit=N, offset=M parameters.

    Returns:
        Tuple of (cleaned_query, ResultControl)
    """
    if not query:
        return '', ResultControl()

    control = ResultControl()
    remaining_parts = []

    for part in query.split('&'):
        part = part.strip()
        if part and not _apply_control_param(control, part):
            remaining_parts.append(part)

    return '&'.join(remaining_parts), control


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
    """Detect if field values are numeric, string, or mixed."""
    values = [item.get(field) for item in items]
    has_numbers = any(isinstance(v, (int, float)) and v is not None for v in values)
    has_strings = any(isinstance(v, str) for v in values)
    return has_numbers, has_strings


def _create_sort_key(field: str, has_mixed_types: bool, sort_descending: bool):
    """Create sort key function for given field and type context."""
    def sort_key(item):
        value = item.get(field)

        if has_mixed_types:
            value = _safe_numeric(value)

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
    """Apply result control to a list of items."""
    result = items[:]

    if control.sort_field:
        result = _apply_sorting(result, control.sort_field, control.sort_descending)

    result = _apply_offset_and_limit(result, control.offset, control.limit)

    return result


def apply_budget_limits(
    items: List[Dict[str, Any]],
    max_items: Optional[int] = None,
    truncate_strings: Optional[int] = None
) -> Dict[str, Any]:
    """Apply budget constraints to results and track truncation.

    Returns:
        Dictionary with 'items' and 'meta' keys containing truncation metadata
    """
    truncated = False
    truncation_reason = None
    total_available = len(items)
    result_items = items.copy()

    if max_items is not None and len(result_items) > max_items:
        result_items = result_items[:max_items]
        truncated = True
        truncation_reason = 'max_items_exceeded'

    if truncate_strings is not None:
        result_items = _truncate_string_values(result_items, truncate_strings)

    meta = {
        'truncated': truncated,
        'reason': truncation_reason,
        'total_available': total_available,
        'returned': len(result_items)
    }

    if truncated:
        meta['next_cursor'] = f'offset={len(result_items)}'

    return {
        'items': result_items,
        'meta': meta
    }


def _truncate_string_values(items: List[Dict[str, Any]], max_length: int) -> List[Dict[str, Any]]:
    """Truncate long string values in items."""
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
    """Recursively truncate strings in a dictionary."""
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
