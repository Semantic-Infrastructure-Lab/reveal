"""Process-wide active --exclude scope for adapter walks, URI and subcommand forms (BACK-1257).

URI adapters each own a private ``os.walk`` -- 13+ of them across 19 files
(BACK-1223 tracks the consolidation). Only ``overview://`` and ``stats://`` ever
read a ``?exclude=`` query param (BACK-1042), so ``--exclude`` on any other
scheme was accepted by argparse, warned about on stderr, and otherwise
discarded. Threading an ``exclude_patterns`` kwarg through every walker is the
consolidation project, not a fix.

Instead the CLI publishes the active scope here once at dispatch time (``dispatch_scope``,
from handle_uri, the subcommand seam, BACK-1539, and a bare directory path, BACK-1581), and
the shared walker's predicate (``utils.path_utils.walk_filter``, which every walk over the
user's target goes through since BACK-1223) consults it, per walk purpose: an evidence walk
does not. Patterns are gitignore syntax, one matcher (``utils.gitignore.PatternSet``,
BACK-1576).

Scope is process-global and therefore must be cleared between dispatches in any
long-lived host (the MCP server, the test suite). Use ``exclusion_scope`` rather
than calling the setters directly wherever a scope has a natural extent.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Callable, List, Optional, Tuple

_ACTIVE_ROOT: Optional[Path] = None
_ACTIVE_PATTERNS: Tuple[str, ...] = ()
# Set when a walk actually checks a path against the active scope. The flag ledger
# (BACK-1514) counts --exclude as used only then: publishing a scope for an adapter that
# never walks (sqlite://, json://) applied nothing.
_CONSULTED = False


def set_active_exclusions(root: Path, patterns: List[str]) -> None:
    """Publish the --exclude scope for subsequent walks in this process."""
    global _ACTIVE_ROOT, _ACTIVE_PATTERNS, _CONSULTED
    _ACTIVE_ROOT = Path(root)
    _ACTIVE_PATTERNS = tuple(patterns or ())
    _CONSULTED = False


def clear_active_exclusions() -> None:
    """Drop the active scope. Long-lived hosts must call this between requests."""
    global _ACTIVE_ROOT, _ACTIVE_PATTERNS, _CONSULTED
    _ACTIVE_ROOT, _ACTIVE_PATTERNS = None, ()
    _CONSULTED = False


def exclusions_consulted() -> bool:
    """True once a walk has checked a path against the active scope since it was set."""
    return _CONSULTED


def active_exclusions() -> Tuple[Optional[Path], Tuple[str, ...]]:
    """Current (root, patterns). Patterns is empty when no scope is active."""
    return _ACTIVE_ROOT, _ACTIVE_PATTERNS


def dispatch_scope(target: str, exclude: Optional[List[str]]) -> Tuple[Optional[Path], List[str]]:
    """The walk scope one dispatch publishes for ``target``: (walk root, patterns).

    Patterns are ``--exclude`` plus the REVEAL_IGNORE / config ``ignore:`` patterns
    (BACK-1266), discovered relative to the walk root the way ``check``'s walker does. The
    root is None when ``target`` is not an existing path: an empty target (env://, help://)
    means the command takes no path at all, not "the current directory". Every CLI entry
    point computes its scope here -- URI dispatch and the subcommands (BACK-1539) -- so
    REVEAL_IGNORE cannot again reach one form and not the other.
    """
    from ..config import RevealConfig

    exclude_values = list(exclude or [])
    path = Path(target) if target else None
    walk_root = None
    if path is not None and path.exists():
        walk_root = path if path.is_dir() else path.parent
    ignore_values = RevealConfig.get(start_path=walk_root).ignore_patterns()
    return walk_root, exclude_values + [p for p in ignore_values if p not in exclude_values]


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


def scope_matcher(root: Path) -> Optional[Callable[[str, bool], bool]]:
    """The active scope as a matcher on posix paths relative to *root*, a walk's root, which
    is resolved once rather than every path the walk visits (BACK-1581). None when no scope
    is active. The walk root may sit under the scope root, or above it (depends:// walks
    from the project root while the scope is the target it was given); a path outside the
    scope matches nothing, but the check still counts as consulted.
    """
    if not _ACTIVE_PATTERNS or _ACTIVE_ROOT is None:
        return None
    from .gitignore import pattern_set
    compiled = pattern_set(_ACTIVE_PATTERNS)
    walk_root: Optional[Path] = None
    scope_root: Optional[Path] = None
    try:
        walk_root, scope_root = Path(root).resolve(), Path(_ACTIVE_ROOT).resolve()
    except OSError:
        pass  # neither resolves: nothing can be matched against the scope
    to_scope = _to_scope_relative(walk_root, scope_root)

    def excluded(rel: str, is_dir: bool) -> bool:
        global _CONSULTED
        _CONSULTED = True
        scoped = to_scope(rel)
        if not scoped:
            return False
        return compiled.covers_dir(scoped) if is_dir else compiled.matches(scoped)

    return excluded


def _to_scope_relative(walk_root: Optional[Path],
                       scope_root: Optional[Path]) -> Callable[[str], Optional[str]]:
    """Map a path relative to *walk_root* to one relative to *scope_root* (None outside it)."""
    if walk_root is None or scope_root is None:
        return lambda rel: None
    try:
        prefix = walk_root.relative_to(scope_root).as_posix()
    except ValueError:
        prefix = None
    if prefix is not None:  # the walk is inside the scope
        head = '' if prefix == '.' else prefix + '/'
        return lambda rel: head + rel
    try:
        below = scope_root.relative_to(walk_root).as_posix() + '/'
    except ValueError:  # disjoint
        return lambda rel: None
    return lambda rel: rel[len(below):] if rel.startswith(below) else None


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
    global _CONSULTED
    if not _ACTIVE_PATTERNS or _ACTIVE_ROOT is None:
        return False
    _CONSULTED = True
    from ..cli.file_checker import should_skip_file  # deferred: cli imports utils
    rel = _relative_to_scope(path)
    if rel is None:
        return False
    return should_skip_file(rel, list(_ACTIVE_PATTERNS))


def dir_is_excluded(path: Path) -> bool:
    """True if the *directory* at *path* is entirely excluded, so a walk can
    prune it rather than visiting every file inside.

    ``PatternSet.covers_dir`` answers it: the directory matches, or every child would
    ('app/assets/*'), and it stays precise -- 'app/assets/*.js' covers no directory, so
    that one is still walked and filtered file by file.
    """
    global _CONSULTED
    if not _ACTIVE_PATTERNS or _ACTIVE_ROOT is None:
        return False
    _CONSULTED = True
    from .gitignore import pattern_set
    from .path_utils import to_posix
    rel = _relative_to_scope(path)
    if rel is None:
        return False
    return pattern_set(_ACTIVE_PATTERNS).covers_dir(to_posix(rel))
