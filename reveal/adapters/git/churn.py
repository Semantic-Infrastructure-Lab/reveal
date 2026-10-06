"""Per-file commit-touch counts for hotspot churn scoring (BACK-483, BACK-624)."""

import hashlib
from datetime import datetime
from typing import Any, Dict, Optional, cast, TYPE_CHECKING

from ...core import disk_cache

# One entry per (repo, HEAD commit, since, no_merges) -- low cardinality like
# I002's import-graph cache (one entry per scan root), not per-file like the
# structure cache, so the default 64-entry prune cap is correct as-is.
_CHURN_CACHE_NAMESPACE = "churn"

if TYPE_CHECKING:
    import pygit2


def _churn_fingerprint(
    repo: 'pygit2.Repository',
    start_oid: Any,
    since: Optional[str],
    no_merges: bool,
) -> Optional[str]:
    """Disk-cache key for a full-history churn walk, or None to skip caching.

    Bound to (repo workdir, resolved start commit oid, since, no_merges) —
    deliberately NOT scope_paths, since the walk's expensive step
    (diff_to_tree per commit) runs identically regardless of scope; only
    which deltas get tallied differs. Caching the unscoped walk once means
    every differently-scoped caller on the same commit reuses one entry
    instead of fragmenting the cache per scope_paths set. A HEAD move (new
    oid) is a cache miss, never a stale hit.
    """
    try:
        workdir = repo.workdir or str(repo.path)
    except Exception:  # boundary-ok: silent-except -- None means "walk uncached", the same answer
        return None
    hasher = hashlib.sha256()
    hasher.update(str(workdir).encode("utf-8", "replace"))
    hasher.update(b"\x00")
    hasher.update(str(start_oid).encode("ascii"))
    hasher.update(b"\x00")
    hasher.update((since or "").encode("utf-8", "replace"))
    hasher.update(b"\x00")
    hasher.update(str(int(no_merges)).encode("ascii"))
    return hasher.hexdigest()


def get_churn_counts(
    repo: 'pygit2.Repository',
    ref: str,
    scope_paths: Optional[set],
    since: Optional[str] = None,
    no_merges: bool = False,
) -> Dict[str, int]:
    """Tally commit touches per file with a single repo-wide walk.

    One walk over history, tallying which paths each commit's diff touches
    (against its first parent), rather than one history walk per file —
    O(total historical file-touches) instead of O(files x commits). See
    internal-docs/design/BACK483_CHURN_COMPLEXITY_HOTSPOTS_2026-07-07.md.

    The walk result is disk-cached (BACK-624) keyed on the resolved HEAD
    commit, since, and no_merges — repo-history walks on a real repo (one
    diff_to_tree per historical commit) dominate `reveal hotspots` wall time
    by 85-94% on an unchanged tree, dwarfing everything else `stats://`
    computes. scope_paths is applied as a post-filter on the cached full
    result rather than during the walk, so it doesn't fragment the cache.

    Args:
        repo: Open pygit2 repository
        ref: Starting ref (e.g. 'HEAD')
        scope_paths: Repo-relative paths to tally, or None for all paths.
        since: Optional ISO date string — commits before this are skipped
        no_merges: If True, skip merge commits (multiple parents) entirely

    Returns:
        Dict mapping repo-relative path -> commit touch count (only paths
        with at least one touch; unlisted paths have zero touches)
    """
    import pygit2
    from collections import defaultdict

    since_ts: Optional[float] = None
    if since:
        since_ts = datetime.fromisoformat(since).timestamp()

    obj = repo.revparse_single(ref)
    while hasattr(obj, 'peel') and not isinstance(obj, pygit2.Commit):
        obj = obj.peel(pygit2.Commit)  # type: ignore[assignment]
    start = cast('pygit2.Commit', obj)

    fingerprint = _churn_fingerprint(repo, start.id, since, no_merges)
    if fingerprint is not None:
        cached = disk_cache.get(_CHURN_CACHE_NAMESPACE, fingerprint)
        if cached is not None:
            if scope_paths is None:
                return cached
            return {p: c for p, c in cached.items() if p in scope_paths}

    counts: Dict[str, int] = defaultdict(int)
    for commit in repo.walk(start.id, pygit2.GIT_SORT_TIME):  # type: ignore[arg-type]
        if no_merges and len(commit.parents) > 1:
            continue
        if since_ts is not None and commit.commit_time < since_ts:
            continue

        if commit.parents:
            diff = commit.parents[0].tree.diff_to_tree(commit.tree)
        else:
            diff = commit.tree.diff_to_tree()

        for delta in diff.deltas:
            path = delta.new_file.path or delta.old_file.path
            counts[path] += 1

    result = dict(counts)
    if fingerprint is not None:
        disk_cache.put(_CHURN_CACHE_NAMESPACE, fingerprint, result)

    if scope_paths is None:
        return result
    return {p: c for p, c in result.items() if p in scope_paths}
