"""Core types for import analysis.

Shared types used by both the import analysis framework and language extractors.
Extracted to a separate module to avoid circular imports.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict, deque

from .unused import unused_entries
from ...core.node_taxonomy import LOCAL_SCOPE

# BACK-2077: which edges a graph view keeps, by the scope of the imports behind each edge.
# 'include' keeps every edge, 'exclude' the load-time ones (an edge with at least one import
# that is not function-level), 'only' the rest; exclude and only partition the edges.
LAZY_INCLUDE, LAZY_EXCLUDE, LAZY_ONLY = 'include', 'exclude', 'only'
LAZY_MODES = (LAZY_INCLUDE, LAZY_EXCLUDE, LAZY_ONLY)


@dataclass
class ImportStatement:
    """Single import statement in source file.

    Represents one import (e.g., 'import os' or 'from sys import path').
    """
    file_path: Path
    line_number: int
    module_name: str  # 'os', 'sys.path', './utils'
    imported_names: List[str]  # ['path', 'environ'] or ['*'] or []
    is_relative: bool  # True for './', '../', etc.
    import_type: str  # 'import', 'from_import', 'star_import'
    alias: Optional[str] = None  # 'np' in 'import numpy as np'
    is_type_checking: bool = False  # True if inside 'if TYPE_CHECKING:' block
    # BACK-2076: where the import sits, from node_taxonomy.edge_scope(): 'module' (file,
    # class or namespace body; runs when the file loads) or 'local' (a function or lambda
    # body). Positional, not a runtime claim. None: the extractor does not record it yet
    # (Python and JavaScript/TypeScript/TSX record it; other languages opt in with BACK-2079).
    scope: Optional[str] = None
    # BACK-2076: True for a loader call (JS/TS `import()` and `require()`), False for a
    # declaration (Python `import`, ES `import`/`export ... from`). None: not recorded.
    dynamic: Optional[bool] = None
    source_line: str = ""  # Full source line (for noqa comment detection)
    level: int = 0  # Relative import level: 0=absolute, 1='.', 2='..', etc.
    skip_unused: bool = False  # True when unused-detection is unreliable for this
                               # import (e.g. C/C++ #include, namespace/require imports)
    alt_names: Tuple[str, ...] = ()  # Other spellings the one bound name may take; a use
                               # of any counts (Go: the name is the target's `package`
                               # clause, which the import path only suggests -- BACK-1397)
    resolved_path: Optional[Path] = None  # Set by ImportsAdapter._resolve_dependencies
                               # once resolve_import() finds a real in-tree file for
                               # this statement. None means "did not resolve" — may
                               # still be a real external/stdlib package, never a
                               # positive local-file claim (BACK-1193).


@dataclass
class ImportExtraction:
    """Complete per-file analysis artifact, persisted without selecting diagnostic fields."""
    imports: List[ImportStatement] = field(default_factory=list)
    parse_failed: bool = False
    # The file was never parsed: its pool worker died (BACK-1753). Also sets parse_failed
    # so every consumer that treats a failed file as incomplete keeps doing so.
    worker_lost: bool = False
    # The failure came from the environment, not the content: the file could not be read (an
    # OSError such as a denied permission). A later run can succeed with the same mtime and
    # size (chmod moves only ctime), so no stat-keyed cache may keep it (BACK-2083).
    environmental: bool = False
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    @property
    def cacheable(self) -> bool:
        """Whether this record is the file's answer for its stat key (BACK-2083)."""
        return not (self.environmental or self.worker_lost)


@dataclass
class ImportAnalysis:
    """Complete graph build artifact, before request-specific presentation."""
    graph: Optional['ImportGraph'] = None
    symbols_by_file: Dict[Path, Set[str]] = field(default_factory=dict)
    scanned_files: Set[Path] = field(default_factory=set)
    unsupported_extensions: Dict[str, int] = field(default_factory=dict)
    files_failed: List[Path] = field(default_factory=list)
    # The subset of files_failed lost to a dead pool worker rather than parsed with errors
    # (BACK-1753); includes code files with no import extractor (BACK-1752).
    files_lost: List[Path] = field(default_factory=list)
    # (file, "ErrorType: message") for files whose structure analysis raised under
    # collect_structures=True: absent from the structures, disclosed (BACK-1856).
    structure_failures: List[Tuple[str, str]] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    extractions: Dict[Path, ImportExtraction] = field(default_factory=dict)

    @property
    def cacheable(self) -> bool:
        """Whether the build is the tree's answer: no file lost to a dead worker and none
        that failed for an environmental reason (BACK-2083)."""
        return not self.files_lost and all(e.cacheable for e in self.extractions.values())


