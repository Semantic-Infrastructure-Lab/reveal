"""MarkdownAnalyzer pays only for what it is asked (BACK-1562).

The markdown_inline tree (links, code spans) was parsed in __init__ for every file,
and the heading index -- the outline, --grep's grouping, section extraction -- had no
disk cache, so each run re-parsed and re-walked every markdown file it touched.
"""

import pytest

from reveal import treesitter as ts_mod
from reveal.analyzers import markdown as md_mod
from reveal.analyzers.markdown import MarkdownAnalyzer
from reveal.core import disk_cache

# BACK-1149: exercises internal functions/modules directly, not CLI/MCP/network surface
pytestmark = [pytest.mark.component, pytest.mark.disk_cache]

DOC = "# Title\n\nIntro with a [link](other.md).\n\n## Setup\n\nRun `make`.\n\nSetext\n------\n\nend\n"


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    ts_mod._get_parse_cache().clear()
    md_mod._inline_parse_cache.clear()
    yield
    ts_mod._get_parse_cache().clear()
    md_mod._inline_parse_cache.clear()


@pytest.fixture
def doc(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(DOC, encoding="utf-8")
    return str(path)


def _headings(structure):
    return [(h["line"], h["level"], h["name"]) for h in structure["headings"]]


def test_outline_never_parses_the_inline_tree(doc):
    analyzer = MarkdownAnalyzer(doc)
    assert _headings(analyzer.get_outline()) == [(1, 1, "Title"), (5, 2, "Setup"), (9, 2, "Setext")]
    assert analyzer._inline_parsed is False


def test_links_still_parse_the_inline_tree_on_demand(doc):
    analyzer = MarkdownAnalyzer(doc)
    links = analyzer.get_structure(extract_links=True)["links"]
    assert [link["url"] for link in links] == ["other.md"]
    assert analyzer._inline_parsed is True and analyzer.inline_tree is not None


def test_heading_index_served_from_disk_without_parsing(doc, monkeypatch):
    fresh = MarkdownAnalyzer(doc).get_structure()
    ts_mod._get_parse_cache().clear()
    analyzer = MarkdownAnalyzer(doc)

    def _boom(*a, **k):
        raise AssertionError("heading-index cache hit parsed the file")

    monkeypatch.setattr(analyzer, "_parse_tree", _boom)
    cached = analyzer.get_structure()

    assert _headings(cached) == _headings(fresh)
    assert cached == fresh  # section sizes and the tree parse_mode too
    assert "tree_sitter_full" in repr(cached)


def test_regex_fallback_is_never_cached(doc, monkeypatch):
    analyzer = MarkdownAnalyzer(doc)
    analyzer.tree = None  # as if the markdown grammar were unavailable
    analyzer.get_structure()

    fingerprint = analyzer._structure_fingerprint()
    assert disk_cache.get(md_mod._HEADINGS_CACHE_NAMESPACE, fingerprint) is None


def test_edit_invalidates_heading_cache(doc):
    import os
    MarkdownAnalyzer(doc).get_structure()
    with open(doc, "a", encoding="utf-8") as f:
        f.write("\n# Appended\n")
    st = os.stat(doc)
    os.utime(doc, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    ts_mod._get_parse_cache().clear()

    names = [h["name"] for h in MarkdownAnalyzer(doc).get_structure()["headings"]]
    assert names[-1] == "Appended"
