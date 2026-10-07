"""I002: Circular dependency detector.

Detects circular import dependencies between modules.
Supports Python, JavaScript, Go, and Rust.
"""

import hashlib
import logging
import os
import stat as stat_module
from pathlib import Path
from typing import List, Dict, Any, Iterator, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports import ImportGraph
from ...analyzers.imports import service as import_analysis
from ...analyzers.imports.base import get_extractor, get_all_extensions
from ...analyzers.imports.file_index import basename_index
from ...analyzers.imports.types import ImportAnalysis
from ...core import disk_cache
from ...utils.parallel import pool_worker_count, submit_each
from ...utils.path_utils import (
    EVIDENCE, _walk_code_files, cross_file_scan_root,
)

logger = logging.getLogger(__name__)

# Disk-cache namespace for the resolved import graph. Value keyed on a
# fingerprint of the whole source-file set (path + mtime_ns + size), so any
# edit/add/delete/rename under the root produces a different key and misses.
# Bumped to v2 (BACK-982): ImportGraph gained a failed_files field, so an
# old-shape cached object (pickled before this field existed) must never be
# unpickled and returned as-is. v3 (BACK-1579): the file set is now the evidence walk's
# (noise dirs, gitignored and REVEAL_IGNORE'd files left out), not every file under the root.
_IMPORT_GRAPH_NAMESPACE = "import_graph_v3"

# Module-level cache: project_root → ImportGraph.
# _build_import_graph scans every source file under the project root via
# tree-sitter; caching by project root makes the scan happen once per project
# per process (was once per subdirectory, defeating the cache on deep trees).
_graph_cache: Dict[Path, 'ImportGraph'] = {}

# Safety ceiling on the import-graph scan. A correctly-detected project root
# almost never exceeds this; blowing past it means root detection went wrong
# (BACK-338). When tripped we log and return an empty graph — a logged skip, not
# a silent multi-minute hang. Override with REVEAL_I002_MAX_FILES for monorepos.
_DEFAULT_MAX_GRAPH_FILES = 20000

# BACK-615 (BACK-536 opt 3): a *legitimate*, correctly-detected root can still
# be big enough that whole-project cycle detection dominates `check`'s wall
# time with zero progress feedback — measured 2m30s on a real 3,661-file repo
# and 4m55s on 7,755 files (this machine, 12-way parallel Pass-B, i.e. the
# already-optimized BACK-536 opt-1 path). That's well under the 20,000-file
# mis-detection ceiling above, so nothing warns the user before they sit
# through it. This is a separate, lower threshold with separate semantics:
# _DEFAULT_MAX_GRAPH_FILES means "this root is probably wrong, abort";
# this one means "this root is right but big, skip by default and say so"
# (the same honest-decline convention used elsewhere in reveal rather than a
# flag nobody would find in time — see BACK-547/capabilities.py precedent).
# Override with REVEAL_I002_CYCLE_LIMIT to force the scan on a big tree.
_DEFAULT_CYCLE_DETECTION_MAX_FILES = 2000

# BACK-536: the Pass-B parse loop in _collect_raw_imports is the dominant cost of
# `check` on large trees (measured ~97% of `check samples/go` — one tree-sitter
# parse per source file under the project root). Per-file extraction is
# independent, so fan it out across processes, reusing BACK-489 P1's pattern and
# its REVEAL_MAX_WORKERS override. The graph is built in the main process (see
# rules/scan_caches._i002_preload) before the check worker pool spawns, so this pool
# never nests inside another; results are read in submission order
# (utils.parallel.submit_each), so the assembled graph is identical to the serial path.
_GRAPH_PARALLEL_MIN_FILES = 200   # below this, pool startup/IPC outweighs the win
_GRAPH_PARALLEL_MAX_WORKERS = 16  # cap so huge core counts don't oversubscribe


