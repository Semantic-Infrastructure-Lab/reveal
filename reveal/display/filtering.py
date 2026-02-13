"""
File and directory filtering for reveal.

Provides smart filtering to hide build artifacts, test output, and other
noise from directory listings. Supports .gitignore patterns and custom
exclusion rules.

Features:
---------
1. .gitignore parsing and pattern matching
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


class GitignoreParser:
    """Parse and match .gitignore patterns.

    Implements a simplified version of gitignore pattern matching:
    - Supports glob patterns (*, ?, [...])
    - Supports directory patterns (trailing /)
    - Supports negation (leading !)
    - Respects .gitignore location (patterns relative to that directory)
    """

    def __init__(self, gitignore_path: Path):
        """Initialize parser with .gitignore file path.

        Args:
            gitignore_path: Path to .gitignore file
        """
        self.gitignore_dir = gitignore_path.parent
        self.patterns: List[Dict[str, Any]] = []
        self._parse(gitignore_path)

    def _parse(self, gitignore_path: Path):
        """Parse .gitignore file and extract patterns.

        Args:
            gitignore_path: Path to .gitignore file
        """
        try:
            with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue

                    # Handle negation patterns
                    negate = False
                    if line.startswith('!'):
                        negate = True
                        line = line[1:]

                    # Store pattern with metadata
                    self.patterns.append({
                        'pattern': line,
                        'negate': negate,
                        'dir_only': line.endswith('/')
                    })
        except (IOError, OSError):
            # If we can't read .gitignore, just continue without it
            pass

    def matches(self, path: Path) -> bool:
        """Check if path matches any gitignore pattern.

        Args:
            path: Path to check (can be file or directory)

        Returns:
            True if path should be ignored
        """
        # Make path relative to gitignore directory
        try:
            relative_path = path.relative_to(self.gitignore_dir)
        except ValueError:
            # Path is not under gitignore directory
            return False

        # Check against patterns
        ignored = False
        for pattern_info in self.patterns:
            pattern = pattern_info['pattern'].rstrip('/')

            # Check if pattern matches
            if self._match_pattern(str(relative_path), pattern, path.is_dir()):
                if pattern_info['negate']:
                    ignored = False  # Negation patterns override
                else:
                    ignored = True

        return ignored

    def _match_pattern(self, path_str: str, pattern: str, is_dir: bool) -> bool:
        """Check if path matches gitignore pattern.

        Args:
            path_str: String representation of path
            pattern: Gitignore pattern
            is_dir: Whether path is a directory

        Returns:
            True if pattern matches
        """
        # Match against full path
        if fnmatch.fnmatch(path_str, pattern):
            return True

        # Match against filename only
        if '/' not in pattern:
            basename = os.path.basename(path_str)
            if fnmatch.fnmatch(basename, pattern):
                return True

        # Match directory patterns
        if is_dir:
            if fnmatch.fnmatch(path_str + '/', pattern + '/'):
                return True

        return False


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

        # Load .gitignore if present
        self.gitignore_parser = None
        if respect_gitignore:
            gitignore_path = self.root_path / '.gitignore'
            if gitignore_path.exists():
                self.gitignore_parser = GitignoreParser(gitignore_path)

    def should_filter(self, path: Path) -> bool:
        """Check if path should be filtered out.

        Args:
            path: Path to check

        Returns:
            True if path should be filtered (hidden)
        """
        # Check .gitignore
        if self.gitignore_parser and self.gitignore_parser.matches(path):
            return True

        # Check default noise patterns
        if self.include_defaults:
            if self._matches_noise_pattern(path):
                return True

        # Check custom exclude patterns
        if self._matches_exclude_pattern(path):
            return True

        return False

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
