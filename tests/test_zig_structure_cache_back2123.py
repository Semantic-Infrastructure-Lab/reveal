"""Zig goes through the structure disk cache like every other code analyzer (BACK-2123).

ZigAnalyzer.get_structure used to build its own structure and never reach
TreeSitterAnalyzer._get_or_build_structure, so the BACK-535 structure cache was
bypassed: every Zig query re-parsed and re-extracted every file. These tests count
cache traffic and extractions (deterministic) instead of timing, and pin that the
cached answer equals the uncached one for everything Zig adds on top of the shared
builder (tests, enums, unions, imports).
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

from reveal import treesitter as ts_mod
from reveal.analyzers.lua import LuaAnalyzer
from reveal.analyzers.zig import ZigAnalyzer
from reveal.core import disk_cache

# BACK-1149: exercises internal functions/modules directly, not CLI/MCP/network surface
pytestmark = [pytest.mark.component, pytest.mark.disk_cache]

ZIG_SOURCE = """\
const std = @import("std");
const util = @import("util.zig");

pub const Point = struct {
    x: i32,
    y: i32,

    pub fn add(self: Point, other: Point) Point {
        return .{ .x = self.x + other.x, .y = self.y + other.y };
    }
};

const Color = enum { red, green, blue };

const Value = union(enum) {
    int: i64,
    float: f64,
};

pub fn Generic(comptime T: type) type {
    return struct {
        item: T,
        fn get(self: @This()) T {
            return self.item;
        }
    };
}

fn helper(a: i32) i32 {
    if (a > 0) {
        return util.double(a);
    }
    return comptime blk: {
        break :blk 1;
    };
}

pub fn main() void {
    const p = Point{ .x = 1, .y = 2 };
    _ = p.add(p);
    std.debug.print("{d}\\n", .{helper(3)});
}

test "helper positive" {
    try std.testing.expect(helper(2) == 4);
}

test Point {
    _ = Point{ .x = 0, .y = 0 };
}
"""

EDITED_ZIG_SOURCE = ZIG_SOURCE + """
const Mode = enum { fast, slow };

