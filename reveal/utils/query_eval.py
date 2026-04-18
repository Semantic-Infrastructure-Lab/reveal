"""Filter evaluation: compare_values, apply_filter, apply_filters."""

import re
from typing import Any, Dict, List, Optional

from .query_parser import QueryFilter


def _handle_range_operator(field_value: Any, target_value: Any, opts: dict) -> bool:
    """Handle range operator (..) comparison."""
    if not isinstance(target_value, str) or '..' not in str(target_value):
        return False

    try:
        parts = str(target_value).split('..', 1)
        min_val, max_val = parts[0].strip(), parts[1].strip()

        if opts['coerce_numeric']:
            try:
                field_num = field_value if isinstance(field_value, (int, float)) else float(field_value)
                min_num = float(min_val) if min_val else float('-inf')
                max_num = float(max_val) if max_val else float('inf')
                return min_num <= field_num <= max_num
            except (ValueError, TypeError):
                pass

        return min_val <= str(field_value) <= max_val
    except (ValueError, TypeError, AttributeError):
        return False


def _handle_wildcard_operator(field_value: Any, target_value: Any, opts: dict) -> bool:
    """Handle wildcard operator (*) comparison."""
    pattern_str = str(target_value)
    pattern_str = re.escape(pattern_str).replace(r'\*', '.*')
    try:
        pattern = re.compile(pattern_str, re.IGNORECASE if not opts['case_sensitive'] else 0)
        return bool(pattern.search(str(field_value)))
    except re.error:
        return False


_REGEX_MAX_LEN = 200


def _handle_regex_operator(field_value: Any, operator: str, target_value: Any) -> bool:
    """Handle regex operators (~=, !~)."""
    pattern_str = str(target_value)
    if len(pattern_str) > _REGEX_MAX_LEN:
        return False if operator == '~=' else True
    try:
        pattern = re.compile(pattern_str)
        matches = bool(pattern.search(str(field_value)))
        return matches if operator == '~=' else not matches
    except re.error:
        return False if operator == '~=' else True


def _handle_equality_operator(field_value: Any, operator: str, target_value: Any, opts: dict) -> bool:
    """Handle equality operators (=, !=)."""
    if operator == '=' and isinstance(target_value, str) and '..' in str(target_value):
        return _handle_range_operator(field_value, target_value, opts)

    if opts['coerce_numeric']:
        try:
            field_num = field_value if isinstance(field_value, (int, float)) else float(field_value)
            target_num = float(target_value)
            numeric_equal = field_num == target_num
            return numeric_equal if operator == '=' else not numeric_equal
        except (ValueError, TypeError):
            pass

    field_str = str(field_value).lower() if not opts['case_sensitive'] else str(field_value)
    target_str = str(target_value).lower() if not opts['case_sensitive'] else str(target_value)
    strings_equal = field_str == target_str
    return strings_equal if operator == '=' else not strings_equal


_ORDERED_OPS = {
    '>': lambda a, b: a > b,
    '<': lambda a, b: a < b,
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b,
}


def _apply_ordered_op(a, b, operator: str) -> bool:
    """Apply an ordered comparison operator to two comparable values."""
    fn = _ORDERED_OPS.get(operator)
    return bool(fn(a, b)) if fn else False


def _handle_numeric_operator(field_value: Any, operator: str, target_value: Any, opts: dict) -> bool:
    """Handle numeric comparison operators (>, <, >=, <=)."""
    try:
        field_num = field_value if isinstance(field_value, (int, float)) else float(field_value)
        return _apply_ordered_op(field_num, float(target_value), operator)
    except (ValueError, TypeError):
        if not opts['coerce_numeric']:
            return _apply_ordered_op(str(field_value), str(target_value), operator)
        return False


def _handle_none_comparison(operator: str, target_value: Any, opts: Dict[str, bool]) -> Optional[bool]:
    """Handle comparison when field_value is None."""
    if opts['none_matches_not_equal'] and operator in ('!=', '!~'):
        return True
    if operator == '=' and isinstance(target_value, str) and target_value.lower() == 'null':
        return True
    return False


def _dispatch_comparison(field_value: Any, operator: str, target_value: Any,
                         opts: Dict[str, bool]) -> bool:
    """Dispatch comparison to appropriate operator handler."""
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


def compare_values(
    field_value: Any,
    operator: str,
    target_value: Any,
    options: Optional[Dict[str, bool]] = None
) -> bool:
    """Universal comparison function for all adapters.

    Single source of truth for comparison logic across all adapters.

    Args:
        field_value: The value to compare (from data)
        operator: Comparison operator (=, !=, >, <, >=, <=, ~=, .., ==, !~)
        target_value: The target value to compare against
        options: Optional behavior flags:
            - allow_list_any: Check if any list element matches (default: True)
            - case_sensitive: Case-sensitive string comparison (default: False)
            - coerce_numeric: Try numeric comparison first (default: True)
            - none_matches_not_equal: None matches != operator (default: True)
    """
    opts = {
        'allow_list_any': True,
        'case_sensitive': False,
        'coerce_numeric': True,
        'none_matches_not_equal': True
    }
    if options:
        opts.update(options)

    if operator == '==':
        operator = '='

    if field_value is None:
        return _handle_none_comparison(operator, target_value, opts) or False

    if opts['allow_list_any'] and isinstance(field_value, list):
        return any(compare_values(item, operator, target_value, options) for item in field_value)

    return _dispatch_comparison(field_value, operator, target_value, opts)


def apply_filter(item: Dict[str, Any], filter: QueryFilter) -> bool:
    """Apply a single filter to an item."""
    field_value = item.get(filter.field)

    if filter.op == '!':
        return field_value is None or field_value == ''

    if filter.op == '?':
        return field_value is not None and field_value != ''

    return compare_values(field_value, filter.op, filter.value)


def apply_filters(item: Dict[str, Any], filters: List[QueryFilter]) -> bool:
    """Apply multiple filters to an item (AND logic)."""
    return all(apply_filter(item, f) for f in filters)
