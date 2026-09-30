"""get_outline(): get_structure() without per-function metrics, calls or imports (BACK-1560).

--grep only needs each element's name and line range to group hits, but built the full
structure (complexity walk, callee extraction, import resolution, callers index) for
every matching file -- ~95% of a cold grep. The outline must locate exactly what the
full structure locates, and must never be served where a full structure is expected.
"""

from pathlib import Path

import pytest

from reveal import treesitter as ts_mod
from reveal.analyzers.python import PythonAnalyzer
from reveal.grep_handler import _get_structural_elements
from reveal.registry import get_analyzer

# BACK-1149: exercises internal functions/modules directly, not CLI/MCP/network surface
pytestmark = pytest.mark.component

CONFORMANCE = sorted((Path(__file__).parent / "fixtures" / "conformance").glob("*/sample.*"))


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("REVEAL_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("REVEAL_DISK_CACHE", raising=False)
    ts_mod._get_parse_cache().clear()
    yield
    ts_mod._get_parse_cache().clear()


def _located(structure):
    """(category, name, line, line_end) of every element, imports aside."""
    return sorted(
        (category, item.get("name"), item.get("line"), item.get("line_end"))
        for category, items in structure.items()
        if category != "imports" and isinstance(items, list)
        for item in items
        if isinstance(item, dict)
    )


def _write_module(path):
    path.write_text(
        "import os\n\ndef alpha():\n    return beta()\n\ndef beta():\n    return 1\n\nclass Gamma:\n    pass\n",
        encoding="utf-8",
    )
    return path


def test_conformance_fixtures_present():
    assert len(CONFORMANCE) >= 10


@pytest.mark.parametrize("path", CONFORMANCE, ids=lambda p: p.parent.name)
def test_outline_locates_what_the_full_structure_locates(path):
    analyzer_class = get_analyzer(str(path))
    outline = analyzer_class(str(path)).get_outline()  # cold: builds + caches the outline
    full = analyzer_class(str(path)).get_structure()   # must not be served the outline

    assert _located(outline) == _located(full)
    assert any(f.get("complexity") for f in full.get("functions", [])), "full structure lost its metrics"


def test_outline_omits_metrics_calls_and_imports(tmp_path):
    outline = PythonAnalyzer(str(_write_module(tmp_path / "mod.py"))).get_outline()

    assert "imports" not in outline
    assert [f["name"] for f in outline["functions"]] == ["alpha", "beta"]
    for func in outline["functions"]:
        assert set(func) <= {"line", "line_end", "name", "decorators"}


def test_outline_build_is_never_served_as_full_structure(tmp_path):
    src = _write_module(tmp_path / "mod.py")
    PythonAnalyzer(str(src)).get_outline()
    ts_mod._get_parse_cache().clear()

    full = PythonAnalyzer(str(src)).get_structure()

    assert full["imports"]
    assert all("complexity" in f and "called_by" in f for f in full["functions"])


def test_full_cache_entry_answers_outline_without_parsing(tmp_path, monkeypatch):
    src = _write_module(tmp_path / "mod.py")
    full = PythonAnalyzer(str(src)).get_structure()
    ts_mod._get_parse_cache().clear()
    analyzer = PythonAnalyzer(str(src))

    def _boom(*a, **k):
        raise AssertionError("a full cache entry should answer the outline")

    monkeypatch.setattr(analyzer, "_parse_tree", _boom)
    assert analyzer.get_outline() == full


def test_outline_flag_is_reset(tmp_path):
    analyzer = PythonAnalyzer(str(_write_module(tmp_path / "mod.py")))
    analyzer.get_outline()
    assert analyzer._outline_only is False


def test_grep_groups_without_the_metrics_walk(tmp_path, monkeypatch):
    """--grep's element lookup takes the outline path: the complexity/calls walk never runs."""
    monkeypatch.setenv("REVEAL_DISK_CACHE", "0")

    def _boom(*a, **k):
        raise AssertionError("grep ran the complexity/calls walk")

    monkeypatch.setattr(ts_mod.TreeSitterAnalyzer, "_complexity_depth_and_calls", _boom)
    monkeypatch.setattr(ts_mod.TreeSitterAnalyzer, "_extract_imports", _boom)

    elements = _get_structural_elements(str(_write_module(tmp_path / "mod.py")))

    # _get_structural_elements swallows analyzer errors into [], so a non-empty
    # result is what proves neither walk ran.
    assert [(e["name"], e["line"], e["line_end"]) for e in elements] == [
        ("alpha", 3, 4), ("beta", 6, 7), ("Gamma", 9, 10),
    ]
