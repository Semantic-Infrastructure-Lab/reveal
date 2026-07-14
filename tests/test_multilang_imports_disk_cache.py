"""Correctness tests for the persistent non-Python import-extraction disk
caches (BACK-626, extending BACK-625's PythonExtractor fix to JS/Go/Rust/Zig
and the shared generic tree-sitter extractor).

Each of these extractors independently parses + walks the tree per call (they
do not share TreeSitterAnalyzer.get_structure()'s own structure cache,
BACK-535) and are called repeatedly per file across I001/I002/I005,
calls://'s build_symbol_map, depends://, and imports:// -- both within one CLI
invocation and across fresh ones. The cache must be a pure performance
optimization: a result served from disk must be indistinguishable from a
fresh parse, and any change to the source file must invalidate its entry.
"""

import os

import pytest

from reveal.core import disk_cache
from reveal.analyzers.imports import javascript as js_mod
from reveal.analyzers.imports import go as go_mod
from reveal.analyzers.imports import rust as rust_mod
from reveal.analyzers.imports import zig as zig_mod
from reveal.analyzers.imports import generic as generic_mod


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the disk cache at a throwaway dir and start every test cold."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)
    for mod in (js_mod, go_mod, rust_mod, zig_mod, generic_mod):
        mod._IMPORTS_CACHE.clear()
    yield
    for mod in (js_mod, go_mod, rust_mod, zig_mod, generic_mod):
        mod._IMPORTS_CACHE.clear()


def _rewrite(path, content):
    """Overwrite content and force a distinct mtime_ns (racy on coarse-resolution
    filesystems with a bare write_text(), per BACK-535/BACK-625's tests)."""
    path.write_text(content)
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    return path


# (module, extractor class, suffix, initial source, initial expected module
# names, rewritten source, rewritten expected module names)
CASES = [
    pytest.param(
        js_mod, js_mod.JavaScriptExtractor, ".js",
        "import os from 'os';\nimport { readFile } from 'fs';\n",
        {"os", "fs"},
        "const path = require('path');\n",
        {"path"},
        id="javascript",
    ),
    pytest.param(
        go_mod, go_mod.GoExtractor, ".go",
        'package main\n\nimport (\n\t"fmt"\n\t"os"\n)\n',
        {"fmt", "os"},
        'package main\n\nimport "strings"\n',
        {"strings"},
        id="go",
    ),
    pytest.param(
        rust_mod, rust_mod.RustExtractor, ".rs",
        "use std::collections::HashMap;\nuse std::io;\n",
        {"std::collections::HashMap", "std::io"},
        "use std::fs;\n",
        {"std::fs"},
        id="rust",
    ),
    pytest.param(
        zig_mod, zig_mod.ZigImportExtractor, ".zig",
        'const std = @import("std");\n',
        {"std"},
        'const builtin = @import("builtin");\n',
        {"builtin"},
        id="zig",
    ),
]


@pytest.mark.parametrize("mod,extractor_cls,suffix,src,expect,src2,expect2", CASES)
def test_second_extraction_served_from_disk(tmp_path, monkeypatch, mod, extractor_cls, suffix, src, expect, src2, expect2):
    path = tmp_path / f"mod{suffix}"
    path.write_text(src)
    extractor = extractor_cls()

    fresh = extractor.extract_imports(path)
    assert fresh, "fixture should have imports"

    # Simulate a fresh process: clear the in-process cache. If disk caching
    # works, the tree-sitter parse never re-runs.
    mod._IMPORTS_CACHE.clear()

    def _boom(*a, **k):
        raise AssertionError("disk cache miss: uncached extraction was re-run")

    monkeypatch.setattr(extractor, "_extract_imports_uncached", _boom)
    cached = extractor.extract_imports(path)
    assert cached == fresh


