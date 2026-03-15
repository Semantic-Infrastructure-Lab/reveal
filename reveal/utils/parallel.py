"""Parallel file scanning utilities for high-throughput text search."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Iterable, Sequence

# Files below this threshold scan sequentially; process-spawn overhead
# outweighs the parallelism benefit for tiny inputs.
_PARALLEL_THRESHOLD = 8

# Optional stringzilla SIMD accelerator (pip install stringzilla).
# When present, provides faster substring search on warm-cache workloads.
try:
    import stringzilla as _sz  # noqa: F401
    _HAS_STRINGZILLA = True
except ImportError:
    _HAS_STRINGZILLA = False


def _scan_one(args: tuple) -> Path | None:
    """Worker: return path if all needles appear in file bytes, else None.

    Must be module-level (not a closure or lambda) so multiprocessing can
    pickle it across process boundaries.

    Args:
        args: ``(path, needles)`` where *needles* is a tuple of lowercased
            ``bytes`` objects — one per search term.

    Returns:
        *path* if every needle was found, ``None`` otherwise.
    """
    path, needles = args
    try:
        with open(path, 'rb') as f:
            data = f.read()
        if _HAS_STRINGZILLA:
            import stringzilla as sz
            data_lower = sz.Str(data).lower()
            return path if all(
                next(sz.find_all(data_lower, n), None) is not None
                for n in needles
            ) else None
        else:
            data_lower = data.lower()
            return path if all(n in data_lower for n in needles) else None
    except Exception:
        return None


def grep_files(
    paths: Sequence[Path] | Iterable[Path],
    terms: str | Iterable[str],
    *,
    workers: int = 8,
) -> list[Path]:
    """Return paths where all *terms* appear (case-insensitive byte scan).

    Uses parallel worker processes for large corpora. Falls back to sequential
    scanning for small inputs where process-spawn overhead exceeds the benefit.

    This is a **whole-file scan** — it does not distinguish frontmatter from
    body content.  Use it as a fast pre-filter; callers that need body-only
    matching should run a secondary check on the returned paths.

    Args:
        paths: File paths to scan.  Accepts any iterable; converted to a list
            internally.
        terms: One term (``str``) or multiple terms (iterable of ``str``).
            All terms must be present for a file to match (AND logic).
        workers: Maximum number of parallel worker processes.  Defaults to 8.

    Returns:
        Subset of *paths* where all terms were found, in input order.

    Example::

        from reveal.utils.parallel import grep_files
        matches = grep_files(Path('/docs').rglob('*.md'), 'authentication')
        matches = grep_files(all_files, ['deploy', 'production'])
    """
    paths_list = list(paths)
    if not paths_list:
        return []

    # Normalise terms → tuple of lowercased bytes (empty strings skipped).
    if isinstance(terms, str):
        terms = [terms]
    needles = tuple(t.lower().encode() for t in terms if t)

    if not needles:
        return paths_list  # no constraints → everything matches

    # Sequential fast path for small inputs.
    if len(paths_list) < _PARALLEL_THRESHOLD:
        return [p for p in paths_list if _scan_one((p, needles)) is not None]

    # Parallel scan — ProcessPoolExecutor preserves result order via .map().
    args = [(p, needles) for p in paths_list]
    with ProcessPoolExecutor(max_workers=min(workers, len(paths_list))) as pool:
        results = pool.map(_scan_one, args)
    return [p for p in results if p is not None]