def _graph_worker_count(n_files: int) -> int:
    """Workers for the Pass-B parse; 1 means run serially (no pool).

    REVEAL_MAX_WORKERS overrides everything (set to 1 to force the serial path —
    used by tests and for byte-identical verification); otherwise parallelize
    only above _GRAPH_PARALLEL_MIN_FILES, capped at _GRAPH_PARALLEL_MAX_WORKERS
    and the CPU count.
    """
    if n_files < _GRAPH_PARALLEL_MIN_FILES:
        return pool_worker_count(1)
    return pool_worker_count(min(os.cpu_count() or 1, _GRAPH_PARALLEL_MAX_WORKERS))


def _extract_imports_for_file(fp_str: str) -> tuple:
    """Extract imports for one file. Module-level and picklable so it runs
    unchanged under a ProcessPoolExecutor (fork or spawn).

    Returns ``(imports, failed)``. Swallows per-file extraction errors and
    returns ``([], False)`` for files with no extractor — mirroring
    _collect_raw_imports's serial per-file try/except so the parallel and
    serial paths produce identical results. ``failed`` is True when the
    extractor's language IS supported but tree-sitter could not parse the
    file (``extractor.parse_failed``, BACK-982). Recovered imports remain in the
    graph, but missing edges can hide a cycle. Consumers disclose incomplete
    coverage rather than treating an empty cycle list as confirmed clean.
    """
    fp = Path(fp_str)
    extractor = get_extractor(fp)
    if not extractor:
        return [], False
    try:
        imports = list(extractor.extract_imports(fp))
        return imports, extractor.parse_failed
    except Exception:
        # Intentional silence here: the `True` failed-flag IS the visible
        # signal, surfaced as a logger.warning by the caller once per graph
        # build (_build_import_graph) rather than once per file here.
        return [], True


def _extract_in_pool(file_strs: List[str], workers: int, results: Dict[str, tuple]) -> None:
    """``_extract_imports_for_file`` over *file_strs* in a process pool, one future
    per file, into ``results[fp_str] = (imports, failed)`` in submission order.

    A dead worker breaks the pool and fails every pending future, so the culprit
    cannot be told from the files lost with it; each of them is a failed file
    (``([], True)``), the channel a file tree-sitter could not parse already uses,
    which ``get_scan_disclosures`` reports. None is re-run in this process, where
    the culprit could take the whole run down (BACK-1726).
    """
    from concurrent.futures import ProcessPoolExecutor
    from ...logging_setup import worker_bootstrap
    lost: List[BaseException] = []
    with ProcessPoolExecutor(max_workers=workers, initializer=worker_bootstrap) as executor:
        for fp_str, future in zip(file_strs, submit_each(executor, _extract_imports_for_file, file_strs)):
            try:
                results[fp_str] = future.result()
            except Exception as e:  # recorded as a failed file; disclosed below
                results[fp_str] = ([], True)
                lost.append(e)
    if lost:
        logger.warning("I002: %d file(s) lost to a dead import-extraction worker (%s: %s); "
                       "circular-dependency results may be incomplete",
                       len(lost), type(lost[0]).__name__, lost[0])


def _max_graph_files() -> int:
    """Read the import-graph file ceiling, honoring REVEAL_I002_MAX_FILES."""
    raw = os.environ.get('REVEAL_I002_MAX_FILES')
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            logger.debug("Invalid REVEAL_I002_MAX_FILES=%r, using default", raw)
    return _DEFAULT_MAX_GRAPH_FILES


def _cycle_detection_max_files() -> int:
    """Read the cycle-detection auto-skip threshold (BACK-615), honoring
    REVEAL_I002_CYCLE_LIMIT. Set to 0 (or a value >= REVEAL_I002_MAX_FILES)
    to disable the auto-skip entirely and always run full cycle detection."""
    raw = os.environ.get('REVEAL_I002_CYCLE_LIMIT')
    if raw:
        try:
            value = int(raw)
            if value >= 0:
                return value
        except ValueError:
            logger.debug("Invalid REVEAL_I002_CYCLE_LIMIT=%r, using default", raw)
    return _DEFAULT_CYCLE_DETECTION_MAX_FILES


