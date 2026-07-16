"""Project-level callers index for calls:// adapter.

Builds and caches an inverted call graph across all code files in a directory:

    callee_name → [(file_path, caller_func_name, line)]

Cache key is a frozenset of (file_path, mtime_ns) tuples so any file change
invalidates only the entries affected.  In practice the whole index is rebuilt
per directory when any file changes (simple and correct).
"""

import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..ast.analysis import collect_structures, is_code_file, PYTHON_BUILTINS
from ..ast.call_graph import build_alias_map, build_symbol_map, resolve_callees as _resolve_callees
from ...defaults import TEST_FRAMEWORK_CALLEE_NAMES
from ...registry import language_for_extension
from ...utils.path_utils import is_unsafe_scan_root

# Module-level LRU cache: directory → (cache_key, index)
# cache_key is a tuple of (abspath_str, mtime_ns) pairs so it's hashable.
# Capped at 8 entries — call graphs are expensive to rebuild but rarely need
# more than a handful cached simultaneously.
_INDEX_CACHE: OrderedDict = OrderedDict()
_INDEX_CACHE_MAX = 8

# Decorators that cause the runtime to dispatch the function implicitly —
# never appear as explicit call expressions in source code.
_IMPLICIT_DECORATORS: frozenset = frozenset({'property', 'classmethod', 'staticmethod'})

# BACK-446: test methods are invoked by a test runner via reflection/collection,
# not by an explicit call expression — so they always show up as "uncalled" and
# swamp the dead-code signal (1,577 false positives on Jellyfin/C#, nearly all
# xUnit [Fact]/[Theory] methods). Excluded by default; opt back in with
# ?test-framework=true.
#
# C#/.NET and Java mark tests with attributes/annotations that Reveal's
# structure pass does NOT surface as `decorators`, so these are matched by a
# scoped source-scan of the annotation lines immediately preceding the def.
_TEST_ANNOTATION_MARKERS: tuple = (
    # C# / .NET — xUnit, NUnit, MSTest
    '[Fact', '[Theory', '[Test', '[SetUp', '[TearDown',
    '[OneTimeSetUp', '[OneTimeTearDown',
    # Java / JVM — JUnit 4/5, TestNG
    '@Test', '@ParameterizedTest', '@RepeatedTest', '@TestFactory',
    '@BeforeEach', '@AfterEach', '@BeforeAll', '@AfterAll',
    '@Before', '@After', '@BeforeClass', '@AfterClass',
)
# Python test entry points Reveal *does* capture as decorators (pytest).
_TEST_DECORATOR_NAMES: frozenset = frozenset({'fixture'})
# Python name conventions collected by pytest/unittest without an explicit call.
_PY_UNITTEST_LIFECYCLE: frozenset = frozenset({
    'setUp', 'tearDown', 'setUpClass', 'tearDownClass',
    'setUpModule', 'tearDownModule',
})

# Tree-sitter language slug → coarse family, for scoping callee resolution to
# the caller's language (BACK-405). C/C++ share one family since headers (.h)
# are ambiguous between the two and both target the same symbol namespace.
# Deliberately coarse — the goal is only to stop bare-name collisions across
# unrelated languages (e.g. a C `write()` resolving to a Python `def write`),
# not to build a precise per-language classifier. Extension→language identity
# itself is NOT re-declared here — it's looked up from the registry
# (BACK-431 Issue B) so a new extension routed to an existing language is
# automatically in-family with no edit needed here.
_FAMILY_BY_LANGUAGE: Dict[str, str] = {
    'c': 'c', 'cpp': 'c',
    'python': 'python',
    'javascript': 'js', 'typescript': 'js', 'tsx': 'js',
    'go': 'go',
    'rust': 'rust',
    'java': 'java',
    'csharp': 'csharp',
    'ruby': 'ruby',
    'php': 'php',
    'kotlin': 'kotlin',
    'swift': 'swift',
    'scala': 'scala',
    'lua': 'lua',
    'dart': 'dart',
}


