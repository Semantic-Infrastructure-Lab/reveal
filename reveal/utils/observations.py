"""Preserve measured answer containers across presentation, using existing cut receipts."""
from typing import Any, Dict, Iterable, Optional, Tuple

from .results import truncations_of

ObservationCounts = Dict[Tuple[str, ...], Optional[Tuple[type, int]]]


def _field_at(result, path):
    value = result
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def count_observations(result: dict, paths: Iterable[Tuple[str, ...]]) -> ObservationCounts:
    return {path: (type(value), len(value)) if isinstance(value, (list, str, dict)) else None
            for path in paths for value in (_field_at(result, path),)}


def _count(value: Any) -> bool:
    return type(value) is int and value >= 0


def has_truncation_receipt(result, path, shown, previous):
    return any(receipt.get('field') == '.'.join(path)
               and _count(receipt.get('shown')) and receipt['shown'] == shown
               and _count(receipt.get('total')) and receipt['total'] >= previous
               for receipt in truncations_of(result))


def validate_observation_counts(result, previous: ObservationCounts, current: ObservationCounts,
                                *, label='Answer') -> Optional[str]:
    for path, before in previous.items():
        after = current.get(path)
        if before is None or after is None or before[0] is not after[0]:
            return f'{label} answer missing required observation containers'
        if after[1] > before[1]:
            return f'{label} presentation cannot create new source observations'
        if after[1] < before[1] and not has_truncation_receipt(result, path, after[1], before[1]):
            return f'{label} presentation removed observations without a matching truncation receipt'
    if any(value and value[1] for path, value in current.items() if path not in previous):
        return f'{label} presentation cannot create new source observations'
    return None
