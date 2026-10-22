"""Persisted raw result of one surface scanner on one file (BACK-2151).

``reveal surface`` runs a per-language scanner over every file, and the scan is nearly all of the
command: the type filter, the directory-loss validation, the cross-file route passes and the
rendering run on what the scanners return. A DD scan runs ``surface`` once per type (nine times)
and each run re-scanned every file. This module keeps the scanner's FULL result per file in the
disk cache, so a repeat run, or a run for another type, scans only files that changed.

Namespace ``surface-file`` (``disk_cache``, so build-keyed: an edit to reveal, tree-sitter or the
language pack lands in a different directory and is never read). One entry per source file, capped
by ``REVEAL_STRUCTURE_CACHE_MAX_FILES`` like the structure cache (same sizing problem: one entry per
file). Key: sha256 of (absolute path, the path spelling the scanner received, mtime_ns, size, scanner
identity, interpreter minor version for the scanner that uses the stdlib ``ast``).

What the key is not: a content hash. It inherits the structure cache's hole: an edit that keeps both
mtime_ns and size is not seen. The stat is taken before the scan and again after it; the entry is
stored only when they agree, so an edit during the scan cannot file the old result under the new
stat (the BACK-2116 narrowing for the structure cache).

What is stored: the scanner's complete result, as returned, before anything the caller does to it
(``UNPARSED_KEY``, ``RECOVERED_KEY`` and ``ROUTE_CLASSES_KEY`` ride inside it). Never a type-filtered
result and never one merged across files: a typed run validates only its own category under
directory loss (BACK-2028), so a typed result is not always a projection of the untyped one, and the
cross-file passes need every file's classes. Each hit is a fresh unpickled object, so the caller's
pops and the route passes' mutations can not reach the stored copy.

What is never stored: a result that is not a dict, one that fails full validation, and one that
lists the file as unparsed. The scanners fold a read error, a missing grammar and a syntax error into
the same ``UNPARSED_KEY`` row, so the cause is not visible from the result, and a failure the
content did not cause must not be served on (BACK-2138); such a file is scanned again on the next
run, as it is without a cache. A scan that raises stores nothing and re-raises. A hit is also not
served when the file is not readable now (``chmod`` changes neither mtime nor size).
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core import disk_cache
from .ast.surface_matrix import UNPARSED_KEY

_SURFACE_FILE_NAMESPACE = 'surface-file'

# Bumped when the stored shape changes. disk_cache's build directory already separates code
# versions; this guards a dev checkout whose reveal files did not change but this module's shape did.
_ENTRY_SCHEMA = 1

# Scanners whose output depends on the interpreter that parsed the file (stdlib ``ast``).
_INTERPRETER_SCANNERS = frozenset({'python'})


def _max_files() -> int:
    from ..treesitter import _structure_cache_max_files
    return _structure_cache_max_files()


def _stat_stamp(file_path: str) -> Optional[Tuple[int, int]]:
    try:
        st = os.stat(file_path)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def file_key(file_path: str, scanner_id: str, language: str, stamp: Tuple[int, int]) -> str:
    """The cache key of one file under one scanner at one stat stamp."""
    parts: List[str] = [
        os.path.abspath(file_path), file_path, str(stamp[0]), str(stamp[1]), scanner_id,
    ]
    if language in _INTERPRETER_SCANNERS:
        parts.append(f'py{sys.version_info[0]}.{sys.version_info[1]}')
    return hashlib.sha256('\x00'.join(parts).encode('utf-8', 'replace')).hexdigest()


def _storable(result: Any, validate: Callable[[Any, str], None]) -> bool:
    if not isinstance(result, dict) or result.get(UNPARSED_KEY):
        return False
    try:
        validate(result, '')
    except ValueError:
        return False
    return True


def _lookup(key: str, file_path: str, scanner_id: str) -> Optional[Dict[str, Any]]:
    entry = disk_cache.get(_SURFACE_FILE_NAMESPACE, key)
    if not isinstance(entry, dict) or entry.get('schema') != _ENTRY_SCHEMA or entry.get('scanner') != scanner_id:
        return None
    result = entry.get('result')
    if not isinstance(result, dict) or not os.access(file_path, os.R_OK):
        return None
    return result


def scan_file_cached(
    scan_fn: Callable[[str], Dict[str, List[Any]]], scanner_id: str, language: str, file_path: str,
    validate: Callable[[Any, str], None],
) -> Dict[str, List[Any]]:
    """``scan_fn(file_path)``, served from the persisted raw result when the file is unchanged.

    ``validate(result, type_filter)`` is the caller's full-result check, raising ``ValueError``."""
    if not disk_cache.is_enabled():
        return scan_fn(file_path)
    before = _stat_stamp(file_path)
    if before is None:
        return scan_fn(file_path)
    key = file_key(file_path, scanner_id, language, before)
    hit = _lookup(key, file_path, scanner_id)
    if hit is not None:
        return hit
    result = scan_fn(file_path)
    if _storable(result, validate) and _stat_stamp(file_path) == before:
        disk_cache.put(_SURFACE_FILE_NAMESPACE, key,
                       {'schema': _ENTRY_SCHEMA, 'scanner': scanner_id, 'result': result},
                       max_entries=_max_files())
    return result
