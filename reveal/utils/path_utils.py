"""Path utilities for directory traversal and file discovery.

Consolidates common patterns for searching up directory trees.
"""

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Callable, Dict, Optional, List, Set, Union

from ..defaults import SKIP_DIRECTORIES
from ..registry import language_for_extension, LANGUAGE_DISPLAY_NAMES

_SKIP_DIRS: frozenset = SKIP_DIRECTORIES


def to_posix(path: Union[str, PurePath]) -> str:
    """Serialize a path with forward slashes on every OS.

    Use this — never ``str(path)`` — whenever a path is written to output
    (JSON, display strings), used as a dict key, or compared as a string.
    ``str(Path)`` emits backslashes on Windows, which makes reveal's output
    non-portable and breaks cross-OS string comparisons (e.g. an agent or a
    test comparing against ``'tests/foo.py'`` fails on a Windows-produced
    ``'tests\\foo.py'``). Mirrors the ad-hoc ``.replace('\\\\', '/')`` idiom
    that was scattered across the codebase, in one canonical place.

    A path *relative* to a root serializes cleanly; pass the ``relative_to()``
    result. Absolute Windows paths keep their drive (``C:/foo/bar``).
    """
    if isinstance(path, PurePath):
        return path.as_posix()
    return str(path).replace('\\', '/')


# Directories that must never be treated as a project root or scanned as if they
# were a project — the filesystem anchor, the OS temp dir, the user's home, and
# the classic shallow POSIX system dirs. Single source of truth: three separate
# hardcoded POSIX-only sets used to live in path_utils/I002/calls-index and each
# silently no-opped on Windows (temp = ``C:\\...\\Temp``, anchor = ``C:\\``) and
# macOS (temp = ``/var/folders/...``; ``/tmp`` -> ``/private/tmp`` under realpath).
_STATIC_UNSAFE_ROOTS = (
    '/', '/tmp', '/var', '/var/tmp', '/usr', '/usr/local',
    '/home', '/opt', '/etc', '/root', '/mnt',
)


def _unsafe_scan_roots() -> frozenset:
    """Realpath'd set of unsafe roots, derived fresh (temp/home can be patched).

    Not cached: ``tempfile.gettempdir()`` and ``Path.home()`` are read at call
    time so tests can monkeypatch them to simulate other platforms, and the
    cost (realpath of ~13 paths) is trivial next to the walks it guards.
    """
    roots = set()
    for base in (tempfile.gettempdir(), str(Path.home())):
        try:
            roots.add(os.path.realpath(base))
        except (OSError, RuntimeError, ValueError):
            pass
    for p in _STATIC_UNSAFE_ROOTS:
        roots.add(os.path.realpath(p))
    return frozenset(roots)


def is_unsafe_scan_root(path: Union[str, PurePath, None]) -> bool:
    """True if *path* is a filesystem/system/home root, platform-aware.

    Used to refuse treating a path as a project boundary (``find_project_root``)
    or scanning it as if it were a project (I002 circular-dep scan, calls
    widen-the-path hint) — guards against parsing thousands of unrelated files
    under ``/tmp``, ``$HOME``, or a drive root. Recognizes:

    - the filesystem *anchor* (``/`` on POSIX, ``C:\\`` on Windows);
    - the OS temp dir (``tempfile.gettempdir()``) and the user home dir, both
      realpath-normalized so macOS symlinks (``/tmp`` -> ``/private/tmp``) match;
    - the classic shallow POSIX system dirs (harmless no-ops on Windows).

    Accepts a ``str`` or ``PurePath``; ``None`` is not a root (False).
    """
    if path is None:
        return False
    real = os.path.realpath(str(path))
    if real == os.path.realpath(Path(real).anchor):
        return True
    return real in _unsafe_scan_roots()


