"""Correctness tests for the persistent Python import-extraction disk cache
(BACK-625).

`PythonExtractor.extract_imports()` independently parses + walks the tree
(it does not share `TreeSitterAnalyzer.get_structure()`'s own structure
cache, BACK-535) and is called by I001/I002/I005, `calls://`'s
`build_symbol_map`, `depends://`, and `imports://` -- all across fresh CLI
invocations. The cache must be a pure performance optimization: a result
served from disk must be indistinguishable from a fresh parse, and ANY
change to the source file must invalidate its entry.
"""

import os

import pytest

from reveal.core import disk_cache
from reveal.analyzers.imports import python as py_imports_mod


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the disk cache at a throwaway dir and start every test cold."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)
    py_imports_mod._extract_imports_cache.clear()
    yield
    py_imports_mod._extract_imports_cache.clear()


def _write_module(path):
    path.write_text(
        "import os\n"
        "from sys import path as syspath\n"
        "\n"
        "def alpha():\n"
        "    return os.getcwd()\n"
    )
    return path


def _rewrite(path, content):
    """Overwrite content and force a distinct mtime_ns (see BACK-535's tests
    for why a bare write_text() is racy on coarse-resolution filesystems)."""
    path.write_text(content)
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    return path


def test_second_extraction_served_from_disk(tmp_path, monkeypatch):
    src = _write_module(tmp_path / "mod.py")
    extractor = py_imports_mod.PythonExtractor()

    fresh = extractor.extract_imports(src)
    assert fresh, "fixture should have imports"

    # Simulate a fresh process: clear the in-process cache. If disk caching
    # works, the tree-sitter parse never re-runs.
    py_imports_mod._extract_imports_cache.clear()

    def _boom(*a, **k):
        raise AssertionError("disk cache miss: _get_tree_analyzer was re-run")

    monkeypatch.setattr(extractor, "_get_tree_analyzer", _boom)
    cached = extractor.extract_imports(src)

    assert cached == fresh

def test_disk_result_equals_fresh_scan(tmp_path):
    src = _write_module(tmp_path / "mod.py")
    extractor = py_imports_mod.PythonExtractor()
    scanned = extractor.extract_imports(src)

    path_str = os.path.abspath(str(src))
    mtime_ns = os.stat(path_str).st_mtime_ns
    fp = py_imports_mod._imports_fingerprint(path_str, mtime_ns)
    from_disk = disk_cache.get(py_imports_mod._IMPORTS_CACHE_NAMESPACE, fp)
    assert from_disk is not None
    assert from_disk == scanned


def test_edit_invalidates_cache(tmp_path):
    src = _write_module(tmp_path / "mod.py")
    extractor = py_imports_mod.PythonExtractor()
    before = extractor.extract_imports(src)
    assert {imp.module_name for imp in before} == {"os", "sys"}

    py_imports_mod._extract_imports_cache.clear()
    _rewrite(src, "import json\n\ndef only_one():\n    return 42\n")

    after = extractor.extract_imports(src)
    assert {imp.module_name for imp in after} == {"json"}


def test_kill_switch_writes_nothing(tmp_path, monkeypatch):
    src = _write_module(tmp_path / "mod.py")
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    extractor = py_imports_mod.PythonExtractor()
    extractor.extract_imports(src)

    path_str = os.path.abspath(str(src))
    mtime_ns = os.stat(path_str).st_mtime_ns
    fp = py_imports_mod._imports_fingerprint(path_str, mtime_ns)
    assert disk_cache.get(py_imports_mod._IMPORTS_CACHE_NAMESPACE, fp) is None


def test_max_files_env_override(monkeypatch):
    monkeypatch.setenv("REVEAL_IMPORTS_CACHE_MAX_FILES", "5")
    assert py_imports_mod._imports_cache_max_files() == 5
    monkeypatch.setenv("REVEAL_IMPORTS_CACHE_MAX_FILES", "not-a-number")
    assert py_imports_mod._imports_cache_max_files() == py_imports_mod._DEFAULT_IMPORTS_CACHE_MAX_FILES
    monkeypatch.delenv("REVEAL_IMPORTS_CACHE_MAX_FILES")
    assert py_imports_mod._imports_cache_max_files() == py_imports_mod._DEFAULT_IMPORTS_CACHE_MAX_FILES
