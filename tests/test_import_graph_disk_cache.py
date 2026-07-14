"""Correctness tests for the persistent import-graph disk cache (BACK-536 opt 2).

The cache must be a pure performance optimization: a graph served from disk
must be byte-for-byte the graph a fresh scan would build, and ANY change to the
source tree must invalidate it. These tests pin that invariant, plus the
fail-open / kill-switch behavior of the underlying disk-cache primitive.
"""

import pickle

import pytest

from reveal.core import disk_cache
from reveal.rules.imports import I002 as i002_mod


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the disk cache at a throwaway dir and start every test cold."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)
    i002_mod._graph_cache.clear()
    yield
    i002_mod._graph_cache.clear()


def _project(root):
    """A tiny 3-module Python project with a real A->B->C->A cycle."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (root / "a.py").write_text("from b import beta\n\ndef alpha():\n    return beta()\n")
    (root / "b.py").write_text("from c import gamma\n\ndef beta():\n    return gamma()\n")
    (root / "c.py").write_text("from a import alpha\n\ndef gamma():\n    return alpha()\n")
    return root


# --------------------------------------------------------------------------- #
# disk_cache primitive
# --------------------------------------------------------------------------- #

def test_put_get_roundtrip():
    disk_cache.put("ns", "k1", {"x": [1, 2, 3]})
    assert disk_cache.get("ns", "k1") == {"x": [1, 2, 3]}


def test_get_miss_returns_none():
    assert disk_cache.get("ns", "absent") is None


def test_kill_switch_disables_read_and_write(monkeypatch):
    disk_cache.put("ns", "k", "value")           # written while enabled
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    assert disk_cache.get("ns", "k") is None      # read disabled
    disk_cache.put("ns", "k2", "value2")          # write disabled
    monkeypatch.setenv("REVEAL_DISK_CACHE", "1")
    assert disk_cache.get("ns", "k2") is None      # nothing was written


def test_corrupt_entry_is_a_miss_not_a_crash():
    disk_cache.put("ns", "k", {"real": True})
    entry = disk_cache._entry_path("ns", "k")
    entry.write_bytes(b"\x00\x01 not a pickle \xff")
    assert disk_cache.get("ns", "k") is None       # fails open


def test_default_prune_cap_evicts_past_64_entries():
    """Regression guard for BACK-535: a per-file cache needs a bigger cap.

    The default (no max_entries override) must stay at the historical 64 —
    I002's whole-tree cache relies on this. A per-file cache (BACK-535,
    treesitter.py) passes its own much larger max_entries to avoid thrashing.
    """
    for i in range(70):
        disk_cache.put("prune_default_ns", f"k{i}", i)
    ns_dir = disk_cache._namespace_dir("prune_default_ns")
    assert len(list(ns_dir.glob("*.pkl"))) == 64


def test_max_entries_override_avoids_thrashing():
    for i in range(70):
        disk_cache.put("prune_override_ns", f"k{i}", i, max_entries=1000)
    ns_dir = disk_cache._namespace_dir("prune_override_ns")
    assert len(list(ns_dir.glob("*.pkl"))) == 70
    # every entry should still be a hit — nothing evicted
    for i in range(70):
        assert disk_cache.get("prune_override_ns", f"k{i}") == i


def test_version_keyed_path_isolates_reveal_versions(monkeypatch):
    disk_cache.put("ns", "k", "old")
    monkeypatch.setattr(disk_cache, "__version__", "999.999.999")
    assert disk_cache.get("ns", "k") is None        # different version dir → miss


# --------------------------------------------------------------------------- #
# I002 integration — the correctness-critical part
# --------------------------------------------------------------------------- #

def test_second_build_served_from_disk(tmp_path, monkeypatch):
    root = _project(tmp_path / "proj")
    rule = i002_mod.I002()

    fresh = rule._build_import_graph(root)
    fresh_groups = fresh.find_cycle_groups()
    assert fresh_groups, "fixture should contain a cycle"

    # Second invocation in a *new* process is simulated by clearing the
    # in-process cache. If disk caching works, the graph never re-scans.
    i002_mod._graph_cache.clear()

    def _boom(*a, **k):
        raise AssertionError("disk cache miss: _collect_raw_imports was re-run")

    monkeypatch.setattr(rule, "_collect_raw_imports", _boom)
    cached = rule._build_import_graph(root)

    assert cached.find_cycle_groups() == fresh_groups
    assert cached == fresh          # dataclass equality: files/deps/reverse_deps


def test_disk_graph_equals_fresh_scan(tmp_path):
    """A from-disk graph must be indistinguishable from a from-scan graph."""
    root = _project(tmp_path / "proj")
    rule = i002_mod.I002()

    scanned = rule._build_import_graph(root)          # populates disk
    i002_mod._graph_cache.clear()

    # Read straight from disk via the same fingerprint and compare.
    fp = i002_mod._tree_fingerprint(root)
    from_disk = disk_cache.get(i002_mod._IMPORT_GRAPH_NAMESPACE, fp)
    assert from_disk is not None
    assert from_disk == scanned
    assert from_disk.find_cycle_groups() == scanned.find_cycle_groups()


def test_edit_invalidates_cache(tmp_path, monkeypatch):
    root = _project(tmp_path / "proj")
    rule = i002_mod.I002()
    rule._build_import_graph(root)                    # populate
    fp_before = i002_mod._tree_fingerprint(root)

    # Break the cycle: c.py no longer imports a. mtime + size change.
    (root / "c.py").write_text("def gamma():\n    return 42\n")
    fp_after = i002_mod._tree_fingerprint(root)
    assert fp_after != fp_before, "edited tree must fingerprint differently"

    i002_mod._graph_cache.clear()
    rebuilt = rule._build_import_graph(root)
    assert rebuilt.find_cycle_groups() == [], "rebuilt graph must reflect the edit"


def test_added_file_invalidates_fingerprint(tmp_path):
    root = _project(tmp_path / "proj")
    fp_before = i002_mod._tree_fingerprint(root)
    (root / "d.py").write_text("x = 1\n")
    assert i002_mod._tree_fingerprint(root) != fp_before


def test_deleted_file_invalidates_fingerprint(tmp_path):
    root = _project(tmp_path / "proj")
    fp_before = i002_mod._tree_fingerprint(root)
    (root / "c.py").unlink()
    assert i002_mod._tree_fingerprint(root) != fp_before


def test_unchanged_tree_fingerprint_is_stable(tmp_path):
    root = _project(tmp_path / "proj")
    assert i002_mod._tree_fingerprint(root) == i002_mod._tree_fingerprint(root)


def test_fingerprint_none_over_ceiling(tmp_path, monkeypatch):
    root = _project(tmp_path / "proj")
    monkeypatch.setenv("REVEAL_I002_MAX_FILES", "1")   # 3 .py files > 1
    assert i002_mod._tree_fingerprint(root) is None


def test_kill_switch_writes_nothing(tmp_path, monkeypatch):
    root = _project(tmp_path / "proj")
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    rule = i002_mod.I002()
    rule._build_import_graph(root)
    fp = i002_mod._tree_fingerprint(root)
    assert disk_cache.get(i002_mod._IMPORT_GRAPH_NAMESPACE, fp) is None


def test_fingerprint_matches_pass_a_file_selection(tmp_path):
    """The fingerprint must digest exactly the files Pass A parses — no drift.

    A file with an unsupported extension must not affect the fingerprint;
    adding a supported-extension file must.
    """
    root = _project(tmp_path / "proj")
    fp = i002_mod._tree_fingerprint(root)
    (root / "notes.txt").write_text("not source\n")     # unsupported ext
    assert i002_mod._tree_fingerprint(root) == fp
    (root / "e.py").write_text("y = 2\n")                # supported ext
    assert i002_mod._tree_fingerprint(root) != fp


def test_graph_is_picklable():
    """Regression guard: the cached artifact must survive a pickle roundtrip."""
    from reveal.analyzers.imports import ImportGraph
    from pathlib import Path
    g = ImportGraph()
    g.add_dependency(Path("a.py"), Path("b.py"))
    assert pickle.loads(pickle.dumps(g)) == g
