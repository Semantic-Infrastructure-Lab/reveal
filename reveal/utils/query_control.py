"""Result control: sorting, pagination, budget limits — ResultControl dataclass."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Tuple

from .query_parser import query_key_recorder

@dataclass(frozen=True)
class BudgetAccounting:
    """A count for one stage, never conflating scan, matching, pages or text."""
    scope: Literal['scan', 'match', 'page', 'text']
    total: int
    returned: int
    exact: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.returned <= self.total:
            raise ValueError('Budget counts require 0 <= returned <= total')

    @property
    def remaining(self) -> int:
        return self.total - self.returned


@dataclass(frozen=True)
class ScanBudget:
    """A source-scan ceiling, distinct from page/text presentation limits.

    None is unlimited; zero admits no candidates. Consumers retain ownership of
    their defaults and overrides while sharing validation and count semantics.
    """
    limit: Optional[int]

    def __post_init__(self) -> None:
        if self.limit is not None and self.limit < 0:
            raise ValueError('Scan limit must be nonnegative')

    def accounting(self, returned: int, capped: bool = False) -> BudgetAccounting:
        """A stopped walk knows at least one additional candidate, not the full total."""
        return BudgetAccounting('scan', returned + int(capped), returned, exact=not capped)


# The query key behind each field, for the flag ledger (BACK-1537).
_FIELD_KEYS = {'sort_field': 'sort', 'sort_descending': 'sort', 'limit': 'limit', 'offset': 'offset'}


@dataclass
class ResultControl:
    """Control parameters for result formatting.

    Attributes:
        sort_field: Field to sort by (None = no sorting)
        sort_descending: Sort in descending order
        limit: Maximum number of results (None = no limit)
        offset: Number of results to skip (default: 0)

    One from ``parse_result_control`` counts its query key as used when a field is read, not
    when it is parsed: git:// parses ?limit= for every view and the file view never reads it.
    """
    sort_field: Optional[str] = None
    sort_descending: bool = False
    limit: Optional[int] = None
    offset: int = 0

    def any_set(self) -> bool:
        """Whether any control was asked for, without counting it as read (BACK-1542).

        A check before applying is not an application: json:// validated ``?limit=`` on an
        object, which it never limits, and the ledger took that for a use.
        """
        fields = object.__getattribute__(self, '__dict__')
        return (fields.get('sort_field', type(self).sort_field) is not None
                or fields.get('limit', type(self).limit) is not None
                or (fields.get('offset', type(self).offset) or 0) > 0)

    def page_start(self) -> int:
        """The ``?offset=`` the adapter's page starts at, without counting it as read.

        The router asks it to continue a page it cut further (``meta.budget.next_cursor``,
        BACK-2276); asking is not applying, as with ``any_set``.
        """
        fields = object.__getattribute__(self, '__dict__')
        return fields.get('offset', type(self).offset) or 0

    def __getattribute__(self, name: str) -> Any:
        key = _FIELD_KEYS.get(name)
        if key is not None:
            reads = object.__getattribute__(self, '__dict__').get('_reads')
            if reads is not None:
                reads.add(key)
        return object.__getattribute__(self, name)


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
    elif part.startswith(('limit=', 'offset=')):
        key, raw = part.split('=', 1)
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValueError(f'{key} must be a non-negative integer: {raw!r}') from exc
        if value < 0:
            raise ValueError(f'{key} must be a non-negative integer: {raw!r}')
        setattr(control, key, value)
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

    applied = []
    for part in query.split('&'):
        part = part.strip()
        if not part:
            continue
        if _apply_control_param(control, part):
            applied.append(part)
        else:
            remaining_parts.append(part)

    vars(control)['_reads'] = query_key_recorder(*applied)  # set last: parsing is not reading
    return '&'.join(remaining_parts), control


def unknown_sort_field_warning(field: Optional[str], items: List[Any],
                               get: Optional[Callable[[Any, str], Any]] = None,
                               sortable: Optional[Iterable[str]] = None) -> Optional[Dict[str, Any]]:
    """The warning for a ``?sort=`` field that no item carries, or None.

    Sorting by a missing field leaves every key equal, so the list comes back in its
    original order and reads as sorted (ast:// BACK-1423; stats://, git://, markdown://
    and json:// until BACK-1644). Every adapter that sorts asks this one question.

    ``get(item, field)`` reads a field the way the adapter's sort does (dotted paths,
    aliases); by default a field is a key of the item. ``sortable`` names the fields to
    suggest; by default, the scalar keys of the items.
    """
    if not field or not items:
        return None
    if get is None:
        if any(isinstance(item, dict) and field in item for item in items):
            return None
    elif any(get(item, field) is not None for item in items):
        return None
    if sortable is None:
        sortable = {k for item in items[:200] if isinstance(item, dict) for k, v in item.items()
                    if isinstance(v, (int, float, str)) and not k.startswith('_')}
    return {
        'type': 'unknown_sort_field',
        'field': field,
        'message': (f"sort field '{field}' is not a field of any result, so results are "
                    f"unsorted. Sortable: {', '.join(sorted(sortable))}"),
    }


def sort_nulls_last(items: List[Any], value: Callable[[Any], Any], descending: bool = False) -> List[Any]:
    """``items`` ordered by ``value(item)``; an item whose value is None (null or missing) goes
    last in either direction, and such items keep their source order.

    The one ``?sort=`` null rule (json:// and ast:// BACK-2276, markdown:// and metrics://
    BACK-2298). Values that do not compare with each other raise TypeError: the caller decides
    whether that is a ``sort_failed`` warning or an ordering as text.
    """
    keyed = [(value(item), item) for item in items]
    valued = [pair for pair in keyed if pair[0] is not None]
    valued.sort(key=lambda pair: pair[0], reverse=descending)
    return [item for _, item in valued] + [item for key, item in keyed if key is None]


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


def _apply_sorting(items: List[Dict[str, Any]], field: str, descending: bool) -> List[Dict[str, Any]]:
    """Sort items by ``field``, nulls last (``sort_nulls_last``). Numbers beside text compare as
    numbers, text that is not a number counting as null; values that still do not compare
    (a dict and a number) order as text."""
    has_numbers, has_strings = _detect_value_types(items, field)
    if has_numbers and has_strings:
        def value(item: Dict[str, Any]) -> Any:
            return _safe_numeric(item.get(field))
    else:
        def value(item: Dict[str, Any]) -> Any:
            return item.get(field)

    try:
        return sort_nulls_last(items, value, descending)
    except TypeError:
        return sort_nulls_last(items, lambda item: None if value(item) is None else str(value(item)), descending)


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
    truncate_strings: Optional[int] = None,
    offset: int = 0
) -> Dict[str, Any]:
    """Apply budget constraints to results and track truncation.

    ``offset`` is where ``items`` starts in the whole answer (the request's ``?offset=``):
    the cut's ``next_cursor`` continues from there, not from 0 (BACK-2276).

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

    accounting = BudgetAccounting('page', total_available, len(result_items))
    meta = {
        'truncated': truncated,
        'reason': truncation_reason,
        'total_available': accounting.total,
        'returned': accounting.returned
    }

    if truncated:
        meta['next_cursor'] = f'offset={offset + len(result_items)}'

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


def omitted_line(total: int, shown: int, indent: str = '  ') -> str:
    """The "... and N more" footer for a text list cut at *shown* of *total*; '' when
    nothing was cut. JSON carries every item, so the footer says where to find them
    (BACK-1550)."""
    remaining = total - shown
    if remaining <= 0:
        return ''
    return f"{indent}... and {remaining} more (--format json lists all)"
