"""Query parsing and formatting for AST adapter."""

from typing import Dict, Any
from ...utils.query import parse_query_filters


def parse_equality_value(key: str, value: str) -> Dict[str, Any]:
    """Parse equality parameter value based on content.

    Args:
        key: Parameter key (e.g., 'type', 'name')
        value: Parameter value to parse

    Returns:
        Filter dict with operator and parsed value
    """
    # Check for OR logic (| or , separator) for type filters
    if key == 'type' and ('|' in value or ',' in value):
        separator = '|' if '|' in value else ','
        types = [t.strip() for t in value.split(separator)]
        return {'op': 'in', 'value': types}

    # Check if value contains wildcards
    if '*' in value or '?' in value:
        return {'op': 'glob', 'value': value}

    # Try to parse as int, otherwise keep as string
    try:
        return {'op': '==', 'value': int(value)}
    except ValueError:
        return {'op': '==', 'value': value}


def parse_query(query_string: str) -> Dict[str, Any]:
    """Parse query string into filter conditions.

    Now uses unified query parser from utils.query while maintaining
    backward compatibility with existing filter format.

    Args:
        query_string: URL query string (e.g., "lines>50&type=function")

    Returns:
        Dict of filter conditions
    """
    if not query_string:
        return {}

    # Use unified query parser to get list of QueryFilter objects
    query_filters = parse_query_filters(query_string)

    # Convert to existing dict format for backward compatibility
    filters: Dict[str, Dict[str, Any]] = {}
    for qf in query_filters:
        key = qf.field
        value = qf.value
        op = qf.op

        # Handle special cases from old _parse_equality_value logic
        if qf.op == '=' and ('|' in str(value) or ',' in str(value)):
            # OR logic for any field: type=class|function, name=main|init
            separator = '|' if '|' in str(value) else ','
            items = [t.strip() for t in str(value).split(separator)]
            filters[key] = {'op': 'in', 'value': items}
        elif qf.op == '*':
            # Wildcard becomes glob operator
            # Support OR logic: name=*run*|*process* → match any pattern
            if '|' in str(value) or ',' in str(value):
                separator = '|' if '|' in str(value) else ','
                patterns = [p.strip() for p in str(value).split(separator)]
                filters[key] = {'op': 'glob', 'value': patterns}
            else:
                filters[key] = {'op': 'glob', 'value': value}
        elif qf.op == '=':
            # Check if value contains range operator (..)
            # Unified parser may have parsed "lines=10..100" as op='=' with value='10..100'
            if isinstance(value, str) and '..' in value:
                # Convert to range operator
                filters[key] = {'op': '..', 'value': value}
            else:
                # AST adapter historically used '==' for all equality checks
                # This maintains backward compatibility with existing behavior
                filters[key] = {'op': '==', 'value': value}
        else:
            # Standard operators (>, <, >=, <=, !=, ~=, ..)
            filters[key] = {'op': op, 'value': value}

    return filters


def format_query(query: Dict[str, Any]) -> str:
    """Format query dict back to readable string.

    Args:
        query: Query dict with filter conditions

    Returns:
        Formatted query string
    """
    if not query:
        return "none"

    parts = []
    for key, condition in query.items():
        op = condition['op']
        val = condition['value']
        if op == 'in':
            # Format OR logic nicely: type=class|function
            parts.append(f"{key}=={'|'.join(val)}")
        else:
            parts.append(f"{key}{op}{val}")
    return " AND ".join(parts)
