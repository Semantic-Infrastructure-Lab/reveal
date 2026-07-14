"""Correctness tests for the persistent structure disk cache (BACK-535).

`TreeSitterAnalyzer.get_structure()` is the single choke point behind
overview/hotspots/architecture/contracts/testability/deps for every
tree-sitter language. The cache must be a pure performance optimization: a
structure served from disk must be indistinguishable from a fresh build, and
ANY change to the source file must invalidate its entry.
"""

import os

import pytest

from reveal.core import disk_cache
from reveal import treesitter as ts_mod
from reveal.analyzers.python import PythonAnalyzer


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the disk cache at a throwaway dir and start every test cold."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)
    ts_mod._parse_cache.clear()
    yield
    ts_mod._parse_cache.clear()


def _write_module(path):
    path.write_text(
        "import os\n"
        "\n"
        "def alpha():\n"
        "    return beta()\n"
        "\n"
        "def beta():\n"
        "    return 1\n"
        "\n"
        "class Gamma:\n"
        "    pass\n"
    )
    return path


def _rewrite(path, content):
    """Overwrite path's content and force a distinct mtime_ns.

    A bare write_text() can land in the same filesystem mtime tick as a
    preceding write on fast/coarse-resolution filesystems, which would fool
    both the in-process parse cache and our own fingerprint (both keyed on
    mtime_ns) into treating the edit as a no-op. Tests need a *guaranteed*
    change, not a racy one.
    """
    path.write_text(content)
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    return path


def test_second_build_served_from_disk(tmp_path, monkeypatch):
    src = _write_module(tmp_path / "mod.py")

    fresh = PythonAnalyzer(str(src))
    fresh_structure = fresh._get_or_build_structure()
    assert fresh_structure["functions"], "fixture should have functions"

    # Simulate a fresh process: new analyzer instance, in-process parse
    # cache cleared. If disk caching works, extraction never re-runs.
    ts_mod._parse_cache.clear()
    cached_analyzer = PythonAnalyzer(str(src))

    def _boom(*a, **k):
        raise AssertionError("disk cache miss: _extract_functions was re-run")

    monkeypatch.setattr(cached_analyzer, "_extract_functions", _boom)
    cached_structure = cached_analyzer._get_or_build_structure()

    assert cached_structure == fresh_structure


def test_disk_structure_equals_fresh_scan(tmp_path):
    src = _write_module(tmp_path / "mod.py")
    analyzer = PythonAnalyzer(str(src))
    scanned = analyzer._get_or_build_structure()

    fp = analyzer._structure_fingerprint()
    from_disk = disk_cache.get(ts_mod._STRUCTURE_CACHE_NAMESPACE, fp)
    assert from_disk is not None
    assert from_disk == scanned


def test_edit_invalidates_cache(tmp_path):
    src = _write_module(tmp_path / "mod.py")
    analyzer = PythonAnalyzer(str(src))
    fp_before = analyzer._structure_fingerprint()
    analyzer._get_or_build_structure()  # populate

    _rewrite(src, "def only_one():\n    return 42\n")
    analyzer_after = PythonAnalyzer(str(src))
    fp_after = analyzer_after._structure_fingerprint()
    assert fp_after != fp_before, "edited file must fingerprint differently"

    rebuilt = analyzer_after._get_or_build_structure()
    assert [f["name"] for f in rebuilt["functions"]] == ["only_one"]


def test_unchanged_file_fingerprint_is_stable(tmp_path):
    src = _write_module(tmp_path / "mod.py")
    a = PythonAnalyzer(str(src))
    b = PythonAnalyzer(str(src))
    assert a._structure_fingerprint() == b._structure_fingerprint()


def test_kill_switch_writes_nothing(tmp_path, monkeypatch):
    src = _write_module(tmp_path / "mod.py")
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    analyzer = PythonAnalyzer(str(src))
    analyzer._get_or_build_structure()
    fp = analyzer._structure_fingerprint()
    assert disk_cache.get(ts_mod._STRUCTURE_CACHE_NAMESPACE, fp) is None


def test_slicing_applies_uniformly_to_cache_hit(tmp_path):
    """head/tail/range must slice a cached structure exactly like a fresh one."""
    src = _write_module(tmp_path / "mod.py")
    fresh = PythonAnalyzer(str(src))
    fresh.get_structure()  # populates disk cache

    ts_mod._parse_cache.clear()
    cached = PythonAnalyzer(str(src))
    sliced = cached.get_structure(head=1)
    assert len(sliced["functions"]) == 1
    assert sliced["functions"][0]["name"] == "alpha"


def test_cache_hit_does_not_mutate_stored_entry(tmp_path):
    """A caller mutating its returned dict must not corrupt future cache hits."""
    src = _write_module(tmp_path / "mod.py")
    analyzer = PythonAnalyzer(str(src))
    analyzer._get_or_build_structure()  # populate

    ts_mod._parse_cache.clear()
    first_hit = PythonAnalyzer(str(src))
    structure = first_hit._get_or_build_structure()
    structure["functions"].append({"name": "injected"})

    ts_mod._parse_cache.clear()
    second_hit = PythonAnalyzer(str(src))
    fresh_again = second_hit._get_or_build_structure()
    assert [f["name"] for f in fresh_again["functions"]] == ["alpha", "beta"]


def test_fingerprint_none_on_missing_file(tmp_path):
    src = _write_module(tmp_path / "mod.py")
    analyzer = PythonAnalyzer(str(src))
    src.unlink()
    assert analyzer._structure_fingerprint() is None