def _non_python_display_name(ext: str) -> str:
    """Human-readable language label for *ext*, or '' if Python/unknown.

    Derived from the registry's single-sourced language_for_extension()
    instead of a hand-maintained extension table (BACK-431 Issue B) — the
    prior _NON_PYTHON_LANG_EXTS dict was itself created to fix BACK-403,
    which was caused by exactly this kind of table falling out of sync.
    """
    lang = language_for_extension(ext)
    if not lang or lang == 'python':
        return ''
    return LANGUAGE_DISPLAY_NAMES.get(lang, lang.capitalize())


def detect_non_python_language(path: Path) -> str:
    """Return dominant non-Python source language for path, or '' if Python/unknown.

    Walks the directory counting source files by extension and returns the most
    common non-Python language found.  Used to emit actionable "not yet supported"
    notes instead of silent empty results.
    """
    if path.is_file():
        return _non_python_display_name(path.suffix.lower())
    counts: Dict[str, int] = {}
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            lang = _non_python_display_name(Path(fname).suffix.lower())
            if lang:
                counts[lang] = counts.get(lang, 0) + 1
    return max(counts, key=counts.__getitem__) if counts else ''


@dataclass(frozen=True)
class LanguageCoverage:
    """How much of a directory a language-limited command can actually analyze.

    Commands like ``surface`` and ``contracts`` only understand a fixed set of
    languages (Python + TypeScript). When pointed at a tree whose dominant
    language is *not* in that set, they used to silently build their whole
    report from whatever handful of supported-language files happened to share
    the directory — e.g. ``surface`` on Kong (a 1,300-file Lua gateway with 15
    stray ``.py`` tooling scripts) confidently reported the surface of those 15
    scripts as if it were the project's. This census lets a command detect that
    case and warn (BACK-518).

    Attributes:
        total_code_files: Count of all code files in the tree (registry
            ``get_code_extensions()``; data/markup/config excluded so the ratio
            is meaningful).
        analyzed_files: Code files in a language the command supports.
        dominant_language: Display name of the tree's single most common code
            language ('' when there are no code files).
        dominant_count: File count of ``dominant_language``.
        dominant_supported: Whether the dominant language is one the command can
            analyze.
    """

    total_code_files: int
    analyzed_files: int
    dominant_language: str
    dominant_count: int
    dominant_supported: bool

    @property
    def should_warn(self) -> bool:
        """True when the results don't represent the codebase.

        Threshold-free by design: warn only when the tree's dominant language is
        one the command *cannot* analyze **and** the supported-language files it
        did analyze are outnumbered by that single dominant language. A repo
        whose majority language is supported never warns (so a genuine Python
        project with a few stray ``.lua`` files is silent — no false positives);
        only a repo built mostly in an unsupported language does.
        """
        return (
            self.total_code_files > 0
            and not self.dominant_supported
            and self.analyzed_files < self.dominant_count
        )

    def warning_line(self, command: str) -> str:
        """One-line coverage warning for the text renderer (empty if no warn)."""
        if not self.should_warn:
            return ''
        return (
            f"⚠ Analyzed {self.analyzed_files:,} of {self.total_code_files:,} "
            f"source files. Dominant language '{self.dominant_language}' "
            f"({self.dominant_count:,} files) is not supported by `{command}` "
            f"— the rest of the tree was not analyzed."
        )


def assess_language_coverage(path: Path, supported_languages: Set[str]) -> LanguageCoverage:
    """Census *path*'s code files by language and compare against a command's
    supported set (registry language keys, e.g. ``{'python', 'typescript', 'tsx'}``).

    Counts only extensions in the registry's ``get_code_extensions()`` so
    markdown/JSON/YAML/config never dilute the denominator. See
    :class:`LanguageCoverage` for how the result is used.
    """
    from ..registry import get_code_extensions

    code_exts = get_code_extensions()
    counts: Dict[str, int] = {}  # registry language key -> file count

    def _tally(ext: str) -> None:
        ext = ext.lower()
        if ext not in code_exts:
            return
        lang = language_for_extension(ext)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1

    if path.is_file():
        _tally(path.suffix)
    else:
        for root, dirs, filenames in os.walk(str(path)):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
            for fname in filenames:
                _tally(Path(fname).suffix)

    total = sum(counts.values())
    analyzed = sum(c for lang, c in counts.items() if lang in supported_languages)

    if counts:
        dominant_key = max(counts, key=counts.__getitem__)
        dominant_count = counts[dominant_key]
        dominant_supported = dominant_key in supported_languages
        dominant_display = LANGUAGE_DISPLAY_NAMES.get(
            dominant_key, dominant_key.capitalize())
    else:
        dominant_count, dominant_supported, dominant_display = 0, True, ''

    return LanguageCoverage(
        total_code_files=total,
        analyzed_files=analyzed,
        dominant_language=dominant_display,
        dominant_count=dominant_count,
        dominant_supported=dominant_supported,
    )

