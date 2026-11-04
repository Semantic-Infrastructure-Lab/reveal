"""Correctness tests for the persistent import-graph disk cache (BACK-536 opt 2).

The cache must be a pure performance optimization: a graph served from disk
must be byte-for-byte the graph a fresh scan would build, and ANY change to the
source tree must invalidate it. These tests pin that invariant, plus the
fail-open / kill-switch behavior of the underlying disk-cache primitive.
"""

import pickle

import pytest

from reveal.analyzers.imports import service as import_service
from reveal.analyzers.imports.build_cache import _ADAPTER_IMPORT_GRAPH_NAMESPACE as GRAPH_NAMESPACE
from reveal.core import disk_cache
from reveal.rules.imports import I002 as i002_mod

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP/network
pytestmark = [pytest.mark.component, pytest.mark.disk_cache]


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the disk cache at a throwaway dir and start every test cold."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
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


def test_prune_skips_stat_when_under_cap(monkeypatch):
    """Regression guard: BACK-1152's O(N)-per-put cliff.

    ``_prune`` must not pay for a ``stat``-per-entry sort while the namespace
    is under its cap — that per-call cost is what turned a 934-file test into
    a 10+ minute hang against a real ~13k-entry cache namespace. Spy on
    ``Path.stat`` to prove the cheap ``os.scandir`` count path is what runs.
    """
    from pathlib import Path

    calls = []
    real_stat = Path.stat

    def _spy_stat(self, *a, **kw):
        calls.append(self)
        return real_stat(self, *a, **kw)

    monkeypatch.setattr(Path, "stat", _spy_stat)
    for i in range(40):
        disk_cache.put("prune_under_cap_ns", f"k{i}", i)  # default cap is 64
    ns_dir = disk_cache._namespace_dir("prune_under_cap_ns")
    assert len(list(ns_dir.glob("*.pkl"))) == 40
    # mkdir(exist_ok=True)'s own is_dir() check stats the namespace dir itself
    # (harmless, once per put) — what must never happen is a stat per *entry*.
    entry_stats = [p for p in calls if p.suffix == ".pkl"]
    assert entry_stats == []


def test_prune_evicts_exactly_at_cap_boundary():
    """The eviction path (over cap) still keeps exactly ``max_entries``."""
    for i in range(65):
        disk_cache.put("prune_boundary_ns", f"k{i}", i, max_entries=64)
    ns_dir = disk_cache._namespace_dir("prune_boundary_ns")
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
# I002 integration — the correctness-critical part. Since BACK-2156 I002 builds
# through the analysis service, so the disk layer is the service's
# (``adapter_import_graph``), keyed on the source and resolution-target stats.
# --------------------------------------------------------------------------- #

@pytest.fixture
def builds(monkeypatch):
    """Uncached service builds (extraction and resolution), i.e. disk-cache misses."""
    calls = []
    real = import_service._extract_and_resolve

    def counting(scope, *args, **kwargs):
        calls.append(scope.root)
        return real(scope, *args, **kwargs)

    monkeypatch.setattr(import_service, '_extract_and_resolve', counting)
    return calls


def _fresh_process_graph(root):
    """The graph a new process would build: the in-process memo forgotten, the disk kept."""
    i002_mod._graph_cache.clear()
    return i002_mod.I002()._build_import_graph(root)


def test_second_build_served_from_disk(tmp_path, builds):
    root = _project(tmp_path / "proj")
    fresh = i002_mod.I002()._build_import_graph(root)
    fresh_groups = fresh.find_cycle_groups()
    assert fresh_groups, "fixture should contain a cycle"
    cached = _fresh_process_graph(root)
    assert len(builds) == 1, "disk cache miss: the graph was extracted again"
    assert cached.find_cycle_groups() == fresh_groups
    assert cached == fresh          # dataclass equality: files/deps/reverse_deps and disclosures


