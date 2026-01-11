"""Directory tree view for reveal."""

import os
from pathlib import Path
from typing import List
from .registry import get_analyzer


def show_directory_tree(path: str, depth: int = 3, show_hidden: bool = False,
                        max_entries: int = 200, fast: bool = False) -> str:
    """Show directory tree with file info.

    Args:
        path: Directory path
        depth: Maximum depth to traverse
        show_hidden: Whether to show hidden files/dirs
        max_entries: Maximum entries to display (0=unlimited)
        fast: Skip expensive line counting for performance

    Returns:
        Formatted tree string
    """
    path = Path(path)

    if not path.is_dir():
        return f"Error: {path} is not a directory"

    # Count total entries first for warnings
    total_entries = _count_entries(path, depth, show_hidden)

    lines = [f"{path.name or path}/\n"]

    # Warn if directory is large and user hasn't disabled limits
    if total_entries > 500 and max_entries > 0:
        lines.append(f"⚠️  Large directory detected ({total_entries} entries)")
        lines.append(f"   Showing first {max_entries} entries (use --max-entries 0 for unlimited)")
        if not fast:
            lines.append("   Consider using --fast to skip line counting for better performance\n")

    # Track how many entries we've shown
    context = {'count': 0, 'max_entries': max_entries, 'truncated': 0}
    _walk_directory(path, lines, depth=depth, show_hidden=show_hidden,
                   fast=fast, context=context)

    # Show truncation message if we hit the limit
    if context['truncated'] > 0:
        lines.append(f"\n... {context['truncated']} more entries (use --max-entries 0 to show all)")

    # Add navigation hint
    lines.append(f"\nUsage: reveal {path}/<file>")

    return '\n'.join(lines)


def _count_entries(path: Path, depth: int, show_hidden: bool) -> int:
    """Count total entries in directory tree (fast, no analysis)."""
    if depth <= 0:
        return 0

    try:
        entries = list(path.iterdir())
    except PermissionError:
        return 0

    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith('.')]

    count = len(entries)
    for entry in entries:
        if entry.is_dir():
            count += _count_entries(entry, depth - 1, show_hidden)

    return count


def _walk_directory(path: Path, lines: List[str], prefix: str = '', depth: int = 3,
                   show_hidden: bool = False, fast: bool = False, context: dict = None):
    """Recursively walk directory and build tree.

    Args:
        path: Directory to walk
        lines: Output lines list
        prefix: Tree prefix for indentation
        depth: Remaining depth
        show_hidden: Show hidden files
        fast: Skip expensive operations
        context: Shared context dict with 'count', 'max_entries', 'truncated'
    """
    if depth <= 0:
        return

    if context is None:
        context = {'count': 0, 'max_entries': 0, 'truncated': 0}

    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return

    # Filter hidden files/dirs
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith('.')]

    for i, entry in enumerate(entries):
        # Check if we've hit the entry limit
        if context['max_entries'] > 0 and context['count'] >= context['max_entries']:
            # Count remaining entries
            context['truncated'] += len(entries) - i
            return

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
            file_info = _get_file_info(entry, fast=fast)
            lines.append(f"{prefix}{connector}{file_info}")
            context['count'] += 1

        elif entry.is_dir():
            # Show directory
            lines.append(f"{prefix}{connector}{entry.name}/")
            context['count'] += 1
            # Recurse into subdirectory
            _walk_directory(entry, lines, prefix + extension, depth - 1,
                          show_hidden, fast, context)


def _get_file_info(path: Path, fast: bool = False) -> str:
    """Get formatted file info for tree display.

    Args:
        path: File path
        fast: If True, skip expensive line counting

    Returns:
        Formatted string like "app.py (247 lines, Python)" or "app.py (12.5 KB)"
    """
    try:
        if fast:
            # Fast mode: just show file size, no analyzer
            stat = os.stat(path)
            size = _format_size(stat.st_size)
            return f"{path.name} ({size})"

        # Normal mode: Try to get analyzer for this file
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