def _graph_source_files(directory: Path, supported) -> Iterator[Path]:
    """The source files I002's import graph is built from: one selection, shared by the
    disk-cache fingerprint and ``_collect_raw_imports``' Pass A, so the two cannot drift.

    An evidence walk (BACK-1579): noise directories (``.venv``, ``node_modules``, ...), what
    git ignores and REVEAL_IGNORE are left out; ``--exclude`` is not, since narrowing the
    report must not hide a cycle that runs through an excluded file. It used to be a bare
    ``rglob('*')``: an in-tree ``.venv`` pushed a small project over the cycle-detection
    limit and real cycles went unreported.
    """
    for file_path in _walk_code_files(directory, purpose=EVIDENCE):
        if file_path.suffix in supported:
            yield file_path


def _tree_fingerprint(directory: Path) -> Optional[str]:
    """Hash the source-file set under ``directory`` for the disk-cache key.

    Selects files with ``_graph_source_files``, as Pass A does, then digests each file's
    ``(relpath, mtime_ns, size)``.
    A content edit bumps mtime_ns (and usually size); an add/delete/rename
    changes the file set — every realistic change yields a different digest, so
    a stale graph is never served. Stat-only (no parse), so it is cheap relative
    to the ~O(files) tree-sitter build it may let us skip.

    Returns ``None`` (→ caller skips the cache and builds directly) when:
    * the file count exceeds the ceiling — same guard as Pass A; a mis-detected
      giant root should not pay a full stat walk, and its graph is not cached;
    * the file count exceeds the cycle-detection auto-skip threshold (BACK-615)
      — ``_collect_raw_imports`` will short-circuit to an empty graph for the
      same reason, and that skip result must never be cached: caching it would
      make a later ``REVEAL_I002_CYCLE_LIMIT`` override (raised or disabled) on
      an unchanged tree keep silently serving the stale empty graph instead of
      actually running the scan the override asked for;
    * any stat/walk error occurs — fail open to the uncached path.

    The digest deliberately includes ``get_all_extensions()`` and the reveal
    version (via the disk-cache path) so that a change in *which* files are
    considered source, or in extraction logic, cannot reuse an old graph.
    """
    try:
        supported = get_all_extensions()
        max_files = _max_graph_files()
        cycle_limit = _cycle_detection_max_files()
        hasher = hashlib.sha256()
        # Bind the digest to the exact extension set that selected the files —
        # if support changes, the same tree fingerprints differently.
        hasher.update(("\x00".join(sorted(supported))).encode("utf-8", "replace"))
        hasher.update(b"\x01")
        entries = []
        for file_path in _graph_source_files(directory, supported):
            try:
                st = file_path.stat()
            except OSError:
                # Vanished mid-walk / unreadable — abort fingerprinting rather
                # than key on a partial view.
                return None
            if not stat_module.S_ISREG(st.st_mode):
                continue
            entries.append((str(file_path), st.st_mtime_ns, st.st_size))
            if len(entries) > max_files:
                return None
        if cycle_limit and len(entries) > cycle_limit:
            return None
        entries.sort()
        for path_str, mtime_ns, size in entries:
            hasher.update(path_str.encode("utf-8", "replace"))
            hasher.update(f"\x02{mtime_ns}\x03{size}\x04".encode("ascii"))
        return hasher.hexdigest()
    except Exception:  # boundary-ok: silent-except -- None means "skip the cache, build directly", not a lost result
        # Intentional silence: None means "skip the cache, build directly" --
        # not a lost result. See the docstring above.
        return None


