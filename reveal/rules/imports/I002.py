"""I002: Circular dependency detector.

Detects load-time import cycles between files, in every language with an import extractor,
from the analysis service's import graph: the graph and default edge rule ``imports://?circular``
uses (TYPE_CHECKING imports never an edge, function-level imports left out, module and
convention edges never close a cycle; BACK-2077, BACK-2156). Counting rule: one finding per file
per cycle group (strongly connected component), so a file reports at most one; the message names
the group and its size, the context a shortest cycle through the file.
"""

from dataclasses import asdict, replace
import logging
import os
from ...utils.request_cache import register_request_cache, register_validated_cache
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity, RuleScope
from ...analyzers.imports import ImportGraph
from ...analyzers.imports import service as import_analysis
from ...analyzers.imports.base import get_all_extensions
from ...analyzers.imports.types import LAZY_EXCLUDE
from ...utils.exclusions import suspended_exclusions
from ...utils.query_control import ScanBudget
from ...utils.path_utils import (
    cross_file_scan_root,
    scan_roots,
    traversal_failed_warning,
)

logger = logging.getLogger(__name__)

# Module-level cache: project_root → ImportGraph, the rule's view of the analysis service's
# build of that root (BACK-2156): one build per project per process, shared with the pool
# workers through rules/scan_caches._i002_preload, and the carrier of the scan's disclosures.
_graph_cache: Dict[Path, 'ImportGraph'] = {}

# Safety ceiling on the import-graph scan. A correctly-detected project root
# almost never exceeds this; blowing past it means root detection went wrong
# (BACK-338). When tripped we log and return an empty graph — a logged skip, not
# a silent multi-minute hang. Override with REVEAL_I002_MAX_FILES for monorepos.
# The analysis service's own default cap, so an unchanged default shares imports://'s build.
_DEFAULT_MAX_GRAPH_FILES = import_analysis.DEFAULT_FILE_CAP

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


def get_scan_budgets(files: List[Path]) -> List[Dict[str, Any]]:
    """Source accounting for graphs reached by this report's files."""
    return [{'rule': 'I002', 'root': directory, **graph.scan_budget}
            for directory, graph in _graph_cache.items() if graph.scan_budget
            and any(path.resolve().is_relative_to(directory) for path in files)]


def get_scan_disclosures(files: Optional[List[Path]] = None) -> List[str]:
    """BACK-1051: one-line skip reasons for every capped/truncated graph
    currently in ``_graph_cache`` (the same process-local cache
    ``_build_import_graph`` populates and ``scan_caches._i002_preload``
    fills in the main process before workers spawn). A directory-level
    ``check``/``review`` run must surface these instead of letting a capped
    scan present its empty cycle list as a clean "no circular dependencies
    found" -- the exact silent-skip symptom that motivated this ticket.
    """
    roots = scan_roots(files, _find_project_root) if files is not None else None
    disclosures = []
    for directory, graph in _graph_cache.items():
        if roots is not None and directory not in roots:
            continue
        traversal = traversal_failed_warning(graph.traversal_failures, directory)
        if traversal:
            disclosures.append(f"I002: {traversal['message']}; circular-dependency results may be incomplete")
        if graph.scan_skipped_reason:
            disclosures.append(graph.scan_skipped_reason)
        lost = set(graph.lost_files)
        unreadable = graph.unreadable_files
        parse_failed = [fp for fp in graph.failed_files if fp not in lost and fp not in unreadable]
        if unreadable:
            errors = ', '.join(sorted(set(unreadable.values())))
            disclosures.append(
                f"I002: {len(unreadable)} file(s) under {directory} could not be read ({errors}); "
                "circular-dependency results may be incomplete"
            )
        if parse_failed:
            disclosures.append(
                f"I002: {len(parse_failed)} file(s) under {directory} parsed with errors; "
                "circular-dependency results may be incomplete"
            )
        if lost:
            disclosures.append(
                f"I002: {len(lost)} file(s) under {directory} not analyzed, a pool worker died; "
                "circular-dependency results may be incomplete"
            )
    return disclosures


def _cycle_view(graph: ImportGraph, root: Path) -> ImportGraph:
    """The edges a cycle is made of: the default view ``imports://?circular`` counts
    (``ImportView._edges(LAZY_EXCLUDE)`` with tests included): load-time edges to files under the
    scan root."""
    return graph.edge_view(LAZY_EXCLUDE).within_root(root)


def _groups_by_file(view: ImportGraph) -> Dict[Path, Tuple[List[Path], int, int]]:
    """Each file in a cycle group of *view* -> ``(group, group number, group count)``: the
    groups ``find_cycle_groups`` returns (``imports://?circular``'s groups), numbered in its
    order, computed once per view (BACK-1873; not a dataclass field, so never pickled stale:
    the views are rebuilt from the graph's fields)."""
    index = view.__dict__.get('_groups_by_file')
    if index is None:
        groups = view.find_cycle_groups()
        index = {member: (group, number, len(groups))
                 for number, group in enumerate(groups, 1) for member in group}
        view.__dict__['_groups_by_file'] = index
    return index


