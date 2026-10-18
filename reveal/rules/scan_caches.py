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
from typing import Dict, List, Optional

from . import RuleRegistry
from ..utils.path_utils import scan_roots
from ..utils.request_cache import register_request_cache

# Rule code -> why its shared-index preload failed in this process. A failed preload falls
# back to every worker building the index itself, and a scan cap a worker hits never
# reaches the parent that renders the summary (BACK-1051), so the failure is itself a scan
# disclosure (get_scan_disclosures), which makes the run incomplete (exit 3).
_preload_failures: Dict[str, str] = {}


def _clear_preload_failures() -> None:
    _preload_failures.clear()


register_request_cache(__name__, _clear_preload_failures)


def _record_preload_failure(code: str, error: BaseException) -> None:
    """Warn, and remember for get_scan_disclosures, that *code*'s preload failed."""
    _preload_failures[code] = f"{type(error).__name__}: {error}"
    logging.warning("shared-index preload failed; workers will build it "
                    "themselves", exc_info=True)


def rule_will_run(code: str, select, ignore) -> bool:
    """Return True if rule *code* is in the effective rule set for the filters.

    Delegates to the same RuleRegistry resolution the per-file check uses, so
    a preload decision can never drift from what actually runs. In particular
    this honors --select: ``check <dir> --select C901`` must not trigger an
    expensive project-wide index build (BACK-338).
    """
    rules = RuleRegistry.get_rules(select=select, ignore=ignore)
    return any(r.code == code for r in rules)


def _project_roots(directory: Path, files, find_root):
    """Resolve each reached root once, using the rule's own root policy."""
    return scan_roots(files or [directory], find_root)


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
        for root in _project_roots(directory, files, _find_project_root):
            I002()._build_import_graph(root)
        return dict(_graph_cache)          # plain dict is picklable
    except Exception as e:  # boundary-ok: broad-except -- the preload is an optimisation over a rule-owned index builder (tree-sitter extraction, filesystem walks; no enumerable error set); the documented fallback is that workers build the index themselves, and the failure is recorded as a scan disclosure so the run is not reported complete
        _record_preload_failure("I002", e)
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
        for root in _project_roots(directory, files, _find_project_root):
            if root not in _project_index:
                _project_index[root] = _build_index(root, D005())
        return dict(_project_index)
    except Exception as e:  # boundary-ok: broad-except -- the preload is an optimisation over a rule-owned index builder (tree-sitter extraction, filesystem walks; no enumerable error set); the documented fallback is that workers build the index themselves, and the failure is recorded as a scan disclosure so the run is not reported complete
        _record_preload_failure("D005", e)
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
        # Every reached root, not files[0]: a capped second project's skip reason
        # must land in the main process too (BACK-1823). A standalone file in the
        # temp dir/$HOME has no root: nothing to index.
        for root in _project_roots(directory, files, _find_project_root):
            if root not in _project_index:
                _project_index[root] = _build_index(root)
        return dict(_project_index)
    except Exception as e:  # boundary-ok: broad-except -- the preload is an optimisation over a rule-owned index builder (tree-sitter extraction, filesystem walks; no enumerable error set); the documented fallback is that workers build the index themselves, and the failure is recorded as a scan disclosure so the run is not reported complete
        _record_preload_failure("T006", e)
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
        eligible = [path for path in files or []
                    if path.suffix == '.py' and not rule._is_entry_point(path)
                    and not rule._is_test_file(path)]
        # Every reached root (BACK-1823 audit), so a second project is built once here
        # instead of once per worker. No eligible file builds nothing, as no worker would
        # (_project_roots would fall back to the directory).
        for root in _project_roots(directory, eligible, _project_root) if eligible else ():
            rule._collect_all_imports(root)   # populates _import_cache
        return dict(_import_cache)
    except Exception as e:  # boundary-ok: broad-except -- the preload is an optimisation over a rule-owned index builder (tree-sitter extraction, filesystem walks; no enumerable error set); the documented fallback is that workers build the index themselves, and the failure is recorded as a scan disclosure so the run is not reported complete
        _record_preload_failure("M102", e)
        return {}


def _m102_init_worker(import_cache: dict) -> None:
    """ProcessPoolExecutor initializer: seed each worker's M102 import cache."""
    if not import_cache:
        return
    from .maintainability.M102 import _import_cache
    _import_cache.update(import_cache)


def _i007_preload(directory: Path, select, ignore, files: Optional[List[Path]] = None) -> dict:
    """Keep I007's parent disclosure and workers on the same reached import facts."""
    try:
        if not rule_will_run('I007', select, ignore):
            return {}
        from .imports._dep_reconciliation import _preload_project_imports
        return _preload_project_imports(files)
    except Exception as e:  # boundary-ok: broad-except -- the existing shared-index preload boundary records builder failures and falls back to per-worker evaluation
        _record_preload_failure('I007', e)
        return {}


def _i007_init_worker(scans: dict) -> None:
    if not scans:
        return
    from .imports._dep_reconciliation import _scan_cache
    for root, keys in scans.items():
        _scan_cache.setdefault(root, {}).update(keys)


def preload_scan_caches(files: List[Path], directory: Path, select, ignore) -> dict:
    """Preload every scan-capped rule's shared index/graph in the main
    process, returning a dict of {rule_code: cache} for the pool initializer.
    Single call site so a future rule with the same shape (BACK-1051's
    "shared result-envelope contract" direction, see BACK-1093/1086) has one
    place to register, not one more copy-pasted preload/init pair wired by
    hand into every parallel entry point.
    """
    _preload_failures.clear()
    return {
        'I002': _i002_preload(directory, select, ignore, files),
        'I007': _i007_preload(directory, select, ignore, files),
        'D005': _d005_preload(directory, select, ignore, files),
        'T006': _t006_preload(directory, select, ignore, files),
        'M102': _m102_preload(directory, select, ignore, files),
    }


def init_scan_caches(caches: dict) -> None:
    """ProcessPoolExecutor initializer counterpart to preload_scan_caches."""
    _i002_init_worker(caches.get('I002', {}))
    _i007_init_worker(caches.get('I007', {}))
    _d005_init_worker(caches.get('D005', {}))
    _t006_init_worker(caches.get('T006', {}))
    _m102_init_worker(caches.get('M102', {}))


def get_scan_budgets(files: List[Path], select, ignore) -> List[dict]:
    """Numeric source accounting for reached shared indexes, independent of paging."""
    from .imports.I002 import get_scan_budgets as i002_budgets
    from .duplicates.D005 import get_scan_budgets as d005_budgets
    return [row for code, budgets in [('I002', i002_budgets), ('D005', d005_budgets)]
            if rule_will_run(code, select, ignore) for row in budgets(files)]


def get_scan_disclosures(files: Optional[List[Path]] = None, select=None, ignore=None) -> List[str]:
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
    from .imports._dep_reconciliation import get_scan_disclosures as i007_disclosures
    messages = [message for code, collect in [('I002', i002_disclosures),
                                             ('D005', d005_disclosures), ('T006', t006_disclosures),
                                             ('I007', i007_disclosures)]
                if rule_will_run(code, select, ignore) for message in collect(files)]
    for code, reason in sorted(_preload_failures.items()):
        if rule_will_run(code, select, ignore):
            messages.append(
                f"{code}: shared-index preload failed ({reason}); workers built the index "
                "themselves, so a scan cap they hit is not reported and results may be incomplete")
    return messages