def _find_project_root(path: Path) -> Optional[Path]:
    """Nearest project root above *path*, via the shared ceiling-bounded
    resolver (BACK-612). Resolution order, first that applies:
      0. ``.reveal.yaml root:true`` — an explicit pin (newly honored here).
      1. Nearest package/build marker (the widened, ``__init__``-guarded set —
         a marker-bearing dir that is itself a Python package is skipped so the
         real root above it is found, not the package dir).
      2. Nearest ``.git`` root.
      3. Top of the *contiguous* ``__init__.py`` chain rooted at the target's
         own directory (Python packages only) — the BACK-338 guard: a stray
         far-ancestor ``__init__.py`` can never hijack a non-package tree.
      4. ``path.parent`` when nothing matches before the hard ceiling --
         ``None`` when that is the OS temp dir, $HOME or a filesystem root
         (:func:`cross_file_scan_root`); ``check`` then skips the scan.

    Adopting the shared resolver closes the scan-root over-climb bug for I002
    the way BACK-609/610 closed it for ``depends://``: a marker-less C/C++ tree
    nested under an ancestor ``.git`` now scopes correctly given a
    ``.reveal.yaml root:true`` in the component. Tiers 1 and 3 compose — when
    the guard skips a marker-bearing package dir and there is no real higher
    root, the contiguous-``__init__`` tier recovers the same dir.
    """
    return cross_file_scan_root(path, python_init_chain=True)


def get_scan_disclosures() -> List[str]:
    """BACK-1051: one-line skip reasons for every capped/truncated graph
    currently in ``_graph_cache`` (the same process-local cache
    ``_build_import_graph`` populates and ``scan_caches._i002_preload``
    fills in the main process before workers spawn). A directory-level
    ``check``/``review`` run must surface these instead of letting a capped
    scan present its empty cycle list as a clean "no circular dependencies
    found" -- the exact silent-skip symptom that motivated this ticket.
    """
    disclosures = []
    for directory, graph in _graph_cache.items():
        if graph.scan_skipped_reason:
            disclosures.append(graph.scan_skipped_reason)
        if graph.failed_files:
            disclosures.append(
                f"I002: {len(graph.failed_files)} file(s) under {directory} parsed with errors; "
                "circular-dependency results may be incomplete"
            )
    return disclosures


# Initialize file patterns from all registered extractors at module load time
def _initialize_file_patterns():
    """Get all supported file extensions from registered extractors."""
    try:
        return list(get_all_extensions())
    except Exception:
        # Fallback to common extensions if registry not yet initialized
        return ['.py', '.js', '.go', '.rs']