@pytest.mark.parametrize("mod,extractor_cls,suffix,src,expect,src2,expect2", CASES)
def test_disk_result_equals_fresh_scan(tmp_path, mod, extractor_cls, suffix, src, expect, src2, expect2):
    path = tmp_path / f"mod{suffix}"
    path.write_text(src)
    extractor = extractor_cls()
    scanned = extractor.extract_imports(path)

    path_str = os.path.abspath(str(path))
    mtime_ns = os.stat(path_str).st_mtime_ns
    fp = mod._IMPORTS_CACHE.fingerprint(path_str, mtime_ns)
    from_disk = disk_cache.get(mod._IMPORTS_CACHE.namespace, fp)
    assert from_disk is not None
    assert from_disk == scanned


@pytest.mark.parametrize("mod,extractor_cls,suffix,src,expect,src2,expect2", CASES)
def test_edit_invalidates_cache(tmp_path, mod, extractor_cls, suffix, src, expect, src2, expect2):
    path = tmp_path / f"mod{suffix}"
    path.write_text(src)
    extractor = extractor_cls()
    before = extractor.extract_imports(path)
    assert {imp.module_name for imp in before} == expect

    mod._IMPORTS_CACHE.clear()
    _rewrite(path, src2)

    after = extractor.extract_imports(path)
    assert {imp.module_name for imp in after} == expect2


@pytest.mark.parametrize("mod,extractor_cls,suffix,src,expect,src2,expect2", CASES)
def test_kill_switch_writes_nothing(tmp_path, monkeypatch, mod, extractor_cls, suffix, src, expect, src2, expect2):
    path = tmp_path / f"mod{suffix}"
    path.write_text(src)
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    extractor = extractor_cls()
    extractor.extract_imports(path)

    path_str = os.path.abspath(str(path))
    mtime_ns = os.stat(path_str).st_mtime_ns
    fp = mod._IMPORTS_CACHE.fingerprint(path_str, mtime_ns)
    assert disk_cache.get(mod._IMPORTS_CACHE.namespace, fp) is None


def test_max_files_env_override(monkeypatch):
    monkeypatch.setenv("REVEAL_IMPORTS_CACHE_MAX_FILES", "5")
    assert js_mod._IMPORTS_CACHE.max_files() == 5
    monkeypatch.setenv("REVEAL_IMPORTS_CACHE_MAX_FILES", "not-a-number")
    assert js_mod._IMPORTS_CACHE.max_files() == js_mod._IMPORTS_CACHE._default_max_files
    monkeypatch.delenv("REVEAL_IMPORTS_CACHE_MAX_FILES")
    assert js_mod._IMPORTS_CACHE.max_files() == js_mod._IMPORTS_CACHE._default_max_files


class TestGenericExtractorConstantIndexBypass:
    """PHP's constant_index path (BACK-565) must never be served from -- or
    write into -- the disk cache: its result depends on more than the file's
    own contents."""

    def test_constant_index_call_is_not_cached(self, tmp_path):
        from reveal.analyzers.imports import get_extractor

        path = tmp_path / "mod.php"
        path.write_text("<?php\nrequire 'a.php';\n")
        extractor = get_extractor(path)
        assert extractor is not None

        # A constant_index-bearing call must bypass the cache entirely.
        extractor.extract_imports(path, constant_index={"FOO": ("literal", "bar")})

        path_str = os.path.abspath(str(path))
        mtime_ns = os.stat(path_str).st_mtime_ns
        fp = generic_mod._IMPORTS_CACHE.fingerprint(path_str, mtime_ns)
        assert disk_cache.get(generic_mod._IMPORTS_CACHE.namespace, fp) is None

    def test_plain_call_is_cached(self, tmp_path, monkeypatch):
        from reveal.analyzers.imports import get_extractor

        path = tmp_path / "mod.php"
        path.write_text("<?php\nrequire 'a.php';\n")
        extractor = get_extractor(path)
        fresh = extractor.extract_imports(path)
        assert fresh

        generic_mod._IMPORTS_CACHE.clear()

        def _boom(*a, **k):
            raise AssertionError("disk cache miss: uncached extraction was re-run")

        monkeypatch.setattr(extractor, "_extract_imports_uncached", _boom)
        cached = extractor.extract_imports(path)
        assert cached == fresh
