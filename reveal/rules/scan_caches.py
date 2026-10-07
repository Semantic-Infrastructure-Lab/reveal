"""Project-wide indexes some rules build once per process, shared with pool workers.

I002 (import graph), D005 (literal index), T006 (TypedDict index) and M102 (who
imports what, BACK-1437) each scan the whole project on first use and cache the result in a module-level dict. A
ProcessPoolExecutor worker starts with those dicts empty, so without help every worker
rebuilds every index -- and a scan-ceiling disclosure recorded in a worker never reaches
the parent that renders the summary (BACK-1051). Every pool that runs rules -- `reveal
check` on a directory (cli/file_checker.py) and stats:// (overview, hotspots) -- builds
them here, in the parent, with preload_scan_caches(), and seeds each worker with
init_scan_caches() as the pool initializer.

This lives in the rules package, not cli/, because stats:// is an adapter and must not
import the CLI layer (it carried its own I002-only copy until BACK-1437).
"""

import logging
from pathlib import Path
from typing import List, Optional

from . import RuleRegistry


def rule_will_run(code: str, select, ignore) -> bool:
    """Return True if rule *code* is in the effective rule set for the filters.

    Delegates to the same RuleRegistry resolution the per-file check uses, so
    a preload decision can never drift from what actually runs. In particular
    this honors --select: ``check <dir> --select C901`` must not trigger an
    expensive project-wide index build (BACK-338).
    """
    rules = RuleRegistry.get_rules(select=select, ignore=ignore)
    return any(r.code == code for r in rules)


def _i002_preload(directory: Path, select, ignore, files: Optional[List[Path]] = None) -> dict:
    """Build the I002 import graph in the main process before spawning workers.

    Returns a plain dict (project_root -> ImportGraph) ready to pickle into
    each worker via the ProcessPoolExecutor initializer.  Workers that receive
    a non-empty cache skip the expensive tree-sitter scan entirely.

    Skips the build entirely (returns {}) when I002 is not in the effective rule
    set — e.g. it is ignored, or --select asks for unrelated rules only.

    BACK-1041: root resolution must start from an actual source file, not the
    bare scan directory. ``_find_project_root`` only climbs *upward* looking
    for markers, so a `directory` that sits above a package boundary (e.g. the
    CLI target is a vendored corpus's parent, with the real `package.json`/
    `.git` one level down inside it) never sees that marker and climbs past it
    to whatever VCS root is further up — which can be a much larger, unrelated
    tree. Each file's own `check()` call resolves its root from the file's own
    path and correctly stops at the nearer marker, so preloading from
    `directory` alone can guess a different (and wrong) root than every
    worker actually ends up using — wasting the preload and logging a
    misleading "likely project-root mis-detection" warning even though the
    real per-file analysis goes on to succeed. Preloading from a real file
    under `directory` keeps the guess consistent with what workers resolve.
    """
    try:
        if not rule_will_run("I002", select, ignore):
            return {}
        from .imports.I002 import I002, _find_project_root, _graph_cache
        sample = files[0] if files else directory
        root = _find_project_root(sample.resolve())
        if root is None:  # standalone file in the temp dir/$HOME: nothing to index
            return {}
        I002()._build_import_graph(root)   # populates _graph_cache in main process
        return dict(_graph_cache)          # plain dict is picklable
    except Exception:
        # Documented fallback: workers build the index themselves, as they would
        # with no preload at all.
        logging.warning("shared-index preload failed; workers will build it "
                        "themselves", exc_info=True)
        return {}


def _i002_init_worker(graph_cache: dict) -> None:
    """ProcessPoolExecutor initializer: seed each worker's I002 cache.

    Runs once per worker process, before any files are checked.  Importing
    the module here is safe because each worker is a fresh process.
    """
    if not graph_cache:
        return
    from .imports.I002 import _graph_cache
    _graph_cache.update(graph_cache)


def _d005_preload(directory: Path, select, ignore, files: Optional[List[Path]] = None) -> dict:
    """Build the D005 cross-file literal index in the main process before
    spawning workers. Mirrors _i002_preload:

    1. Without this, each worker builds its own copy of the index
       independently on first use (no cross-worker sharing) instead of once.
    2. BACK-1051: a capped scan records its skip reason on
       ``reveal.rules.duplicates.D005._project_skip_reasons``, a process-local
       dict. A worker-process build is invisible to the main process that
       renders the final summary, so the disclosure would silently vanish
       under the (default, >=4 files) parallel path — the exact case
       BACK-1051 exists to fix. Building here, in the main process, is what
       makes ``D005.get_scan_disclosures()`` reliable regardless of whether
       the run went parallel or serial.

    Returns a plain dict (project_root -> {canonical_key -> occurrences}) —
    D005's index values are plain dicts/lists/tuples/strings, so this is
    picklable without any extra work, same as I002's ImportGraph return.
    """
    try:
        if not rule_will_run("D005", select, ignore):
            return {}
        from .duplicates.D005 import D005, _build_index, _find_project_root, _project_index
        sample = files[0] if files else directory
        root = _find_project_root(sample.resolve())
        if root is None:  # standalone file in the temp dir/$HOME: nothing to index
            return {}
        if root not in _project_index:
            _project_index[root] = _build_index(root, D005())
        return dict(_project_index)
    except Exception:
        # Documented fallback: workers build the index themselves, as they would
        # with no preload at all.
        logging.warning("shared-index preload failed; workers will build it "
                        "themselves", exc_info=True)
        return {}