def _lang_family(file_path: str) -> str:
    """Return the coarse language family for a file path, or '' if unknown."""
    lang = language_for_extension(Path(file_path).suffix.lower())
    return _FAMILY_BY_LANGUAGE.get(lang, '') if lang else ''


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


def _bare_callee_name(callee: str) -> str:
    """Strip a qualified callee down to its final bare segment.

    Handles PHP `$this->validate` -> `validate`, dotted `obj.method` /
    `pkg.Func` -> `method`/`Func`, and C++ `ClassName::get_singleton` ->
    `get_singleton` (BACK-414: `::` was never handled, so the overwhelming
    majority of real-world C++ call sites — which use scope-qualified static
    calls like `Engine::get_singleton()` — were never indexed under the bare
    name callers/callees actually search for). Whichever separator occurs
    last in the string wins, so mixed forms resolve to the final segment.
    """
    idx = max(callee.rfind('->'), callee.rfind('.'), callee.rfind('::'))
    if idx == -1:
        return callee
    if callee[idx:idx + 2] in ('->', '::'):
        return callee[idx + 2:]
    return callee[idx + 1:]


def _index_callee(
    index: Dict[str, List[Dict[str, Any]]],
    callee: str,
    record: Dict[str, Any],
    alias_map: Dict[str, str],
) -> None:
    """Add *record* to *index* under the bare name, dotted/arrow form, and canonical alias."""
    bare = _bare_callee_name(callee)
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
    from ...utils.path_utils import is_skippable_dir
    try:
        mtimes = [os.stat(directory).st_mtime_ns]
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False) and not is_skippable_dir(directory, entry.name):
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
            # 'tests' (Zig's TestDecl blocks — the only 'tests'-category
            # producer today) counts as a caller here for the same reason
            # JS/TS's describe()/it() callbacks are folded into 'functions'
            # (BACK-334): a function called only from a test previously
            # reported zero callers — indistinguishable from dead code,
            # BACK-660's exact failure mode, just one hop further in.
            if elem.get('category') not in ('functions', 'methods', 'tests'):
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