def _rule_graph(built: 'import_analysis.ImportBuild', scan_budget: Dict[str, Any]) -> ImportGraph:
    """The service's graph with the scan's disclosures on it, for the per-root memo and the pool
    workers. A copy: the service's build may be shared through its own caches."""
    analysis = built.analysis
    assert analysis.graph is not None
    lost = set(analysis.files_lost)
    traversal = list(dict.fromkeys([*built.files.traversal_failures,
                                    *getattr(analysis.resolution, 'traversal_failures', ())]))
    budget = dict(scan_budget)
    if traversal:
        budget['exact'] = False
    return replace(
        analysis.graph,
        failed_files=list(analysis.files_failed),
        lost_files=list(analysis.files_lost),
        unreadable_files={fp: e.read_error for fp, e in analysis.extractions.items()
                          if e.read_error and fp not in lost},
        transient_files={fp: e.transient_error for fp, e in analysis.extractions.items()
                         if e.transient_error and fp not in lost},
        traversal_failures=traversal,
        scan_skipped_reason=None,
        scan_budget=budget,
    )


# Initialize file patterns from all registered extractors at module load time
def _initialize_file_patterns():
    """Extensions with an import extractor in languages where a load-time import cycle can
    break the program; other languages' cycles are legal and are an `imports ?circular`
    fact, disclosed as W-CAP-3 by `check` (BACK-2156)."""
    from ...capabilities import load_order_cycle_extension
    return sorted(ext for ext in get_all_extensions() if load_order_cycle_extension(ext))


