"""File analysis functions for stats adapter."""

from pathlib import Path
from typing import Dict, Any, Optional, List, Iterator, cast

from ...registry import DECLARATION_ONLY_EXTENSIONS, get_analyzer
from ...utils.path_utils import _walk_code_files


def _is_excluded_code_only(file_path: Path) -> bool:
    """Return True if file should be excluded in code_only mode."""
    suffix = file_path.suffix.lower()
    if suffix in {'.xml', '.csv', '.sql'}:
        return True
    if suffix in {'.yaml', '.yml', '.toml'}:
        return True
    return suffix == '.json' and _is_large_json(file_path)


def _is_large_json(file_path: Path) -> bool:
    """Return True if file_path is a JSON file larger than 10KB."""
    try:
        return file_path.stat().st_size > 10240
    except (OSError, PermissionError):
        return False


def find_analyzable_files(
    directory: Path,
    code_only: bool = False,
    respect_gitignore: Optional[bool] = None,
    exclude_patterns: Optional[List[str]] = None,
    excluded_by_extension: Optional[Dict[str, int]] = None,
) -> Iterator[Path]:
    """Yield files that can be analyzed.

    Args:
        directory: Directory to search
        code_only: If True, exclude data/config files
        respect_gitignore: skip what git ignores (utils/gitignore.py);
            None follows the process switch (--no-gitignore)
        exclude_patterns: BACK-1042 — additional user-supplied --exclude
            patterns, matched with the same semantics as gitignore_patterns
            (same directory-pruning behavior, so an excluded subtree is
            never walked/analyzed at all)
        excluded_by_extension: BACK-1241 — when given, a dict this function
            increments (by lowercased extension, or '(no extension)') every
            time a file is skipped purely because it has no registered
            analyzer (registry.get_analyzer() returned None) -- the gap
            classify:// silently fell into (its population/count is this
            same generator's yielded set, with nothing disclosing what was
            filtered out). Optional and additive: existing callers that
            don't pass it see no change in behavior or yield order.

    Yields:
        Analyzable file paths one at a time (generator — avoids materializing
        the full list into memory before analysis begins).
    """
    # The shared walk (BACK-1223): .gitignore via git's own verdict (BACK-1485),
    # REVEAL_IGNORE/config 'ignore:' (BACK-1221) and --exclude (BACK-1042), pruning
    # well-known directories so os.walk never descends into them. This walker had its own
    # copy of each rule.
    for file_path in _walk_code_files(directory, exclude_patterns, respect_gitignore):
        # Check if reveal can analyze this file type (a .pyi stub can, but a
        # scan skips declaration-only files -- DECLARATION_ONLY_EXTENSIONS)
        if (file_path.suffix.lower() in DECLARATION_ONLY_EXTENSIONS
                or not get_analyzer(str(file_path))):
            if excluded_by_extension is not None:
                ext = file_path.suffix.lower() or '(no extension)'
                excluded_by_extension[ext] = excluded_by_extension.get(ext, 0) + 1
            continue

        # Apply code_only filter
        if code_only and _is_excluded_code_only(file_path):
            continue

        yield file_path


def analyze_file(file_path: Path, calculate_file_stats_func) -> Optional[Dict[str, Any]]:
    """Analyze a single file.

    Args:
        file_path: Path to file
        calculate_file_stats_func: Function to calculate file statistics

    Returns:
        Dict with file statistics; None when no analyzer handles the file; a
        failure record (``analysis_failed`` + ``path``) when analysis raised, so a
        crash is never counted as an unsupported file (BACK-1614)
    """
    try:
        # Get analyzer for this file
        analyzer_class = get_analyzer(str(file_path))
        if not analyzer_class:
            return None

        # Analyze structure
        analyzer = analyzer_class(str(file_path))
        structure_dict = analyzer.get_structure()

        # Calculate statistics (analyzer has content)
        stats = calculate_file_stats_func(file_path, structure_dict, analyzer.content)

        # Release large buffers immediately; don't wait for GC.
        # During directory scans (stats://, overview) hundreds of analyzers are
        # created sequentially — each holds the file's full content in memory.
        # Clearing here keeps peak memory proportional to one file, not all files.
        analyzer.lines = []
        analyzer.content = ''
        if hasattr(analyzer, '_content_bytes'):
            analyzer._content_bytes = None

        return cast(Dict[str, Any], stats)

    except Exception as e:  # any analyzer, any file: one failure must not stop a repo-wide scan
        return {'analysis_failed': f"{type(e).__name__}: {e}", 'path': str(file_path)}


def is_failure(file_stats: Optional[Dict[str, Any]]) -> bool:
    """True for analyze_file's failure record."""
    return bool(file_stats) and 'analysis_failed' in file_stats  # type: ignore[operator]


def get_file_display_path(file_path: Path, base_path: Path) -> str:
    """Get display path for a file.

    Args:
        file_path: Path to file
        base_path: Base path for relative calculations

    Returns:
        Display-friendly path string
    """
    if base_path.is_file() and file_path == base_path:
        return file_path.name
    elif file_path.is_relative_to(base_path):
        return file_path.relative_to(base_path).as_posix()
    else:
        return str(file_path)