test "added after the edit" {
    _ = Mode.fast;
}
"""

LUA_SOURCE = "local M = {}\nfunction M.alpha()\n  return 1\nend\nreturn M\n"


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("REVEAL_DISK_CACHE", "1")
    ts_mod._get_parse_cache().clear()
    yield
    ts_mod._get_parse_cache().clear()


def _write(path, content):
    path.write_text(content, encoding="utf-8")
    return path


def _rewrite(path, content):
    """Overwrite and force a distinct mtime_ns (same tick on coarse filesystems otherwise)."""
    path.write_text(content, encoding="utf-8")
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    return path


class _Traffic:
    """Counts structure-namespace disk_cache calls and tree-sitter parses."""

    def __init__(self, monkeypatch):
        self.gets = []   # (namespace, hit)
        self.puts = []   # namespace
        self.parses = 0
        real_get, real_put = disk_cache.get, disk_cache.put
        real_parse = ts_mod.TreeSitterAnalyzer._parse_tree

        def get(namespace, key):
            value = real_get(namespace, key)
            self.gets.append((namespace, value is not None))
            return value

        def put(namespace, key, value, max_entries=None):
            self.puts.append(namespace)
            return real_put(namespace, key, value, max_entries=max_entries)

        def parse(analyzer):
            self.parses += 1
            return real_parse(analyzer)

        monkeypatch.setattr(disk_cache, "get", get)
        monkeypatch.setattr(disk_cache, "put", put)
        monkeypatch.setattr(ts_mod.TreeSitterAnalyzer, "_parse_tree", parse)

    def structure_hits(self):
        return [hit for ns, hit in self.gets if ns == ts_mod._STRUCTURE_CACHE_NAMESPACE]

    def structure_puts(self):
        return [ns for ns in self.puts if ns == ts_mod._STRUCTURE_CACHE_NAMESPACE]

    def reset(self):
        self.gets.clear()
        self.puts.clear()
        self.parses = 0


def _fresh_structure(analyzer_cls, path):
    """A new analyzer with the in-process parse cache cleared (a fresh process's view)."""
    ts_mod._get_parse_cache().clear()
    return analyzer_cls(str(path)).get_structure()


def test_warm_zig_structure_hits_cache_and_never_parses(tmp_path, monkeypatch):
    """Red on the old code: cold wrote nothing, warm looked nothing up and parsed again."""
    src = _write(tmp_path / "main.zig", ZIG_SOURCE)
    traffic = _Traffic(monkeypatch)

    cold = _fresh_structure(ZigAnalyzer, src)
    assert cold["functions"], "fixture should have functions"
    assert traffic.structure_hits() == [False], "cold build looks the structure up once and misses"
    assert traffic.structure_puts() == [ts_mod._STRUCTURE_CACHE_NAMESPACE], \
        "cold build stores exactly one structure entry"
    assert traffic.parses >= 1

    traffic.reset()
    warm = _fresh_structure(ZigAnalyzer, src)
    assert traffic.structure_hits() == [True], "warm build must be served by the structure namespace"
    assert traffic.structure_puts() == [], "a hit stores nothing"
    assert traffic.parses == 0, "a structure hit never parses the file"
    assert warm == cold


def test_warm_zig_structure_runs_no_extraction(tmp_path, monkeypatch):
    """Red on the old code: the warm analysis re-ran every extractor."""
    src = _write(tmp_path / "main.zig", ZIG_SOURCE)
    _fresh_structure(ZigAnalyzer, src)

    ts_mod._get_parse_cache().clear()
    analyzer = ZigAnalyzer(str(src))
    runs = []
    for name in ("_extract_functions", "_extract_container_decls", "_extract_tests", "_extract_imports"):
        real = getattr(analyzer, name)

        def spy(*a, _real=real, _name=name, **k):
            runs.append(_name)
            return _real(*a, **k)

        monkeypatch.setattr(analyzer, name, spy)
    analyzer.get_structure()
    assert runs == [], f"warm analysis re-extracted: {runs}"


def test_zig_cache_survives_a_new_process(tmp_path):
    """Two interpreter processes sharing REVEAL_CACHE_DIR: the second one is all hits."""
    src = _write(tmp_path / "main.zig", ZIG_SOURCE)
    script = textwrap.dedent("""
        import json, sys
        from reveal import treesitter as ts_mod
        from reveal.analyzers.zig import ZigAnalyzer
        from reveal.core import disk_cache

        gets, puts, parses = [], [], [0]
        real_get, real_put = disk_cache.get, disk_cache.put
        real_parse = ts_mod.TreeSitterAnalyzer._parse_tree
        def get(ns, key):
            v = real_get(ns, key); gets.append([ns, v is not None]); return v
        def put(ns, key, value, max_entries=None):
            puts.append(ns); return real_put(ns, key, value, max_entries=max_entries)
        def parse(self):
            parses[0] += 1; return real_parse(self)
        disk_cache.get, disk_cache.put = get, put
        ts_mod.TreeSitterAnalyzer._parse_tree = parse
        structure = ZigAnalyzer(sys.argv[1]).get_structure()
        print(json.dumps({"gets": gets, "puts": puts, "parses": parses[0], "structure": structure}))
    """)
    env = {**os.environ, "REVEAL_DISK_CACHE": "1", "REVEAL_CACHE_DIR": str(tmp_path / "xproc-cache"),
           "PYTHONHASHSEED": "0"}

    def run():
        proc = subprocess.run([sys.executable, "-c", script, str(src)], env=env,
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)

    first, second = run(), run()
    ns = ts_mod._STRUCTURE_CACHE_NAMESPACE
    # The Zig imports extractor keeps its own per-file namespace; only the structure one is asserted.
    assert [ns, False] in first["gets"] and ns in first["puts"]
    assert [g for g in second["gets"] if g[0] == ns] == [[ns, True]], second["gets"]
    assert ns not in second["puts"] and second["parses"] == 0
    assert second["structure"] == first["structure"]


def test_cached_zig_structure_equals_uncached_byte_for_byte(tmp_path, monkeypatch):
    """Cache off, cold, warm and after an edit give the same answer, tests/enums/unions/imports included."""
    src = _write(tmp_path / "main.zig", ZIG_SOURCE)

    def dump(structure):
        return json.dumps(structure, default=str)  # key order is part of the output

    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    off = dump(_fresh_structure(ZigAnalyzer, src))
    monkeypatch.setenv("REVEAL_DISK_CACHE", "1")
    cold = dump(_fresh_structure(ZigAnalyzer, src))
    warm = dump(_fresh_structure(ZigAnalyzer, src))
    assert off == cold == warm

    structure = json.loads(warm)
    assert [t["name"] for t in structure["tests"]] == ["helper positive", "Point"]
    assert [e["name"] for e in structure["enums"]] == ["Color"]
    assert [u["name"] for u in structure["unions"]] == ["Value"]
    assert [s["name"] for s in structure["structs"]] == ["Point"]
    assert [i["content"] for i in structure["imports"]] == [
        'const std = @import("std");', 'const util = @import("util.zig");']
    assert "called_by" not in structure["functions"][0], "Zig's output shape is unchanged"

    _rewrite(src, EDITED_ZIG_SOURCE)
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
    off_after = dump(_fresh_structure(ZigAnalyzer, src))
    monkeypatch.setenv("REVEAL_DISK_CACHE", "1")
    cold_after = dump(_fresh_structure(ZigAnalyzer, src))
    warm_after = dump(_fresh_structure(ZigAnalyzer, src))
    assert off_after == cold_after == warm_after
    assert off_after != warm
    after = json.loads(warm_after)
    assert [e["name"] for e in after["enums"]] == ["Color", "Mode"]
    assert after["tests"][-1]["name"] == "added after the edit"


def test_edit_refreshes_the_extra_zig_categories_through_the_cache(tmp_path, monkeypatch):
    """The cached value carries tests/enums/unions/imports, and an edit refetches them."""
    src = _write(tmp_path / "main.zig", ZIG_SOURCE)
    _fresh_structure(ZigAnalyzer, src)
    traffic = _Traffic(monkeypatch)

    _rewrite(src, EDITED_ZIG_SOURCE)
    edited = _fresh_structure(ZigAnalyzer, src)
    assert traffic.structure_hits() == [False], "the edit changes the fingerprint: a miss, not a stale hit"
    assert [e["name"] for e in edited["enums"]] == ["Color", "Mode"]
    assert "added after the edit" in [t["name"] for t in edited["tests"]]

    traffic.reset()
    again = _fresh_structure(ZigAnalyzer, src)
    assert traffic.structure_hits() == [True] and traffic.parses == 0
    assert again == edited


def test_zig_recovered_parse_flag_survives_the_cache(tmp_path):
    """A broken Zig file keeps its recovered-parse disclosure on a warm answer (BACK-1084/1589)."""
    src = _write(tmp_path / "broken.zig", 'const std = @import("std");\npub fn ok() void {}\npub fn bad( void {\n')
    cold = _fresh_structure(ZigAnalyzer, src)
    warm = _fresh_structure(ZigAnalyzer, src)
    assert cold.get("_has_errors") is True
    assert warm == cold
    assert warm["meta"]["parse_mode"] == "tree_sitter_partial"


def test_other_language_cache_traffic_is_unchanged(tmp_path, monkeypatch):
    """Negative control: Lua already used the shared builder, and still hits on the warm run."""
    src = _write(tmp_path / "mod.lua", LUA_SOURCE)
    traffic = _Traffic(monkeypatch)

    cold = _fresh_structure(LuaAnalyzer, src)
    assert traffic.structure_hits() == [False] and traffic.parses >= 1
    traffic.reset()
    warm = _fresh_structure(LuaAnalyzer, src)
    assert traffic.structure_hits() == [True] and traffic.parses == 0
    assert warm == cold
