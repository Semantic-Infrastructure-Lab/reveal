"""Path utilities for directory traversal and file discovery.

Consolidates common patterns for searching up directory trees.
"""

from pathlib import Path
from typing import Callable, Optional, List


def find_file_in_parents(
    start: Path,
    filename: str,
    max_depth: int = 20
) -> Optional[Path]:
    """Find a file by searching up the directory tree.

    Common pattern for finding config files like .reveal.yaml, pyproject.toml, etc.

    Args:
        start: Starting path (file or directory)
        filename: Name of file to find
        max_depth: Maximum directories to traverse up (default: 20)

    Returns:
        Path to the file if found, None otherwise

    Example:
        # Find nearest .reveal.yaml
        config = find_file_in_parents(Path("src/module/file.py"), ".reveal.yaml")
    """
    current = start if start.is_dir() else start.parent
    depth = 0

    while current != current.parent and depth < max_depth:
        target = current / filename
        if target.exists():
            return target
        current = current.parent
        depth += 1

    return None


def search_parents(
    start: Path,
    condition: Callable[[Path], bool],
    max_depth: int = 20
) -> Optional[Path]:
    """Search up directory tree until condition is met.

    Generic parent search for flexible conditions.

    Args:
        start: Starting path (file or directory)
        condition: Function that takes a Path and returns True if match found
        max_depth: Maximum directories to traverse up (default: 20)

    Returns:
        First parent path that satisfies condition, None if not found

    Example:
        # Find nearest parent named 'docs'
        docs = search_parents(
            Path("docs/guides/intro.md"),
            lambda p: p.name == 'docs'
        )

        # Find parent containing 'pyproject.toml'
        project_root = search_parents(
            Path("src/module.py"),
            lambda p: (p / 'pyproject.toml').exists()
        )
    """
    current = start if start.is_dir() else start.parent
    depth = 0

    while current != current.parent and depth < max_depth:
        if condition(current):
            return current
        current = current.parent
        depth += 1

    return None


def find_project_root(
    start: Path,
    markers: Optional[List[str]] = None
) -> Optional[Path]:
    """Find the project root by looking for common project markers.

    Args:
        start: Starting path
        markers: List of filenames that indicate project root
                 Defaults to common markers like pyproject.toml, .git, etc.

    Returns:
        Project root path if found, None otherwise

    Example:
        root = find_project_root(Path("src/deep/module.py"))
        # Returns path containing pyproject.toml, .git, etc.
    """
    if markers is None:
        markers = [
            'pyproject.toml',
            'setup.py',
            'setup.cfg',
            '.git',
            'Cargo.toml',
            'package.json',
            'go.mod',
        ]

    def has_marker(p: Path) -> bool:
        return any((p / marker).exists() for marker in markers)

    return search_parents(start, has_marker)


def get_relative_to_root(
    path: Path,
    root_markers: Optional[List[str]] = None
) -> Path:
    """Get path relative to project root.

    Useful for display and logging - shows "src/module.py" instead of
    "/home/user/projects/myproject/src/module.py".

    Args:
        path: Absolute or relative path
        root_markers: Project root markers (see find_project_root)

    Returns:
        Path relative to project root, or original path if root not found
    """
    path = Path(path).resolve()
    root = find_project_root(path, root_markers)

    if root:
        try:
            return path.relative_to(root)
        except ValueError:
            pass

    return path
