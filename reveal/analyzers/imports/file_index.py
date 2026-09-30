"""One walk for import graphs: the graph's files and the basename index they resolve against.

imports:// (and deps://, architecture://) and depends:// each built the same two things with
their own copy of the walk, and the copies drifted: depends:// never gained REVEAL_IGNORE,
file-level --exclude or the declaration-only skip that imports:// did (BACK-1362, BACK-1495,
BACK-1467). generic.py kept three more walks for callers that pass no index. They all go
through the shared walker's resolution purpose now (BACK-1580).
"""

from fnmatch import fnmatch
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from ...registry import DECLARATION_ONLY_EXTENSIONS
from ...utils.path_utils import RESOLUTION, walk_with_causes


def discover_import_files(
    root: Path,
    is_candidate: Callable[[Path], bool],
    cap: Optional[int] = None,
) -> Tuple[List[Path], Dict[str, List[Path]], bool]:
    """Walk *root* once: ``(graph files, basename -> paths index, capped)``.

    The index holds every file an import could point to, including gitignored and
    ``--exclude``'d ones (a generated module or a vendored header is still a real target;
    BACK-491 keeps it extension-agnostic for ``.inc``/``.tcc`` includes). The graph files are
    those with no such cause that *is_candidate* accepts, minus declaration-only stubs, which
    would duplicate their module's edges (BACK-1467). Past *cap* graph files the walk stops
    and ``capped`` is True.
    """
    candidates: List[Path] = []
    index: Dict[str, List[Path]] = {}
    for file_path, cause in walk_with_causes(root, RESOLUTION):
        index.setdefault(file_path.name, []).append(file_path)
        if cause is not None or file_path.suffix.lower() in DECLARATION_ONLY_EXTENSIONS:
            continue
        if not is_candidate(file_path):
            continue
        if cap is not None and len(candidates) >= cap:
            return candidates, index, True
        candidates.append(file_path)
    return candidates, index, False


def basename_index(roots: Iterable[Path]) -> Dict[str, List[Path]]:
    """The basename index for callers that hand an extractor only search paths."""
    index: Dict[str, List[Path]] = {}
    for root in roots:
        if root.is_dir():
            for name, paths in discover_import_files(root, lambda _p: False)[1].items():
                index.setdefault(name, []).extend(paths)
    return index


def load_path_manifests(root: Path, pattern: str) -> List[Path]:
    """Every manifest matching *pattern* (RubyGems ``*.gemspec``) under *root*, found by the
    resolution walk: noise directories are never entered, and the skip is judged relative
    to *root* -- the old filter tested the absolute path, so a project under ``~/.cache``
    lost every gemspec."""
    return [path for path, _ in walk_with_causes(root, RESOLUTION) if fnmatch(path.name, pattern)]
