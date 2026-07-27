"""Correctness tests for the markdown link-graph disk cache (BACK-866).

Mirrors test_import_graph_disk_cache.py's contract for I002 (BACK-536): the
cache must be a pure performance optimization — a graph served from disk must
be byte-for-byte what a fresh scan would build, and ANY change to the source
tree (edit, add, delete) must invalidate it.
"""

from pathlib import Path

import pytest

from reveal.adapters.markdown import files, operations
from reveal.core import disk_cache


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Point the disk cache at a throwaway dir and start every test cold."""
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)


def _corpus(root):
    """Two files, a->b, with b having no outbound links."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "a.md").write_text("[b](b.md)\n")
    (root / "b.md").write_text("no links\n")
    return root


# --------------------------------------------------------------------------- #
# fingerprint
# --------------------------------------------------------------------------- #

class TestLinkGraphFingerprint:
    def test_unchanged_tree_fingerprint_is_stable(self, tmp_path):
        base = _corpus(tmp_path)
        all_files = files.find_markdown_files(base)
        fp1 = operations._link_graph_fingerprint(base, all_files)
        fp2 = operations._link_graph_fingerprint(base, all_files)
        assert fp1 is not None
        assert fp1 == fp2

    def test_edit_changes_fingerprint(self, tmp_path):
        base = _corpus(tmp_path)
        all_files = files.find_markdown_files(base)
        fp1 = operations._link_graph_fingerprint(base, all_files)
        (base / "a.md").write_text("[b](b.md)\nextra content\n")
        fp2 = operations._link_graph_fingerprint(base, all_files)
        assert fp1 != fp2

    def test_added_file_changes_fingerprint(self, tmp_path):
        base = _corpus(tmp_path)
        fp1 = operations._link_graph_fingerprint(base, files.find_markdown_files(base))
        (base / "c.md").write_text("new file\n")
        fp2 = operations._link_graph_fingerprint(base, files.find_markdown_files(base))
        assert fp1 != fp2

    def test_deleted_file_changes_fingerprint(self, tmp_path):
        base = _corpus(tmp_path)
        fp1 = operations._link_graph_fingerprint(base, files.find_markdown_files(base))
        (base / "b.md").unlink()
        fp2 = operations._link_graph_fingerprint(base, files.find_markdown_files(base))
        assert fp1 != fp2


# --------------------------------------------------------------------------- #
# build_link_graph — cache integration
# --------------------------------------------------------------------------- #

class TestLinkGraphCache:
    def test_second_build_served_from_disk(self, tmp_path, monkeypatch):
        base = _corpus(tmp_path)
        fresh = operations.build_link_graph(base)
        assert fresh['total_edges'] == 1

        def _boom(*a, **k):
            raise AssertionError("disk cache miss: extract_internal_links was re-run")

        monkeypatch.setattr(files, "extract_internal_links", _boom)
        cached = operations.build_link_graph(base)
        assert cached == fresh

    def test_disk_graph_equals_fresh_scan(self, tmp_path):
        base = _corpus(tmp_path)
        fresh = operations.build_link_graph(base)
        disk_cache_dir_before = list((tmp_path / "cache").rglob("*.pkl"))
        assert disk_cache_dir_before  # something was written

        # New op call, no monkeypatching — should transparently hit cache and
        # still return an identical structure.
        again = operations.build_link_graph(base)
        assert again == fresh

    def test_edit_invalidates_cache(self, tmp_path):
        base = _corpus(tmp_path)
        first = operations.build_link_graph(base)
        assert first['isolated'] == []

        # b.md no longer linked from a.md -> both isolated
        (base / "a.md").write_text("no links now\n")
        second = operations.build_link_graph(base)
        assert second != first
        assert sorted(second['isolated']) == ['a.md', 'b.md']

    def test_added_file_invalidates_cache(self, tmp_path):
        base = _corpus(tmp_path)
        first = operations.build_link_graph(base)
        assert first['total_files'] == 2

        (base / "c.md").write_text("standalone\n")
        second = operations.build_link_graph(base)
        assert second['total_files'] == 3

    def test_kill_switch_bypasses_cache(self, tmp_path, monkeypatch):
        base = _corpus(tmp_path)
        operations.build_link_graph(base)  # warm cache while enabled

        monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
        calls = []
        orig = files.extract_internal_links

        def _spy(*a, **k):
            calls.append(1)
            return orig(*a, **k)

        monkeypatch.setattr(files, "extract_internal_links", _spy)
        operations.build_link_graph(base)
        assert calls, "kill switch should force a live scan, not serve the cache"

    def test_get_backlinks_benefits_from_same_cache(self, tmp_path, monkeypatch):
        base = _corpus(tmp_path)
        operations.build_link_graph(base)  # warm cache

        def _boom(*a, **k):
            raise AssertionError("get_backlinks should reuse the cached graph")

        monkeypatch.setattr(files, "extract_internal_links", _boom)
        result = operations.get_backlinks(base, "b.md")
        assert result['found'] is True
        assert result['linked_by'] == ['a.md']