def find_file_in_parents(
    start: Path,
    filename: str,
    max_depth: int = 20
) -> Optional[Path]:
    """Find a file by searching up the directory tree.

    Common pattern for finding config files like .reveal.yaml, pyproject.toml, etc.

    Args:
        start: Starting path (file or directory)
        filename: Name of file to find
        max_depth: Maximum directories to traverse up (default: 20)

    Returns:
        Path to the file if found, None otherwise

    Example:
        # Find nearest .reveal.yaml
        config = find_file_in_parents(Path("src/module/file.py"), ".reveal.yaml")
    """
    current = start if start.is_dir() else start.parent
    depth = 0

    while current != current.parent and depth < max_depth:
        target = current / filename
        if target.exists():
            return target
        current = current.parent
        depth += 1

    return None


def search_parents(
    start: Path,
    condition: Callable[[Path], bool],
    max_depth: int = 20
) -> Optional[Path]:
    """Search up directory tree until condition is met.

    Generic parent search for flexible conditions.

    Args:
        start: Starting path (file or directory)
        condition: Function that takes a Path and returns True if match found
        max_depth: Maximum directories to traverse up (default: 20)

    Returns:
        First parent path that satisfies condition, None if not found

    Example:
        # Find nearest parent named 'docs'
        docs = search_parents(
            Path("docs/guides/intro.md"),
            lambda p: p.name == 'docs'
        )

        # Find parent containing 'pyproject.toml'
        project_root = search_parents(
            Path("src/module.py"),
            lambda p: (p / 'pyproject.toml').exists()
        )
    """
    current = start if start.is_dir() else start.parent
    depth = 0

    while current != current.parent and depth < max_depth:
        if condition(current):
            return current
        current = current.parent
        depth += 1

    return None


def find_project_root(
    start: Path,
    markers: Optional[List[str]] = None
) -> Optional[Path]:
    """Find the project root by looking for common project markers.

    Args:
        start: Starting path
        markers: List of filenames that indicate project root
                 Defaults to common markers like pyproject.toml, .git, etc.

    Returns:
        Project root path if found, None otherwise

    Example:
        root = find_project_root(Path("src/deep/module.py"))
        # Returns path containing pyproject.toml, .git, etc.
    """
    if markers is None:
        markers = [
            'pyproject.toml',
            'setup.py',
            'setup.cfg',
            '.git',
            'Cargo.toml',
            'package.json',
            'go.mod',
        ]

    def has_marker(p: Path) -> bool:
        return any((p / marker).exists() for marker in markers)

    result = search_parents(start, has_marker)
    return None if is_unsafe_scan_root(result) else result


def get_relative_to_root(
    path: Path,
    root_markers: Optional[List[str]] = None
) -> Path:
    """Get path relative to project root.

    Useful for display and logging - shows "src/module.py" instead of
    "/home/user/projects/myproject/src/module.py".

    Args:
        path: Absolute or relative path
        root_markers: Project root markers (see find_project_root)

    Returns:
        Path relative to project root, or original path if root not found
    """
    path = Path(path).resolve()
    root = find_project_root(path, root_markers)

    if root:
        try:
            return path.relative_to(root)
        except ValueError:
            pass

    return path
