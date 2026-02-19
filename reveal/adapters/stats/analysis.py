"""File analysis functions for stats adapter."""

import os
from pathlib import Path
from typing import Dict, Any, Optional, List

from ...registry import get_analyzer


def _is_large_json(file_path: Path) -> bool:
    """Return True if file_path is a JSON file larger than 10KB."""
    try:
        return file_path.stat().st_size > 10240
    except (OSError, PermissionError):
        return False


def find_analyzable_files(directory: Path, code_only: bool = False) -> List[Path]:
    """Find all files that can be analyzed.

    Args:
        directory: Directory to search
        code_only: If True, exclude data/config files

    Returns:
        List of analyzable file paths
    """
    # Data/config extensions to exclude when code_only=True
    DATA_EXTENSIONS = {'.xml', '.csv', '.sql'}
    CONFIG_EXTENSIONS = {'.yaml', '.yml', '.toml'}

    analyzable = []
    for root, dirs, files in os.walk(directory):
        # Skip common ignore directories
        dirs[:] = [d for d in dirs if d not in {
            '.git', '__pycache__', 'node_modules', '.venv', 'venv',
            'dist', 'build', '.pytest_cache', '.mypy_cache'
        }]

        for file in files:
            file_path = Path(root) / file

            # Check if reveal can analyze this file type
            if not get_analyzer(str(file_path)):
                continue

            # Apply code_only filter
            if code_only:
                suffix = file_path.suffix.lower()

                # Exclude data files
                if suffix in DATA_EXTENSIONS:
                    continue

                # Exclude config files
                if suffix in CONFIG_EXTENSIONS:
                    continue

                # Exclude large JSON files (>10KB, likely data not code)
                if suffix == '.json' and _is_large_json(file_path):
                    continue

            analyzable.append(file_path)

    return analyzable


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
        return stats

    except Exception as e:
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
        return str(file_path.relative_to(base_path))
    else:
        return str(file_path)
