"""I002: Circular dependency detector.

Detects circular import dependencies between modules.
Supports Python, JavaScript, Go, and Rust.
"""

import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports import ImportGraph
from ...analyzers.imports.base import get_extractor, get_all_extensions
from ...utils.path_utils import is_unsafe_scan_root

logger = logging.getLogger(__name__)

# Module-level cache: project_root → ImportGraph.
# _build_import_graph scans every source file under the project root via
# tree-sitter; caching by project root makes the scan happen once per project
# per process (was once per subdirectory, defeating the cache on deep trees).
_graph_cache: Dict[Path, 'ImportGraph'] = {}

# Project-root marker files, one per supported language. The presence of any of
# these at a directory level means "this directory is a project root, stop here".
# Without the non-Python markers, a TS/Go/Rust project with no .git would fall
# through to the __init__.py heuristic and could mis-detect a far ancestor as the
# root (BACK-338), then scan tens of thousands of unrelated files.
_PROJECT_MARKERS = (
    'pyproject.toml',  # Python
    'setup.py',        # Python
    'package.json',    # JavaScript / TypeScript
    'go.mod',          # Go
    'Cargo.toml',      # Rust
)

# Safety ceiling on the import-graph scan. A correctly-detected project root
# almost never exceeds this; blowing past it means root detection went wrong
# (BACK-338). When tripped we log and return an empty graph — a logged skip, not
# a silent multi-minute hang. Override with REVEAL_I002_MAX_FILES for monorepos.
_DEFAULT_MAX_GRAPH_FILES = 20000

# BACK-536: the Pass-B parse loop in _collect_raw_imports is the dominant cost of
# `check` on large trees (measured ~97% of `check samples/go` — one tree-sitter
# parse per source file under the project root). Per-file extraction is
# independent, so fan it out across processes, reusing BACK-489 P1's pattern and
# its REVEAL_MAX_WORKERS override. The graph is built in the main process (see
# file_checker._i002_preload) before the check worker pool spawns, so this pool
# never nests inside another; ProcessPoolExecutor.map preserves order, so the
# assembled graph is identical to the serial path.
_GRAPH_PARALLEL_MIN_FILES = 200   # below this, pool startup/IPC outweighs the win
_GRAPH_PARALLEL_MAX_WORKERS = 16  # cap so huge core counts don't oversubscribe


def _graph_worker_count(n_files: int) -> int:
    """Workers for the Pass-B parse; 1 means run serially (no pool).

    REVEAL_MAX_WORKERS overrides everything (set to 1 to force the serial path —
    used by tests and for byte-identical verification); otherwise parallelize
    only above _GRAPH_PARALLEL_MIN_FILES, capped at _GRAPH_PARALLEL_MAX_WORKERS
    and the CPU count.
    """
    override = os.environ.get('REVEAL_MAX_WORKERS')
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass
    if n_files < _GRAPH_PARALLEL_MIN_FILES:
        return 1
    return max(1, min(os.cpu_count() or 1, _GRAPH_PARALLEL_MAX_WORKERS))


def _extract_imports_for_file(fp_str: str) -> list:
    """Extract imports for one file. Module-level and picklable so it runs
    unchanged under a ProcessPoolExecutor (fork or spawn).

    Swallows per-file extraction errors and returns [] for files with no
    extractor — mirroring _collect_raw_imports's serial per-file try/except so
    the parallel and serial paths produce identical results.
    """
    fp = Path(fp_str)
    extractor = get_extractor(fp)
    if not extractor:
        return []
    try:
        return list(extractor.extract_imports(fp))
    except Exception:
        return []


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


