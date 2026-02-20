"""I002: Circular dependency detector.

Detects circular import dependencies between modules.
Supports Python, JavaScript, Go, and Rust.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports import ImportGraph
from ...analyzers.imports.base import get_extractor, get_all_extensions

logger = logging.getLogger(__name__)

# Module-level cache: project_root → ImportGraph.
# _build_import_graph scans every source file under the project root via
# tree-sitter; caching by project root makes the scan happen once per project
# per process (was once per subdirectory, defeating the cache on deep trees).
_graph_cache: Dict[Path, 'ImportGraph'] = {}


def _find_project_root(path: Path) -> Path:
    """Walk up from path to find the project root (pyproject.toml/setup.py).

    Falls back to the topmost directory containing __init__.py, then to
    path.parent if no markers are found.
    """
    current = path.parent

    # Pass 1: look for project-level markers (strongest signal)
    sentinel = current
    git_root = None
    for _ in range(15):
        if (current / 'pyproject.toml').exists() or (current / 'setup.py').exists():
            return current
        if git_root is None and (current / '.git').exists():
            git_root = current  # note it, keep walking for pyproject.toml above it
        parent = current.parent
        if parent == current:
            break
        current = parent

    # .git is a strong project root signal even without pyproject.toml
    if git_root is not None:
        return git_root

    # Pass 2: topmost __init__.py boundary
    current = sentinel
    for _ in range(15):
        if (current / '__init__.py').exists():
            parent = current.parent
            if not (parent / '__init__.py').exists():
                return current
        current = current.parent

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
        """Phase 1: Walk directory and extract raw import statements from all files."""
        all_imports = []
        supported_extensions = get_all_extensions()

        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in supported_extensions:
                continue
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            try:
                all_imports.extend(extractor.extract_imports(file_path))
            except Exception as e:
                logger.debug(f"Failed to extract imports from {file_path}: {e}")

        return all_imports

    def _resolve_graph_dependencies(self, graph: ImportGraph) -> None:
        """Phase 2: Resolve import statements to actual file paths and add edges."""
        for file_path, imports in graph.files.items():
            extractor = get_extractor(file_path)
            if not extractor:
                continue
            base_path = file_path.parent
            for stmt in imports:
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
