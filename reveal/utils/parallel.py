"""Parallel file scanning utilities for high-throughput text search."""

from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from ..logging_setup import worker_bootstrap
from pathlib import Path
from typing import Any, Iterable, Sequence
from ..reveal_types import PathFailure
from .path_utils import failure_of, to_posix

logger = logging.getLogger(__name__)

# Files below this threshold scan sequentially; process-spawn overhead
# outweighs the parallelism benefit for tiny inputs.
_PARALLEL_THRESHOLD = 8

def pool_worker_count(default: int) -> int:
    """Worker processes for one of reveal's process pools; 1 means run serially.

    ``REVEAL_MAX_WORKERS`` overrides *default* everywhere reveal fans work out
    across processes (set it to 1 to force every serial path -- used by the test
    suite under pytest-xdist and for byte-identical verification; BACK-1004,
    BACK-1436). A non-integer value is ignored and *default* applies.
    """
    override = os.environ.get('REVEAL_MAX_WORKERS')
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass
    return max(1, default)


def submit_each(executor, fn, items: Iterable) -> list[Future]:
    """``executor.submit(fn, item)`` for every item: one Future per item, in order.

    A worker that dies while items are still being handed out breaks the pool, and
    every later ``submit`` raises BrokenProcessPool instead of returning a Future.
    Those items get a Future that already holds that error, so a caller's per-future
    handling treats them like the pending futures the dead worker failed: lost items,
    never a whole-run failure or a serial re-run of the culprit (BACK-1717, BACK-1718;
    seen only on a fast-dying worker, macOS under fork).
    """
    futures = []
    for item in items:
        try:
            futures.append(executor.submit(fn, item))
        except BrokenProcessPool as e:
            refused: Future = Future()
            refused.set_exception(e)
            futures.append(refused)
    return futures


def _scan_one(args: tuple) -> Path | PathFailure | None:
    """Return a matching path, a read failure, or a proven nonmatch.

    Must be module-level (not a closure or lambda) so multiprocessing can
    pickle it across process boundaries.

    Args:
        args: ``(path, needles)`` where *needles* is a tuple of lowercased
            ``bytes`` objects — one per search term.

    Returns:
        *path* if every needle was found, ``None`` for a nonmatch, or the
        candidate's ``PathFailure`` when its content could not be read or decoded.
    """
    path, needles = args
    try:
        with open(path, 'rb') as f:
            data = f.read()
        # Match the body reader's universal-newline view before rejecting candidates.
        data = data.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        data_lower = (data.lower() if data.isascii()
                      else data.decode('utf-8').lower().encode('utf-8'))
        return path if all(n in data_lower for n in needles) else None
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("grep_file_worker failed for %s: %s", path, e)
        return PathFailure(to_posix(path), failure_of(e).cause)


class GrepResult(list):
    """The matching paths (a plain list to every caller) plus ``lost``: the paths a dead
    pool worker kept from being scanned, which are not matches and not non-matches
    (BACK-1754). ``unreadable`` separately retains read and UTF-8 decoding failures.
    Neither kind of failure establishes that a file did not match."""

    lost: list[Path]
    unreadable: list[PathFailure]

    def __init__(self, matches=(), lost=(), *, unreadable=()):
        super().__init__(matches)
        self.lost = list(lost)
        self.unreadable = list(unreadable)


def _record_scan(result: GrepResult, path: Path, outcome: Path | PathFailure | None) -> None:
    if isinstance(outcome, PathFailure):
        result.unreadable.append(outcome)
    elif outcome is not None:
        result.append(path)


def _grep_sequential(paths: list[Path], needles: tuple[bytes, ...]) -> GrepResult:
    result = GrepResult()
    for path in paths:
        _record_scan(result, path, _scan_one((path, needles)))
    return result


def worker_lost_warning(lost: Iterable, consequence: str, base: Path | None = None) -> dict[str, Any] | None:
    """One ``worker_lost`` meta warning for files a dead pool worker kept from being
    processed (BACK-1753/1754); None when nothing was lost. *consequence* says what is
    missing from the result, so the same disclosure reads right for imports and for grep."""
    from .path_utils import to_posix, to_relative_display
    paths = sorted(str(p) for p in lost)
    if not paths:
        return None
    shown = [to_relative_display(p, base) if base else to_posix(p) for p in paths[:5]]
    more = f" and {len(paths) - len(shown)} more" if len(paths) > len(shown) else ''
    return {
        'type': 'worker_lost',
        'count': len(paths),
        'files': shown,
        'message': f"{len(paths)} file(s) not processed, a pool worker died -- {consequence}: "
                   f"{', '.join(shown)}{more}",
    }


def grep_files(
    paths: Sequence[Path] | Iterable[Path],
    terms: str | Iterable[str],
    *,
    workers: int = 8,
) -> GrepResult:
    """Return paths where all *terms* appear under Unicode lowercase matching.

    Uses parallel worker processes for large corpora. Falls back to sequential
    scanning for small inputs where process-spawn overhead exceeds the benefit.

    This is a **whole-file UTF-8 scan** — it does not distinguish frontmatter from
    body content.  Use it as a fast pre-filter; callers that need body-only
    matching should run a secondary check on the returned paths.

    Args:
        paths: File paths to scan.  Accepts any iterable; converted to a list
            internally.
        terms: One term (``str``) or multiple terms (iterable of ``str``).
            All terms must be present for a file to match (AND logic).
        workers: Maximum number of parallel worker processes.  Defaults to 8.

    Returns:
        Subset of *paths* where all terms were found, in input order. A file
        that could not be read, or was lost to a dead pool worker, is logged
        as a warning and left out. ``unreadable`` contains read/decode failures;
        ``lost`` contains paths lost to a dead worker (BACK-1754).

    Example::

        from reveal.utils.parallel import grep_files
        matches = grep_files(Path('/docs').rglob('*.md'), 'authentication')
        matches = grep_files(all_files, ['deploy', 'production'])
    """
    paths_list = list(paths)
    if not paths_list:
        return GrepResult()

    # Normalise terms → tuple of lowercased bytes (empty strings skipped).
    if isinstance(terms, str):
        terms = [terms]
    needles = tuple(t.lower().encode() for t in terms if t)

    if not needles:
        return GrepResult(paths_list)  # no constraints → everything matches

    # Sequential fast path for small inputs.
    if len(paths_list) < _PARALLEL_THRESHOLD:
        return _grep_sequential(paths_list, needles)

    # Parallel scan, one future per file, read in input order. A file lost to a
    # dead worker (which fails every pending future) gets the warning a file
    # _scan_one cannot read gets, and is not a match (BACK-1726).
    with ProcessPoolExecutor(
        max_workers=min(workers, len(paths_list)), initializer=worker_bootstrap,
    ) as pool:
        futures = submit_each(pool, _scan_one, [(p, needles) for p in paths_list])
        matches, lost = GrepResult(), []
        for path, future in zip(paths_list, futures):
            try:
                _record_scan(matches, path, future.result())
            except Exception as e:  # boundary-ok: broad-except -- future.result() re-raises whatever the worker raised; the lost file is reported by the warning below
                lost.append((path, e))
    if lost:
        logger.warning("grep_files: %d file(s) not scanned, a pool worker died (%s: %s): %s%s",
                       len(lost), type(lost[0][1]).__name__, lost[0][1],
                       ', '.join(str(p) for p, _ in lost[:5]), ' ...' if len(lost) > 5 else '')
    matches.lost = [p for p, _ in lost]
    return matches
