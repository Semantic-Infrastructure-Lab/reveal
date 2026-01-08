"""I002: Circular dependency detector.

Detects circular import dependencies between Python modules.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ...analyzers.imports import ImportGraph
from ...analyzers.imports.python import extract_python_imports

logger = logging.getLogger(__name__)


class I002(BaseRule):
    """Detect circular dependencies in Python imports."""

    code = "I002"
    message = "Circular dependency detected"
    category = RulePrefix.I
    severity = Severity.HIGH
    file_patterns = ['.py']
    version = "1.0.0"

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Check for circular dependencies involving this file.

        Args:
            file_path: Path to Python file
            structure: Parsed structure (not used)
            content: File content

        Returns:
            List of detections for circular dependencies
        """
        detections = []
        target_path = Path(file_path).resolve()

        try:
            # Build import graph for the directory containing this file
            graph = self._build_import_graph(target_path.parent)

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
        """Build import graph for all Python files in directory and subdirs.

        Args:
            directory: Directory to analyze

        Returns:
            ImportGraph with all imports and resolved dependencies
        """
        from ...analyzers.imports.resolver import resolve_python_import

        all_imports = []

        # Recursively find all Python files
        for py_file in directory.rglob("*.py"):
            if py_file.is_file():
                try:
                    imports = extract_python_imports(py_file)
                    all_imports.extend(imports)
                except Exception as e:
                    logger.debug(f"Failed to extract imports from {py_file}: {e}")

        # Build graph from all imports
        graph = ImportGraph.from_imports(all_imports)

        # Resolve imports to build dependency edges
        for file_path, imports in graph.files.items():
            base_path = file_path.parent

            for stmt in imports:
                resolved = resolve_python_import(stmt, base_path)
                # Skip self-references (e.g., logging.py importing stdlib logging
                # should not create logging.py → logging.py dependency)
                if resolved and resolved != file_path:
                    graph.add_dependency(file_path, resolved)

        return graph

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
