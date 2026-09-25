"""
File and directory filtering for reveal.

Provides smart filtering to hide build artifacts, test output, and other
noise from directory listings. Honors what git ignores (utils/gitignore.py,
the same oracle every analysis walk uses) and custom exclusion rules.

Features:
---------
1. git's own ignore verdict (tracked files are never hidden)
2. Smart defaults for common noise patterns
3. Custom exclude patterns
4. Per-project filtering rules

Usage:
------
    from reveal.display.filtering import should_filter_path

    if should_filter_path(path, respect_gitignore=True):
        continue  # Skip this path
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import fnmatch

from ..utils.gitignore import gitignore_filter


# Common noise patterns that should be filtered by default
# These are universal build artifacts and development files
DEFAULT_NOISE_PATTERNS = [
    # Python
    '__pycache__',
    '*.pyc',
    '*.pyo',
    '*.pyd',
    '.Python',
    'pip-log.txt',
    'pip-delete-this-directory.txt',
    '.tox/',
    '.coverage',
    '.coverage.*',
    'htmlcov/',
    '.pytest_cache/',
    '.mypy_cache/',
    '.ruff_cache/',

    # Build artifacts
    'dist/',
    'build/',
    '*.egg-info/',
    '.eggs/',
    '*.egg',

    # IDEs
    '.vscode/',
    '.idea/',
    '*.swp',
    '*.swo',
    '*~',
    '.DS_Store',

    # Version control
    '.git/',
    '.hg/',
    '.svn/',

    # Node.js
    'node_modules/',
    'npm-debug.log',
    'yarn-error.log',

    # Testing and benchmarking
    '.benchmarks/',

    # Temporary files
    'tmp/',
    'temp/',
    '*.tmp',
]


class PathFilter:
    """Unified path filtering system.

    Combines multiple filtering strategies:
    - .gitignore patterns (if respect_gitignore=True)
    - Default noise patterns
    - Custom exclude patterns
    """

    def __init__(self,
                 root_path: Path,
                 respect_gitignore: bool = True,
                 exclude_patterns: Optional[List[str]] = None,
                 include_defaults: bool = True):
        """Initialize path filter.

        Args:
            root_path: Root directory being analyzed
            respect_gitignore: Whether to use .gitignore rules
            exclude_patterns: Additional patterns to exclude
            include_defaults: Whether to include default noise patterns
        """
        self.root_path = Path(root_path)
        self.respect_gitignore = respect_gitignore
        self.exclude_patterns = exclude_patterns or []
        self.include_defaults = include_defaults

        # BACK-1485: git's verdict, shared with every analysis walk -- this
        # used to be a second root-.gitignore parser that hid tracked files.
        self.gitignore = gitignore_filter(self.root_path, respect_gitignore)

    def should_filter(self, path: Path) -> bool:
        """Check if path should be filtered out.

        Args:
            path: Path to check

        Returns:
            True if path should be filtered (hidden)
        """
        return self.filter_reason(path) is not None

    def filter_reason(self, path: Path) -> Optional[str]:
        """Check if path should be filtered out, and why.

        Same checks as should_filter(), in the same order, but returns which
        one fired so callers (e.g. the directory-tree "N hidden" footer,
        BACK-1224) can tell a silent .gitignore exclusion from an explicit
        --exclude the user already knows about.

        Args:
            path: Path to check

        Returns:
            'gitignore', 'noise', or 'exclude' if filtered; None if it survives.
        """
        # Check what git ignores
        if self.gitignore is not None and self.gitignore.ignored(path, is_dir=path.is_dir()):
            return 'gitignore'

        # Check default noise patterns
        if self.include_defaults:
            if self._matches_noise_pattern(path):
                return 'noise'

        # Check custom exclude patterns
        if self._matches_exclude_pattern(path):
            return 'exclude'

        return None

    def _matches_noise_pattern(self, path: Path) -> bool:
        """Check if path matches default noise patterns.

        Args:
            path: Path to check

        Returns:
            True if matches noise pattern
        """
        name = path.name

        for pattern in DEFAULT_NOISE_PATTERNS:
            # Directory pattern
            if pattern.endswith('/'):
                if path.is_dir() and fnmatch.fnmatch(name, pattern.rstrip('/')):
                    return True
            # File/directory pattern
            elif fnmatch.fnmatch(name, pattern):
                return True

        return False

    def _matches_exclude_pattern(self, path: Path) -> bool:
        """Check if path matches custom exclude patterns.

        Args:
            path: Path to check

        Returns:
            True if matches exclude pattern
        """
        name = path.name

        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True

        return False


def should_filter_path(path: Path,
                       root_path: Optional[Path] = None,
                       respect_gitignore: bool = True,
                       exclude_patterns: Optional[List[str]] = None,
                       include_defaults: bool = True) -> bool:
    """Check if path should be filtered (convenience function).

    Args:
        path: Path to check
        root_path: Root directory (defaults to path's parent)
        respect_gitignore: Whether to use .gitignore rules
        exclude_patterns: Additional patterns to exclude
        include_defaults: Whether to include default noise patterns

    Returns:
        True if path should be filtered (hidden)

    Examples:
        >>> should_filter_path(Path('__pycache__'))
        True

        >>> should_filter_path(Path('src/app.py'))
        False

        >>> should_filter_path(Path('build/'), exclude_patterns=['build'])
        True
    """
    if root_path is None:
        root_path = path.parent if path.is_file() else path

    filter_obj = PathFilter(
        root_path=root_path,
        respect_gitignore=respect_gitignore,
        exclude_patterns=exclude_patterns,
        include_defaults=include_defaults
    )

    return filter_obj.should_filter(path)
