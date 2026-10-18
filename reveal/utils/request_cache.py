"""Owner-registered caches whose evidence is valid for one serialized host request.

Owners register only caches with reproduced edit-staleness. Grammar and disk
caches have independent invalidation policies and do not belong here. Hosts
hold their request lock across both reset and evaluation.

Two lifetimes:

* ``register_request_cache`` -- cheap to rebuild: reset at every request.
* ``register_validated_cache`` -- expensive per-root indexes (BACK-1825). An entry
  survives a request only while a stat fingerprint of its tree (path, mtime, size of
  every walked file) is unchanged, so a repeated call on an unchanged project does not
  rebuild a D005/T006/M102/I002 index, and an edit still drops it.
"""
import hashlib
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, MutableMapping, Optional, Tuple

_RESETTERS: Dict[str, Callable[[], None]] = {}
_VALIDATED: Dict[str, Tuple[MutableMapping[Any, Any], Callable[[Path], None]]] = {}
_STAMPS: Dict[Tuple[str, Path], str] = {}


def register_request_cache(name: str, reset: Callable[[], None]) -> None:
    """Give a cache owner one explicit place to declare its request lifetime."""
    _RESETTERS[name] = reset


def register_validated_cache(name: str, cache: MutableMapping[Any, Any],
                             evict: Callable[[Path], None]) -> None:
    """Declare a ``{root: index}`` cache that lives while its root's tree is unchanged.

    *evict(root)* must drop everything the owner recorded for that root, including
    skip reasons, so a rebuild re-records them.
    """
    _VALIDATED[name] = (cache, evict)


def _tree_stamp(root: Path, started_ns: Optional[int] = None) -> Optional[str]:
    """Fingerprint of the files a walk of *root* reaches; None when it cannot be trusted.

    None means: the root is gone, or (with *started_ns*) a file changed at or after the
    request began, so an index built during the request may predate that edit.
    """
    from .path_utils import EVIDENCE, _walk_code_files
    if not root.is_dir():
        return None
    hasher = hashlib.sha256()
    enumeration_errors: List[OSError] = []
    try:
        # EVIDENCE is the widest walk the owners use (it ignores --exclude).
        for path in sorted(_walk_code_files(root, purpose=EVIDENCE, on_error=enumeration_errors.append)):
            st = os.stat(path)
            if started_ns is not None and st.st_mtime_ns >= started_ns:
                return None
            hasher.update(f'{path}\0{st.st_mtime_ns}\0{st.st_size}\n'.encode('utf-8', 'surrogateescape'))
    except OSError:
        return None
    return None if enumeration_errors else hasher.hexdigest()


def reset_request_caches() -> None:
    """Reset imported owners; a new owner first imported during a request is cold.

    A validated entry is kept only when its recorded stamp equals the tree's current
    stamp; an entry with no stamp (built outside a request) is dropped.
    """
    for reset in tuple(_RESETTERS.values()):
        reset()
    seen: Dict[Path, Optional[str]] = {}
    for name, (cache, evict) in tuple(_VALIDATED.items()):
        for root in tuple(cache):
            if root not in seen:
                seen[root] = _tree_stamp(root)
            recorded = _STAMPS.get((name, root))
            if recorded is None or recorded != seen[root]:
                evict(root)
                _STAMPS.pop((name, root), None)
        for key in [k for k in _STAMPS if k[0] == name and k[1] not in cache]:
            del _STAMPS[key]


def seal_request_caches(started_ns: int) -> None:
    """Record the stamp of every validated entry built during the request that began at
    *started_ns*. Entries whose tree changed since the request began stay unstamped, so
    the next request rebuilds them."""
    seen: Dict[Path, Optional[str]] = {}
    for name, (cache, _evict) in tuple(_VALIDATED.items()):
        for root in tuple(cache):
            if (name, root) in _STAMPS:
                continue
            if root not in seen:
                seen[root] = _tree_stamp(root, started_ns)
            stamp = seen[root]
            if stamp is not None:
                _STAMPS[(name, root)] = stamp


def request_started_ns() -> int:
    return time.time_ns()
