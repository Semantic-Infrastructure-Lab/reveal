"""Project-level callers index for calls:// adapter.

Builds and caches an inverted call graph across all code files in a directory:

    callee_name → [(file_path, caller_func_name, line)]

Cache key is a frozenset of (file_path, mtime_ns) tuples so any file change
invalidates only the entries affected.  In practice the whole index is rebuilt
per directory when any file changes (simple and correct).
"""

import builtins as _builtins_module
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..ast.analysis import collect_structures, is_code_file
from ..ast.call_graph import build_alias_map

# Module-level LRU cache: directory → (cache_key, index)
# cache_key is a tuple of (abspath_str, mtime_ns) pairs so it's hashable.
# Capped at 8 entries — call graphs are expensive to rebuild but rarely need
# more than a handful cached simultaneously.
_INDEX_CACHE: OrderedDict = OrderedDict()
_INDEX_CACHE_MAX = 8

# All public names in the Python builtins module — used to filter noise from
# callees results.  Built at import time so it stays in sync with the running
# Python version automatically.
PYTHON_BUILTINS: frozenset = frozenset(
    name for name in dir(_builtins_module) if not name.startswith('_')
)

# Decorators that cause the runtime to dispatch the function implicitly —
# never appear as explicit call expressions in source code.
_IMPLICIT_DECORATORS: frozenset = frozenset({'property', 'classmethod', 'staticmethod'})


def _get_decorator_names(elem: Dict[str, Any]) -> Set[str]:
    """Return the bare decorator names for *elem* (strips leading '@' and module prefix)."""
    return {d.split('.')[-1].lstrip('@') for d in elem.get('decorators', [])}


def _is_method_elem(elem: Dict[str, Any], decorator_names: Set[str]) -> bool:
    """Return True if *elem* is a method (not a module-level function)."""
    sig = elem.get('signature', '')
    return (
        elem.get('category') == 'methods'
        or sig.startswith('(self') or sig.startswith('(cls')
        or 'classmethod' in decorator_names
        or 'staticmethod' in decorator_names
    )


def _is_implicit_element(
    name: str,
    is_method: bool,
    decorator_names: Set[str],
    only_functions: bool,
) -> bool:
    """Return True if element is implicitly invoked and should never be flagged as dead code."""
    if only_functions and is_method:
        return True
    if name.startswith('__') and name.endswith('__'):
        return True
    return bool(decorator_names & _IMPLICIT_DECORATORS)


def _uncalled_entry_mtime(entry: Dict[str, Any]) -> float:
    """Return negated mtime for sort key (most-recently-modified first)."""
    try:
        return -os.stat(entry['file']).st_mtime
    except OSError:
        return 0.0


def _index_callee(
    index: Dict[str, List[Dict[str, Any]]],
    callee: str,
    record: Dict[str, Any],
    alias_map: Dict[str, str],
) -> None:
    """Add *record* to *index* under the bare name, dotted form, and canonical alias."""
    bare = callee.split('.')[-1] if '.' in callee else callee
    index.setdefault(bare, []).append(record)
    if bare != callee:
        index.setdefault(callee, []).append(record)
    canonical = alias_map.get(bare)
    if canonical and canonical != bare:
        index.setdefault(canonical, []).append(record)


