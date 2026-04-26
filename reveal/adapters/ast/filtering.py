"""Filter matching logic for AST adapter."""

import re
from fnmatch import fnmatch
from typing import Dict, List, Any
from ...utils.query import compare_values


def apply_filters(structures: List[Dict[str, Any]], query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply query filters to collected structures.

    When a name= glob filter is used without an explicit type= filter, import
    declarations are excluded from results. Use type=import to find imports.

    Args:
        structures: List of file structures
        query: Query dict with filter conditions

    Returns:
        Filtered list of matching elements
    """
    # If name= glob is active but no type= filter, skip imports by default.
    # This avoids cluttering results with import declarations when the user
    # is searching for defs/calls (the common case).
    exclude_imports = (
        'name' in query
        and query['name'].get('op') == 'glob'
        and 'type' not in query
    )

    results = []

    for structure in structures:
        for element in structure.get('elements', []):
            if exclude_imports and element.get('category') == 'imports':
                continue
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
        elif key == 'calls':
            # calls=<name>: find functions whose calls list contains <name>
            # Supports bare name match or attribute suffix: "validate_item" matches "self.validate_item"
            if not _matches_call_list(element.get('calls', []), condition):
                return False
            continue
        elif key == 'callee_of':
            # callee_of=<name>: find functions whose called_by list contains <name>
            if not _matches_call_list(element.get('called_by', []), condition):
                return False
            continue
        elif key == 'param_type':
            # param_type=dict: find functions where any param has this type annotation
            if not _matches_param_type(element.get('signature', ''), condition):
                return False
            continue
        elif key == 'return_type':
            # return_type=bool: find functions with this return annotation
            if not _matches_return_type(element.get('signature', ''), condition):
                return False
            continue
        elif key == 'has_annotations':
            # has_annotations=false: fully unannotated functions (no param or return hints)
            # has_annotations=true: at least one annotation present
            if not compare_value(_has_annotations(element.get('signature', '')), condition):
                return False
            continue
        elif key == 'callers':
            # callers>N: filter by number of inbound callers (length of called_by list)
            if not compare_value(len(element.get('called_by', [])), condition):
                return False
            continue
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
        # Support single pattern or OR list: name=*run*|*process*
        if isinstance(target, list):
            return any(fnmatch(str(value), str(p)) for p in target)
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


def _matches_param_type(signature: str, condition: Dict[str, Any]) -> bool:
    """Check if any parameter in the signature has the given type annotation.

    Parses ': TYPE' patterns from the parameter section of a signature string
    like '(x: dict, y: str) -> bool'. Supports exact match and glob patterns.

    Examples:
        param_type=dict   matches (x: dict, y: str)
        param_type=Dict*  matches (x: Dict[str, Any])
    """
    param_str = signature.split(' -> ')[0] if ' -> ' in signature else signature
    # Extract bare type names after ': ' (handles generics like Dict[str, Any])
    types = re.findall(r':\s*([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])*)', param_str)
    target = str(condition['value'])
    op = condition['op']
    for t in types:
        bare = t.split('[')[0]  # Dict[str, Any] → Dict for glob matching
        for candidate in {t, bare}:
            if op in ('==', '=') and candidate == target:
                return True
            elif op == 'glob' and fnmatch(candidate, target):
                return True
            elif op == '~=':
                if re.search(target, candidate):
                    return True
    return False


def _matches_return_type(signature: str, condition: Dict[str, Any]) -> bool:
    """Check if the return annotation matches the condition.

    Parses the ' -> TYPE' suffix of a signature string.
    Supports exact match and glob patterns.

    Examples:
        return_type=bool   matches (...) -> bool
        return_type=List*  matches (...) -> List[str]
        return_type=None   matches (...) -> None
    """
    if ' -> ' not in signature:
        return False
    return_part = signature.split(' -> ', 1)[1].strip().rstrip(':').strip()
    bare = return_part.split('[')[0]
    target = str(condition['value'])
    op = condition['op']
    for candidate in {return_part, bare}:
        if op in ('==', '=') and candidate == target:
            return True
        elif op == 'glob' and fnmatch(candidate, target):
            return True
        elif op == '~=':
            if re.search(target, candidate):
                return True
    return False


def _matches_call_list(call_list: List[str], condition: Dict[str, Any]) -> bool:
    """Check if any entry in a calls/called_by list satisfies the condition.

    Supports bare name match with attribute suffix stripping:
    - "validate_item" matches "validate_item" and "self.validate_item"
    - Glob patterns supported: "self.*" matches "self.bar"

    Args:
        call_list: List of callee/caller name strings
        condition: Condition dict with 'op' and 'value'

    Returns:
        True if any entry in call_list matches the condition
    """
    target = str(condition['value'])
    op = condition['op']

    for entry in call_list:
        # Also check the bare suffix (strips "self.", "obj.", etc.)
        local_name = entry.split('.')[-1]
        for candidate in {entry, local_name}:
            if op in ('==', '='):
                if candidate == target:
                    return True
            elif op == 'glob':
                if fnmatch(candidate, target):
                    return True
            elif op == '~=':
                import re
                if re.search(target, candidate):
                    return True
    return False


def _has_annotations(signature: str) -> bool:
    """Return True if the signature contains any type annotation.

    Checks for return annotation (->) or param annotations (: inside parens).
    """
    if not signature:
        return False
    if '->' in signature:
        return True
    paren_open = signature.find('(')
    paren_close = signature.rfind(')')
    if paren_open == -1 or paren_close == -1:
        return False
    params = signature[paren_open + 1:paren_close]
    return ':' in params
