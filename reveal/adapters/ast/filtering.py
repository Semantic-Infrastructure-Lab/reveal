"""Filter matching logic for AST adapter."""

from fnmatch import fnmatch
from typing import Dict, List, Any
from ...utils.query import compare_values


def apply_filters(structures: List[Dict[str, Any]], query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply query filters to collected structures.

    Args:
        structures: List of file structures
        query: Query dict with filter conditions

    Returns:
        Filtered list of matching elements
    """
    results = []

    for structure in structures:
        for element in structure.get('elements', []):
            if matches_filters(element, query):
                results.append(element)

    return results


def matches_filters(element: Dict[str, Any], query: Dict[str, Any]) -> bool:
    """Check if element matches all query filters.

    Args:
        element: Element dict
        query: Query dict with filter conditions

    Returns:
        True if element matches all filters
    """
    for key, condition in query.items():
        # Handle special key mappings
        if key == 'type':
            # Map 'type' to 'category'
            value = element.get('category', '')
            # Normalize singular/plural for type filter
            # Categories are plural (functions, classes) but users may type singular
            condition = normalize_type_condition(condition)
        elif key == 'lines':
            # Map 'lines' to 'line_count'
            value = element.get('line_count', 0)
        elif key == 'decorator':
            # Special handling: check if any decorator matches
            decorators = element.get('decorators', [])
            if not matches_decorator(decorators, condition):
                return False
            continue  # Already handled, skip normal comparison
        else:
            value = element.get(key)

        if value is None:
            return False

        if not compare_value(value, condition):
            return False

    return True


def matches_decorator(decorators: List[str], condition: Dict[str, Any]) -> bool:
    """Check if any decorator matches the condition.

    Supports:
    - Exact match: decorator=property
    - Wildcard: decorator=*cache* (matches @lru_cache, @cached_property, etc.)

    Args:
        decorators: List of decorator strings (e.g., ['@property', '@lru_cache(maxsize=100)'])
        condition: Condition dict with 'op' and 'value'

    Returns:
        True if any decorator matches
    """
    if not decorators:
        return False

    target = condition['value']
    op = condition['op']

    # Normalize target - add @ if not present
    if not target.startswith('@') and not target.startswith('*'):
        target = f'@{target}'

    for dec in decorators:
        # Exact match
        if op == '==':
            # Match decorator name (ignore args)
            # @lru_cache(maxsize=100) should match @lru_cache
            dec_name = dec.split('(')[0]
            if dec_name == target or dec == target:
                return True
        # Wildcard match
        elif op == 'glob':
            if fnmatch(dec, target) or fnmatch(dec, f'@{target}'):
                return True

    return False


def normalize_type_condition(condition: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize type condition to handle singular/plural forms.

    Args:
        condition: Condition dict with 'op' and 'value'

    Returns:
        Normalized condition (singular -> plural)
    """
    # Map singular forms to plural (matching category values)
    singular_to_plural = {
        'function': 'functions',
        'class': 'classes',
        'method': 'methods',
        'struct': 'structs',
        'import': 'imports',
    }

    # Handle 'in' operator (OR logic) - normalize each type
    if condition.get('op') == 'in' and isinstance(condition.get('value'), list):
        normalized = [singular_to_plural.get(t.lower(), t.lower()) for t in condition['value']]
        return {'op': 'in', 'value': normalized}

    # Handle single type
    if condition.get('op') == '==' and isinstance(condition.get('value'), str):
        value = condition['value'].lower()
        if value in singular_to_plural:
            return {'op': '==', 'value': singular_to_plural[value]}

    return condition


def compare_value(value: Any, condition: Dict[str, Any]) -> bool:
    """Compare value against condition.

    Uses unified compare_values() from query.py to eliminate duplication.
    Adapts AST's condition dict format to the standard interface.

    Args:
        value: Actual value
        condition: Condition dict with 'op' and 'value'

    Returns:
        True if comparison passes
    """
    op = condition['op']
    target = condition['value']

    # Special case: 'glob' operator (AST-specific, not in unified parser)
    if op == 'glob':
        # Wildcard pattern matching (case-sensitive)
        return fnmatch(str(value), str(target))

    # Special case: 'in' operator (list membership, AST-specific)
    elif op == 'in':
        # OR logic: check if value matches any in target list
        return str(value) in [str(t) for t in target]

    # All other operators: use unified comparison
    return compare_values(
        value,
        op,
        target,
        options={
            'allow_list_any': False,  # AST doesn't have list fields
            'case_sensitive': True,   # AST comparisons are case-sensitive
            'coerce_numeric': True,
            'none_matches_not_equal': False
        }
    )
