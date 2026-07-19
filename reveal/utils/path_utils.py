"""Path utilities for directory traversal and file discovery.

Consolidates common patterns for searching up directory trees.
"""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Callable, Dict, Optional, List, Set, Union

from ..defaults import SKIP_DIRECTORIES, AMBIGUOUS_SKIP_DIRECTORIES
from ..registry import _is_cpp_header_content, language_for_extension, LANGUAGE_DISPLAY_NAMES


def _language_for_path(fpath: Path) -> Optional[str]:
    """Like registry.language_for_extension, but content-sniffs `.h` for C++
    (BACK-421/630) instead of always resolving it to C."""
    ext = fpath.suffix.lower()
    if ext == '.h' and _is_cpp_header_content(str(fpath)):
        return 'cpp'
    return language_for_extension(ext)

_SKIP_DIRS: frozenset = SKIP_DIRECTORIES
_AMBIGUOUS_SKIP_DIRS: frozenset = AMBIGUOUS_SKIP_DIRECTORIES


def is_skippable_dir(parent: Path, name: str) -> bool:
    """True if directory *name* under *parent* is a build/vendor/cache dir a
    walk should exclude — the SKIP_DIRECTORIES membership check, made
    context-sensitive for ambiguous names.

    Callers combine this with their own hidden-dir (``startswith('.')``)
    filtering as before; this function does not itself treat dot-dirs
    specially, so it's a drop-in replacement for ``name in SKIP_DIRECTORIES``
    without changing hidden-dir behavior at any call site.

    Unconditional names (SKIP_DIRECTORIES) always skip. Ambiguous names
    (AMBIGUOUS_SKIP_DIRECTORIES — ``env``/``venv``/``build``/``dist``) only
    skip when the directory has no source-code file directly at its own top
    level — a real virtualenv or build-output directory never does (a venv's
    Python files live many `site-packages/pkg/` levels down; setuptools'
    `build/` holds `lib/`/`bdist.*/` subdirs, not source at the top). A
    same-named source package does (BACK-552: Elasticsearch's
    ``org.elasticsearch.env``, 297 `.java` files directly inside, was
    silently excluded from every walk by bare-name match alone before this
    check existed). Not recursive — deliberately cheap, one `os.scandir` per
    ambiguous name encountered, not a sub-walk.
    """
    if name in _SKIP_DIRS:
        return True
    if name not in _AMBIGUOUS_SKIP_DIRS:
        return False
    from ..registry import get_code_extensions
    code_exts = get_code_extensions()
    try:
        with os.scandir(parent / name) as entries:
            for entry in entries:
                if entry.is_file() and Path(entry.name).suffix.lower() in code_exts:
                    return False
    except OSError:
        return True
    return True


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


def _non_python_display_name(fpath: Path) -> str:
    """Human-readable language label for *fpath*, or '' if Python/unknown.

    Derived from the registry's single-sourced language_for_extension()
    instead of a hand-maintained extension table (BACK-431 Issue B) — the
    prior _NON_PYTHON_LANG_EXTS dict was itself created to fix BACK-403,
    which was caused by exactly this kind of table falling out of sync.
    Content-sniffs `.h` for C++ rather than always resolving it to C
    (BACK-421/630).
    """
    lang = _language_for_path(fpath)
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
        return _non_python_display_name(path)
    counts: Dict[str, int] = {}
    for root, dirs, filenames in os.walk(str(path)):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
        for fname in filenames:
            lang = _non_python_display_name(Path(os.path.join(root, fname)))
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

    def _tally(fpath: Path) -> None:
        ext = fpath.suffix.lower()
        if ext not in code_exts:
            return
        lang = _language_for_path(fpath)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1

    if path.is_file():
        _tally(path)
    else:
        for root, dirs, filenames in os.walk(str(path)):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith('.')]
            for fname in filenames:
                _tally(Path(os.path.join(root, fname)))

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