def _build_forward_index(
    structures: List[Dict[str, Any]],
    include_builtins: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build name → [{file, line, calls}] forward call index from collected structures."""
    forward: Dict[str, List[Dict[str, Any]]] = {}
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            name = elem.get('name', '')
            if not name:
                continue
            calls = elem.get('calls', [])
            if not include_builtins:
                calls = [c for c in calls if c.split('.')[-1] not in PYTHON_BUILTINS]
            forward.setdefault(name, []).append({
                'file': file_path,
                'line': elem.get('line', 0),
                'calls': calls,
            })
    return forward


def _collect_level_entries(
    current_names: Set[Tuple[str, str]],
    forward: Dict[str, List[Dict[str, Any]]],
    visited: Set[str],
) -> Tuple[List[Dict[str, Any]], Set[Tuple[str, str]]]:
    """Collect callee entries for one BFS level; return (entries, next_names).

    *current_names*/*next_names* are (name, language_family) pairs — family is
    '' for the root (unscoped) or an unrecognized-extension caller. BACK-405:
    propagating the family across levels (not just the first hop) keeps a
    resolved name's *own* forward-index lookup scoped too, so a same-named
    definition in an unrelated language doesn't leak into what that node
    "calls" once it becomes a source for the next level.

    *visited* stays name-only (not (name, family)) to preserve the original
    cycle-prevention guarantee — a name, once visited via any language, is
    never re-expanded, regardless of which family resolved it.
    """
    level_entries: List[Dict[str, Any]] = []
    next_names: Set[Tuple[str, str]] = set()

    for source_name, source_family in sorted(current_names):
        seen_this_source: Set[str] = set()
        defs = forward.get(source_name, [])
        if source_family:
            defs = [d for d in defs if _lang_family(d['file']) == source_family]
        for defn in defs:
            caller_family = source_family or _lang_family(defn['file'])
            for callee in defn['calls']:
                tail = _bare_callee_name(callee)
                # BACK-405: scope resolution to the caller's language family
                # before accepting a bare-name match — a flat, language-blind
                # index lets a same-named definition in an unrelated language
                # win over the correct "unresolved/external" fallback (e.g. a
                # C write() syscall resolving to an unrelated Python def write).
                candidates = forward.get(tail, [])
                if caller_family:
                    candidates = [c for c in candidates if _lang_family(c['file']) == caller_family]
                resolved = bool(candidates)
                resolved_name = tail if resolved else callee
                resolved_family = caller_family if resolved else ''
                if resolved_name in seen_this_source or resolved_name in visited:
                    continue
                seen_this_source.add(resolved_name)
                visited.add(resolved_name)
                level_entries.append({
                    'caller': source_name,
                    'callee': resolved_name,
                    'resolved': resolved,
                    'caller_file': defn['file'],
                    'caller_line': defn['line'],
                })
                if resolved:
                    next_names.add((resolved_name, resolved_family))

    return level_entries, next_names


def find_callees_recursive(
    path: str,
    root: str,
    depth: int = 2,
    include_builtins: bool = False,
) -> Dict[str, Any]:
    """Recursive callees walk: follow what *root* calls, then what those call.

    Args:
        path: Root directory (or file) to search.
        root: Entry-point function name to start the walk from.
        depth: How many levels to expand (1 = direct callees only, max 5).
        include_builtins: When False (default), Python builtins are excluded
            from callee lists, keeping the output focused on project code.

    Returns:
        Dict with ``root``, ``depth``, ``levels`` (one per BFS level),
        ``total_resolved`` (callees found in the project),
        ``total_unresolved`` (external / not-found names).
    """
    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    structures = collect_structures(str(directory))
    forward = _build_forward_index(structures, include_builtins)

    # '' family = unscoped: root has no caller edge to inherit a language from.
    visited: Set[str] = {root}
    current_names: Set[Tuple[str, str]] = {(root, '')}
    levels: List[Dict[str, Any]] = []

    for level_num in range(1, depth + 1):
        level_entries, next_names = _collect_level_entries(current_names, forward, visited)
        if level_entries:
            levels.append({'level': level_num, 'callees': level_entries})
        if not next_names:
            break
        current_names = next_names

    total_resolved = sum(sum(1 for e in lvl['callees'] if e['resolved']) for lvl in levels)
    total_unresolved = sum(sum(1 for e in lvl['callees'] if not e['resolved']) for lvl in levels)

    return {
        'root': root,
        'query': 'callees_recursive',
        'depth': depth,
        'levels': levels,
        'total_resolved': total_resolved,
        'total_unresolved': total_unresolved,
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
        if parent != path and os.path.isdir(parent) and _parent_hint_scan_is_cheap(parent):
            parent_index = build_callers_index(parent)
            potential = len(parent_index.get(target, []))
            if potential:
                result['hint'] = (
                    f"0 callers found in '{path}' — "
                    f"{potential} potential caller(s) exist in '{parent}'; "
                    f"try widening the path"
                )

    return result


# The "try widening the path" hint (above) builds a full call index over the
# *parent* directory — an implicit scan the user never asked for. It must never
# become an unbounded parse of a huge or system-level tree; that's the exact
# unbounded-scan footgun BACK-418 fixed for I002/hotspots. Skip the hint when the
# parent is a well-known system/home root, or when a cheap parse-free count of
# its code files exceeds this ceiling.
_HINT_SCAN_MAX_FILES = 2000


def _parent_hint_scan_is_cheap(parent: str) -> bool:
    """True if scanning *parent* for the widen-the-path hint is bounded and safe.

    A parse-free directory walk that aborts as soon as the code-file count
    crosses the ceiling, so it stays fast even when the answer is "no". Also
    refuses outright on system/home roots (e.g. a tempdir whose parent is /tmp).
    """
    from ...utils.path_utils import is_skippable_dir
    if is_unsafe_scan_root(parent):
        return False
    count = 0
    for root, dirs, files in os.walk(parent):
        dirs[:] = [
            d for d in dirs
            if not is_skippable_dir(Path(root), d) and not d.endswith('.egg-info')
        ]
        for name in files:
            if is_code_file(Path(name)):
                count += 1
                if count > _HINT_SCAN_MAX_FILES:
                    return False
    return True


def _read_lines(file_path: str, cache: Dict[str, List[str]]) -> List[str]:
    """Return (cached) source lines for *file_path*; empty list on read error."""
    if file_path not in cache:
        try:
            with open(file_path, encoding='utf-8', errors='replace') as fh:
                cache[file_path] = fh.readlines()
        except OSError:
            cache[file_path] = []
    return cache[file_path]


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
    lines = _read_lines(file_path, cache)
    for ln in range(line_no, min(line_no + 4, len(lines) + 1)):
        if 1 <= ln <= len(lines) and '# noqa: uncalled' in lines[ln - 1]:
            return True
    return False


def _has_test_annotation(
    file_path: str,
    line_no: int,
    cache: Dict[str, List[str]],
) -> bool:
    """True if a test attribute/annotation (``[Fact]``, ``@Test``, …) sits on or
    immediately above the def at ``line_no``.

    Scans only the contiguous block of attribute/annotation/blank lines directly
    preceding the definition (and the def line itself), so a marker is
    associated with *its own* method — never a neighbour's — avoiding the
    false-exclusion trap of a fixed look-back window over adjacent methods.
    """
    lines = _read_lines(file_path, cache)
    texts: List[str] = []
    if 1 <= line_no <= len(lines):
        texts.append(lines[line_no - 1])
    j = line_no - 1
    while j >= 1:
        stripped = lines[j - 1].strip()
        if stripped == '' or stripped.startswith('[') or stripped.startswith('@'):
            texts.append(lines[j - 1])
            j -= 1
        else:
            break
    blob = ''.join(texts)
    return any(marker in blob for marker in _TEST_ANNOTATION_MARKERS)


def _is_test_entry_point(
    name: str,
    file_path: str,
    line_no: int,
    decorator_names: Set[str],
    cache: Dict[str, List[str]],
) -> bool:
    """True if *name* is invoked by a test runner rather than an explicit call
    (BACK-446) — a pytest fixture/test, a unittest lifecycle hook, or a
    C#/Java method carrying a test attribute/annotation."""
    if decorator_names & _TEST_DECORATOR_NAMES:
        return True
    if _lang_family(file_path) == 'python' and (
        name.startswith('test_') or name in _PY_UNITTEST_LIFECYCLE
    ):
        return True
    return bool(line_no) and _has_test_annotation(file_path, line_no, cache)


def find_uncalled(
    path: str,
    only_functions: bool = False,
    top: int = 0,
    include_test_framework: bool = False,
) -> Dict[str, Any]:
    """Find functions/methods defined but never called within the project.

    Uses the callers index (set of all callees) and subtracts from the full
    set of function/method definitions.  In-degree = 0 → nothing in the
    project statically calls this symbol.

    Automatically excluded (implicitly invoked, not statically reachable):
    - ``__dunder__`` methods (``__init__``, ``__str__``, etc.)
    - Functions decorated with ``@property``, ``@classmethod``, ``@staticmethod``
    - Test-runner entry points (pytest/unittest, xUnit ``[Fact]``/``[Theory]``,
      JUnit ``@Test``, …) — invoked by reflection, not a call (BACK-446).
      Set ``include_test_framework=True`` to keep them in the result.

    Args:
        path: Root directory (or file) to analyse.
        only_functions: If True, skip methods (category='methods') — useful
            to focus on module-level dead code.
        top: If > 0, limit results to this many entries sorted by file mtime
            descending (most-recently-added uncalled first).
        include_test_framework: If True, do not exclude test-runner entry
            points (default False — they are noise for a dead-code read).

    Returns:
        Dict with ``path``, ``total_defined``, ``total_uncalled``,
        ``test_entrypoints_excluded``, and ``entries`` (list of uncalled
        symbols).
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
    test_entrypoints_excluded = 0
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
            if not include_test_framework and _is_test_entry_point(
                name, file_path, line_no, decorator_names, file_lines
            ):
                test_entrypoints_excluded += 1
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
        'test_entrypoints_excluded': test_entrypoints_excluded,
        'entries': entries,
    }


def rank_by_callers(
    path: str,
    top: int = 10,
    include_builtins: bool = False,
    include_test_framework: bool = False,
) -> Dict[str, Any]:
    """Rank all callable symbols by how many unique callers they have.

    Uses the already-built callers index (cached) — zero extra infrastructure.

    Args:
        path: Root directory (or file) to analyse.
        top: Maximum number of entries to return (default 10, capped at 100).
        include_builtins: If False (default), skip Python builtins from the ranking.
        include_test_framework: If False (default), suppress test-framework symbols
            (expect, describe, it, vi, jest, cy, etc.) that dominate TS rankings
            with fake in-degree.  Pass ``?test-framework=true`` in the URI to opt in.

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
        if not include_test_framework and callee_name.split('.')[-1] in TEST_FRAMEWORK_CALLEE_NAMES:
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


def build_module_dependency_graph(
    path: str,
    include_external: bool = False,
) -> Dict[str, Any]:
    """Build a module-level dependency graph using cross-file call resolution.

    For each function call in the project, resolves the callee to its source
    file via the import graph (``build_symbol_map`` + ``resolve_callees``).
    Collapses the function-level edges to unique module → module edges with
    a per-edge call count.

    Args:
        path: Root directory (or file) to scan.
        include_external: When True, include edges where the callee resolves
            to a file outside the project root (stdlib/third-party).  Default
            False keeps the graph focused on project-internal dependencies.

    Returns:
        Dict with ``nodes`` (sorted list of module file paths that appear as
        caller or callee), ``edges`` (list of ``{from, to, call_count}``
        sorted descending by call_count), and summary counts.
    """
    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    dir_str = str(directory)
    structures = collect_structures(dir_str)

    # edge_counts: (from_file, to_file) → call count
    edge_counts: Dict[Tuple[str, str], int] = {}
    # symbol_map cache per file
    sym_cache: Dict[str, Dict[str, Optional[str]]] = {}

    for file_struct in structures:
        from_file = file_struct.get('file', '')
        if not from_file:
            continue

        if from_file not in sym_cache:
            sym_cache[from_file] = build_symbol_map(from_file)
        symbol_map = sym_cache[from_file]

        for elem in file_struct.get('elements', []):
            if elem.get('category') not in ('functions', 'methods'):
                continue
            raw_calls = elem.get('calls', [])
            if not raw_calls:
                continue

            resolved = _resolve_callees(raw_calls, symbol_map)
            for entry in resolved:
                to_file = entry.get('resolved_file')
                if not to_file:
                    continue
                if not include_external:
                    # Skip files outside the project root
                    try:
                        Path(to_file).relative_to(directory)
                    except ValueError:
                        continue
                # Skip self-loops
                if to_file == from_file:
                    continue
                edge_key = (from_file, to_file)
                edge_counts[edge_key] = edge_counts.get(edge_key, 0) + 1

    # Build edges list
    edges = [
        {'from': frm, 'to': to, 'call_count': cnt}
        for (frm, to), cnt in edge_counts.items()
    ]
    edges.sort(key=lambda e: e['call_count'], reverse=True)

    # Nodes = all files that appear in any edge
    node_set: Set[str] = set()
    for e in edges:
        node_set.add(e['from'])
        node_set.add(e['to'])
    nodes = sorted(node_set)

    return {
        'query': 'module_graph',
        'path': dir_str,
        'nodes': nodes,
        'edges': edges,
        'total_nodes': len(nodes),
        'total_edges': len(edges),
    }
