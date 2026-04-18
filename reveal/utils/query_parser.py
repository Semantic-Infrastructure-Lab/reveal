"""Query string parsing: query params, filter expressions, QueryFilter dataclass."""

import re as _re  # noqa: F401 — imported for use by query_eval, kept here for consumers
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union


def coerce_value(value: str) -> Union[bool, int, float, str]:
    """Coerce a string value to its appropriate type."""
    if not isinstance(value, str):
        return value

    if value.lower() in ('true', 'false', 'yes', 'no', '1', '0'):
        return value.lower() in ('true', 'yes', '1')

    try:
        if '.' in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def parse_query_params(query: str, coerce: bool = False) -> Dict[str, Any]:
    """Parse URL query string into parameter dictionary."""
    if not query:
        return {}

    params = {}
    for part in query.split('&'):
        part = part.strip()
        if not part:
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
        if self.op == '==':
            self.op = '='

        if self.op not in self.VALID_OPERATORS:
            raise ValueError(f"Invalid operator: {self.op}. Must be one of {sorted(self.VALID_OPERATORS)}")


def _try_parse_negation_filter(part: str) -> Optional[QueryFilter]:
    """Try to parse negation filter (!field)."""
    if part.startswith('!'):
        field = part[1:].strip()
        if field:
            return QueryFilter(field, '!', '')
    return None


def _try_parse_two_char_operators(part: str, coerce_numeric: bool) -> Optional[QueryFilter]:
    """Try to parse two-character operators (>=, <=, !=, ~=, !~)."""
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
    """Parse special cases for = operator (wildcards, ranges)."""
    if '*' in value:
        return QueryFilter(field, '*', value)

    if '..' in value:
        return QueryFilter(field, '..', value)

    return None


def _try_parse_single_char_operators(part: str, coerce_numeric: bool) -> Optional[QueryFilter]:
    """Try to parse single-character operators (>, <, =)."""
    for op in ['>', '<', '=']:
        if op not in part:
            continue
        field, value = part.split(op, 1)
        field = field.strip()
        value = value.strip()
        if op == '=':
            special_filter = _parse_equals_special_cases(field, value)
            if special_filter:
                return special_filter
        final_value: Union[bool, int, float, str] = coerce_value(value) if coerce_numeric else value
        return QueryFilter(field, op, final_value)
    return None


def parse_query_filters(
    query: str,
    coerce_numeric: bool = True,
    support_existence: bool = True
) -> List[QueryFilter]:
    """Parse query string into list of QueryFilter objects.

    Supports operators: >, <, >=, <=, =, ==, !=, ~=, .., ?, !
    """
    if not query:
        return []

    filters = []
    parts = query.split('&')

    for part in parts:
        part = part.strip()
        if not part:
            continue

        parsed_filter = None

        if support_existence:
            parsed_filter = _try_parse_negation_filter(part)
            if parsed_filter:
                filters.append(parsed_filter)
                continue

        parsed_filter = _try_parse_two_char_operators(part, coerce_numeric)
        if parsed_filter:
            filters.append(parsed_filter)
            continue

        parsed_filter = _try_parse_single_char_operators(part, coerce_numeric)
        if parsed_filter:
            filters.append(parsed_filter)
            continue

        if support_existence:
            filters.append(QueryFilter(part, '?', ''))

    return filters