def test_disk_graph_is_the_one_imports_reads(tmp_path, builds):
    """One owner, one entry: imports:// over the same root is served by the build I002 stored."""
    from reveal.adapters.imports import ImportsAdapter
    root = _project(tmp_path / "proj")
    scanned = i002_mod.I002()._build_import_graph(root)
    adapter = ImportsAdapter(resource=str(root))
    adapter._build_graph(root)
    assert len(builds) == 1
    assert adapter.analysis.graph.dependencies == scanned.dependencies
    assert adapter.analysis.graph.find_cycle_groups() == scanned.find_cycle_groups()


def test_edit_invalidates_cache(tmp_path, builds):
    root = _project(tmp_path / "proj")
    i002_mod.I002()._build_import_graph(root)                    # populate
    # Break the cycle: c.py no longer imports a. mtime + size change.
    (root / "c.py").write_text("def gamma():\n    return 42\n")
    rebuilt = _fresh_process_graph(root)
    assert len(builds) == 2
    assert rebuilt.find_cycle_groups() == [], "rebuilt graph must reflect the edit"


@pytest.mark.parametrize('change', ['add_source', 'delete_source', 'add_target', 'none'])
def test_tree_changes_invalidate_and_an_unchanged_tree_hits(tmp_path, builds, change):
    """Added and deleted sources and a non-source file (a resolution target) each miss;
    an unchanged tree is served from disk (the negative control)."""
    root = _project(tmp_path / "proj")
    i002_mod.I002()._build_import_graph(root)
    if change == 'add_source':
        (root / "d.py").write_text("x = 1\n")
    elif change == 'delete_source':
        (root / "c.py").unlink()
    elif change == 'add_target':
        (root / "notes.txt").write_text("not source\n")
    _fresh_process_graph(root)
    assert len(builds) == (1 if change == 'none' else 2)


def test_over_the_ceiling_nothing_is_built_or_stored(tmp_path, builds, monkeypatch):
    root = _project(tmp_path / "proj")
    monkeypatch.setenv("REVEAL_I002_MAX_FILES", "1")   # 3 .py files > 1
    graph = i002_mod.I002()._build_import_graph(root)
    assert graph.scan_skipped_reason and not graph.dependencies
    assert builds == []
    assert not list(disk_cache._namespace_dir(GRAPH_NAMESPACE).glob("*.pkl"))


def test_kill_switch_writes_nothing(tmp_path, monkeypatch, builds):
    root = _project(tmp_path / "proj")
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    i002_mod.I002()._build_import_graph(root)
    _fresh_process_graph(root)
    assert len(builds) == 2
    assert not list(disk_cache._namespace_dir(GRAPH_NAMESPACE).glob("*.pkl"))


def test_graph_is_picklable():
    """Regression guard: the cached artifact must survive a pickle roundtrip."""
    from reveal.analyzers.imports import ImportGraph
    from pathlib import Path
    g = ImportGraph()
    g.add_dependency(Path("a.py"), Path("b.py"))
    assert pickle.loads(pickle.dumps(g)) == g


def test_target_only_add_delete_changes_i002_disk_fingerprint(tmp_path):
    (tmp_path / '.gitignore').write_text('generated.py\n', encoding='utf-8')
    (tmp_path / 'use.py').write_text('import generated\n', encoding='utf-8')
    rule = i002_mod.I002()
    graph = rule._build_import_graph(tmp_path)
    target = tmp_path / 'generated.py'
    assert tmp_path / 'use.py' not in graph.reverse_deps.get(target, set())
    target.write_text('VALUE = 1\n', encoding='utf-8')
    i002_mod._graph_cache.clear()  # model a fresh CLI invocation, using the disk cache
    graph = rule._build_import_graph(tmp_path)
    assert tmp_path / 'use.py' in graph.reverse_deps.get(target, set())
    target.unlink()
    i002_mod._graph_cache.clear()
    assert tmp_path / 'use.py' not in rule._build_import_graph(tmp_path).reverse_deps.get(target, set())
