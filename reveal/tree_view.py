"""Directory tree view for reveal."""

import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional
from .registry import get_analyzer
from .display.filtering import PathFilter
from .utils import format_size


@dataclass
class TreeViewOptions:
    """Options controlling directory tree rendering."""
    depth: int = 3
    show_hidden: bool = False
    max_entries: int = 200
    fast: bool = False
    respect_gitignore: bool = True
    exclude_patterns: Optional[List[str]] = None
    dir_limit: int = 50
    sort_by: Optional[str] = None
    sort_desc: bool = False
    include_extensions: Optional[List[str]] = None


def _collect_matching_files(root_path: Path, show_hidden: bool, path_filter: Any, exts: Optional[set]) -> list:
    """Walk root_path and return list of (fpath, stat) for files passing all filters."""
    files = []
    for root, dirs, filenames in os.walk(root_path):
        if not show_hidden:
            dirs[:] = [d for d in dirs if not d.startswith('.')]
        dirs[:] = [d for d in dirs if not path_filter.should_filter(Path(root) / d)]
        for fname in filenames:
            fpath = Path(root) / fname
            if not show_hidden and fname.startswith('.'):
                continue
            if path_filter.should_filter(fpath):
                continue
            if exts and fpath.suffix.lower().lstrip('.') not in exts:
                continue
            try:
                files.append((fpath, fpath.stat()))
            except OSError:
                continue
    return files


def _sort_files(files: list, sort_by: Optional[str], sort_desc: bool) -> None:
    """Sort (fpath, stat) list in-place by sort_by key."""
    effective_sort = sort_by or 'mtime'
    if effective_sort in ('mtime', 'modified'):
        files.sort(key=lambda x: x[1].st_mtime, reverse=sort_desc)
    elif effective_sort == 'size':
        files.sort(key=lambda x: x[1].st_size, reverse=sort_desc)
    elif effective_sort == 'name':
        files.sort(key=lambda x: x[0].name.lower(), reverse=sort_desc)


def show_file_list(path: str, show_hidden: bool = False,
                   respect_gitignore: bool = True,
                   exclude_patterns: Optional[List[str]] = None,
                   sort_by: Optional[str] = None,
                   sort_desc: bool = True,
                   include_extensions: Optional[List[str]] = None) -> str:
    """Show a flat sorted file list — replaces `find dir/ | sort -rn`.

    Args:
        path: Directory path
        show_hidden: Whether to include hidden files/dirs
        respect_gitignore: Whether to respect .gitignore rules
        exclude_patterns: Additional patterns to exclude
        sort_by: Sort key: 'mtime'/'modified' (default), 'name', 'size'
        sort_desc: If True, newest/largest/z-first (default: True)
        include_extensions: If set, only include files with these extensions

    Returns:
        Formatted list string, one file per line with date prefix
    """
    root_path = Path(path)
    if not root_path.is_dir():
        return f"Error: {root_path} is not a directory"

    path_filter = PathFilter(
        root_path=root_path,
        respect_gitignore=respect_gitignore,
        exclude_patterns=exclude_patterns,
        include_defaults=True
    )
    exts = {e.lower().lstrip('.') for e in include_extensions} if include_extensions else None

    files = _collect_matching_files(root_path, show_hidden, path_filter, exts)
    if not files:
        ext_suffix = f" (ext: {','.join(include_extensions)})" if include_extensions else ""
        return f"No files found in {path}{ext_suffix}"

    _sort_files(files, sort_by, sort_desc)

    lines = []
    for fpath, stat in files:
        date_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')
        try:
            rel = fpath.relative_to(root_path)
        except ValueError:
            rel = fpath
        lines.append(f"{date_str}  {rel}")

    return '\n'.join(lines)


