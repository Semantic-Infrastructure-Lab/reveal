"""One walk for import graphs: the graph's files and the basename index they resolve against.

imports:// (and deps://, architecture://) and depends:// each built the same two things with
their own copy of the walk, and the copies drifted: depends:// never gained REVEAL_IGNORE,
file-level --exclude or the declaration-only skip that imports:// did (BACK-1362, BACK-1495,
BACK-1467). generic.py kept three more walks for callers that pass no index. They all go
through the shared walker's resolution purpose now (BACK-1580).
"""

import hashlib
import stat
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ...registry import DECLARATION_ONLY_EXTENSIONS
from ...utils.path_utils import RESOLUTION, OnHidden, walk_with_causes
from ...reveal_types import PathFailure


class FileIndex(Dict[str, List[Path]]):
    """The ``basename -> paths`` index, plus the directories the walk met.

    An import can resolve to a directory (a namespace package, a Go or Rust module directory),
    and an empty one appears in no file path, so a key over files alone cannot see it
    (BACK-2085). A plain dict compares and iterates as before.
    """

    def __init__(self) -> None:
        super().__init__()
        self.directories: Set[Path] = set()


def discover_import_files(
    root: Path,
    is_candidate: Callable[[Path], bool],
    cap: Optional[int] = None,
    *,
    on_error: Optional[Callable[[OSError], None]] = None,
    on_hidden: Optional[OnHidden] = None,
) -> Tuple[List[Path], FileIndex, bool]:
    """Walk *root* once: ``(graph files, basename -> paths index, capped)``.

    The index holds every file an import could point to, including gitignored and
    ``--exclude``'d ones (a generated module or a vendored header is still a real target;
    BACK-491 keeps it extension-agnostic for ``.inc``/``.tcc`` includes). The graph files are
    those with no such cause that *is_candidate* accepts, minus declaration-only stubs, which
    would duplicate their module's edges (BACK-1467). Past *cap* graph files the walk stops
    and ``capped`` is True. *on_hidden* sees each entry left out of the graph by a skip
    cause, once (BACK-2065).
    """
    candidates: List[Path] = []
    index = FileIndex()
    for file_path, cause in walk_with_causes(root, RESOLUTION, on_error=on_error, on_hidden=on_hidden,
                                             on_dir=index.directories.add):
        index.setdefault(file_path.name, []).append(file_path)
        if cause is not None or file_path.suffix.lower() in DECLARATION_ONLY_EXTENSIONS:
            continue
        if not is_candidate(file_path):
            continue
        if cap is not None and len(candidates) >= cap:
            return candidates, index, True
        candidates.append(file_path)
    return candidates, index, False


def basename_index(roots: Iterable[Path], *,
                   on_error: Optional[Callable[[OSError], None]] = None) -> FileIndex:
    """The basename index for callers that hand an extractor only search paths."""
    index = FileIndex()
    for root in roots:
        if root.is_dir():
            found = discover_import_files(root, lambda _p: False, on_error=on_error)[1]
            for name, paths in found.items():
                index.setdefault(name, []).extend(paths)
            index.directories |= found.directories
    return index


def load_path_manifests(root: Path, pattern: str, *,
                        on_error: Optional[Callable[[OSError], None]] = None) -> List[Path]:
    """Every manifest matching *pattern* (RubyGems ``*.gemspec``) under *root*, found by the
    resolution walk: noise directories are never entered, and the skip is judged relative
    to *root* -- the old filter tested the absolute path, so a project under ``~/.cache``
    lost every gemspec."""
    return [path for path, _ in walk_with_causes(root, RESOLUTION, on_error=on_error)
            if fnmatch(path.name, pattern)]


def resolution_fingerprint(candidates: Iterable[Path], index: Dict[str, List[Path]],
                           excluded_root: Optional[Path] = None, *, root: Path,
                           traversal_failures: Sequence[PathFailure] = ()) -> Optional[str]:
    """Hash the scan root, source membership and the complete resolution target set (BACK-1755).
    The target set is every indexed file and, when *index* is a :class:`FileIndex`, every
    directory the walk descended, by path alone: a file's stat covers its content, and a
    directory's membership is covered by its files, but an empty directory is a target
    only its own path names (BACK-2085).

    Roles stay distinct: changing source eligibility still invalidates an unchanged
    target index. *root* is the scan root the graph resolves against: every file gets it
    as an extra search path, so two roots that walk the same files (``w`` holding only
    ``w/sub``) still resolve differently and must not share an entry (BACK-2082).
    Known traversal loss or stat failure disables caching. Reveal's own cache artifacts are
    excluded so writing this graph does not invalidate the next read.
    """
    if traversal_failures:
        return None
    try:
        excluded = excluded_root.resolve() if excluded_root is not None else None
        hasher = hashlib.sha256()
        hasher.update(b'root\x01' + str(root).encode('utf-8', 'replace') + b'\x04')
        groups = (('sources', set(candidates)), ('targets', {p for paths in index.values() for p in paths}))
        for role, paths in groups:
            hasher.update(role.encode('ascii'))
            for path in sorted(paths):
                if excluded is not None and path.resolve().is_relative_to(excluded):
                    continue
                info = path.stat()
                if not stat.S_ISREG(info.st_mode):
                    continue
                hasher.update(str(path).encode('utf-8', 'replace'))
                hasher.update(f"\x02{info.st_mtime_ns}\x03{info.st_size}\x04".encode('ascii'))
        hasher.update(b'directories')
        for directory in sorted(getattr(index, 'directories', ())):
            if excluded is not None and directory.resolve().is_relative_to(excluded):
                continue
            hasher.update(str(directory).encode('utf-8', 'replace') + b'\x04')
        return hasher.hexdigest()
    except (OSError, ValueError):
        return None
