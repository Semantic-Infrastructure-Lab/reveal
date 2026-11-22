"""Query parsing and formatting for AST adapter."""

from typing import Any, Dict, Iterator, List, Optional, Tuple
from ...utils.query import parse_query_filters
from ...utils.query_parser import coerce_value


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


# A key given more than once (``type=function&type!=method``, ``lines>3&lines<8``) holds
# ``{'op': ALL_OP, 'value': [condition, ...]}``; every condition must match (BACK-2307).
ALL_OP = 'all'


# Filter keys whose element value is a count (``lines`` reads ``line_count``, ``callers`` counts
# ``called_by``); a comparison of one with a non-number can never match.
NUMERIC_FILTER_KEYS = frozenset({'lines', 'line_count', 'complexity', 'depth', 'callers', 'line'})
_ORDERING_OPS = frozenset({'>', '<', '>=', '<='})
_TEXT_OPS = frozenset({'~=', '!~', 'glob'})


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _non_numbers(condition: Dict[str, Any]) -> List[str]:
    """The parts of one condition's value that are not numbers."""
    op, value = condition.get('op'), condition.get('value')
    if op == '..':
        return [end for end in str(value).split('..') if end and not _is_number(end)]
    if op == 'in':
        return [str(part) for part in value or () if not _is_number(part)]
    return [] if _is_number(value) else [str(value)]


def validate_filter_values(query: Dict[str, Any]) -> None:
    """Reject a filter value that can never match (BACK-2531): a numeric field, or an ordering
    comparison of any field, given a non-number (``complexity>abc``, ``complexity>>3``,
    ``name>a``). Raises ValueError, which the adapter reports as an invalid request (exit 2)."""
    for key, condition in condition_pairs(query):
        op = condition.get('op')
        if op in _TEXT_OPS or not (key in NUMERIC_FILTER_KEYS or op in _ORDERING_OPS):
            continue
        bad = _non_numbers(condition)
        if bad:
            what = f'{key} is a number' if key in NUMERIC_FILTER_KEYS else f"'{op}' compares numbers"
            raise ValueError(
                f"filter on {key!r}: {what}, and {', '.join(repr(b) for b in bad)} is not, "
                "so it would match nothing. See: reveal help://ast")


def condition_pairs(query: Dict[str, Any]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Each ``(key, condition)`` of *query*, one pair per condition of a repeated key."""
    for key, condition in query.items():
        if condition.get('op') == ALL_OP:
            for part in condition['value']:
                yield key, part
        else:
            yield key, condition


def _split_alternatives(value: Any) -> List[str]:
    separator = '|' if '|' in str(value) else ','
    return [t.strip() for t in str(value).split(separator)]


def _condition(op: str, value: Any) -> Dict[str, Any]:
    """The filter condition of one parsed ``key op value``."""
    if op == '=' and isinstance(value, str) and value.startswith('='):
        # ``complexity==5``: the shared parser reads '=' and leaves '=5' as the value, which
        # matched nothing; '==' is equality, as it reads (BACK-2531).
        value = value[1:]
    if isinstance(value, str) and op not in ('~=', '!~'):
        # Keep numeric literals distinct from actual true/false predicates.
        value = int(value) if value in ('0', '1') else coerce_value(value)
    has_alternatives = '|' in str(value) or ',' in str(value)
    if op == '=' and has_alternatives:
        # OR logic for any field: type=class|function, name=main|init
        return {'op': 'in', 'value': _split_alternatives(value)}
    if op == '*':
        # Wildcard becomes glob; name=*run*|*process* matches any pattern
        return {'op': 'glob', 'value': _split_alternatives(value) if has_alternatives else value}
    if op == '=':
        # The unified parser leaves "lines=10..100" as op '=' with value '10..100'
        if isinstance(value, str) and '..' in value:
            return {'op': '..', 'value': value}
        # AST adapter historically used '==' for all equality checks
        return {'op': '==', 'value': value}
    # Standard operators (>, <, >=, <=, !=, ~=, ..)
    return {'op': op, 'value': value}


def parse_query(query_string: str) -> Dict[str, Any]:
    """Parse query string into filter conditions.

    Uses the unified query parser from utils.query and keys its conditions by field.
    A field given once maps to its condition; a field given more than once maps to an
    ``ALL_OP`` condition that holds each of them, so they AND instead of the last one
    replacing the rest (BACK-2307).

    Args:
        query_string: URL query string (e.g., "lines>50&type=function")

    Returns:
        Dict of filter conditions
    """
    if not query_string:
        return {}

    by_key: Dict[str, List[Dict[str, Any]]] = {}
    for qf in parse_query_filters(query_string, coerce_numeric=False):
        by_key.setdefault(qf.field, []).append(_condition(qf.op, qf.value))
    return {
        key: conditions[0] if len(conditions) == 1 else {'op': ALL_OP, 'value': conditions}
        for key, conditions in by_key.items()
    }


def format_query(query: Dict[str, Any], names: Optional[Dict[str, str]] = None) -> str:
    """Format query dict back to readable string.

    Args:
        query: Query dict with filter conditions
        names: Engine field -> the name to print it as (the canonical field of a retired word)

    Returns:
        Formatted query string
    """
    if not query:
        return "none"

    parts = []
    for engine_key, condition in condition_pairs(query):
        key = (names or {}).get(engine_key, engine_key)
        op = condition['op']
        val = condition['value']
        if op == 'in':
            # Format OR logic nicely: type=class|function
            parts.append(f"{key}=={'|'.join(val)}")
        elif op.isalpha():
            # A word operator (glob) glued on printed 'nameglob*x*', which the
            # hint code then read as an unknown key 'nameglob' (BACK-1510).
            parts.append(f"{key}={val} ({op})")
        else:
            parts.append(f"{key}{op}{val}")
    return " AND ".join(parts)
