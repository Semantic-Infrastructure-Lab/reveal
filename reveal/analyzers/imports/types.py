"""Core types for import analysis.

Shared types used by both the import analysis framework and language extractors.
Extracted to a separate module to avoid circular imports.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict


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
    source_line: str = ""  # Full source line (for noqa comment detection)


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

    def add_dependency(self, from_file: Path, to_file: Path) -> None:
        """Add a dependency edge: from_file imports to_file."""
        self.dependencies[from_file].add(to_file)
        self.reverse_deps[to_file].add(from_file)

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

            for neighbor in self.dependencies.get(node, set()):
                dfs(neighbor)

            current_path.pop()
            rec_stack.remove(node)

        # Run DFS from each node
        for file_path in self.files:
            if file_path not in visited:
                dfs(file_path)

        return cycles

    def find_unused_imports(self, symbols_by_file: Dict[Path, Set[str]]) -> List[ImportStatement]:
        """Find imports that are never used in the code.

        Args:
            symbols_by_file: Map of file_path -> set of symbols used in that file
                             (should include __all__ exports to handle re-exports)

        Returns:
            List of unused import statements
        """
        unused = []

        for file_path, imports in self.files.items():
            symbols_used = symbols_by_file.get(file_path, set())

            for stmt in imports:
                # Skip imports explicitly marked as intentional (# noqa comment)
                if '# noqa' in stmt.source_line or '# type: ignore' in stmt.source_line:
                    continue

                # Skip TYPE_CHECKING imports - they're type-checking only
                if stmt.is_type_checking:
                    continue

                # Check if any imported name is used
                if stmt.import_type == 'star_import':
                    # Can't reliably detect unused star imports
                    continue

                if stmt.imported_names:
                    # from X import Y, Z - check if Y or Z (or their aliases) are used
                    # Handle "from X import Y as Z" by extracting alias if present
                    used_names = []
                    for name in stmt.imported_names:
                        # Handle "Name as Alias" format
                        if ' as ' in name:
                            _, alias = name.split(' as ', 1)
                            check_name = alias.strip()
                        else:
                            check_name = name

                        if check_name in symbols_used:
                            used_names.append(check_name)

                    if not used_names:
                        unused.append(stmt)
                else:
                    # import X - check if X (or its alias) is used
                    check_name = stmt.alias or stmt.module_name.split('.')[0]
                    if check_name not in symbols_used:
                        unused.append(stmt)

        return unused

    def get_import_count(self) -> int:
        """Get total number of import statements."""
        return sum(len(imports) for imports in self.files.values())

    def get_file_count(self) -> int:
        """Get number of files with imports."""
        return len(self.files)


__all__ = ['ImportStatement', 'ImportGraph']
