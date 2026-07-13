"""File analysis functions for stats adapter."""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Iterator, cast

from ...registry import get_analyzer
from ...utils.path_utils import is_skippable_dir


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
    respect_gitignore: bool = True,
) -> Iterator[Path]:
    """Yield files that can be analyzed.

    Args:
        directory: Directory to search
        code_only: If True, exclude data/config files
        respect_gitignore: If True, skip gitignored directories and files

    Yields:
        Analyzable file paths one at a time (generator — avoids materializing
        the full list into memory before analysis begins).
    """
    gitignore_patterns: List[str] = []
    if respect_gitignore:
        try:
            from ...cli.file_checker import load_gitignore_patterns  # deferred: cli cycle
            gitignore_patterns = load_gitignore_patterns(directory)
        except Exception:
            pass

    for root, dirs, files in os.walk(directory):
        root_path = Path(root)

        # Prune well-known and gitignored directories in-place so os.walk
        # never descends into them.
        def _keep_dir(d: str) -> bool:
            if is_skippable_dir(root_path, d):
                return False
            if gitignore_patterns:
                from ...cli.file_checker import should_skip_file  # deferred: cli cycle
                try:
                    rel = (root_path / d).relative_to(directory)
                    # Append a dummy filename so should_skip_file sees parts correctly
                    if should_skip_file(rel / '_', gitignore_patterns):
                        return False
                except ValueError:
                    pass
            return True

        dirs[:] = [d for d in dirs if _keep_dir(d)]

        for file in files:
            file_path = root_path / file

            if gitignore_patterns:
                from ...cli.file_checker import should_skip_file  # deferred: cli cycle
                try:
                    if should_skip_file(file_path.relative_to(directory), gitignore_patterns):
                        continue
                except ValueError:
                    pass

            # Check if reveal can analyze this file type
            if not get_analyzer(str(file_path)):
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
        Dict with file statistics or None if analysis fails
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

    except Exception:
        # Silently skip files that can't be analyzed
        return None


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
