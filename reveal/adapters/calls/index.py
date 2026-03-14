"""Project-level callers index for calls:// adapter.

Builds and caches an inverted call graph across all code files in a directory:

    callee_name → [(file_path, caller_func_name, line)]

Cache key is a frozenset of (file_path, mtime_ns) tuples so any file change
invalidates only the entries affected.  In practice the whole index is rebuilt
per directory when any file changes (simple and correct).
"""

import builtins as _builtins_module
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..ast.analysis import collect_structures, is_code_file

# Module-level cache: directory → (cache_key, index)
# cache_key is a frozenset of (abspath_str, mtime_ns) so it's hashable.
_INDEX_CACHE: Dict[str, Tuple[Any, Dict[str, List[Dict[str, Any]]]]] = {}

# All public names in the Python builtins module — used to filter noise from
# callees results.  Built at import time so it stays in sync with the running
# Python version automatically.
PYTHON_BUILTINS: frozenset = frozenset(
    name for name in dir(_builtins_module) if not name.startswith('_')
)


def _dir_cache_key(directory: Path) -> Any:
    """Compute a hashable cache key from all code-file mtimes in *directory*."""
    entries = []
    for fp in sorted(directory.rglob('*')):
        if fp.is_file() and is_code_file(fp):
            try:
                entries.append((str(fp), os.stat(fp).st_mtime_ns))
            except OSError:
                pass
    return tuple(entries)


def build_callers_index(path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Return project-level callers index for *path* (file or directory).

    The index maps each callee name to a list of caller records::

        {
          "validate_item": [
              {"file": "app.py", "caller": "process_batch", "line": 42},
              {"file": "worker.py", "caller": "run_job", "line": 17},
          ],
          ...
        }

    Results are cached by directory mtime fingerprint; any file change causes
    a full rebuild (rebuilds are fast — just iterating existing structures).

    Args:
        path: File or directory to index.

    Returns:
        Inverted call graph dict (callee → list of caller dicts).
    """
    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    dir_str = str(directory)

    # Check cache
    cache_key = _dir_cache_key(directory)
    if dir_str in _INDEX_CACHE and _INDEX_CACHE[dir_str][0] == cache_key:
        return _INDEX_CACHE[dir_str][1]

    # Build index
    structures = collect_structures(str(directory))
    index: Dict[str, List[Dict[str, Any]]] = {}

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            caller_name = elem.get('name', '')
            caller_line = elem.get('line', 0)
            for callee in elem.get('calls', []):
                # Normalise: "self.foo" → "foo" for lookup, keep original in record
                bare = callee.split('.')[-1] if '.' in callee else callee
                record = {
                    'file': file_path,
                    'caller': caller_name,
                    'line': caller_line,
                    'call_expr': callee,
                }
                index.setdefault(bare, []).append(record)
                # Also index the full dotted form in case callers use it
                if bare != callee:
                    index.setdefault(callee, []).append(record)

    _INDEX_CACHE[dir_str] = (cache_key, index)
    return index


def find_callees(
    path: str,
    target: str,
    include_builtins: bool = False,
) -> Dict[str, Any]:
    """Find what function *target* calls, across all matching definitions.

    Scans the project for every function/method named *target* and returns
    the calls it makes, with per-file breakdown.  Useful when you know a
    function name but not which file it lives in, or when the name appears
    in multiple files.

    Args:
        path: Root directory (or file) to search.
        target: Function/method name to look up.
        include_builtins: When False (default), Python builtins (``len``,
            ``str``, ``sorted``, ``isinstance``, exception types, etc.) are
            stripped from the call list.  Pass True to see the raw list.

    Returns:
        Dict with ``target``, ``matches`` (one entry per definition found),
        ``total_calls`` count, and ``_builtins_hidden`` (count filtered out).
    """
    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    structures = collect_structures(str(directory))

    matches: List[Dict[str, Any]] = []
    builtins_hidden = 0
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            if elem.get('name', '') != target:
                continue
            calls = elem.get('calls', [])
            if not include_builtins:
                filtered = [c for c in calls if c.split('.')[-1] not in PYTHON_BUILTINS]
                builtins_hidden += len(calls) - len(filtered)
                calls = filtered
            matches.append({
                'file': file_path,
                'function': target,
                'line': elem.get('line', 0),
                'calls': calls,
            })

    return {
        'target': target,
        'query': 'callees',
        'matches': matches,
        'total_calls': sum(len(m['calls']) for m in matches),
        '_builtins_hidden': builtins_hidden,
    }


def find_callers(
    path: str,
    target: str,
    depth: int = 1,
) -> Dict[str, Any]:
    """Find callers of *target* across the project, optionally transitively.

    Args:
        path: Root directory (or file) to search.
        target: Function name to look up (bare name, no file qualifier).
        depth: How many levels of transitive callers to expand (1 = direct
               callers only, 2 = callers-of-callers, etc.).

    Returns:
        Dict with ``target``, ``depth``, and ``callers`` (list of records
        at each level).
    """
    index = build_callers_index(path)

    # BFS up to *depth* levels
    visited_callers: Set[Tuple[str, str]] = set()
    current_targets = {target}
    levels: List[Dict[str, Any]] = []

    for level in range(depth):
        level_records: List[Dict[str, Any]] = []
        next_targets: Set[str] = set()

        for t in sorted(current_targets):
            for record in index.get(t, []):
                key = (record['file'], record['caller'])
                if key in visited_callers:
                    continue
                visited_callers.add(key)
                level_records.append({**record, 'callee': t})
                next_targets.add(record['caller'])

        if level_records:
            levels.append({'level': level + 1, 'callers': level_records})

        if not next_targets:
            break
        current_targets = next_targets

    return {
        'target': target,
        'depth': depth,
        'total_callers': sum(len(lvl['callers']) for lvl in levels),
        'levels': levels,
    }