def restamp_file_path(imports: List['ImportStatement'], file_path: Path) -> List['ImportStatement']:
    """Ensure cached ImportStatements carry the caller's requested Path.

    extract_imports() caches are keyed by (absolute path, mtime), so a cache
    hit is valid even when the caller passed a differently-formatted (e.g.
    relative-vs-relative-to-a-different-cwd) Path than whichever call first
    populated the cache. But each ImportStatement.file_path was stamped at
    that first-call's Path — if it doesn't match, callers that key a dict by
    file_path (e.g. ImportGraph.find_unused_imports's symbols_by_file lookup)
    silently miss and treat every import in the file as unused.
    """
    if imports and imports[0].file_path != file_path:
        return [replace(stmt, file_path=file_path) for stmt in imports]
    return imports


@dataclass
class ImportGraph:
    """Complete import graph for a codebase.

    Provides analysis capabilities:
    - Cycle detection (circular dependencies)
    - Unused import detection
    - Layer violation detection
    """
    files: Dict[Path, List[ImportStatement]] = field(default_factory=dict)
    resolved_paths: Dict[str, Optional[Path]] = field(default_factory=dict)
    dependencies: Dict[Path, Set[Path]] = field(default_factory=lambda: defaultdict(set))
    reverse_deps: Dict[Path, Set[Path]] = field(default_factory=lambda: defaultdict(set))
    # Files with incomplete parses (BACK-982): recovered imports are retained,
    # but missing edges can hide cycles. Carried on the graph (not just logged at
    # build time) so it survives the disk/in-process graph cache and callers
    # can tell a clean "no cycles" apart from "couldn't see everything".
    failed_files: List[Path] = field(default_factory=list)
    # The subset of failed_files lost to a dead pool worker, never parsed (BACK-1753).
    lost_files: List[Path] = field(default_factory=list)
    # BACK-1051: set (a one-line human-readable reason) when the scan that
    # produced this graph was skipped/truncated by a safety ceiling — e.g.
    # I002's _DEFAULT_MAX_GRAPH_FILES or _DEFAULT_CYCLE_DETECTION_MAX_FILES.
    # None means "the scan ran to completion", not "no cap exists". Carried
    # on the graph (like failed_files) so it survives the module-level cache
    # and callers can disclose a silent skip instead of presenting an empty
    # cycle list as a clean "no circular dependencies found".
    scan_skipped_reason: Optional[str] = None
    # Source-candidate accounting, distinct from graph membership and output paging.
    scan_budget: Dict[str, Any] = field(default_factory=dict)
    # Directory enumeration loss affects sources and extension-agnostic resolution targets.
    traversal_failures: List[Tuple[Optional[str], str]] = field(default_factory=list)
    # BACK-2077: (from_file, to_file) -> the ImportStatement.scope of every import that
    # produced the edge ('module', 'local', or None where the extractor records no scope).
    # Every edge is stored; views (edge_view) filter at presentation.
    edge_scopes: Dict[Tuple[Path, Path], Set[Optional[str]]] = field(default_factory=dict)
    # The subset of failed_files that could not be read (ImportExtraction.environmental): a
    # later run can read them with mtime and size unchanged (BACK-2084). Last, so positional
    # construction keeps its field order.
    unreadable_files: List[Path] = field(default_factory=list)

    @property
    def cacheable(self) -> bool:
        """Whether the graph is the tree's answer for its stat key: no file lost to a dead
        worker, none unreadable, no directory left unlisted (BACK-2084)."""
        return not (self.lost_files or self.unreadable_files or self.traversal_failures)

    @classmethod
    def from_imports(cls, imports: List[ImportStatement]) -> 'ImportGraph':
        """Build import graph from list of import statements."""
        graph = cls()

        # Group by file
        for stmt in imports:
            if stmt.file_path not in graph.files:
                graph.files[stmt.file_path] = []
            graph.files[stmt.file_path].append(stmt)

        return graph

    def add_dependency(self, from_file: Path, to_file: Path, scope: Optional[str] = None) -> None:
        """Add a dependency edge: from_file imports to_file, from an import at ``scope``
        (``ImportStatement.scope``; None when the extractor does not record it)."""
        self.dependencies[from_file].add(to_file)
        self.reverse_deps[to_file].add(from_file)
        self.edge_scopes.setdefault((from_file, to_file), set()).add(scope)
        self.__dict__.pop('_cycles_by_file', None)
        self.__dict__.pop('_edge_views', None)

    def is_lazy_edge(self, from_file: Path, to_file: Path) -> bool:
        """True when every import behind the edge is function-level (scope 'local')."""
        return self.edge_scopes.get((from_file, to_file)) == {LOCAL_SCOPE}

    def unclassified_edges(self) -> List[Tuple[Path, Path]]:
        """Edges with an import whose scope was not recorded and no load-time import: every
        view counts them as load-time, so &lazy cannot separate them."""
        return [edge for edge, scopes in self.edge_scopes.items()
                if None in scopes and not (scopes - {None, LOCAL_SCOPE})]

    def edge_view(self, lazy: str) -> 'ImportGraph':
        """This graph with only the edges ``lazy`` keeps (LAZY_MODES), computed once per mode.

        The view shares files, resolved paths and diagnostics with this graph; only
        dependencies and reverse_deps are filtered, so every graph method (cycles included)
        answers for the view. LAZY_INCLUDE is the graph itself.
        """
        if lazy not in LAZY_MODES:
            raise ValueError(f'lazy must be one of {LAZY_MODES!r}, got {lazy!r}')
        if lazy == LAZY_INCLUDE:
            return self
        views: Dict[str, 'ImportGraph'] = self.__dict__.setdefault('_edge_views', {})
        view = views.get(lazy)
        if view is None:
            keep_lazy = lazy == LAZY_ONLY
            dependencies: Dict[Path, Set[Path]] = defaultdict(set)
            reverse_deps: Dict[Path, Set[Path]] = defaultdict(set)
            for from_file, to_files in self.dependencies.items():
                for to_file in to_files:
                    if self.is_lazy_edge(from_file, to_file) == keep_lazy:
                        dependencies[from_file].add(to_file)
                        reverse_deps[to_file].add(from_file)
            view = replace(self, dependencies=dependencies, reverse_deps=reverse_deps)
            views[lazy] = view
        return view

    def find_cycles(self) -> List[List[Path]]:
        """Find all circular dependencies using DFS.

        Returns:
            List of cycles, where each cycle is a list of file paths.
        """
        cycles = []
        visited = set()
        rec_stack = set()
        current_path: List[Path] = []

        def dfs(node: Path) -> None:
            """DFS helper to detect cycles."""
            if node in rec_stack:
                # Found a cycle - extract it from current_path
                cycle_start = current_path.index(node)
                cycle = current_path[cycle_start:] + [node]
                cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)
            current_path.append(node)

            # Sorted, not raw set iteration: neighbor order otherwise depends
            # on Python's per-process hash randomization, and since `visited`
            # is a global (once-per-node) marker, traversal order determines
            # *which* cycles are found, not just their order — an unsorted
            # `set` here made cycle counts nondeterministic across runs
            # (BACK-627).
            for neighbor in sorted(self.dependencies.get(node, set()), key=str):
                dfs(neighbor)

            current_path.pop()
            rec_stack.remove(node)

        # Run DFS from each node
        for file_path in self.files:
            if file_path not in visited:
                dfs(file_path)

        return cycles

    def cycles_by_file(self) -> Dict[Path, List[List[Path]]]:
        """Cycles from find_cycles() indexed by member file, computed once per graph.

        The cycle search is a property of the whole graph, so per-file callers
        (I002 runs once per file) share one search instead of repeating it
        (BACK-1873). Each file's list keeps find_cycles() order. Not a dataclass
        field, so it never enters the pickled disk-cache entry; add_dependency
        drops it.
        """
        index = self.__dict__.get('_cycles_by_file')
        if index is None:
            index = {}
            for cycle in self.find_cycles():
                for member in set(cycle):
                    index.setdefault(member, []).append(cycle)
            self.__dict__['_cycles_by_file'] = index
        return index

    def find_cycle_groups(self) -> List[List[Path]]:
        """Find circular dependency groups using Tarjan's SCC algorithm.

        Returns one entry per strongly-connected component with >1 member,
        sorted for determinism. This gives the correct count of distinct cycle
        groups: N analyzers all cycling through a shared registry appear as one
        group, not N separate cycles as find_cycles() would report.

        Use this for counting and reporting cycle groups.
        Use find_cycles() when you need per-path cycles for file-level rule checks.
        """
        index_counter = [0]
        stack: List[Path] = []
        lowlink: Dict[Path, int] = {}
        index: Dict[Path, int] = {}
        on_stack: Set[Path] = set()
        sccs: List[List[Path]] = []

        def strongconnect(v: Path) -> None:
            index[v] = index_counter[0]
            lowlink[v] = index_counter[0]
            index_counter[0] += 1
            stack.append(v)
            on_stack.add(v)

            for w in self.dependencies.get(v, set()):
                if w not in index:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], index[w])

            if lowlink[v] == index[v]:
                scc: List[Path] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                if len(scc) > 1:
                    sccs.append(sorted(scc))

        for v in self.files:
            if v not in index:
                strongconnect(v)

        return sccs

    def find_cycle_path(self, group: List[Path]) -> List[Path]:
        """Find a representative cycle path within an SCC group.

        Returns a path list [A, B, C, A] showing the *shortest* way the first
        node in the group reaches itself via other group members. Used for
        verbose display. Falls back to the group list if no path is found.

        Implemented as a breadth-first search rather than the natural recursive
        DFS (BACK-496): a DFS that copies its ``visited`` set per branch — with
        no global dead-end marking — enumerates every *simple* path from
        ``start`` before returning, which is exponential in a large dense SCC.
        A real one surfaced the day Java/Swift/Kotlin/PHP/Ruby import edges
        first resolved (BACK-487/488): a 30k-file Java repo produced a
        multi-thousand-node strongly-connected component and the old DFS never
        returned (hash-ordering-dependent, so it looked fine on small graphs and
        some seeds). BFS visits each group node at most once — O(V+E) — and, as
        a bonus, returns the shortest representative cycle, which reads better.
        """
        if len(group) < 2:
            return group
        group_set = set(group)
        start = group[0]

        # BFS outward from `start`; `parent` both marks a node visited and
        # records the edge used to reach it, for path reconstruction. `start`
        # is intentionally never marked visited so we can detect the edge that
        # closes the cycle back onto it.
        parent: Dict[Path, Path] = {}
        queue: deque = deque()
        for neighbor in sorted(self.dependencies.get(start, set()), key=str):
            if neighbor == start:
                return [start, start]  # self-loop
            if neighbor in group_set and neighbor not in parent:
                parent[neighbor] = start
                queue.append(neighbor)

        while queue:
            node = queue.popleft()
            for neighbor in sorted(self.dependencies.get(node, set()), key=str):
                if neighbor == start:
                    # Reconstruct start → … → node, then close back to start.
                    path = [node]
                    while path[-1] != start:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path + [start]
                if neighbor in group_set and neighbor not in parent:
                    parent[neighbor] = node
                    queue.append(neighbor)

        return group

    def find_unused_imports(self, symbols_by_file: Dict[Path, Set[str]]) -> List[Tuple[ImportStatement, List[str]]]:
        """Find imports whose names are never used in the code.

        Args:
            symbols_by_file: Map of file_path -> set of symbols used in that file
                             (should include __all__ exports to handle re-exports)

        Returns:
            `(statement, unused names)` pairs -- a `from x import a, b` with only
            `b` unused reports `b`. The decision is shared with I001
            (analyzers/imports/unused.py), so the two never disagree (BACK-1066).
        """
        unused: List[Tuple[ImportStatement, List[str]]] = []
        for file_path, imports in self.files.items():
            symbols_used = symbols_by_file.get(file_path, set())
            for stmt in imports:
                names = unused_entries(stmt, symbols_used)
                if names:
                    unused.append((stmt, names))
        return unused

    def get_import_count(self) -> int:
        """Get total number of import statements."""
        return sum(len(imports) for imports in self.files.values())

    def get_file_count(self) -> int:
        """Get number of files with imports."""
        return len(self.files)


__all__ = ['ImportStatement', 'ImportExtraction', 'ImportAnalysis', 'ImportGraph',
           'LAZY_INCLUDE', 'LAZY_EXCLUDE', 'LAZY_ONLY', 'LAZY_MODES']
