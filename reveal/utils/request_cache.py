"""Owner-registered caches whose evidence is valid for one serialized host request.

Owners register only caches with reproduced edit-staleness. Grammar and disk
caches have independent invalidation policies and do not belong here. Hosts
hold their request lock across both reset and evaluation.
"""
from typing import Callable, Dict

_RESETTERS: Dict[str, Callable[[], None]] = {}


def register_request_cache(name: str, reset: Callable[[], None]) -> None:
    """Give a cache owner one explicit place to declare its request lifetime."""
    _RESETTERS[name] = reset


def reset_request_caches() -> None:
    """Reset imported owners; a new owner first imported during a request is cold."""
    for reset in tuple(_RESETTERS.values()):
        reset()
