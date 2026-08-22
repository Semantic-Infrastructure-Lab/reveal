"""Correctness tests for ImportsAdapter's whole-graph disk cache (BACK-834).

Per-file import extraction was already cached (BACK-625/BACK-535's language
disk caches), but the graph *assembly* step in `ImportsAdapter._build_graph`
(the O(files) dependency-resolution walk `imports://`, `pack --architecture`'s
fan-in, and `pack --focus`'s graph-relevance ranking all pay on every call)
was not. I002's circular-dependency rule already had its own disk cache for
this exact computation (`_tree_fingerprint` / `_IMPORT_GRAPH_NAMESPACE`) but
it was private to that rule module. This mirrors the same recipe for the
adapter's own graph, in its own namespace (the adapter's scan root is whatever
path the caller passed, not I002's resolved *project* root, so entries must
not be shared between the two).

Like the per-file caches, this must be a pure performance optimization: a
cache hit must be indistinguishable from a fresh build, and any edit/add/
delete under the scanned tree must invalidate it.
"""

import os

import pytest

from reveal.adapters.imports import ImportsAdapter, _ADAPTER_IMPORT_GRAPH_NAMESPACE, _candidate_set_fingerprint
from reveal.analyzers.imports.base import get_all_extensions
from reveal.core import disk_cache
from reveal.registry import get_code_extensions

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = pytest.mark.component


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the disk cache at a throwaway dir and start every test cold."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)


def _write_tree(root):
    (root / "a.py").write_text("X = 1\n")
    (root / "b.py").write_text("import a\n")


def _touch_newer(path):
    """Force a distinct mtime_ns (coarse-resolution filesystems can otherwise
    leave a rewritten file with an unchanged mtime_ns within the same test)."""
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))


def _cache_entry_for(root):
    """The one cache entry a plain (non-structure, no-callback) build of *root*
    should produce, or None if nothing was cached."""
    adapter = ImportsAdapter(resource=str(root))
    candidates, _ = adapter._discover_candidate_files(
        adapter._target_path, frozenset(get_all_extensions()), get_code_extensions(),
    )
    fp = _candidate_set_fingerprint(candidates)
    return disk_cache.get(_ADAPTER_IMPORT_GRAPH_NAMESPACE, fp) if fp else None


def test_second_build_served_from_disk(tmp_path, monkeypatch):
    _write_tree(tmp_path)
    adapter = ImportsAdapter(resource=str(tmp_path))
    adapter._build_graph(adapter._target_path)
    fresh_fan_in = {f.name: len(deps) for f, deps in adapter._graph.reverse_deps.items()}

    adapter2 = ImportsAdapter(resource=str(tmp_path))

    def _boom(*a, **k):
        raise AssertionError("disk cache miss: _process_extracted_files was re-run")

    monkeypatch.setattr(adapter2, "_process_extracted_files", _boom)
    adapter2._build_graph(adapter2._target_path)

    cached_fan_in = {f.name: len(deps) for f, deps in adapter2._graph.reverse_deps.items()}
    assert cached_fan_in == fresh_fan_in


def test_cache_hit_restores_all_needed_state(tmp_path):
    _write_tree(tmp_path)
    adapter = ImportsAdapter(resource=str(tmp_path))
    adapter._build_graph(adapter._target_path)
    scanned_before = {f.name for f in adapter._scanned_files}
    unsupported_before = dict(adapter._unsupported_extensions)
    symbols_before = {f.name for f in adapter._symbols_by_file}

    adapter2 = ImportsAdapter(resource=str(tmp_path))
    adapter2._build_graph(adapter2._target_path)
    assert {f.name for f in adapter2._scanned_files} == scanned_before
    assert dict(adapter2._unsupported_extensions) == unsupported_before
    # get_metadata() / unused-import detection depend on _symbols_by_file.
    assert {f.name for f in adapter2._symbols_by_file} == symbols_before


def test_adding_a_file_invalidates_cache(tmp_path):
    _write_tree(tmp_path)
    adapter = ImportsAdapter(resource=str(tmp_path))
    adapter._build_graph(adapter._target_path)
    a_path = next(f for f in adapter._graph.reverse_deps if f.name == "a.py")
    assert len(adapter._graph.reverse_deps[a_path]) == 1

    (tmp_path / "c.py").write_text("import a\n")

    adapter2 = ImportsAdapter(resource=str(tmp_path))
    adapter2._build_graph(adapter2._target_path)
    a_path2 = next(f for f in adapter2._graph.reverse_deps if f.name == "a.py")
    assert len(adapter2._graph.reverse_deps[a_path2]) == 2


def test_editing_a_file_invalidates_cache(tmp_path):
    _write_tree(tmp_path)
    adapter = ImportsAdapter(resource=str(tmp_path))
    adapter._build_graph(adapter._target_path)

    b_path = tmp_path / "b.py"
    b_path.write_text("import os\n")
    _touch_newer(b_path)

    adapter2 = ImportsAdapter(resource=str(tmp_path))
    adapter2._build_graph(adapter2._target_path)
    # a.py now has zero incoming edges — it won't appear as a reverse_deps key
    # at all (add_dependency only ever adds keys with >=1 edge).
    assert not any(f.name == "a.py" for f in adapter2._graph.reverse_deps)


def test_collect_structures_bypasses_cache(tmp_path):
    """collect_structures=True must never read or write the cache — self._structures
    isn't part of the cached payload, so a hit would silently drop it."""
    _write_tree(tmp_path)
    adapter = ImportsAdapter(resource=str(tmp_path))
    adapter._build_graph(adapter._target_path, collect_structures=True)
    assert _cache_entry_for(tmp_path) is None


def test_on_file_processed_callback_bypasses_cache(tmp_path):
    """A live per-file progress callback must always fire — a cache hit would
    silently skip it, breaking `reveal architecture`'s progress reporting."""
    _write_tree(tmp_path)
    calls = []
    adapter = ImportsAdapter(resource=str(tmp_path))
    adapter._build_graph(adapter._target_path, on_file_processed=calls.append)
    assert len(calls) == 2  # a.py, b.py

    adapter2 = ImportsAdapter(resource=str(tmp_path))
    calls2 = []
    adapter2._build_graph(adapter2._target_path, on_file_processed=calls2.append)
    assert len(calls2) == 2  # still fires — never served from cache


def test_kill_switch_writes_nothing(tmp_path, monkeypatch):
    _write_tree(tmp_path)
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    adapter = ImportsAdapter(resource=str(tmp_path))
    adapter._build_graph(adapter._target_path)
    assert _cache_entry_for(tmp_path) is None
