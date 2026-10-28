"""Resolved import graph cache, shared by analysis consumers."""
import hashlib
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ...core import disk_cache
from ...reveal_types import PathFailure
from ...utils.request_cache import in_host_request, register_request_cache, register_validated_cache
from .base import get_all_extensions
from .file_index import resolution_fingerprint
from .types import ImportAnalysis

# Disk-cache namespace for this adapter's resolved import graph (BACK-834).
# Mirrors rules/imports/I002.py's own import-graph disk cache (_tree_fingerprint
# / _IMPORT_GRAPH_NAMESPACE) — same fingerprint recipe (path + mtime_ns + size
# per source and indexed target file), but this adapter builds a graph rooted at whatever
# `path` argument the caller gave it (imports://<path>, pack --architecture,
# pack --focus), not I002's resolved *project* root, so it gets its own
# namespace rather than sharing I002's cache entries.
_ADAPTER_IMPORT_GRAPH_NAMESPACE = "adapter_import_graph"

def _candidate_set_fingerprint(candidates: List[Path],
                               file_index: Optional[Dict[str, List[Path]]] = None, *, root: Path,
                               traversal_failures: Sequence[PathFailure] = ()) -> Optional[str]:
    """Shared root/source/target fingerprint; preserve the private source-only call shape."""
    return resolution_fingerprint(candidates, {} if file_index is None else file_index, excluded_root=disk_cache.cache_root(),
                                  root=root, traversal_failures=traversal_failures)


def _graph_cache_key(candidates: List[Path], file_index: Dict[str, List[Path]], root: Path,
                     traversal_failures: Sequence[PathFailure], cap: Optional[int],
                     parsed: Optional[frozenset] = None) -> Optional[str]:
    """The whole-graph cache key: the resolution fingerprint of the scan root, plus the build's
    identity (the file cap the walk ran under, the extensions it parsed: every supported one unless
    a caller narrowed them, ``parse_extensions``). None: not cacheable."""
    fingerprint = _candidate_set_fingerprint(candidates, file_index, root=root,
                                             traversal_failures=traversal_failures)
    if fingerprint is None:
        return None
    exts = parsed if parsed is not None else get_all_extensions()
    identity = f'{fingerprint}|cap={cap}|exts={",".join(sorted(exts))}'
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


# BACK-1054 (the BACK-2109 pattern): inside a host request (MCP, reveal.api) the resolved graph of
# a scan root is kept across requests while the tree stamp of that root is unchanged
# (register_validated_cache), so a repeated per-file ?importers= answers without a rebuild when
# the disk cache is off or cold. Keyed by the root alone, as resolved; the value holds at most
# _GRAPH_MEMO_VARIANTS builds, each under the cache key it was built for (which already carries
# the source set, targets and file cap) and the --exclude/gitignore scope the walk ran under,
# which the tree stamp cannot see. A build with a gitignore-off scope lives for its request only
# (the BACK-2118 rule). &scope, &tests and &lazy are applied at presentation: never a variant.
_GRAPH_MEMO: 'OrderedDict[str, List[Tuple[Tuple[str, Any, bool], ImportAnalysis]]]' = OrderedDict()
_GRAPH_MEMO_ROOTS = 4
_GRAPH_MEMO_VARIANTS = 2


def _evict_graph_root(root: str) -> None:
    _GRAPH_MEMO.pop(root, None)


def _drop_request_local_graphs() -> None:
    for root, builds in tuple(_GRAPH_MEMO.items()):
        kept = [build for build in builds if build[0][2]]
        if kept:
            _GRAPH_MEMO[root] = kept
        else:
            del _GRAPH_MEMO[root]


register_request_cache(__name__ + '.graph_request_local', _drop_request_local_graphs)
register_validated_cache(__name__ + '.graph', _GRAPH_MEMO, _evict_graph_root)


def _recall_graph(root: Path, variant: Tuple[str, Any, bool]) -> Optional[ImportAnalysis]:
    """The build this host request may reuse for *root* and *key*; None outside a request."""
    if not in_host_request():
        return None
    for built_for, analysis in _GRAPH_MEMO.get(str(root), []):
        if built_for == variant:
            _GRAPH_MEMO.move_to_end(str(root))
            return analysis
    return None


def _remember_graph(root: Path, variant: Tuple[str, Any, bool], analysis: ImportAnalysis) -> None:
    """Keep a cacheable build for the rest of this host request and the next ones (validated)."""
    if not in_host_request() or not analysis.cacheable:
        return
    builds = [build for build in _GRAPH_MEMO.get(str(root), []) if build[0] != variant]
    _GRAPH_MEMO[str(root)] = [*builds, (variant, analysis)][-_GRAPH_MEMO_VARIANTS:]
    _GRAPH_MEMO.move_to_end(str(root))
    if len(_GRAPH_MEMO) > _GRAPH_MEMO_ROOTS:
        _GRAPH_MEMO.popitem(last=False)


def _cached_graph(root: Path, key: Optional[str], variant: Tuple[str, Any, bool]) -> Optional[ImportAnalysis]:
    """The stored build for *key*: the host-request memo first, then the disk layer (a disk hit
    joins the memo). A record from before the cascade (no ``resolution``) is a miss."""
    if key is None:
        return None
    cached = _recall_graph(root, variant)
    if cached is None:
        cached = disk_cache.get(_ADAPTER_IMPORT_GRAPH_NAMESPACE, key)
    if not isinstance(cached, ImportAnalysis) or cached.resolution is None:
        return None
    _remember_graph(root, variant, cached)
    return cached