def _d005_init_worker(project_index: dict) -> None:
    """ProcessPoolExecutor initializer: seed each worker's D005 index cache.
    Mirrors _i002_init_worker."""
    if not project_index:
        return
    from .duplicates.D005 import _project_index
    _project_index.update(project_index)


def _t006_preload(directory: Path, select, ignore, files: Optional[List[Path]] = None) -> dict:
    """Build T006's project-wide TypedDict index in the main process, for the
    same two reasons as _d005_preload: one build instead of one per worker,
    and a capped scan's disclosure stays visible to the main process."""
    try:
        if not rule_will_run("T006", select, ignore):
            return {}
        from .types.T006 import _build_index, _find_project_root, _project_index
        sample = files[0] if files else directory
        root = _find_project_root(sample.resolve())
        if root is None:  # standalone file in the temp dir/$HOME: nothing to index
            return {}
        if root not in _project_index:
            _project_index[root] = _build_index(root)
        return dict(_project_index)
    except Exception:
        # Documented fallback: workers build the index themselves, as they would
        # with no preload at all.
        logging.warning("shared-index preload failed; workers will build it "
                        "themselves", exc_info=True)
        return {}


def _t006_init_worker(project_index: dict) -> None:
    """ProcessPoolExecutor initializer: seed each worker's T006 index cache."""
    if not project_index:
        return
    from .types.T006 import _project_index
    _project_index.update(project_index)


def _m102_preload(directory: Path, select, ignore, files: Optional[List[Path]] = None) -> dict:
    """Build M102's whole-project import scan in the main process (BACK-1437,
    BACK-1429). Without it every worker re-reads every .py file under the
    project root on its first Python file -- ~6.7s per worker process on
    home-assistant's mqtt component. M102 has no scan ceiling (one would mean
    abstaining on large projects, which needs a decision), so there is no
    disclosure to carry; this is the one-build half only.

    The sample is the first file M102 would actually scan from: a .py file
    that is not an entry point or a test (M102 returns before resolving a
    root for those) and has a project root (BACK-1372's resolver), so the
    preload builds the same cache key the workers look up -- and builds
    nothing for, e.g., a tests/ directory where no worker would either.
    """
    try:
        if not rule_will_run("M102", select, ignore):
            return {}
        from .maintainability.M102 import M102, _import_cache, _project_root
        rule = M102()
        for path in files or []:
            if path.suffix != '.py' or rule._is_entry_point(path) or rule._is_test_file(path):
                continue
            root = _project_root(path.resolve())
            if root is not None:
                rule._collect_all_imports(root)   # populates _import_cache
                break
        return dict(_import_cache)
    except Exception:
        # Documented fallback: workers build the index themselves, as they would
        # with no preload at all.
        logging.warning("shared-index preload failed; workers will build it "
                        "themselves", exc_info=True)
        return {}


def _m102_init_worker(import_cache: dict) -> None:
    """ProcessPoolExecutor initializer: seed each worker's M102 import cache."""
    if not import_cache:
        return
    from .maintainability.M102 import _import_cache
    _import_cache.update(import_cache)


def preload_scan_caches(files: List[Path], directory: Path, select, ignore) -> dict:
    """Preload every scan-capped rule's shared index/graph in the main
    process, returning a dict of {rule_code: cache} for the pool initializer.
    Single call site so a future rule with the same shape (BACK-1051's
    "shared result-envelope contract" direction, see BACK-1093/1086) has one
    place to register, not one more copy-pasted preload/init pair wired by
    hand into every parallel entry point.
    """
    return {
        'I002': _i002_preload(directory, select, ignore, files),
        'D005': _d005_preload(directory, select, ignore, files),
        'T006': _t006_preload(directory, select, ignore, files),
        'M102': _m102_preload(directory, select, ignore, files),
    }


def init_scan_caches(caches: dict) -> None:
    """ProcessPoolExecutor initializer counterpart to preload_scan_caches."""
    _i002_init_worker(caches.get('I002', {}))
    _d005_init_worker(caches.get('D005', {}))
    _t006_init_worker(caches.get('T006', {}))
    _m102_init_worker(caches.get('M102', {}))


def get_scan_disclosures() -> List[str]:
    """BACK-1051: collect every capped-scan disclosure recorded in this
    process by rules with a shared-index/graph scan ceiling (I002, D005, T006).
    Call only after the check run has completed (serial or parallel) —
    preload_scan_caches guarantees the main process sees a worker's cap
    hit, not just a serial in-process one. Returns [] when nothing was
    capped, which callers must treat as "confirmed complete", not "unknown".
    """
    # No try/except: [] is read as "confirmed complete", so a failure to collect
    # must not return it (BACK-1614).
    from .imports.I002 import get_scan_disclosures as i002_disclosures
    from .duplicates.D005 import get_scan_disclosures as d005_disclosures
    from .types.T006 import get_scan_disclosures as t006_disclosures
    return [*i002_disclosures(), *d005_disclosures(), *t006_disclosures()]
