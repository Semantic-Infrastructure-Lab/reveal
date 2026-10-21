"""Project-level callers index for calls:// adapter.

Builds and caches an inverted call graph across all code files in a directory:

    callee_name → [(file_path, caller_func_name, line)]

The cache key uses directory mtimes and active scope. It does not detect every
file overwrite or deeper membership change. Known incomplete collections are not
retained. Host requests validate retained roots through the shared request-cache
owner; direct helper reuse remains governed by the cheap key.
"""

import os
import re
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterator, List, NamedTuple, Optional, Sequence, Set, Tuple

from ..ast.analysis import (
    StructureList, collect_structures, environmental_failure, is_code_file, call_sources, unattributed_references,
)
from ...utils.pyparse import parse_python
from ...utils.request_cache import register_validated_cache
from ..ast.call_graph import (
    ClassAliasSpan, build_alias_map, build_class_attribute_aliases, build_symbol_map, class_attribute_alias,
    resolve_callees as _resolve_callees,
)
from ...conventions import conventions_for, family_for_path, is_builtin_anywhere
from ...defaults import TEST_FRAMEWORK_CALLEE_NAMES
from ...utils.gitignore import gitignore_enabled
from ...utils.path_utils import _walk_code_files, is_unsafe_scan_root, to_posix
from ...core.definition_names import lookup_keys, name_matches

# Module-level LRU cache: directory → (cache_key, index)
# cache_key combines the hashable directory-mtime key with active scope.
# Capped at 8 entries — call graphs are expensive to rebuild but rarely need
# more than a handful cached simultaneously.
_INDEX_CACHE: OrderedDict = OrderedDict()
_INDEX_CACHE_MAX = 8

# BACK-1265: web/CLI framework route and handler decorators. A decorated route
# is invoked by the framework's registry, never by a call expression, so every
# endpoint in a Flask/FastAPI/Django/Click/Celery app read as dead code --
# 4 of 20 in an external random-sample precision measurement. BACK-952 already
# provided .reveal.yaml config for exactly this, but an empty default meant the
# rule only worked for projects that had already been bitten by it and knew to
# declare their own framework's decorators.
#
# Matched as bare names after stripping the module prefix (@app.get -> 'get'),
# same convention as _get_decorator_names(). Deliberately the routing/dispatch
# vocabulary only: a function *decorated* with one of these is a registration
# in every framework that uses the name, and suppressing a genuinely dead one
# costs far less than a reader verifying every endpoint by hand.
# Language family for a path; conventions (implicit names, builtins, test markers)
# are scoped per family in reveal/conventions.py.
_lang_family = family_for_path


