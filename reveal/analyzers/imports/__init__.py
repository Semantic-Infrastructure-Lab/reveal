"""Import analysis framework for reveal.

This module provides language-agnostic import graph analysis for detecting:
- Unused imports
- Circular dependencies
- Layer violations

Core types are defined here; language-specific extractors are in submodules.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set
from collections import defaultdict, deque


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
        current_path = []

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

        Returns:
            List of unused import statements
        """
        unused = []

        for file_path, imports in self.files.items():
            symbols_used = symbols_by_file.get(file_path, set())

            for stmt in imports:
                # Check if any imported name is used
                if stmt.import_type == 'star_import':
                    # Can't reliably detect unused star imports
                    continue

                if stmt.imported_names:
                    # from X import Y, Z - check if Y or Z are used
                    used_names = [name for name in stmt.imported_names if name in symbols_used]
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


# Import extractors and layer config after core types are defined (avoid circular imports)
from .layers import LayerRule, LayerConfig, load_layer_config
from .javascript import extract_js_imports
from .go import extract_go_imports
from .rust import extract_rust_imports


__all__ = [
    'ImportStatement',
    'ImportGraph',
    'LayerRule',
    'LayerConfig',
    'load_layer_config',
    'extract_js_imports',
    'extract_go_imports',
    'extract_rust_imports',
]