def search_parents_within_ceiling(
    start: Path,
    condition: Callable[[Path], bool],
    max_depth: int = 20
) -> Optional[Path]:
    """Like ``search_parents``, but the climb is bounded by a *hard ceiling*
    that can never itself be promoted to a match (BACK-525 layer 2).

    The ceiling is: a filesystem/mount boundary (mirrors git's own default,
    ``GIT_DISCOVERY_ACROSS_FILESYSTEM``) and ``is_unsafe_scan_root`` (the
    filesystem anchor, ``$HOME``, OS temp dir, classic POSIX system dirs).
    Splitting "how far may I climb" from "is this a project unit" (the
    condition) is what makes promoting a distant ancestor ``.git`` into a
    scan root structurally impossible — the climb simply stops before it can
    reach an unrelated ancestor repo (BACK-515's failure mode) instead of
    relying on the caller to reject the result after the fact.
    """
    current = start if start.is_dir() else start.parent
    depth = 0
    try:
        start_dev: Optional[int] = os.stat(current).st_dev
    except OSError:
        start_dev = None

    while current != current.parent and depth < max_depth:
        if is_unsafe_scan_root(current):
            return None
        if start_dev is not None:
            try:
                if os.stat(current).st_dev != start_dev:
                    return None
            except OSError:
                return None
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


# ---------------------------------------------------------------------------
# Unified project-root resolution (BACK-612)
#
# One ceiling-bounded, tiered resolver, shared by depends://, config
# discovery, and the I002/D005 rules — replacing five hand-rolled climbers
# that had diverged on their marker sets, on the unsafe-root guard (config
# even kept a stale hand-copy of it), and on whether an explicit
# `.reveal.yaml root:true` was honored at all. Design of record:
# internal-docs/design/SCAN_ROOT_RESOLUTION_2026-07-09.md.
# ---------------------------------------------------------------------------

# BACK-525: a package/build marker is *positive project-unit evidence*; a bare
# VCS root (`.git`) is only a climb ceiling. Keeping them in separate tiers is
# what stops a distant ancestor `.git` from being promoted to a scan root when
# nothing closer exists. Extended for the BACK-515 languages (Scala/Dart/Zig/
# GDScript) whose missing marker reproduced as a full-monorepo-scan "hang".
_PACKAGE_ROOT_MARKERS = [
    'pyproject.toml', 'setup.py', 'setup.cfg', 'Cargo.toml',
    'package.json', 'go.mod',
    'settings.gradle', 'settings.gradle.kts',  # Java/Kotlin (Gradle)
    'pom.xml',  # Java (Maven)
    'Package.swift',  # Swift (SPM)
    'composer.json',  # PHP
    'build.sbt', 'build.sc',  # Scala (sbt / Mill)  — BACK-515
    'pubspec.yaml',  # Dart (pub)                    — BACK-515
    'build.zig',  # Zig                              — BACK-515
    'project.godot',  # GDScript (Godot)             — BACK-515
]

_VCS_ROOT_MARKERS = ['.git']

# BACK-698: explicit lerna/pnpm/npm workspace declarations. Distinct from
# _PACKAGE_ROOT_MARKERS because these are monorepo-membership signals, not
# bare project-unit evidence — a directory holding one of these is safe to
# promote *past* a closer individual package.json.
_JS_WORKSPACE_ROOT_FILES = ['lerna.json', 'pnpm-workspace.yaml']