def _get_decorator_names(elem: Dict[str, Any]) -> Set[str]:
    """Return the bare decorator names for *elem* (strips leading '@', module prefix, and
    any call parens — a decorator *factory* like ``@app.route('/x')`` or ``@pytest.fixture()``
    must still bare-name-match as 'route'/'fixture', the same as its bare form).
    """
    names = set()
    for d in elem.get('decorators', []):
        # Rust attributes arrive as raw `#[tokio::test(flavor = "x")]` text.
        bare = d.lstrip('@#!').lstrip('[').split('(', 1)[0].rstrip(']')
        names.add(bare.replace('::', '.').split('.')[-1])
    return names


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
    extra_implicit_decorators: FrozenSet[str] = frozenset(),
    lang_family: str = '',
) -> bool:
    """Return True if element is implicitly invoked and should never be flagged as dead code.

    extra_implicit_decorators (BACK-952) extends _IMPLICIT_DECORATORS with
    project-declared entry-point decorators (.reveal.yaml adapters.calls.
    entry_points.decorators) — web/CLI framework routes (Flask @app.route,
    FastAPI @app.get, Click @cli.command, …) that are invoked by the
    framework, not a static call expression, so they'd otherwise false-flag
    as dead code on every web app codebase.

    JS/TS/Java-family ``constructor`` methods (BACK-1009) get the same
    treatment as Python's ``__init__``, for a different reason: unlike
    Python (where ``ClassName()`` indexes under the literal definition
    name) or Java/C# (where the constructor method is itself named after
    the class), JS/TS's `new ClassName(...)` is indexed under "ClassName"
    (`_extract_js_new_callee`/`_bare_callee_name`) while the method
    definition is always literally named ``constructor`` — the two names
    never match, so every constructor in a TS/JS codebase was flagged
    dead code (measured 18.5% of all `?uncalled` hits on the VS Code
    corpus).
    """
    if only_functions and is_method:
        return True
    conv = conventions_for(lang_family)
    if conv.is_implicit_name(name):
        return True
    return bool(decorator_names & (
        conv.implicit_decorators | conv.entry_point_decorators | extra_implicit_decorators
    ))


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

    Also strips PHP's "new ClassName" constructor-call prefix (from
    `core/callees/php.py:object_creation`) and a leading backslash fully-qualified-namespace
    marker (PHP's "resolve from the global namespace, not the current one"
    syntax, e.g. sprintf() written as "\\sprintf", common after any
    namespaced file that references a global-namespace builtin). Neither is
    a real-vs-bare distinction any other language has, so both were passed
    through unbroken — the calls-recall-oracle PHP measurement (BACK-730,
    seventh language) found real corpus misses this caused: "new
    Walker_Nav_Menu_Checklist()" and "throw new WP_HTML_Unsupported_Exception"
    never matched a target lookup for the bare class name, and "\\sprintf"/
    "\\in_array"/"\\fopen" (PSR-7 vendor code, this corpus) never matched
    "sprintf"/"in_array"/"fopen".

    Also strips a trailing C# explicit generic-argument suffix
    (`List<Video>`, `Method<string>`, `Class<T>.Static<U>` -> `List`/
    `Method`/`Static`) -- the calls-recall-oracle C# measurement (BACK-730,
    eighth language) found `new List<T>()`/`new NullLogger<T>()`/
    `new GenericEventArgs<T>()` (Jellyfin's dominant generic-constructor
    idiom) and explicit generic-method invocations never matched a bare
    `?target=List`/`?target=Method` lookup, same bug *class* as BACK-733's
    Rust turbofish gap: the raw callee text keeps everything from the type/
    method name's own extraction, unlike Rust where the fix already lives
    in the extraction layer (`_callee_name_from_node`'s `generic_function`
    case) -- C#'s `object_creation_expression`/`invocation_expression`
    extraction has no such node-shape special case, so the suffix survives
    to this bare-name layer instead. Cut from the first `<` to end-of-string
    (mirrors the C# oracle's own `SimpleTypeName`-adjacent stripping) --
    safe because no separator this function handles (`.`, `->`, `::`) is
    ever legally followed by a bare `<` in a real callee.

    Also strips leading/trailing whitespace from the final bare segment --
    a fluent call chain split across lines for readability (e.g. Moq's
    `_mockUserManager.\n    Setup(...)`, a common C# test idiom) makes the
    raw callee text literally `"_mockUserManager.\n    Setup"`: separator
    splitting on the `.` correctly isolates the method name but leaves the
    newline+indentation between it and the separator attached to the bare
    segment (`"\n    Setup"` != `"Setup"`), so it never matched a bare
    `?target=Setup` lookup (calls-recall-oracle C# measurement, BACK-730,
    eighth language). Identifiers can never legally contain whitespace, so
    a plain `.strip()` on the final segment is always safe.

    Also handles Lua's single-colon method-call idiom (`db:init_connector`,
    `self:check_version_compat`) -- Lua's DOMINANT OOP method-call syntax
    (calls-recall-oracle Lua measurement, BACK-730, sixteenth language).
    `_extract_callee` leaves colon-calls receiver-qualified same as dotted
    calls (by design, see nav_calls.py), but this function never split on a
    bare single `:` -- only `->`/`.`/`::` -- so every colon-method call's
    bare callee stayed the full "receiver:method" string and never matched
    a bare `?target=method` lookup. Adding a plain `rfind(':')` to the same
    `max(...)` is safe for `::`-using languages too: for an actual `::`
    occurrence, `rfind(':')` can only land one character to the right of
    `rfind('::')` (the second colon of the same pair), and both branches
    below resolve to the identical split point (either the literal `::`
    branch consumes 2 chars from the `::` start, or the single-`:` branch
    consumes 1 char from one position later) -- so C++'s
    `Engine::get_singleton` and PHP/Java's `Class::method` are unaffected.
    """
    if callee.startswith('new '):
        callee = callee[4:]
    if callee.startswith('\\'):
        callee = callee[1:]
    idx = max(callee.rfind('->'), callee.rfind('.'), callee.rfind('::'), callee.rfind(':'))
    if idx == -1:
        bare = callee
    elif callee[idx:idx + 2] in ('->', '::'):
        bare = callee[idx + 2:]
    else:
        bare = callee[idx + 1:]
    gidx = bare.find('<')
    bare = bare[:gidx] if gidx != -1 else bare
    return bare.strip()


def _index_callee(
    index: Dict[str, List[Dict[str, Any]]],
    callee: str,
    record: Dict[str, Any],
    alias_map: Dict[str, str],
    class_aliases: Optional[List[ClassAliasSpan]] = None,
) -> None:
    """Add *record* to *index* under the bare name, dotted/arrow form, and canonical alias."""
    bare = _bare_callee_name(callee)
    index.setdefault(bare, []).append(record)
    if bare != callee:
        index.setdefault(callee, []).append(record)
    # An import alias renames a bare call only: after ``from m import helper as h``, ``h()`` is
    # ``m.helper`` but ``o.h()`` is still a method called h (BACK-1820's rule in resolve.py).
    # The exception is ``self.X``/``cls.X`` where the class body binds ``X = <alias>`` (BACK-1846).
    if bare == callee:
        canonical = alias_map.get(bare)
    else:
        canonical = class_attribute_alias(callee, record.get('line', 0), class_aliases or [])
    if canonical and canonical != bare:
        index.setdefault(canonical, []).append(record)


def _bfs_level(
    index: Dict[str, List[Dict[str, Any]]],
    current_targets: Set[str],
    visited_callers: Set[Tuple[str, str]],
) -> Tuple[List[Dict[str, Any]], Set[str]]:
    """Run one BFS level: return (level_records, next_targets).

    A qualified target (`Foo::run`, and every caller name fed back in as the
    next level's target) is also looked up by its bare name, which is how call
    sites are indexed (BACK-1390).
    """
    level_records: List[Dict[str, Any]] = []
    next_targets: Set[str] = set()
    for t in sorted(current_targets):
        bare = _bare_callee_name(t)
        records = index.get(t, []) + (index.get(bare, []) if bare != t else [])
        for record in records:
            key = (record['file'], record['caller'])
            if key in visited_callers:
                continue
            visited_callers.add(key)
            level_records.append({**record, 'callee': t})
            next_targets.add(record['caller'])
    return level_records, next_targets


# BACK-1265: names referenced without a call expression, per Python file.
# Separate cache from _INDEX_CACHE because it is derived from a different pass.
_REFERENCE_CACHE: OrderedDict = OrderedDict()
_REFERENCE_CACHE_MAX = 8


def _evict_callers_root(root: str) -> None:
    _INDEX_CACHE.pop(root, None)


def _evict_reference_root(root: str) -> None:
    _REFERENCE_CACHE.pop(root, None)


register_validated_cache(__name__ + '.callers', _INDEX_CACHE, _evict_callers_root)
register_validated_cache(__name__ + '.references', _REFERENCE_CACHE, _evict_reference_root)


def _python_referenced_names(directory: Path, *,
                             structures: Optional[StructureList] = None) -> Set[str]:
    """Names a Python file references without calling them directly.

    build_callers_index only walks `elements`, and only those in the
    functions/methods/tests categories, so it sees two kinds of use and misses
    a third:

    1. Module-level calls are invisible. A function called as `main()` inside
       `if __name__ == "__main__":` is not inside any element, so it was
       reported as uncalled in the same file that calls it -- the single
       clearest false positive in the external precision sample.
    2. A bare identifier passed as an argument, keyword, or assigned value --
       `Thread(target=fn)`, `set_defaults(func=fn)`, `mock.side_effect = fn`,
       Airflow's `python_callable=fn`, Flask's `view_func=` -- is a use, and a
       statically visible one. The extractor records the *call* (`Thread`) and
       drops its arguments, so every callback registered this way read as dead.

    Deliberately errs toward "referenced": a bare Name load that happens to be
    an unrelated variable of the same name suppresses one true positive, while
    the inverse costs a reader a full manual verification to disprove. For a
    dead-code report that trade is the right way round.

    Python-only, and honest about it: this reads Python's own AST. The
    equivalent JS/TS mechanisms (JSX invocation, test-framework callbacks,
    object shorthand) need the same treatment in that analyzer.
    """
    from ...utils.exclusions import active_exclusions
    cache_key = (_dir_cache_key(directory), active_exclusions(), gitignore_enabled())
    dir_str = str(directory)
    known_loss = structures is not None and bool(getattr(structures, 'traversal_failures', ()))
    if known_loss:
        _REFERENCE_CACHE.pop(dir_str, None)
    cached = _REFERENCE_CACHE.get(dir_str)
    if cached and cached[0] == cache_key:
        _REFERENCE_CACHE.move_to_end(dir_str)
        return cached[1]

    skipped: List[Tuple[str, str]] = []
    traversal_failures: List[Tuple[Optional[str], str]] = []

    def on_error(error: OSError) -> None:
        traversal_failures.append((
            to_posix(error.filename) if error.filename else None, f'{type(error).__name__}: {error}'))

    referenced: Set[str] = set()
    for py_file in _iter_python_files(directory, on_error=on_error):
        try:
            if is_unsafe_scan_root(py_file.parent):
                continue
            tree = parse_python(py_file.read_text(encoding='utf-8', errors='ignore'), str(py_file))
        except (OSError, SyntaxError, ValueError, RecursionError) as error:
            skipped.append((to_posix(py_file), f'{type(error).__name__}: {error}'))
            continue

        referenced.update(_python_tree_referenced_names(tree))

    if structures is not None:
        _record_reference_failures(structures, skipped, traversal_failures)
    if known_loss or skipped or traversal_failures:
        _REFERENCE_CACHE.pop(dir_str, None)
        return referenced
    _REFERENCE_CACHE[dir_str] = (cache_key, referenced)
    _REFERENCE_CACHE.move_to_end(dir_str)
    if len(_REFERENCE_CACHE) > _REFERENCE_CACHE_MAX:
        _REFERENCE_CACHE.popitem(last=False)
    return referenced


def _python_tree_referenced_names(tree: Any) -> Set[str]:
    """Collect the existing call/decorator/load references from one parsed Python tree."""
    import ast as _ast

    referenced: Set[str] = set()
    called_here = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Call):
            func = node.func
            if isinstance(func, _ast.Name):
                called_here.add(func.id)
                referenced.add(func.id)
            elif isinstance(func, _ast.Attribute):
                referenced.add(func.attr)
        elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, _ast.Call) else dec
                if isinstance(target, _ast.Name):
                    referenced.add(target.id)
                elif isinstance(target, _ast.Attribute):
                    referenced.add(target.attr)

    # Second pass: bare identifiers in load position that are not the
    # function of a call (those are already counted above).
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Name) and isinstance(node.ctx, _ast.Load):
            referenced.add(node.id)

    return referenced


def _record_reference_failures(structures: StructureList, skipped: List[Tuple[str, str]],
                               traversal_failures: List[Tuple[Optional[str], str]]) -> None:
    """Merge required reference loss into the existing collection's diagnostic channels."""
    identified = {os.path.normcase(os.path.realpath(path)) for path, _ in structures.skipped}
    for path, cause in skipped:
        identity = os.path.normcase(os.path.realpath(path))
        if identity not in identified:
            structures.skipped.append((path, cause))
            identified.add(identity)
    structures.traversal_failures.extend(traversal_failures)


def _iter_python_files(directory: Path, *,
                       on_error: Optional[Callable[[OSError], None]] = None) -> Iterator[Path]:
    """The .py files the callers index sees: the shared walker's, as collect_structures'
    (BACK-1577) -- skip dirs, what git ignores, REVEAL_IGNORE and --exclude.

    BACK-1386: this was a bare rglob('*.py') that walked .venv/,
    node_modules/ and every git-ignored tree, so a name referenced only in a
    vendored or generated file hid a genuinely uncalled function.
    """
    for fp in _walk_code_files(directory, on_error=on_error):
        if fp.suffix == '.py' and is_code_file(fp):
            yield fp


def _dir_cache_key(directory: Path) -> Any:
    """Compute a hashable cache key for *directory*.

    Stats every immediate child directory in addition to the directory itself.
    Immediate membership changes can update these mtimes; file overwrites and
    deeper changes need not. This cheap key is not complete file evidence.

    An unreadable key records a failed key lookup, not proof that the directory
    is empty. Structural discovery separately records encountered input loss.
    """
    from ...utils.path_utils import is_noise_dir
    try:
        mtimes = [os.stat(directory).st_mtime_ns]
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False) and not is_noise_dir(directory, entry.name):
                    try:
                        mtimes.append(os.stat(entry).st_mtime_ns)
                    except OSError:
                        pass
        return ('dir_mtimes', tuple(sorted(mtimes)))
    except OSError:
        return ('unreadable', str(directory))


class CallersIndex(Dict[str, List[Dict[str, Any]]]):
    """The callers index plus ``skipped``: ``(file, cause)`` for every file whose
    analysis failed, so the cached index keeps saying what it is missing (BACK-1860)."""

    skipped: List[Tuple[str, str]]
    traversal_failures: List[Tuple[Optional[str], str]]


def _disclose_skipped(result: Dict[str, Any], skipped: Sequence[Tuple[str, str]], *,
                      traversal_failures: Sequence[Tuple[Optional[str], str]] = ()) -> Dict[str, Any]:
    """Carry file and directory loss separately for adapter metadata construction.

    Private carriers are absent when empty and consumed before building the envelope.
    """
    if skipped:
        result['analysis_skipped'] = [list(item) for item in skipped]
    if traversal_failures:
        result['analysis_traversal_failures'] = [list(item) for item in traversal_failures]
    return result


def _structures_or_collect(structures: Optional[StructureList], directory: Path) -> StructureList:
    """The caller's already-collected structures, else collect them (BACK-1868)."""
    return collect_structures(str(directory)) if structures is None else structures


def _cache_callers_index(dir_str: str, cache_key: Any, index: CallersIndex,
                         structures: StructureList) -> None:
    # Directory mtimes cannot prove recovery after an included subtree was unreadable, nor
    # can a tree stamp after a file was (chmod moves only ctime) or a worker died (BACK-2093).
    # A failure the content causes is stored: the same bytes fail the same way.
    if getattr(structures, 'traversal_failures', []) or any(
            environmental_failure(cause) for _, cause in index.skipped):
        _INDEX_CACHE.pop(dir_str, None)
        return
    _INDEX_CACHE[dir_str] = (cache_key, index)
    _INDEX_CACHE.move_to_end(dir_str)
    if len(_INDEX_CACHE) > _INDEX_CACHE_MAX:
        _INDEX_CACHE.popitem(last=False)


def _cached_callers_index(dir_str: str, cache_key: Any,
                          structures: Optional[StructureList]) -> Optional[CallersIndex]:
    """Reuse a matching index only when supplied evidence has no known directory loss."""
    if getattr(structures, 'traversal_failures', []):
        return None
    if dir_str in _INDEX_CACHE and _INDEX_CACHE[dir_str][0] == cache_key:
        _INDEX_CACHE.move_to_end(dir_str)
        return _INDEX_CACHE[dir_str][1]
    return None


def build_callers_index(path: str, structures: Optional[StructureList] = None) -> CallersIndex:
    """Return project-level callers index for *path* (file or directory).

    The index maps each callee name to a list of caller records::

        {
          "validate_item": [
              {"file": "app.py", "caller": "process_batch", "line": 42},
              {"file": "worker.py", "caller": "run_job", "line": 17},
          ],
          ...
        }

    Results are cached by a directory mtime fingerprint and active scope. This
    cheap key does not detect every file change. Supplied structures with known
    directory traversal loss bypass a matching hit and are not cached; nor is an index
    with a file skipped for an environmental reason (``environmental_failure``).

    Args:
        path: File or directory to index.
        structures: ``collect_structures(<the directory>)`` the caller already
            holds, used instead of collecting again on a cache miss (BACK-1868:
            ``find_uncalled`` built every file's structure twice). Must come from
            the same directory and scope as *path*.

    Returns:
        Inverted call graph dict (callee → list of caller dicts).
    """
    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    dir_str = str(directory)

    # Check cache. BACK-1257: the key must include the active --exclude scope,
    # or a long-lived host (the MCP server) would serve an unfiltered index to a
    # later filtered request over the same tree — _dir_cache_key fingerprints
    # directory mtimes only, which exclusion does not change. BACK-1386: same
    # for the gitignore switch (--no-gitignore changes the file set).
    from ...utils.exclusions import active_exclusions
    cache_key = (_dir_cache_key(directory), active_exclusions(), gitignore_enabled())
    cached = _cached_callers_index(dir_str, cache_key, structures)
    if cached is not None:
        return cached

    # Build index
    structures = _structures_or_collect(structures, directory)
    index = CallersIndex()
    index.skipped = list(structures.skipped)
    index.traversal_failures = list(getattr(structures, 'traversal_failures', ()))

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        # Build alias → canonical name map for this file so that calls using
        # an import alias (e.g. `h` for `from utils import helper as h`) also
        # index the definition name (`helper`).  This prevents find_uncalled
        # from falsely reporting `helper` as dead code and lets find_callers
        # locate callers that use the alias.
        alias_map = build_alias_map(file_path)
        class_aliases = build_class_attribute_aliases(file_path, alias_map)
        for elem in call_sources(file_struct):
            # 'tests' (Zig's TestDecl blocks — the only 'tests'-category
            # producer today) counts as a caller here for the same reason
            # JS/TS's describe()/it() callbacks are folded into 'functions'
            # (BACK-334): a function called only from a test previously
            # reported zero callers — indistinguishable from dead code,
            # BACK-660's exact failure mode, just one hop further in.
            if elem.get('category') not in ('functions', 'methods', 'tests', 'modules'):
                continue
            record_base = {
                'file': file_path,
                'caller': elem.get('name', ''),
                'line': elem.get('line', 0),
            }
            for callee in elem.get('calls', []):
                record = {**record_base, 'call_expr': callee}
                refs = [r for r in elem.get('references', []) if r['callee'] == callee]
                if refs:
                    record.update(relationship='jsx_reference' if callee in elem.get('reference_only_calls', []) else 'call_and_jsx_reference',
                                  reference_lines=sorted({r['line'] for r in refs}))
                    if elem.get('call_lines', {}).get(callee):
                        record['call_lines'] = elem['call_lines'][callee]
                if elem.get('caller_kind') == 'module':
                    # `line` is the first site of any kind; `call_lines` only the calls (JSX uses are `reference_lines`).
                    sites = [site for site in elem['call_sites'] if site['callee'] == callee]
                    record.update(caller_kind='module', line=min(site['line'] for site in sites),
                                  call_lines=sorted({site['line'] for site in sites if site.get('relationship') != 'jsx_reference'}))
                _index_callee(index, callee, record, alias_map, class_aliases)

    _cache_callers_index(dir_str, cache_key, index, structures)
    return index


def find_callees(
    path: str,
    target: str,
    include_builtins: bool = False,
    source: Optional['CalleeSource'] = None,
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
            stripped from the call list of Python-file matches only — other
            languages' calls (e.g. Scala/Ruby ``.map``/``.filter``) are never
            filtered, since PYTHON_BUILTINS names can collide with other
            languages' real methods.  Pass True to see the raw list.
        source: ``callee_source(<the directory>)`` the caller already holds (the
            callee walk reads the same one), used instead of collecting again.

    Returns:
        Dict with ``target``, ``matches`` (one entry per definition found),
        ``total_calls`` count, and ``_builtins_hidden`` (count filtered out).
    """
    if source is None:
        source = callee_source(path)

    matches: List[Dict[str, Any]] = []
    builtins_hidden = 0
    # Every call source, 'tests' included for the same reason as build_callers_index
    # (BACK-663): a Zig test carries a populated `calls` list (BACK-660), so "what does
    # this test call" works the same way "what calls X" already does.
    for definition in source.definitions:
        if not name_matches(definition.name, target):
            continue
        calls = list(definition.calls)
        builtins = conventions_for(_lang_family(definition.file)).builtins
        if not include_builtins and builtins:
            filtered = [c for c in calls if c.split('.')[-1] not in builtins]
            builtins_hidden += len(calls) - len(filtered)
            calls = filtered
        matches.append({
            'file': definition.file,
            'function': definition.name,
            'line': definition.line,
            'calls': calls,
            'references': [dict(reference) for reference in definition.references],
            'reference_only_calls': list(definition.reference_only_calls),
        })

    result: Dict[str, Any] = {
        'target': target,
        'query': 'callees',
        'matches': matches,
        'total_calls': sum(len(m['calls']) for m in matches),
        '_builtins_hidden': builtins_hidden,
    }
    return _disclose_skipped(result, source.skipped, traversal_failures=source.traversal_failures)


# Root selection and per-definition detail for the forward walk (moved from trace.py).
_ROOT_WITH_FILE = re.compile(r'^(?P<file>.+\.[A-Za-z0-9_+]+):(?P<name>[^:].*)$')


def _split_root(root: str) -> Tuple[str, str]:
    """`src/a.py:run` -> ('src/a.py', 'run'); `run` / `Foo::run` -> ('', name)."""
    m = _ROOT_WITH_FILE.match(root)
    return (m.group('file'), m.group('name')) if m else ('', root)


def _path_matches(file_path: str, file_filter: str) -> bool:
    if not file_filter:
        return True
    want = Path(file_filter)
    if want.is_absolute():
        return Path(file_path).resolve() == want.resolve()
    return Path(file_path).parts[-len(want.parts):] == want.parts

def _split_top_level_commas(text: str) -> List[str]:
    """Split on commas that are not nested inside (), [] or {}.

    Type annotations routinely contain commas (`dict[str, str]`,
    `Callable[[int], None]`, `tuple[int, ...]`), so a naive `str.split(',')`
    over a parameter list fabricates phantom parameters.
    """
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    for ch in text:
        if ch in '([{':
            depth += 1
        elif ch in ')]}':
            depth = max(0, depth - 1)
        if ch == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append(''.join(current))
    return parts


def _params_from_signature(signature: str, func_name: str) -> List[str]:
    """Extract parameter names from a function signature string.

    Signature format from tree-sitter: '(param1: Type, *args) -> ReturnType'
    or just '(param1, param2)'. A parameter's type annotation or default can
    itself contain commas, parens and brackets (`dict[str, str]`,
    `Callable[[], None]`, `x=foo()`), so the list is delimited by the paren
    that matches the opening one — not the first close-paren — and split on
    top-level commas only. A naive `split('(',1)[1].split(')',1)[0]` +
    `split(',')` produced phantom params like `str] | None` from
    `error_...placeholders: dict[str, str] | None` and truncated on any
    default containing `)`.
    """
    start = signature.find('(')
    if start == -1:
        return []
    depth = 0
    end = -1
    for i in range(start, len(signature)):
        ch = signature[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                end = i
                break
    inner = signature[start + 1:end] if end != -1 else signature[start + 1:]
    params = []
    for part in _split_top_level_commas(inner):
        name = part.strip().lstrip('*').split(':')[0].split('=')[0].strip()
        if name and name not in ('self', 'cls', '/', ''):
            params.append(name)
    return params


def _effects_from_calls(calls: List[str], classify_call, language=None) -> List[str]:
    """Return deduplicated effect labels for a function's call list."""
    effects: List[str] = []
    seen: Set[str] = set()
    for callee in calls:
        kind = classify_call(callee, language)
        if kind:
            label = f"{kind}:{callee.split('.')[-1]}"
            if label not in seen:
                seen.add(label)
                effects.append(label)
    return effects


# --- The forward walk (BACK-2096): one engine for ?callees=&depth= and the retired ?root=/trace://
#
# Level by level over definitions from every root definition. Each definition is expanded once,
# at the shallowest level the walk reaches it, and every call site of an expanded definition is
# an edge -- an edge to a definition already reached is kept and marked `expanded: false`.
# trace walked depth-first and never expanded a definition it had first reached deeper (its
# callees vanished); ?root dropped the edge itself once its target had been seen, across root
# definitions too. Call sites resolve through calls.resolve.CallResolver, unchanged.

_CALL_SOURCE_CATEGORIES = ('functions', 'methods', 'tests', 'modules')


def _call_definitions(structures: Sequence[Dict[str, Any]]) -> Iterator[Tuple[str, str, Dict[str, Any]]]:
    """(file, name, element) for every named call source: functions, methods, modules and
    'tests', so a Zig test block can be a root or be passed through (BACK-663)."""
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        for elem in call_sources(file_struct):
            if elem.get('category') not in _CALL_SOURCE_CATEGORIES:
                continue
            name = elem.get('name', '')
            if name:
                yield file_path, name, elem


class CallSource(NamedTuple):
    """One named call source as collected: the structure's file spelling, calls unfiltered."""
    file: str
    name: str
    line: int
    signature: Any
    calls: Tuple[str, ...]
    references: Tuple[Dict[str, Any], ...]
    reference_only_calls: Tuple[str, ...]


class CalleeSource:
    """What every forward query reads from one structure collection: ``find_callees``
    (depth 1, ``FILE:NAME``), ``walk_callees`` (depth >= 2, ``?root=``, trace) and the
    ``--detail`` params/effects. Definitions keep collection order and the file spelling of
    the collection; builtins, names, depth and detail apply at query time, never here.
    ``skipped``/``traversal_failures`` are the collection's loss evidence."""

    __slots__ = ('definitions', 'skipped', 'traversal_failures')

    def __init__(self, definitions: Tuple[CallSource, ...], skipped: Sequence[Tuple[str, str]] = (),
                 traversal_failures: Sequence[Tuple[Optional[str], str]] = ()) -> None:
        self.definitions = definitions
        self.skipped: Tuple[Tuple[str, str], ...] = tuple(skipped)
        self.traversal_failures: Tuple[Tuple[Optional[str], str], ...] = tuple(traversal_failures)

    @classmethod
    def from_structures(cls, structures: Sequence[Dict[str, Any]]) -> 'CalleeSource':
        intern = sys.intern
        definitions = tuple(CallSource(
            intern(file_path), intern(name), elem.get('line', 0), elem.get('signature', ''),
            tuple(intern(call) for call in elem.get('calls', [])), tuple(elem.get('references', [])),
            tuple(elem.get('reference_only_calls', []))) for file_path, name, elem in _call_definitions(structures))
        return cls(definitions, getattr(structures, 'skipped', ()), getattr(structures, 'traversal_failures', ()))

    def in_file(self, file_filter: str) -> 'CalleeSource':
        """The definitions of the files FILE:NAME selects, keeping the collection's loss evidence."""
        return CalleeSource(tuple(d for d in self.definitions if _path_matches(d.file, file_filter)),
                            self.skipped, self.traversal_failures)


def callee_source(path: str) -> CalleeSource:
    """The forward queries' input for *path* (a file reads its directory)."""
    path_obj = Path(path)
    directory = path_obj if path_obj.is_dir() else path_obj.parent
    return CalleeSource.from_structures(collect_structures(str(directory)))


def _walk_index(source: CalleeSource) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """Every definition, and name -> its definitions (lookup_keys), both in (file, line) order:
    collect_structures' file order is not stable, levels and candidates must be. Calls are
    stored unfiltered; the builtins switch applies when a definition is walked."""
    definitions = [{
        'name': d.name,
        'file': to_posix(d.file),  # '/' on every OS (BACK-1586)
        'line': d.line,
        'signature': d.signature,
        'calls': list(d.calls),
        'references': [dict(reference) for reference in d.references],
        'reference_only_calls': list(d.reference_only_calls),
    } for d in source.definitions]
    definitions.sort(key=lambda d: (d['file'], d['line']))
    index: Dict[str, List[Dict[str, Any]]] = {}
    for record in definitions:
        # A C++ out-of-line `Cls::poll` is keyed as `poll` too, so a bare `poll()`
        # call site reaches it (BACK-1400).
        for key in lookup_keys(record['name']):
            index.setdefault(key, []).append(record)
    return definitions, index


def _walked_calls(record: Dict[str, Any], include_builtins: bool) -> List[str]:
    """A definition's call sites, de-duplicated by call text, builtins hidden unless asked."""
    calls = record['calls']
    builtins = conventions_for(_lang_family(record['file'])).builtins
    if not include_builtins and builtins:
        calls = [c for c in calls if c.split('.')[-1] not in builtins]
    return list(dict.fromkeys(calls))


@dataclass
class CalleeNode:
    """One definition the walk reached, at the shallowest level it is reached (0 = a root).
    ``edges`` pairs each call site with the node that call placed, or None (external,
    ambiguous, or already reached)."""
    name: str
    file: str
    line: int
    level: int
    params: List[str]
    effects: List[str]
    references: List[Dict[str, Any]]
    expanded: bool
    record: Dict[str, Any] = field(repr=False)
    edges: List[Tuple[Dict[str, Any], Optional['CalleeNode']]] = field(default_factory=list)


@dataclass
class CalleeWalk:
    """The walk from *root*: its root definitions and the edges of each level (1 first)."""
    root: str
    root_name: str
    depth: int
    roots: List[CalleeNode]
    levels: List[Dict[str, Any]]
    skipped: List[Tuple[str, str]]
    traversal_failures: List[Tuple[Optional[str], str]]


def _callee_node(record: Dict[str, Any], name: str, level: int, depth: int) -> CalleeNode:
    """A reached definition with trace's per-node detail: parameters, and the effects its
    calls classify as (a JSX component use is not a call, BACK-1834)."""
    from ..ast.nav_effects import classify_call  # noqa: I006 -- nav_effects imports this module
    from ...registry import language_for_extension
    calls = [c for c in record['calls'] if c not in record['reference_only_calls']]
    return CalleeNode(
        name=name, file=record['file'], line=record['line'], level=level,
        params=_params_from_signature(record['signature'], record['name']),
        effects=_effects_from_calls(calls, classify_call, language_for_extension(Path(record['file']).suffix)),
        references=record['references'], expanded=level < depth, record=record)


def _callee_edge(node: CalleeNode, call: str, resolver: Any) -> Tuple[Dict[str, Any], Any]:
    """One call site of *node*: the edge record and its target (definition, candidates, None)."""
    tail, target = resolver.resolve(call, node.file)
    edge: Dict[str, Any] = {
        'caller': node.name,
        'callee': tail if target is not None else call,
        'resolved': target is not None,
        'caller_file': node.file,
        'caller_line': node.line,
    }
    if isinstance(target, dict):
        edge['callee_file'], edge['callee_line'] = target['file'], target['line']
    elif target:
        edge['ambiguous'] = True
        edge['candidates'] = [{'file': c['file'], 'line': c['line']} for c in target]
    edge['call_expr'] = call
    if any(r['callee'] == call for r in node.references):
        edge['relationship'] = ('jsx_reference' if call in node.record['reference_only_calls']
                                else 'call_and_jsx_reference')
    return edge, target


def walk_callees(path: str, root: str, depth: int = 2, include_builtins: bool = False,
                 source: Optional[CalleeSource] = None) -> CalleeWalk:
    """Walk what *root* calls, level by level, to *depth* levels of edges (1 = direct calls).

    *root* is a name, matched like ``find_callees`` (``core.definition_names.name_matches``),
    or ``FILE:NAME`` to pick the definitions in one file; every matching definition is a
    starting point. A definition is expanded once, at the shallowest level it is reached;
    every call site of an expanded definition is an edge, ``expanded`` true only on the
    edge whose target's own calls the next level lists. Its level-1 edges are exactly
    ``find_callees``' call lists for the same definitions.

    Args:
        path: Root directory (or file) to search.
        root: Entry-point name, or ``FILE:NAME``.
        depth: Levels of edges to walk (the caller clamps it to 1..5).
        include_builtins: Keep calls to language builtins (hidden by default).
        source: ``callee_source`` of the directory the caller already holds (trace builds
            it from the structures it validated); ``callee_source(path)`` when None.
    """
    from .resolve import CallResolver  # noqa: I006 -- resolve imports this module

    if source is None:
        source = callee_source(path)
    definitions, index = _walk_index(source)
    resolver = CallResolver(index)
    file_filter, root_name = _split_root(root)
    placed: Set[Tuple[str, int, str]] = set()

    def place(record: Dict[str, Any], name: str, level: int) -> CalleeNode:
        placed.add((record['file'], record['line'], record['name']))
        return _callee_node(record, name, level, depth)

    roots = [place(record, root_name, 0) for record in definitions
             if name_matches(record['name'], root_name) and _path_matches(record['file'], file_filter)]
    levels: List[Dict[str, Any]] = []
    frontier = list(roots)
    for level in range(1, depth + 1):
        level_edges: List[Dict[str, Any]] = []
        next_frontier: List[CalleeNode] = []
        for node in frontier:
            for call in _walked_calls(node.record, include_builtins):
                edge, target = _callee_edge(node, call, resolver)
                child = None
                if isinstance(target, dict) and (target['file'], target['line'], target['name']) not in placed:
                    child = place(target, edge['callee'], level)
                    if child.expanded:
                        next_frontier.append(child)
                edge['expanded'] = child is not None and child.expanded
                node.edges.append((edge, child))
                level_edges.append(edge)
        if level_edges:
            levels.append({'level': level, 'callees': level_edges})
        frontier = next_frontier
        if not frontier:
            break
    return CalleeWalk(root=root, root_name=root_name, depth=depth, roots=roots, levels=levels,
                      skipped=list(source.skipped), traversal_failures=list(source.traversal_failures))


def callee_levels(walk: CalleeWalk) -> Dict[str, Any]:
    """The ``calls://?root=`` answer: every edge by level. Totals count edges:
    ``total_resolved`` includes the ``total_ambiguous`` ones (a project definition matched,
    several candidates), ``total_unresolved`` are external."""
    edges = [edge for level in walk.levels for edge in level['callees']]
    resolved = sum(1 for edge in edges if edge['resolved'])
    return _disclose_skipped({
        'root': walk.root,
        'query': 'callees_recursive',
        'depth': walk.depth,
        'levels': walk.levels,
        'total_resolved': resolved,
        'total_unresolved': len(edges) - resolved,
        'total_edges': len(edges),
        'total_ambiguous': sum(1 for edge in edges if edge.get('ambiguous')),
    }, walk.skipped, traversal_failures=walk.traversal_failures)


def _build_forward_index(
    structures: List[Dict[str, Any]],
    include_builtins: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build name → [{file, line, calls}] forward call index from collected structures
    (``--sideeffects --transitive``; builtins filtered at build, in structure order)."""
    forward: Dict[str, List[Dict[str, Any]]] = {}
    for file_path, name, elem in _call_definitions(structures):
        calls = elem.get('calls', [])
        builtins = conventions_for(_lang_family(file_path)).builtins
        if not include_builtins and builtins:
            calls = [c for c in calls if c.split('.')[-1] not in builtins]
        record = {'file': file_path, 'line': elem.get('line', 0), 'calls': calls,
                  'references': elem.get('references', []),
                  'reference_only_calls': elem.get('reference_only_calls', [])}
        for key in lookup_keys(name):
            forward.setdefault(key, []).append(record)
    return forward


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
            # '/' on every OS (BACK-1586); copies, so the cached index keeps its own records.
            levels.append({'level': level + 1,
                           'callers': [{**r, 'file': to_posix(r['file'])} if r.get('file') else r
                                       for r in level_records]})
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
    _disclose_skipped(result, index.skipped, traversal_failures=getattr(index, 'traversal_failures', ()))

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
    if is_unsafe_scan_root(parent):
        return False
    count = 0
    for fp in _walk_code_files(Path(parent)):  # count what the scan itself would see
        if is_code_file(fp):
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


# Families whose constructors are declared as `[modifiers] TypeName(...)` with no
# return type, so a definition line of that shape is a constructor (BACK-1392).
_CTOR_SHAPE_FAMILIES = frozenset({'java', 'csharp', 'c', 'dart'})
_CTOR_MODIFIERS = (r'(?:public|private|protected|internal|static|explicit|inline|constexpr'
                   r'|const|external|factory|extern|unsafe)')
_ANNOTATION_PREFIX = r'(?:(?:@[\w.]+(?:\([^)]*\))?|\[[^\]]*\])\s*)*'
# Families where `override` is a declaration keyword/annotation (Python has no keyword;
# its typing.override arrives as a decorator).
_OVERRIDE_FAMILIES = frozenset({'java', 'csharp', 'c', 'dart', 'kotlin', 'swift', 'scala'})
_OVERRIDE_ANNOTATION = re.compile(r'@[Oo]verride\b')


def _definition_line(lines: List[str], line_no: int, name: str) -> int:
    """1-based line of `name(`'s definition at or just after `line_no` (analyzers
    may report a leading annotation's line as the start), or 0."""
    call = re.compile(rf'(?<![\w.]){re.escape(name)}\s*[(<]')
    for ln in range(line_no, min(line_no + 5, len(lines) + 1)):
        if ln >= 1 and call.search(lines[ln - 1]):
            return ln
    return 0


def _is_constructor_definition(name: str, family: str, file_path: str, line_no: int,
                               cache: Dict[str, List[str]]) -> bool:
    """A Java/C#/C++/Dart constructor: only modifiers and annotations precede the
    type name on its definition line (a method always has a return type). They are
    invoked by `new T()` / `T()` / enum constants / DI, or deliberately never
    (a private utility-class constructor), not by a call to their name."""
    if family not in _CTOR_SHAPE_FAMILIES or file_path.endswith('.c'):
        return False
    if name in conventions_for(family).test_lifecycle_names:  # TEST(...), TEST_F(...)
        return False
    head = name.split('.', 1)[0]
    # Dart methods may omit their return type; its type names are UpperCamel.
    if family == 'dart' and not head[:1].isupper():
        return False
    lines = _read_lines(file_path, cache)
    ln = _definition_line(lines, line_no, name)
    if not ln:
        return False
    shape = rf'^\s*{_ANNOTATION_PREFIX}(?:{_CTOR_MODIFIERS}\s+)*{re.escape(name)}\s*[(<]'
    return re.match(shape, lines[ln - 1]) is not None


# `name(...) [const] [noexcept] override|final` in a C++ class body.
_CPP_OVERRIDE_DECL = re.compile(
    r'(~?\w+)\s*\([^;{}]*\)\s*(?:const\s*)?(?:noexcept(?:\([^)]*\))?\s*)?(?:override|final)\b')


# Godot's GDCLASS macro generates the code that calls these by name (Object's
# notification and property reflection); the class itself never calls them.
_GODOT_GDCLASS_HOOKS = frozenset({
    '_bind_methods', '_bind_compatibility_methods', '_notification', '_validate_property',
    '_set', '_get', '_get_property_list', '_property_can_revert', '_property_get_revert',
})


def _uses_gdclass(file_path: str, cache: Dict[str, List[str]]) -> bool:
    """The definition's file, or its same-stem header, declares a Godot GDCLASS."""
    path = Path(file_path)
    for candidate in (path, path.with_suffix('.h'), path.with_suffix('.hpp')):
        if any('GDCLASS(' in line for line in _read_lines(str(candidate), cache)):
            return True
    return False


def _cpp_override_names(structures: List[Dict[str, Any]], cache: Dict[str, List[str]]) -> Set[str]:
    """Method names declared `override`/`final` in any scanned C/C++ file. The
    keyword lives on the in-class declaration (usually a header), not on the
    out-of-line `Node2D::_notification(...)` definition it names."""
    names: Set[str] = set()
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        if _lang_family(file_path) != 'c' or file_path.endswith('.c'):
            continue
        text = ''.join(_read_lines(file_path, cache))
        if 'override' in text or 'final' in text:
            names.update(_CPP_OVERRIDE_DECL.findall(text))
    return names


def _is_override_definition(name: str, family: str, file_path: str, line_no: int,
                            signature: str, cache: Dict[str, List[str]]) -> bool:
    """`override` modifier (C#, Kotlin, Swift, Scala, C++ `) override`) or an
    `@Override`/`@override` annotation (Java, Dart) on the definition. An override
    is reached through its base type -- usually a framework's -- the same
    reason trait-impl methods are excluded (BACK-1291)."""
    if family not in _OVERRIDE_FAMILIES:
        return False
    if re.search(r'\boverride\b', signature):
        return True
    lines = _read_lines(file_path, cache)
    ln = _definition_line(lines, line_no, name)
    if not ln:
        return False
    if re.search(r'\boverride\b', lines[ln - 1].replace(name, '', 1)):
        return True
    # Annotation lines directly above the definition (and any it was reported at).
    above = ln - 1
    while above >= 1 and lines[above - 1].strip().startswith(('@', '[')):
        if _OVERRIDE_ANNOTATION.search(lines[above - 1]):
            return True
        above -= 1
    return False


def _has_test_annotation(
    file_path: str,
    line_no: int,
    cache: Dict[str, List[str]],
    markers: Tuple[str, ...],
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
    return any(marker in blob for marker in markers)


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
    conv = conventions_for(_lang_family(file_path))
    if decorator_names & conv.test_decorators or conv.is_test_name(name, file_path):
        return True
    return (
        bool(line_no) and bool(conv.test_annotation_markers)
        and _has_test_annotation(file_path, line_no, cache, conv.test_annotation_markers)
    )


def _project_entry_point_decorators(directory: Path) -> FrozenSet[str]:
    """Read project-declared entry-point decorator names from .reveal.yaml (BACK-952).

    ``adapters.calls.entry_points.decorators`` — bare decorator names (after
    stripping the module prefix, same convention as _get_decorator_names())
    for web/CLI framework routes not covered by _IMPLICIT_DECORATORS, e.g.::

        adapters:
          calls:
            entry_points:
              decorators: [route, get, post, put, delete, command]  # Flask/FastAPI/Click

    Project config is additive to each language's own framework decorators
    (``LanguageConventions.entry_point_decorators``, BACK-1265/BACK-1273):
    requiring every web project to declare Flask/FastAPI/Spring/NestJS
    decorators before its routes stop reading as dead code is a configuration
    step nobody knows to take.
    """
    from ...config import get_config
    config = get_config(start_path=directory)
    entry_points = config.get_adapter_config('calls', 'entry_points')
    decorators = entry_points.get('decorators', []) if isinstance(entry_points, dict) else []
    return frozenset(str(d) for d in decorators)


def _record_non_python_reference_failure(skipped: List[Tuple[str, str]],
                                        file_path: str, error: OSError) -> None:
    """Keep first-cause file identity on this query's diagnostic copy only."""
    identity = os.path.normcase(os.path.realpath(file_path))
    if not any(os.path.normcase(os.path.realpath(path)) == identity for path, _ in skipped):
        skipped.append((
            to_posix(file_path), f'{type(error).__name__}: non-Python reference read failed: {error}'))


def _drop_referenced(entries: List[Dict[str, Any]],
                     structures: List[Dict[str, Any]], *,
                     on_read_error: Optional[Callable[[str, OSError], None]] = None) -> List[Dict[str, Any]]:
    """BACK-1391: drop candidates a non-Python file uses without calling them
    (callbacks, function pointers, module/class-body calls, PHP hook strings,
    Ruby symbols). Python files get the same treatment from
    _python_referenced_names before this point."""
    candidates: Dict[str, Set[str]] = {}
    for e in entries:
        candidates.setdefault(_lang_family(e['file']), set()).add(_bare_callee_name(e['name']))
    candidates.pop('python', None)
    if not candidates:
        return entries
    definition_counts: Dict[Tuple[str, str], int] = {}
    defined_in_file: Dict[str, Dict[str, int]] = {}
    for file_struct in structures:
        file_path = file_struct.get('file', '')
        family = _lang_family(file_path)
        for elem in file_struct.get('elements', []):
            if elem.get('category') in ('functions', 'methods', 'tests') and elem.get('name'):
                bare = _bare_callee_name(elem['name'])
                definition_counts[(family, bare)] = definition_counts.get((family, bare), 0) + 1
                here = defined_in_file.setdefault(file_path, {})
                here[bare] = here.get(bare, 0) + 1
    from .references import non_python_referenced_names
    referenced = non_python_referenced_names(
        (fs.get('file', '') for fs in structures), candidates, definition_counts, defined_in_file,
        on_read_error=on_read_error)
    return [e for e in entries
            if _bare_callee_name(e['name']) not in referenced.get(_lang_family(e['file']), ())]


@dataclass
class _UncalledScope:
    """What an uncalled-symbol exclusion needs from the whole scan (BACK-1533)."""
    called_names: Set[str]
    file_lines: Dict[str, List[str]]
    extra_implicit_decorators: Any
    cpp_overrides: Set[str]
    only_functions: bool
    include_test_framework: bool


class _UncalledCandidate:
    """One definition under test, with the facts the exclusions share, computed once."""

    def __init__(self, elem: Dict[str, Any], file_path: str, category: str, name: str) -> None:
        self.elem = elem
        self.file_path = file_path
        self.category = category
        self.name = name
        self.bare_name = _bare_callee_name(name)
        self.decorator_names = _get_decorator_names(elem)
        self.is_method = _is_method_elem(elem, self.decorator_names)
        self.line_no = elem.get('line', 0)
        self.family = _lang_family(file_path)


def _x_test_block(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    # Zig test blocks are unambiguously entry points (BACK-663): category says it all.
    return (c.category == 'tests' or bool(c.elem.get('is_test_callback'))) and not s.include_test_framework


def _x_accessor(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    return bool(c.elem.get('accessor'))  # BACK-1286: runs on property access, never a call


def _x_trait_impl(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    return bool(c.elem.get('trait_impl'))  # BACK-1291: dispatched through the trait


def _x_implicit(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    return _is_implicit_element(
        c.name, c.is_method, c.decorator_names, s.only_functions, s.extra_implicit_decorators,
        lang_family=c.family,
    )


def _x_called(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    # BACK-1390: definitions can be qualified (C++ `Foo::run`, Lua `M:run`) while call
    # sites index under the bare name (`f.run()` -> `run`).
    return c.name in s.called_names or c.bare_name in s.called_names


def _x_noqa(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    return bool(c.line_no) and _has_noqa_uncalled(c.file_path, c.line_no, s.file_lines)


def _x_c_family_hook(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    return c.family == 'c' and (
        c.bare_name in s.cpp_overrides
        or (c.bare_name in _GODOT_GDCLASS_HOOKS and _uses_gdclass(c.file_path, s.file_lines))
    )


def _x_test_entry_point(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    # Before the constructor check: `TEST(Suite, Name) {` has a constructor's shape.
    return not s.include_test_framework and _is_test_entry_point(
        c.name, c.file_path, c.line_no, c.decorator_names, s.file_lines)


def _x_constructor_or_override(c: _UncalledCandidate, s: _UncalledScope) -> bool:
    return bool(c.line_no) and (
        _is_constructor_definition(c.name, c.family, c.file_path, c.line_no, s.file_lines)
        or _is_override_definition(c.name, c.family, c.file_path, c.line_no,
                                   c.elem.get('signature', ''), s.file_lines)
    )


# Evaluated in order; the first that holds names why a definition is not reported. The order
# is behavior (the test-entry-point check must precede the constructor check), and the
# per-reason counts are the result's `excluded_by_reason`, so an over-eager exclusion shows
# up as a number instead of silently shrinking the list.
_UNCALLED_EXCLUSIONS: Tuple[Tuple[str, Any], ...] = (
    ('test_block', _x_test_block),
    ('accessor', _x_accessor),
    ('trait_impl', _x_trait_impl),
    ('implicit', _x_implicit),
    ('called', _x_called),
    ('noqa', _x_noqa),
    ('c_family_hook', _x_c_family_hook),
    ('test_entry_point', _x_test_entry_point),
    ('constructor_or_override', _x_constructor_or_override),
)
_TEST_ENTRYPOINT_REASONS = ('test_block', 'test_entry_point')


def _uncalled_exclusion(candidate: _UncalledCandidate, scope: _UncalledScope) -> Optional[str]:
    """The name of the first exclusion that applies to *candidate*, or None to report it."""
    for reason, applies in _UNCALLED_EXCLUSIONS:
        if applies(candidate, scope):
            return reason
    return None


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
    - Functions decorated with a project-declared entry-point decorator —
      ``.reveal.yaml``'s ``adapters.calls.entry_points.decorators`` (BACK-952),
      for web/CLI framework routes (Flask, FastAPI, Click, …) that are
      dispatched by the framework, not a static call expression.
    - Test-runner entry points (pytest/unittest, xUnit ``[Fact]``/``[Theory]``,
      JUnit ``@Test``, …) — invoked by reflection, not a call (BACK-446).
      Set ``include_test_framework=True`` to keep them in the result.
    - Rust methods of ``impl Trait for T`` (trait dispatch, BACK-1291)
    - Zig ``test`` blocks (category='tests') — always entry points invoked by
      the test runner, never by name (BACK-663). Same opt-out flag applies.

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
        ``test_entrypoints_excluded``, ``excluded_by_reason`` (definition count per
        named exclusion, BACK-1533), and ``entries`` (list of uncalled symbols).
    """
    from ...utils.path_utils import provenance_for_display_path
    path_obj = Path(path)
    is_file = path_obj.is_file()
    directory = path_obj.parent if is_file else path_obj
    # When a single file is given, scope definitions to that file only.
    # The callers index is still built from the full directory so cross-file
    # call sites are counted (a file-local function called from a sibling is
    # NOT dead code).
    file_filter: Optional[str] = str(path_obj.resolve()) if is_file else None

    structures = collect_structures(str(directory))
    called_names: Set[str] = set(build_callers_index(path, structures).keys())
    # BACK-1265: union in names used without a direct call expression --
    # module-level calls and callbacks passed by reference. See
    # _python_referenced_names for why both were invisible to the index.
    called_names |= _python_referenced_names(directory, structures=structures)
    file_lines: Dict[str, List[str]] = {}
    extra_implicit_decorators = _project_entry_point_decorators(directory)
    cpp_overrides = _cpp_override_names(structures, file_lines)

    scope = _UncalledScope(
        called_names=called_names, file_lines=file_lines,
        extra_implicit_decorators=extra_implicit_decorators, cpp_overrides=cpp_overrides,
        only_functions=only_functions, include_test_framework=include_test_framework,
    )
    total_defined = 0
    excluded_by_reason: Dict[str, int] = {}
    entries = []

    for file_struct in structures:
        file_path = file_struct.get('file', '')
        if file_filter and str(Path(file_path).resolve()) != file_filter:
            continue
        for elem in file_struct.get('elements', []):
            category = elem.get('category')
            if category not in ('functions', 'methods', 'tests'):
                continue
            name = elem.get('name', '')
            if not name:
                continue

            total_defined += 1
            candidate = _UncalledCandidate(elem, file_path, category, name)
            reason = _uncalled_exclusion(candidate, scope)
            if reason:
                excluded_by_reason[reason] = excluded_by_reason.get(reason, 0) + 1
                continue

            entries.append({
                'name': name,
                'file': file_path,
                'line': candidate.line_no,
                'category': 'methods' if candidate.is_method else 'functions',
                'is_private': name.startswith('_'),
                # BACK-1258: a dead-code listing is exactly where vendored and
                # test code costs the reader most -- measured 15.5% vendor or
                # minified plus 17.8% test on camaleon-cms, with no field to
                # discount them by. The adapter already excludes test-framework
                # entry points and reports the count; this makes the rest of
                # the provenance visible in the same listing.
                'provenance': provenance_for_display_path(file_path, directory),
            })

    query_skipped = list(structures.skipped)
    entries = _drop_referenced(entries, structures, on_read_error=partial(
        _record_non_python_reference_failure, query_skipped))
    entries.sort(key=lambda e: (_uncalled_entry_mtime(e), e['file'], e['line']))
    total_uncalled = len(entries)
    if top > 0:
        entries = entries[:top]

    return _disclose_skipped({
        'query': 'uncalled',
        'path': path,
        'total_defined': total_defined,
        'total_uncalled': total_uncalled,
        'test_entrypoints_excluded': sum(
            excluded_by_reason.get(r, 0) for r in _TEST_ENTRYPOINT_REASONS),
        'excluded_by_reason': excluded_by_reason,
        'entries': entries,
    }, query_skipped, traversal_failures=getattr(structures, 'traversal_failures', ()))


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
        top: Maximum number of entries to return (default 10; 0 or less means all).
        include_builtins: If False (default), skip Python-file callers of
            Python builtins from the ranking; callers of same-named methods
            in other languages (e.g. Scala/Ruby ``.map``) are unaffected.
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

    entries = []
    for callee_name, caller_records in index.items():
        bare_callee = callee_name.split('.')[-1]
        if not include_builtins and is_builtin_anywhere(bare_callee):
            # Builtin names collide with real methods in other languages
            # (Scala/Ruby `.map`, `.filter`, ...) — only drop the callers whose
            # own language treats the name as a builtin, keep the rest (BACK-748).
            caller_records = [
                r for r in caller_records
                if bare_callee not in conventions_for(_lang_family(r['file'])).builtins
            ]
            if not caller_records:
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

    # Honor an explicit top; the reported 'top' is the number actually shown.
    shown = min(top, len(entries)) if top > 0 else len(entries)

    return _disclose_skipped({
        'query': 'rank_callers',
        'path': path,
        'top': shown,
        'total_unique_callees': len(entries),
        'entries': entries[:shown],
    }, index.skipped, traversal_failures=getattr(index, 'traversal_failures', ()))


def _unattributed_sources(file_struct: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One synthetic module-level source per deferred body whose JSX uses have no tracked owner.

    The module graph is file-to-file: a dependency exists whichever scope renders the
    component, so these uses are kept as edges instead of dropped (BACK-1831)."""
    groups: Dict[Tuple[str, int], List[str]] = {}
    for ref in unattributed_references(file_struct):
        groups.setdefault((ref['owner'], ref['owner_line']), []).append(ref['callee'])
    return [{'category': 'modules', 'name': owner, 'line': line, 'calls': list(dict.fromkeys(callees))}
            for (owner, line), callees in groups.items()]


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

        for elem in [*call_sources(file_struct), *_unattributed_sources(file_struct)]:
            # 'tests' included so a Zig test file's calls into other modules
            # register as real module-dependency edges (BACK-663).
            if elem.get('category') not in ('functions', 'methods', 'tests', 'modules'):
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

    return _disclose_skipped({
        'query': 'module_graph',
        'path': dir_str,
        'nodes': nodes,
        'edges': edges,
        'total_nodes': len(nodes),
        'total_edges': len(edges),
    }, structures.skipped, traversal_failures=getattr(structures, 'traversal_failures', ()))