def _find_project_root(path: Path) -> Path:
    """Walk up from path to find the project root.

    Resolution order:
      1. The nearest ancestor holding a language project marker
         (pyproject.toml, setup.py, package.json, go.mod, Cargo.toml).
      2. The nearest ancestor holding a .git directory.
      3. The top of the *contiguous* __init__.py chain rooted at the target's
         own directory (Python packages only).
      4. path.parent, if none of the above apply.

    Step 3 is deliberately contiguous: a stray __init__.py far up the tree (a
    common leftover in a shared src/ or home dir) must never hijack the root of
    an unrelated, non-package directory and trigger a whole-tree scan (BACK-338).
    """
    current = path.parent

    # Pass 1: look for project-level markers (strongest signal)
    sentinel = current
    git_root = None
    for _ in range(15):
        if any((current / marker).exists() for marker in _PROJECT_MARKERS):
            return current
        if git_root is None and (current / '.git').exists():
            git_root = current  # note it, keep walking for a marker above it
        parent = current.parent
        if parent == current:
            break
        current = parent

    # .git is a strong project root signal even without a marker file
    if git_root is not None and not is_unsafe_scan_root(git_root):
        return git_root

    # Pass 2: contiguous __init__.py chain from the target's own package upward.
    # If the target directory is not itself a Python package, do NOT ascend —
    # this is what prevents a far-ancestor __init__.py from hijacking the root.
    if (sentinel / '__init__.py').exists():
        current = sentinel
        for _ in range(15):
            parent = current.parent
            if parent == current or not (parent / '__init__.py').exists():
                return current
            current = parent

    return sentinel


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
            if is_unsafe_scan_root(scan_root):
                logger.debug(
                    "I002: skipping circular-dependency scan for standalone file under %s",
                    scan_root,
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
            logger.debug(f"Failed to analyze {file_path}: {e}")
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

        all_imports = self._collect_raw_imports(directory)
        graph = ImportGraph.from_imports(all_imports)
        self._resolve_graph_dependencies(graph)

        _graph_cache[directory] = graph
        return graph

    def _collect_raw_imports(self, directory: Path) -> list:
        """Phase 1: Walk directory and extract raw import statements from all files.

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
        """
        supported_extensions = get_all_extensions()
        max_files = _max_graph_files()

        # Pass A: cheap count-only walk — abort before any parsing if over ceiling.
        source_files = []
        for file_path in directory.rglob("*"):
            if file_path.suffix not in supported_extensions:
                continue
            if not file_path.is_file():
                continue
            source_files.append(file_path)
            if len(source_files) > max_files:
                logger.warning(
                    "I002: import-graph scan of %s exceeded %d source files; "
                    "skipping circular-dependency analysis (likely a project-root "
                    "mis-detection — set REVEAL_I002_MAX_FILES to raise the limit)",
                    directory, max_files,
                )
                return []

        # Pass B: parse the (now bounded) set of files. Independent per file, so
        # fan out across processes on large trees (BACK-536). map() preserves
        # submission order, so the assembled graph is identical to the serial path.
        file_strs = [str(f) for f in source_files]
        workers = _graph_worker_count(len(file_strs))

        if workers <= 1:
            all_imports: list = []
            for fp_str in file_strs:
                all_imports.extend(_extract_imports_for_file(fp_str))
            return all_imports

        try:
            from concurrent.futures import ProcessPoolExecutor
            all_imports = []
            with ProcessPoolExecutor(max_workers=workers) as executor:
                for imports in executor.map(_extract_imports_for_file, file_strs):
                    all_imports.extend(imports)
            return all_imports
        except Exception as e:
            # Degrade to serial on any pool failure (restricted/forbidden-fork
            # environments) rather than losing the analysis entirely.
            logger.debug("I002: parallel import extraction failed (%s); running serially", e)
            all_imports = []
            for fp_str in file_strs:
                all_imports.extend(_extract_imports_for_file(fp_str))
            return all_imports

    def _resolve_graph_dependencies(self, graph: ImportGraph) -> None:
        """Phase 2: Resolve import statements to actual file paths and add edges."""
        from dataclasses import replace as dc_replace

        for file_path, imports in graph.files.items():
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            base_path = file_path.parent
            for stmt in imports:
                # Skip imports that can't cause circular ImportError at startup:
                # - TYPE_CHECKING imports never run at runtime
                # - Function-body imports run after all top-level code completes
                if stmt.is_type_checking or stmt.is_in_function:
                    continue
                # For `from . import X, Y, Z` (relative, no module path), each
                # imported name may resolve to a distinct sibling module.  Emit
                # one edge per name so that all submodule dependencies are tracked
                # and resolver.py can match names to their actual files.
                if stmt.is_relative and not stmt.module_name and stmt.imported_names:
                    for name in stmt.imported_names:
                        single = dc_replace(stmt, imported_names=[name])
                        resolved = extractor.resolve_import(single, base_path)
                        if resolved and resolved != file_path:
                            graph.add_dependency(file_path, resolved)
                else:
                    resolved = extractor.resolve_import(stmt, base_path)
                    # Skip self-references (e.g., logging.py importing stdlib logging
                    # should not create logging.py → logging.py dependency)
                    if resolved and resolved != file_path:
                        graph.add_dependency(file_path, resolved)

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