def show_directory_tree(path: str, options: Optional[TreeViewOptions] = None, **kwargs) -> str:
    """Show directory tree with file info.

    Args:
        path: Directory path
        options: TreeViewOptions instance. If not provided, built from kwargs for
                 backwards compatibility.
        **kwargs: Backwards-compatible keyword arguments corresponding to TreeViewOptions
                  fields (depth, show_hidden, max_entries, fast, respect_gitignore,
                  exclude_patterns, dir_limit, sort_by, sort_desc, include_extensions).

    Returns:
        Formatted tree string
    """
    if options is None:
        options = TreeViewOptions(
            depth=kwargs.get('depth', 3),
            show_hidden=kwargs.get('show_hidden', False),
            max_entries=kwargs.get('max_entries', 200),
            fast=kwargs.get('fast', False),
            respect_gitignore=kwargs.get('respect_gitignore', True),
            exclude_patterns=kwargs.get('exclude_patterns', None),
            dir_limit=kwargs.get('dir_limit', 50),
            sort_by=kwargs.get('sort_by', None),
            sort_desc=kwargs.get('sort_desc', False),
            include_extensions=kwargs.get('include_extensions', None),
        )

    root_path = Path(path)

    if not root_path.is_dir():
        return f"Error: {root_path} is not a directory"

    # Create path filter
    path_filter = PathFilter(
        root_path=root_path,
        respect_gitignore=options.respect_gitignore,
        exclude_patterns=options.exclude_patterns,
        include_defaults=True
    )

    # Count total entries first for warnings
    total_entries = _count_entries(root_path, options.depth, options.show_hidden, path_filter)

    lines = [f"{root_path.name or root_path}/\n"]

    # Warn if directory is large and user hasn't disabled limits
    if total_entries > 500 and options.max_entries > 0:
        lines.append(f"⚠️  Large directory detected ({total_entries} entries)")
        lines.append(f"   Showing first {options.max_entries} entries (use --max-entries 0 for unlimited)")
        if not options.fast:
            lines.append("   Consider using --fast to skip line counting for better performance\n")

    # Track how many entries we've shown
    context: dict[str, Any] = {
        'count': 0, 'max_entries': options.max_entries, 'truncated': 0,
        'dir_limit': options.dir_limit, 'sort_by': options.sort_by,
        'sort_desc': options.sort_desc, 'include_extensions': options.include_extensions,
    }
    _walk_directory(root_path, lines, depth=options.depth, show_hidden=options.show_hidden,
                   fast=options.fast, context=context, path_filter=path_filter)

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


def _get_sorted_entries(path: Path, sort_by: Optional[str] = None,
                        sort_desc: bool = False) -> Optional[List[Path]]:
    """Get sorted directory entries, handling permission errors."""
    try:
        entries = list(path.iterdir())
    except PermissionError:
        return None

    if sort_by in ('mtime', 'modified'):
        entries.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=sort_desc)
    elif sort_by == 'size':
        entries.sort(key=lambda p: p.stat().st_size if p.is_file() else 0, reverse=sort_desc)
    elif sort_by == 'name':
        entries.sort(key=lambda p: p.name.lower(), reverse=sort_desc)
    else:
        # Default: dirs first, then alphabetical
        entries.sort(key=lambda p: (not p.is_dir(), p.name))

    return entries


def _filter_entries(entries: List[Path], show_hidden: bool, path_filter: Optional[PathFilter],
                    include_extensions: Optional[List[str]] = None) -> List[Path]:
    """Apply hidden file and path filtering to entries."""
    if not show_hidden:
        entries = [e for e in entries if not e.name.startswith('.')]
    if path_filter:
        entries = [e for e in entries if not path_filter.should_filter(e)]
    if include_extensions:
        exts = {e.lower().lstrip('.') for e in include_extensions}
        entries = [e for e in entries if e.is_dir() or e.suffix.lower().lstrip('.') in exts]
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
                   show_hidden: bool = False, fast: bool = False, context: Optional[dict] = None,
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

    sort_by = context.get('sort_by')
    sort_desc = context.get('sort_desc', False)
    include_extensions = context.get('include_extensions')

    entries = _get_sorted_entries(path, sort_by=sort_by, sort_desc=sort_desc)
    if entries is None:
        return

    entries = _filter_entries(entries, show_hidden, path_filter, include_extensions=include_extensions)

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
