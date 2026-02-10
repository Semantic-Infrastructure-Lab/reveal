"""Directory tree view for reveal."""

import os
from pathlib import Path
from typing import List, Optional
from .registry import get_analyzer
from .display.filtering import PathFilter
from .utils import format_size


def show_directory_tree(path: str, depth: int = 3, show_hidden: bool = False,
                        max_entries: int = 200, fast: bool = False,
                        respect_gitignore: bool = True,
                        exclude_patterns: Optional[List[str]] = None,
                        dir_limit: int = 50) -> str:
    """Show directory tree with file info.

    Args:
        path: Directory path
        depth: Maximum depth to traverse
        show_hidden: Whether to show hidden files/dirs
        max_entries: Maximum entries to display (0=unlimited)
        fast: Skip expensive line counting for performance
        respect_gitignore: Whether to respect .gitignore rules (default: True)
        exclude_patterns: Additional patterns to exclude (e.g., ['*.log', 'tmp/'])
        dir_limit: Maximum entries per directory before snipping (default: 50, 0=unlimited).
                   When exceeded, shows "[snipped N more]" and continues with siblings.

    Returns:
        Formatted tree string
    """
    path = Path(path)

    if not path.is_dir():
        return f"Error: {path} is not a directory"

    # Create path filter
    path_filter = PathFilter(
        root_path=path,
        respect_gitignore=respect_gitignore,
        exclude_patterns=exclude_patterns,
        include_defaults=True
    )

    # Count total entries first for warnings
    total_entries = _count_entries(path, depth, show_hidden, path_filter)

    lines = [f"{path.name or path}/\n"]

    # Warn if directory is large and user hasn't disabled limits
    if total_entries > 500 and max_entries > 0:
        lines.append(f"⚠️  Large directory detected ({total_entries} entries)")
        lines.append(f"   Showing first {max_entries} entries (use --max-entries 0 for unlimited)")
        if not fast:
            lines.append("   Consider using --fast to skip line counting for better performance\n")

    # Track how many entries we've shown
    context = {'count': 0, 'max_entries': max_entries, 'truncated': 0, 'dir_limit': dir_limit}
    _walk_directory(path, lines, depth=depth, show_hidden=show_hidden,
                   fast=fast, context=context, path_filter=path_filter)

    # Show truncation message if we hit the limit
    if context['truncated'] > 0:
        lines.append(f"\n... {context['truncated']} more entries (use --max-entries 0 to show all)")

    # Add navigation hint
    lines.append(f"\nUsage: reveal {path}/<file>")

    return '\n'.join(lines)


def _count_entries(path: Path, depth: int, show_hidden: bool, path_filter: PathFilter) -> int:
    """Count total entries in directory tree (fast, no analysis)."""
    if depth <= 0:
        return 0

    try:
        entries = list(path.iterdir())
    except PermissionError:
        return 0

    # Apply filtering
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith('.')]

    # Apply path filtering (gitignore, noise patterns, custom excludes)
    entries = [e for e in entries if not path_filter.should_filter(e)]

    count = len(entries)
    for entry in entries:
        if entry.is_dir():
            count += _count_entries(entry, depth - 1, show_hidden, path_filter)

    return count


def _initialize_context() -> dict:
    """Initialize empty context dictionary."""
    return {'count': 0, 'max_entries': 0, 'truncated': 0, 'dir_limit': 0}


def _get_sorted_entries(path: Path) -> Optional[List[Path]]:
    """Get sorted directory entries, handling permission errors."""
    try:
        return sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return None


def _filter_entries(entries: List[Path], show_hidden: bool, path_filter: Optional[PathFilter]) -> List[Path]:
    """Apply hidden file and path filtering to entries."""
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith('.')]
    if path_filter:
        entries = [e for e in entries if not path_filter.should_filter(e)]
    return entries


def _check_global_limit(context: dict, entries: List[Path], i: int) -> bool:
    """Check if global entry limit reached. Updates truncated count if so.

    Returns:
        True if limit reached and should stop
    """
    if context['max_entries'] > 0 and context['count'] >= context['max_entries']:
        context['truncated'] += len(entries) - i
        return True
    return False


def _check_dir_limit(dir_limit: int, dir_entry_count: int, entries: List[Path], i: int,
                     lines: List[str], prefix: str, context: dict) -> bool:
    """Check if per-directory limit reached. Adds snip message if so.

    Returns:
        True if limit reached and should stop
    """
    if dir_limit > 0 and dir_entry_count >= dir_limit:
        snipped_count = len(entries) - i
        lines.append(f"{prefix}└── [snipped {snipped_count} more entries] (--dir-limit 0 to show all)")
        context['truncated'] += snipped_count
        return True
    return False


def _get_tree_connectors(is_last: bool) -> tuple:
    """Get tree connector and extension characters.

    Returns:
        (connector, extension) tuple
    """
    if is_last:
        return '└── ', '    '
    else:
        return '├── ', '│   '


def _process_file_entry(entry: Path, lines: List[str], prefix: str, connector: str,
                       context: dict, fast: bool) -> int:
    """Process file entry and add to output.

    Returns:
        Number of entries added (always 1 for files)
    """
    file_info = _get_file_info(entry, fast=fast)
    lines.append(f"{prefix}{connector}{file_info}")
    context['count'] += 1
    return 1


def _process_dir_entry(entry: Path, lines: List[str], prefix: str, connector: str, extension: str,
                      context: dict, depth: int, show_hidden: bool, fast: bool,
                      path_filter: Optional[PathFilter]) -> int:
    """Process directory entry and recurse.

    Returns:
        Number of entries added (always 1 for directories)
    """
    lines.append(f"{prefix}{connector}{entry.name}/")
    context['count'] += 1
    _walk_directory(entry, lines, prefix + extension, depth - 1,
                   show_hidden, fast, context, path_filter)
    return 1


def _walk_directory(path: Path, lines: List[str], prefix: str = '', depth: int = 3,
                   show_hidden: bool = False, fast: bool = False, context: dict = None,
                   path_filter: Optional[PathFilter] = None):
    """Recursively walk directory and build tree.

    Args:
        path: Directory to walk
        lines: Output lines list
        prefix: Tree prefix for indentation
        depth: Remaining depth
        show_hidden: Show hidden files
        fast: Skip expensive operations
        context: Shared context dict with 'count', 'max_entries', 'truncated', 'dir_limit'
        path_filter: PathFilter for smart filtering
    """
    if depth <= 0:
        return

    context = context or _initialize_context()

    entries = _get_sorted_entries(path)
    if entries is None:
        return

    entries = _filter_entries(entries, show_hidden, path_filter)

    dir_limit = context.get('dir_limit', 0)
    dir_entry_count = 0

    for i, entry in enumerate(entries):
        if _check_global_limit(context, entries, i):
            return

        if _check_dir_limit(dir_limit, dir_entry_count, entries, i, lines, prefix, context):
            return

        is_last = (i == len(entries) - 1)
        connector, extension = _get_tree_connectors(is_last)

        if entry.is_file():
            dir_entry_count += _process_file_entry(entry, lines, prefix, connector, context, fast)
        elif entry.is_dir():
            dir_entry_count += _process_dir_entry(entry, lines, prefix, connector, extension,
                                                  context, depth, show_hidden, fast, path_filter)


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
            size = format_size(stat.st_size)
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
            size = format_size(stat.st_size)
            return f"{path.name} ({size})"

    except Exception:
        # If anything fails, just show filename
        return path.name