def _bfs_level(
    index: Dict[str, List[Dict[str, Any]]],
    current_targets: Set[str],
    visited_callers: Set[Tuple[str, str]],
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Run one BFS level: return (level_records, next_targets)."""
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
    return level_records, next_targets


def _dir_cache_key(directory: Path) -> Any:
    """Compute a hashable cache key for *directory*.

    Stats every immediate child directory in addition to the directory itself.
    A single top-level stat is insufficient on Linux because editing a nested
    file only updates the *containing subdirectory's* mtime, not the root.

    Fallback: if all stats fail, walk code-file mtimes (slow but correct).
    """
    from ..ast.analysis import _SKIP_DIRS
    try:
        mtimes = [os.stat(directory).st_mtime_ns]
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False) and entry.name not in _SKIP_DIRS:
                    try:
                        mtimes.append(os.stat(entry).st_mtime_ns)
                    except OSError:
                        pass
        return ('dir_mtimes', tuple(sorted(mtimes)))
    except OSError:
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
        _INDEX_CACHE.move_to_end(dir_str)
        return _INDEX_CACHE[dir_str][1]

    # Build index
    structures = collect_structures(str(directory))
    index: Dict[str, List[Dict[str, Any]]] = {}

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        # Build alias → canonical name map for this file so that calls using
        # an import alias (e.g. `h` for `from utils import helper as h`) also
        # index the definition name (`helper`).  This prevents find_uncalled
        # from falsely reporting `helper` as dead code and lets find_callers
        # locate callers that use the alias.
        alias_map = build_alias_map(file_path)
        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            record_base = {
                'file': file_path,
                'caller': elem.get('name', ''),
                'line': elem.get('line', 0),
            }
            for callee in elem.get('calls', []):
                _index_callee(index, callee, {**record_base, 'call_expr': callee}, alias_map)

    _INDEX_CACHE[dir_str] = (cache_key, index)
    _INDEX_CACHE.move_to_end(dir_str)
    if len(_INDEX_CACHE) > _INDEX_CACHE_MAX:
        _INDEX_CACHE.popitem(last=False)
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
        level_records, next_targets = _bfs_level(index, current_targets, visited_callers)
        if level_records:
            levels.append({'level': level + 1, 'callers': level_records})
        if not next_targets:
            break
        current_targets = next_targets

    total = sum(len(lvl['callers']) for lvl in levels)
    result: Dict[str, Any] = {
        'target': target,
        'depth': depth,
        'total_callers': total,
        'levels': levels,
    }

    if total == 0:
        parent = str(Path(path).parent)
        if parent != path and os.path.isdir(parent):
            parent_index = build_callers_index(parent)
            potential = len(parent_index.get(target, []))
            if potential:
                result['hint'] = (
                    f"0 callers found in '{path}' — "
                    f"{potential} potential caller(s) exist in '{parent}'; "
                    f"try widening the path"
                )

    return result


def _has_noqa_uncalled(
    file_path: str,
    line_no: int,
    cache: Dict[str, List[str]],
) -> bool:
    """Return True if the function at ``line_no`` has a ``# noqa: uncalled`` comment.

    Checks ``line_no`` through ``line_no + 3`` to handle decorators: analyzers
    often report the first decorator line as the function's start, while the
    noqa comment lives on the ``def`` line one or two lines later.
    """
    if file_path not in cache:
        try:
            with open(file_path, encoding='utf-8', errors='replace') as fh:
                cache[file_path] = fh.readlines()
        except OSError:
            cache[file_path] = []
    lines = cache[file_path]
    for ln in range(line_no, min(line_no + 4, len(lines) + 1)):
        if 1 <= ln <= len(lines) and '# noqa: uncalled' in lines[ln - 1]:
            return True
    return False


def find_uncalled(
    path: str,
    only_functions: bool = False,
    top: int = 0,
) -> Dict[str, Any]:
    """Find functions/methods defined but never called within the project.

    Uses the callers index (set of all callees) and subtracts from the full
    set of function/method definitions.  In-degree = 0 → nothing in the
    project statically calls this symbol.

    Automatically excluded (implicitly invoked, not statically reachable):
    - ``__dunder__`` methods (``__init__``, ``__str__``, etc.)
    - Functions decorated with ``@property``, ``@classmethod``, ``@staticmethod``

    Args:
        path: Root directory (or file) to analyse.
        only_functions: If True, skip methods (category='methods') — useful
            to focus on module-level dead code.
        top: If > 0, limit results to this many entries sorted by file mtime
            descending (most-recently-added uncalled first).

    Returns:
        Dict with ``path``, ``total_defined``, ``total_uncalled``, and
        ``entries`` (list of uncalled symbols).
    """
    path_obj = Path(path)
    is_file = path_obj.is_file()
    directory = path_obj.parent if is_file else path_obj
    # When a single file is given, scope definitions to that file only.
    # The callers index is still built from the full directory so cross-file
    # call sites are counted (a file-local function called from a sibling is
    # NOT dead code).
    file_filter: Optional[str] = str(path_obj.resolve()) if is_file else None

    called_names: Set[str] = set(build_callers_index(path).keys())
    file_lines: Dict[str, List[str]] = {}
    structures = collect_structures(str(directory))

    total_defined = 0
    entries = []

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        if file_filter and str(Path(file_path).resolve()) != file_filter:
            continue
        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            name = elem.get('name', '')
            if not name:
                continue

            decorator_names = _get_decorator_names(elem)
            is_method = _is_method_elem(elem, decorator_names)
            total_defined += 1

            line_no = elem.get('line', 0)
            if _is_implicit_element(name, is_method, decorator_names, only_functions):
                continue
            if name in called_names:
                continue
            if line_no and _has_noqa_uncalled(file_path, line_no, file_lines):
                continue

            entries.append({
                'name': name,
                'file': file_path,
                'line': line_no,
                'category': 'methods' if is_method else 'functions',
                'is_private': name.startswith('_'),
            })

    entries.sort(key=lambda e: (_uncalled_entry_mtime(e), e['file'], e['line']))
    if top > 0:
        entries = entries[:top]

    return {
        'query': 'uncalled',
        'path': path,
        'total_defined': total_defined,
        'total_uncalled': len(entries),
        'entries': entries,
    }


def rank_by_callers(
    path: str,
    top: int = 10,
    include_builtins: bool = False,
) -> Dict[str, Any]:
    """Rank all callable symbols by how many unique callers they have.

    Uses the already-built callers index (cached) — zero extra infrastructure.

    Args:
        path: Root directory (or file) to analyse.
        top: Maximum number of entries to return (default 10, capped at 100).
        include_builtins: If False (default), skip Python builtins from the ranking.

    Returns:
        Dict with ``path``, ``top``, ``total_unique_callees``, and ``entries``
        sorted descending by ``caller_count``.

    Example entry::

        {
            "name": "validate_item",
            "caller_count": 5,
            "callers": [
                {"file": "app.py", "caller": "process_batch", "line": 42,
                 "call_expr": "validate_item"},
                ...
            ]
        }
    """
    index = build_callers_index(path)
    top = max(1, min(top, 100))

    entries = []
    for callee_name, caller_records in index.items():
        if not include_builtins and callee_name.split('.')[-1] in PYTHON_BUILTINS:
            continue
        # Deduplicate caller records by (file, caller) to count unique callers
        seen: Set[Tuple[str, str]] = set()
        unique_records = []
        for rec in caller_records:
            key = (rec['file'], rec['caller'])
            if key not in seen:
                seen.add(key)
                unique_records.append(rec)
        entries.append({
            'name': callee_name,
            'caller_count': len(unique_records),
            'callers': unique_records,
        })

    entries.sort(key=lambda e: e['caller_count'], reverse=True)

    return {
        'query': 'rank_callers',
        'path': path,
        'top': top,
        'total_unique_callees': len(entries),
        'entries': entries[:top],
    }