class I002(BaseRule):
    """Detect load-time import cycles through each checked file (see the module docstring)."""

    code = "I002"
    scope = RuleScope.PROJECT_INDEX
    message = "Circular dependency detected"
    category = RulePrefix.I
    severity = Severity.HIGH
    file_patterns = _initialize_file_patterns()  # Populated at module load time
    version = "2.0.0"
    # The last build's source accounting (``_record_scan_budget``), copied onto its graph.
    _scan_budget_metadata: Dict[str, Any]

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

            # One finding per file per cycle group (strongly connected component), the groups
            # ``imports://?circular`` counts, with a shortest witness cycle through this file; the
            # group search runs once per graph (BACK-1873, BACK-2156). Load-time edges to files
            # under the scan root only, ?circular's default view (BACK-445, BACK-2077, BACK-2251).
            view = _cycle_view(graph, scan_root)
            located = _groups_by_file(view).get(target_path)
            if located is None:
                return detections
            group, number, total = located
            witness = view.find_cycle_path([target_path, *(m for m in group if m != target_path)])
            detections.append(self.create_detection(
                file_path=file_path,
                line=1,  # Circular deps are file-level, not line-specific
                column=1,
                message=(f"Circular dependency detected: in import cycle group {number} of {total} "
                         f"({len(group)} files; one finding per file per group, "
                         "the groups imports://?circular counts)"),
                suggestion=self._suggest_break_point(witness, target_path),
                context=f"Import cycle: {self._format_cycle(witness)}",
            ))

        except Exception as e:  # boundary-ok: broad-except -- graph building runs the extractors over arbitrary user source (native tree-sitter, no enumerable error set); one file must not end the run, and it is recorded as this rule's unavailable outcome with the file as subject
            logger.warning(f"I002: failed to analyze {file_path}: {e}")
            return self.unavailable(
                f"circular-dependency analysis failed: {type(e).__name__}: {e}", file_path)

        return detections

    def _build_import_graph(self, directory: Path) -> ImportGraph:
        """The import graph of the project rooted at *directory*: the analysis service's build
        (``service.analyze``), the one ``imports://?circular`` reads, so the two answer from the
        same files and the same edges, cascade stages included (BACK-2156). Memoized per root for
        this process; the service owns extraction, resolution and the graph caches.

        Two policies stay the rule's own. The scan ignores ``--exclude`` (narrowing the report must
        not hide a cycle that runs through an excluded file, BACK-1579). And it declines, with a
        disclosure instead of an empty clean answer, over REVEAL_I002_MAX_FILES source files (a
        mis-detected root, BACK-338) or over REVEAL_I002_CYCLE_LIMIT (a right but big root,
        BACK-615); both are counted on the service's discovery before anything is parsed.

        The returned graph is a copy of the service's (``dataclasses.replace``, the service's own
        build is shared and never mutated) carrying the scan's disclosures: failed, lost,
        unreadable and transient files and traversal failures (BACK-982/1753/2099/2136).
        """
        if directory in _graph_cache:
            return _graph_cache[directory]

        budget = ScanBudget(_max_graph_files())
        scope = import_analysis.path_scope(directory, cap=budget.limit)
        built = None
        with suspended_exclusions():
            files = import_analysis.discover(scope)
            sources = sum(1 for path in files.candidates if path.suffix in scope.extensions)
            skipped_reason = self._scan_limit_reason(directory, budget, files.capped, sources)
            if skipped_reason is None:
                try:
                    built = import_analysis.analyze(scope)
                except Exception as e:  # boundary-ok: broad-except -- the service runs every extractor over arbitrary user source in this process and lets an extractor's error propagate (native tree-sitter, no enumerable error set); the graph is recorded as skipped with the error, a scan disclosure that makes the run incomplete (exit 3), once per root rather than once per checked file
                    skipped_reason = (f"I002: import-graph build of {directory} failed ({type(e).__name__}: {e}); "
                                      "skipping circular-dependency analysis")
                    logger.warning(skipped_reason)
                    self._scan_budget_metadata = {**self._scan_budget_metadata, 'analyzed_files': 0,
                                                  'skipped': True, 'exact': False}
        if built is None:
            graph = ImportGraph(scan_skipped_reason=skipped_reason, scan_budget=self._scan_budget_metadata,
                                traversal_failures=list(files.traversal_failures))
        else:
            graph = _rule_graph(built, self._scan_budget_metadata)
        # An invocation-local memo, so preload and per-file disclosures share evidence.
        _graph_cache[directory] = graph
        return graph

    def _scan_limit_reason(self, directory: Path, budget: ScanBudget, capped: bool,
                           sources: int) -> Optional[str]:
        """The one-line reason the scan declines (BACK-1051), or None when it runs; records the
        scan budget either way. The disclosure must be shown, never read as "no cycles"."""
        max_files = budget.limit
        if capped:
            self._record_scan_budget(budget, max_files or sources, capped=True, analyzed=0)
            reason = (
                f"I002: import-graph scan of {directory} exceeded {max_files} "
                "source files; skipping circular-dependency analysis (likely a "
                "project-root mis-detection — set REVEAL_I002_MAX_FILES to "
                "raise the limit)"
            )
            logger.warning(reason)
            return reason
        cycle_limit = ScanBudget(_cycle_detection_max_files() or None).limit
        if cycle_limit and sources > cycle_limit:
            self._record_scan_budget(budget, sources, analyzed=0, skipped=True)
            reason = (
                f"I002: import-graph scan of {directory} found {sources} "
                f"source files (over the {cycle_limit}-file cycle-detection "
                "threshold); skipping circular-dependency analysis to avoid a "
                "multi-minute whole-project parse — set REVEAL_I002_CYCLE_LIMIT to "
                "raise the limit or 0 to disable it"
            )
            logger.warning(reason)
            return reason
        self._record_scan_budget(budget, sources, analyzed=sources)
        return None

    def _record_scan_budget(self, budget: ScanBudget, count: int, *,
                            capped: bool = False, analyzed: int, skipped: bool = False) -> None:
        """Source accounting for ``get_scan_budgets``; a build that lost a directory is marked
        inexact where it is assembled (``_rule_graph``)."""
        self._scan_budget_metadata = {
            **asdict(budget.accounting(count, capped)),
            'limit': budget.limit,
            'cycle_limit': _cycle_detection_max_files(),
            'analyzed_files': analyzed,
            'skipped': capped or skipped,
        }
        if skipped:
            self._scan_budget_metadata['exact'] = False

    def _format_cycle(self, cycle: List[Path]) -> str:
        """Format a cycle for human-readable display.

        Args:
            cycle: List of file paths forming a cycle

        Returns:
            Formatted string like "A.py -> B.py -> C.py -> A.py"
        """
        # File names for brevity, widened to the shortest trailing path that tells the cycle's
        # files apart: two `mod.rs` in different directories are two nodes, and "mod.rs ->
        # mod.rs" reads as one file repeated (BACK-2129).
        members = list(dict.fromkeys(cycle))
        depth = 1
        while depth < max(len(p.parts) for p in members):
            if len({p.parts[-depth:] for p in members}) == len(members):
                break
            depth += 1
        return " -> ".join("/".join(p.parts[-depth:]) for p in cycle)

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


def _evict_root(root: Path) -> None:
    _graph_cache.pop(root, None)


def _evict_incomplete_graphs() -> None:
    """Retain partial graphs within an invocation, never across host requests.

    A recovered sealing walk can stamp a graph built from incomplete input, and a file
    that was unreadable, lost to a dead worker or failed in reveal's machinery leaves the tree
    stamp unchanged when it recovers (BACK-2084, BACK-2136). Drop that memo before validation; the existing owner then
    removes its orphan stamp. A genuine parse failure of unchanged content is kept.
    Private direct builders without host resets retain their invocation memo lifetime.
    """
    for root, graph in tuple(_graph_cache.items()):
        if not graph.cacheable:
            _evict_root(root)


register_request_cache(__name__ + '.traversal', _evict_incomplete_graphs)
register_validated_cache(__name__, _graph_cache, _evict_root)
