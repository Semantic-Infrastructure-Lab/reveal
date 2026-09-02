"""Process-wide active --exclude scope for URI-form adapter walks (BACK-1257).

URI adapters each own a private ``os.walk`` -- 13+ of them across 19 files
(BACK-1223 tracks the consolidation). Only ``overview://`` and ``stats://`` ever
read a ``?exclude=`` query param (BACK-1042), so ``--exclude`` on any other
scheme was accepted by argparse, warned about on stderr, and otherwise
discarded. Threading an ``exclude_patterns`` kwarg through every walker is the
consolidation project, not a fix.

Instead the CLI publishes the active scope here once at dispatch time, and the
one directory-pruning predicate every walker already routes through
(``utils.path_utils.is_skippable_dir``, 30 call sites) consults it. Semantics
are delegated to ``cli.file_checker.should_skip_file`` so URI-form ``--exclude``
matches what the ``check`` subcommand has always done, including BACK-1249's
trailing-slash handling -- one matcher, not a second implementation that can
drift.

Scope is process-global and therefore must be cleared between dispatches in any
long-lived host (the MCP server, the test suite). Use ``exclusion_scope`` rather
than calling the setters directly wherever a scope has a natural extent.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional, Tuple

_ACTIVE_ROOT: Optional[Path] = None
_ACTIVE_PATTERNS: Tuple[str, ...] = ()


def set_active_exclusions(root: Path, patterns: List[str]) -> None:
    """Publish the --exclude scope for subsequent walks in this process."""
    global _ACTIVE_ROOT, _ACTIVE_PATTERNS
    _ACTIVE_ROOT = Path(root)
    _ACTIVE_PATTERNS = tuple(patterns or ())


def clear_active_exclusions() -> None:
    """Drop the active scope. Long-lived hosts must call this between requests."""
    global _ACTIVE_ROOT, _ACTIVE_PATTERNS
    _ACTIVE_ROOT, _ACTIVE_PATTERNS = None, ()


def active_exclusions() -> Tuple[Optional[Path], Tuple[str, ...]]:
    """Current (root, patterns). Patterns is empty when no scope is active."""
    return _ACTIVE_ROOT, _ACTIVE_PATTERNS


@contextmanager
def exclusion_scope(root: Optional[Path], patterns: Optional[List[str]]):
    """Apply an exclusion scope for the duration of the block, then restore.

    Restores the previous scope rather than clearing, so nesting is safe.
    """
    global _ACTIVE_ROOT, _ACTIVE_PATTERNS
    prev = (_ACTIVE_ROOT, _ACTIVE_PATTERNS)
    if patterns and root is not None:
        set_active_exclusions(root, patterns)
    try:
        yield
    finally:
        _ACTIVE_ROOT, _ACTIVE_PATTERNS = prev


def _relative_to_scope(path: Path) -> Optional[Path]:
    """Path relative to the active scope root, or None if outside/unavailable."""
    try:
        return Path(path).resolve().relative_to(Path(_ACTIVE_ROOT).resolve())
    except (ValueError, OSError):
        return None


def path_is_excluded(path: Path) -> bool:
    """True if the *file* at *path* matches an active --exclude pattern.

    Patterns are matched against the path relative to the scope root, which is
    the URI's own target directory -- the same relativization the ``check``
    subcommand uses, so ``--exclude 'app/*'`` means the same thing in both
    forms and means nothing when the target is already ``app/models``.
    """
    if not _ACTIVE_PATTERNS or _ACTIVE_ROOT is None:
        return False
    from ..cli.file_checker import should_skip_file  # deferred: cli imports utils
    rel = _relative_to_scope(path)
    if rel is None:
        return False
    return should_skip_file(rel, list(_ACTIVE_PATTERNS))


def dir_is_excluded(path: Path) -> bool:
    """True if the *directory* at *path* is entirely excluded, so a walk can
    prune it rather than visiting every file inside.

    should_skip_file only ever sees file paths, so it answers 'app/assets/*'
    for 'app/assets/lib.js' but not for the directory 'app/assets' itself --
    fnmatch needs something after the slash. Probing with a synthetic child is
    what makes 'prune this whole subtree' expressible, and it stays precise:
    'app/assets/*.js' does not match the probe, so that directory is correctly
    still walked and filtered file by file.
    """
    if not _ACTIVE_PATTERNS or _ACTIVE_ROOT is None:
        return False
    from ..cli.file_checker import should_skip_file
    rel = _relative_to_scope(path)
    if rel is None:
        return False
    patterns = list(_ACTIVE_PATTERNS)
    return (
        should_skip_file(rel, patterns)
        or should_skip_file(rel / '__reveal_probe__', patterns)
    )
