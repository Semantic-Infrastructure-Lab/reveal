"""Directory tree view for reveal."""

import os
from pathlib import Path
from typing import List, Optional
from .base import get_analyzer


def show_directory_tree(path: str, depth: int = 3, show_hidden: bool = False) -> str:
    """Show directory tree with file info.

    Args:
        path: Directory path
        depth: Maximum depth to traverse
        show_hidden: Whether to show hidden files/dirs

    Returns:
        Formatted tree string
    """
    path = Path(path)

    if not path.is_dir():
        return f"Error: {path} is not a directory"

    lines = [f"{path.name or path}/\n"]
    _walk_directory(path, lines, depth=depth, show_hidden=show_hidden)

    # Add navigation hint
    lines.append(f"\nUsage: reveal {path}/<file>")

    return '\n'.join(lines)


def _walk_directory(path: Path, lines: List[str], prefix: str = '', depth: int = 3, show_hidden: bool = False):
    """Recursively walk directory and build tree."""
    if depth <= 0:
        return

    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return

    # Filter hidden files/dirs
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith('.')]

    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)

        # Tree characters
        if is_last:
            connector = '└── '
            extension = '    '
        else:
            connector = '├── '
            extension = '│   '

        if entry.is_file():
            # Show file with metadata
            file_info = _get_file_info(entry)
            lines.append(f"{prefix}{connector}{file_info}")

        elif entry.is_dir():
            # Show directory
            lines.append(f"{prefix}{connector}{entry.name}/")
            # Recurse into subdirectory
            _walk_directory(entry, lines, prefix + extension, depth - 1, show_hidden)


def _get_file_info(path: Path) -> str:
    """Get formatted file info for tree display.

    Returns:
        Formatted string like "app.py (247 lines, Python)"
    """
    try:
        # Try to get analyzer for this file
        analyzer_class = get_analyzer(str(path))

        if analyzer_class:
            # Use analyzer to get info
            analyzer = analyzer_class(str(path))
            meta = analyzer.get_metadata()
            file_type = analyzer.type_name

            return f"{path.name} ({meta['lines']} lines, {file_type})"
        else:
            # No analyzer - just show basic info
            stat = os.stat(path)
            size = _format_size(stat.st_size)
            return f"{path.name} ({size})"

    except Exception:
        # If anything fails, just show filename
        return path.name


def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