class I002(BaseRule):
    """Detect circular dependencies in imports.

    Supports multiple languages through dynamic extractor selection.
    Works with Python, JavaScript, Go, and Rust.
    """

    code = "I002"
    message = "Circular dependency detected"
    category = RulePrefix.I
    severity = Severity.HIGH
    file_patterns = _initialize_file_patterns()  # Populated at module load time
    version = "2.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for circular dependencies involving this file.

        Args:
            file_path: Path to source file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections for circular dependencies
        """
        detections: List[Detection] = []
        target_path = Path(file_path).resolve()

        try:
            # Build import graph rooted at the project root so that:
            # 1. The cache hits for every file in the same project (not per-subdir)
            # 2. Cross-package cycles are detected (subdir scan misses them)
            scan_root = _find_project_root(target_path)
            if scan_root is None:
                logger.debug(
                    "I002: skipping circular-dependency scan for standalone file under %s",
                    target_path.parent,
                )
                return detections
            graph = self._build_import_graph(scan_root)

            # Find all cycles in the graph
            cycles = graph.find_cycles()

            # Filter to cycles involving this specific file
            relevant_cycles = [
                cycle for cycle in cycles
                if target_path in cycle
            ]

            # Create detection for each relevant cycle
            for cycle in relevant_cycles:
                # Format the cycle for display
                cycle_str = self._format_cycle(cycle)

                # Determine where to suggest breaking the cycle
                suggestion = self._suggest_break_point(cycle, target_path)

                detections.append(self.create_detection(
                    file_path=file_path,
                    line=1,  # Circular deps are file-level, not line-specific
                    column=1,
                    suggestion=suggestion,
                    context=f"Import cycle: {cycle_str}"
                ))

        except Exception as e:
            logger.warning(f"I002: failed to analyze {file_path}: {e}")
            return detections

        return detections

    def _build_import_graph(self, directory: Path) -> ImportGraph:
        """Build import graph for all source files in directory and subdirs.

        Analyzes files in all supported languages (Python, JavaScript, Go, Rust).
        Results are cached by directory so the tree-sitter scan runs once per
        directory per process instead of once per file (was O(n²)).

        Args:
            directory: Directory to analyze

        Returns:
            ImportGraph with all imports and resolved dependencies
        """
        if directory in _graph_cache:
            return _graph_cache[directory]

        # Cross-invocation disk cache (BACK-536 opt 2 / BACK-535). The resolved
        # graph is deterministic for an unchanged tree, so a 2nd+ reveal command
        # on the same checkout skips the ~O(files) tree-sitter parse. The
        # fingerprint walk is cheap (stat only, no parse); on a miss we fall
        # through to the full build below.
        fingerprint = _tree_fingerprint(directory)
        if fingerprint is not None:
            cached = disk_cache.get(_IMPORT_GRAPH_NAMESPACE, fingerprint)
            if cached is not None:
                _graph_cache[directory] = cached
                return cached

        all_imports, failed_files, skipped_reason = self._collect_raw_imports(directory)
        graph = ImportGraph.from_imports(all_imports)
        graph.failed_files = failed_files
        graph.scan_skipped_reason = skipped_reason
        self._resolve_graph_dependencies(graph, directory)

        _graph_cache[directory] = graph
        if fingerprint is not None:
            disk_cache.put(_IMPORT_GRAPH_NAMESPACE, fingerprint, graph)
        return graph

    def _collect_raw_imports(self, directory: Path) -> tuple:
        """Phase 1: Walk directory and extract raw import statements from all files.

        Returns ``(all_imports, failed_files, skipped_reason)`` -- ``failed_files``
        (BACK-982) are source files whose language IS supported but that
        tree-sitter parsed with errors. Recovered edges are retained; missing
        edges can still hide a cycle. Empty in the two early-abort paths below (the scan never
        reached Pass B, so failure status is simply unknown, not "none failed").
        ``skipped_reason`` (BACK-1051) is None when the scan ran to completion,
        or a one-line human-readable string naming which ceiling tripped --
        callers must disclose this rather than presenting the resulting empty
        graph as a clean "no circular dependencies found".

        Two passes on purpose. Pass A only *counts* supported source files (a
        cheap directory walk, no parsing); if the count exceeds the configured
        ceiling (REVEAL_I002_MAX_FILES) we bail before parsing a single file.
        That ceiling only trips when project-root detection has gone wrong and
        pointed the scan at a tree far larger than any single project (BACK-338).
        Counting *before* parsing is the point: parsing is the expensive step
        (tree-sitter per file), so counting-as-we-parse — the old behavior —
        still parsed ~ceiling large real-world files before aborting, a
        multi-minute hang on big non-Python trees where the tell (BACK-418) was a
        5-file subdir under a marker root taking >100s to check. Pass B does the
        actual parsing only once the tree is known to be a sane size.

        A second, lower threshold (BACK-615) auto-skips cycle detection on a
        *correctly*-detected but merely large root, honest-decline style,
        rather than silently parsing for minutes with zero progress feedback
        (measured: 2m30s/3,661 files, 4m55s/7,755 files on 12-way parallel
        hardware). This check runs after Pass A's full stat-only walk (cheap
        — no parsing) so it never falsely trips on the mis-detection ceiling's
        early-abort path.
        """
        supported_extensions = get_all_extensions()
        max_files = _max_graph_files()

        # Pass A: cheap count-only walk — abort before any parsing if over ceiling.
        source_files = []
        for file_path in _graph_source_files(directory, supported_extensions):
            if not file_path.is_file():
                continue
            source_files.append(file_path)
            if len(source_files) > max_files:
                reason = (
                    f"I002: import-graph scan of {directory} exceeded {max_files} "
                    "source files; skipping circular-dependency analysis (likely a "
                    "project-root mis-detection — set REVEAL_I002_MAX_FILES to "
                    "raise the limit)"
                )
                logger.warning(reason)
                return [], [], reason

        cycle_limit = _cycle_detection_max_files()
        if cycle_limit and len(source_files) > cycle_limit:
            reason = (
                f"I002: import-graph scan of {directory} found {len(source_files)} "
                f"source files (over the {cycle_limit}-file cycle-detection "
                "threshold); skipping circular-dependency analysis to avoid a "
                "multi-minute whole-project parse — set REVEAL_I002_CYCLE_LIMIT to "
                "raise the limit or 0 to disable it"
            )
            logger.warning(reason)
            return [], [], reason

        # Pass B: parse the (now bounded) set of files. Independent per file, so
        # fan out across processes on large trees (BACK-536). Results are read in
        # submission order, so the assembled graph is identical to the serial path.
        file_strs = [str(f) for f in source_files]
        workers = _graph_worker_count(len(file_strs))
        results: Dict[str, tuple] = {}
        if workers > 1:
            try:
                _extract_in_pool(file_strs, workers, results)
            except Exception as e:
                # The pool itself could not run (restricted/forbidden-fork
                # environments); a worker that dies inside a running pool is
                # handled per file in _extract_in_pool and never lands here.
                # Only the files the pool did not deliver run serially.
                logger.warning("I002: parallel import extraction failed (%s: %s); "
                               "extracting the rest serially", type(e).__name__, e)
        all_imports: list = []
        failed_files: list = []
        for fp_str in file_strs:
            imports, failed = results[fp_str] if fp_str in results else _extract_imports_for_file(fp_str)
            all_imports.extend(imports)
            if failed:
                failed_files.append(Path(fp_str))
        return all_imports, failed_files, None

    def _resolve_graph_dependencies(self, graph: ImportGraph, directory: Path) -> None:
        """Phase 2: resolve import statements to files through the shared
        import-analysis service, the same resolution imports:// uses (BACK-1723).

        The project root is a search path, so an absolute intra-project import
        (`import pkg.b`, `from pkg import b`) resolves, and every target of a
        statement becomes an edge (`from pkg import b` loads pkg/b.py). The
        service skips TYPE_CHECKING and function-body imports, which cannot
        cause a circular ImportError at startup.
        """
        import_analysis.resolve_graph(
            import_analysis.ScanScope(directory, frozenset(get_all_extensions())),
            import_analysis.ImportFileSet(tuple(graph.files), basename_index([directory])),
            ImportAnalysis(graph=graph, scanned_files=set(graph.files)))

    def _format_cycle(self, cycle: List[Path]) -> str:
        """Format a cycle for human-readable display.

        Args:
            cycle: List of file paths forming a cycle

        Returns:
            Formatted string like "A.py -> B.py -> C.py -> A.py"
        """
        # Use file names for brevity (full paths are too long)
        names = [p.name for p in cycle]
        return " -> ".join(names)

    def _suggest_break_point(self, cycle: List[Path], current_file: Path) -> str:
        """Suggest where to break the circular dependency.

        Args:
            cycle: The circular dependency cycle
            current_file: The file being checked

        Returns:
            Suggestion text
        """
        # Find current file's position in cycle
        try:
            idx = cycle.index(current_file)
        except ValueError:
            return "Refactor to remove circular import"

        # The cycle is [A, B, C, A] - so the import we control is from
        # current_file to the next file in the cycle
        if idx < len(cycle) - 1:
            next_file = cycle[idx + 1]
            return f"Consider removing import from {current_file.name} to {next_file.name}, or refactor shared code into a separate module"
        else:
            return "Refactor to remove circular import (move shared code to a separate module)"
