"""Validation utilities for common patterns.

Usage:
    # Path validation
    data_dir = require_directory(Path('data/'))

    # With custom error messages
    require_path_exists(path, "Configuration file")
"""

from pathlib import Path
from typing import Optional


def require_path_exists(
    path: Path,
    path_type: Optional[str] = None
) -> Path:
    """Validate that a path exists.

    Args:
        path: Path to check
        path_type: Description for error message (e.g., "Configuration file", "Data directory")

    Returns:
        The path (for chaining)

    Raises:
        FileNotFoundError: If path does not exist

    Examples:
        >>> config = require_path_exists(Path('config.yaml'))
        >>> data_dir = require_path_exists(Path('data/'), "Data directory")
    """
    if not path.exists():
        type_desc = path_type or "Path"
        raise FileNotFoundError(f"{type_desc} not found: {path}")
    return path


def require_directory(
    path: Path,
    dir_type: Optional[str] = None
) -> Path:
    """Validate that a path exists and is a directory.

    Args:
        path: Path to check
        dir_type: Description for error message (e.g., "Data directory")

    Returns:
        The path (for chaining)

    Raises:
        FileNotFoundError: If path does not exist
        ValueError: If path exists but is not a directory

    Examples:
        >>> data_dir = require_directory(Path('data/'))
        >>> src = require_directory(Path('src/'), "Source directory")
    """
    type_desc = dir_type or "Directory"
    require_path_exists(path, type_desc)

    if not path.is_dir():
        raise ValueError(f"{type_desc} is not a directory: {path}")

    return path
