"""Query string parsing: query params, filter expressions, QueryFilter dataclass."""

import re as _re  # noqa: F401 — imported for use by query_eval, kept here for consumers
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, TextIO, Union

# Characters that only appear in a *filter* key (e.g. `complexity>10`, `msg~=x`),
# never in a fixed param key. Used to distinguish the two in adapters that parse
# the same query string as both params and filters (stats://, git://).
_FILTER_OP_CHARS = frozenset('<>~!')


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


def warn_unknown_query_params(
    query_params: Dict[str, Any],
    known_keys: Iterable[str],
    *,
    adapter: str = '',
    skip_filter_keys: bool = False,
    stream: Optional[TextIO] = None,
) -> List[str]:
    """Warn (to stderr) about query params an adapter doesn't recognize.

    Closed-param adapters read a fixed key set via ``.get()`` and silently
    ignore everything else, so a typo'd or unsupported param (the BACK-507
    repro ``stats://?complexity=true``) returns a valid-looking-but-wrong
    result with no signal. This surfaces that: it emits one stderr warning per
    unrecognized key and returns the list, but does *not* raise — the result is
    still produced (a warning contract, not an error contract).

    Args:
        query_params: parsed ``{key: value}`` dict from ``parse_query_params``.
        known_keys: the adapter's recognized param names (its closed set,
            usually ``get_schema()['query_params'].keys()``).
        adapter: scheme name for the message (e.g. ``'stats'``).
        skip_filter_keys: for *mixed* adapters (``stats://``, ``git://``) that
            parse the same query string as both params and filters — skip any
            key carrying a filter operator (``< > ~ !``), since those are filter
            expressions (``complexity>10``), not fixed params, and are handled
            by the filter parser.
        stream: output stream (defaults to ``sys.stderr``; injectable for tests).

    Returns:
        The list of unrecognized keys (empty if all recognized).
    """
    out = stream if stream is not None else sys.stderr
    known = set(known_keys)
    unknown = []
    for key in query_params:
        if key in known:
            continue
        if skip_filter_keys and any(c in _FILTER_OP_CHARS for c in key):
            continue  # a filter expression, not a fixed param — handled elsewhere
        unknown.append(key)

    if unknown:
        prefix = f"{adapter}://" if adapter else "this resource"
        valid = ', '.join(sorted(known)) if known else '(none)'
        for key in unknown:
            print(
                f"⚠ Unknown query param '{key}' for {prefix} — ignored. "
                f"Valid params: {valid}",
                file=out,
            )

    return unknown


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
    """Try to parse two-character operators (>=, <=, !=, ~=, !~).

    Also handles reversed/doubled forms: => -> >=, =< -> <=, =>= -> >=, =<= -> <=.
    """
    for op in ['>=', '<=', '!=', '~=', '!~']:
        if op in part:
            field, value_str = part.split(op, 1)
            field = field.strip()
            # Strip a spurious trailing = left by =>=, =<= patterns (e.g. field=>=10 -> field>=10)
            if field.endswith('='):
                field = field[:-1].strip()
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
    """Try to parse single-character operators (>, <, =).

    Also handles reversed forms: => -> >=, =< -> <= (field=trailing-= stripped, op promoted).
    """
    for op in ['>', '<', '=']:
        if op not in part:
            continue
        field, value = part.split(op, 1)
        field = field.strip()
        value = value.strip()
        # Detect reversed-operator typos: field=>val or field=<val
        # The trailing = on the field means the user wrote => or =< instead of >= or <=
        if op in ('>', '<') and field.endswith('='):
            field = field[:-1].strip()
            op = '>=' if op == '>' else '<='
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