def reveal_yaml_is_root(config_file: Path) -> bool:
    """True if the ``.reveal.yaml`` at *config_file* declares ``root: true``.

    Standalone (no ``RevealConfig`` dependency) so ``path_utils`` stays free of
    a ``config`` import and ``config.py`` can delegate to it without creating a
    ``path_utils → config → path_utils`` cycle (BACK-612). This is the single
    definition of what ``root: true`` means across reveal.
    """
    try:
        import yaml
    except ImportError:
        return False
    try:
        with open(config_file, encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        return bool(data.get('root'))
    except (OSError, getattr(yaml, 'YAMLError', Exception)):
        return False


def _has_reveal_root_marker(directory: Path) -> bool:
    """Tier 0: *directory* holds a ``.reveal.yaml`` declaring ``root: true`` —
    an explicit, language-agnostic root declaration that beats every *inferred*
    package/VCS marker. The consistent way to pin a root the heuristics can't
    reach: a C/C++ tree whose only build file is a ``Makefile``/``CMakeLists``
    (no package marker), or any project checked out under a larger repo, where
    the VCS tier would otherwise promote a distant ancestor ``.git``.
    """
    config_file = directory / '.reveal.yaml'
    return config_file.exists() and reveal_yaml_is_root(config_file)


def _has_package_marker(directory: Path) -> bool:
    """Tier 1: *directory* holds positive project-unit evidence — a package/
    build marker, never a bare VCS root. Extends the literal-filename check
    with two repo-specific-name globs (``*.sln`` C# solutions, ``*.rockspec``
    Lua/LuaRocks) that can't be fixed literals.

    A directory that is itself an importable Python package (``__init__.py``
    present) is never a project root even if it holds a marker: absolute
    self-package imports (``from homeassistant.core import X``) resolve to the
    package's *parent*, so promoting the package dir to the scan root leaves
    every such import unresolved — a silent fan-in collapse (measured 9% recall
    on Home Assistant, whose ``homeassistant/setup.py`` was mis-read as a root
    marker). The real root is above the top of the package chain — keep climbing.
    """
    if (directory / '__init__.py').exists():
        return False
    if any((directory / marker).exists() for marker in _PACKAGE_ROOT_MARKERS):
        return True
    return any(directory.glob('*.sln')) or any(directory.glob('*.rockspec'))


def _has_js_workspace_marker(directory: Path) -> bool:
    """BACK-698: *directory* explicitly declares itself a JS/TS monorepo
    workspace root — ``lerna.json``, ``pnpm-workspace.yaml``, or a
    ``package.json`` with a ``"workspaces"`` field (npm/yarn workspaces).

    Deliberately narrower than ``_has_package_marker``: a bare ``package.json``
    is NOT enough here (that would promote any distant ancestor package to
    root for every single-package JS/TS repo). Only an explicit workspace
    declaration lets tier 1 climb past the nearest ``package.json`` — see
    ``resolve_project_root``.
    """
    if any((directory / marker).exists() for marker in _JS_WORKSPACE_ROOT_FILES):
        return True
    pkg = directory / 'package.json'
    if not pkg.exists():
        return False
    try:
        with open(pkg, encoding='utf-8') as f:
            data = json.load(f)
        return isinstance(data, dict) and 'workspaces' in data
    except (OSError, ValueError):
        return False


def _has_vcs_marker(directory: Path) -> bool:
    """Tier 2: *directory* is a VCS root — consulted only when no package
    marker exists anywhere in the climb."""
    return any((directory / marker).exists() for marker in _VCS_ROOT_MARKERS)


def _python_package_top(target_path: Path) -> Optional[Path]:
    """Tier 3 (opt-in): the top of the *contiguous* ``__init__.py`` chain
    rooted at the target's own directory — the Python-package fallback the
    I002 circular-import rule needs (BACK-338). Returns ``None`` when the
    target directory is not itself a package, so a stray far-ancestor
    ``__init__.py`` can never hijack the root of an unrelated tree.
    """
    start = target_path if target_path.is_dir() else target_path.parent
    if not (start / '__init__.py').exists():
        return None
    current = start
    for _ in range(20):
        parent = current.parent
        if parent == current or not (parent / '__init__.py').exists():
            return current
        current = parent
    return current


def resolve_project_root(
    target_path: Path,
    *,
    root_override: Optional[Path] = None,
    honor_reveal_root: bool = True,
    use_package_markers: bool = True,
    use_vcs: bool = True,
    python_init_chain: bool = False,
) -> Optional[Path]:
    """Resolve *target_path*'s project root, first applicable tier wins:

    * **-1** ``root_override`` — a validated, per-invocation pin (depends://'s
      ``?root=``); callers with no such lever pass ``None``.
    * **0** ``.reveal.yaml root:true`` (``honor_reveal_root``).
    * **1** nearest package/build marker (``use_package_markers``) — for a JS/TS
      match specifically, climbs further to an ancestor explicitly declaring
      lerna/pnpm/npm workspace membership if one exists (BACK-698), since that
      ancestor is the true scan root for a monorepo package.
    * **2** nearest VCS root (``use_vcs``).
    * **3** contiguous ``__init__.py`` chain top (``python_init_chain``).

    Tiers 0–2 climb via :func:`search_parents_within_ceiling`, so the walk stops
    at a filesystem/``$HOME``/system boundary it can never promote to a root.
    Returns ``None`` if nothing matches before the ceiling — the caller decides
    its own fallback (an inferred subtree, ``start_path``, etc.).
    """
    if root_override is not None:
        return root_override
    if honor_reveal_root:
        reveal_root = search_parents_within_ceiling(target_path, _has_reveal_root_marker)
        if reveal_root is not None:
            return reveal_root
    if use_package_markers:
        package_root = search_parents_within_ceiling(target_path, _has_package_marker)
        if package_root is not None:
            if (package_root / 'package.json').exists():
                workspace_root = search_parents_within_ceiling(
                    package_root.parent, _has_js_workspace_marker
                )
                if workspace_root is not None:
                    return workspace_root
            return package_root
    if use_vcs:
        vcs_root = search_parents_within_ceiling(target_path, _has_vcs_marker)
        if vcs_root is not None:
            return vcs_root
    if python_init_chain:
        return _python_package_top(target_path)
    return None


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
