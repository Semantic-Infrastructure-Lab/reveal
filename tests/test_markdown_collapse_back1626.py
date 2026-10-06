"""BACK-1626: a large markdown section with subsections is its own body plus an outline.

`reveal doc.md "Title"` on an H1 returned the whole document (60-132 KB in the
2026-10-01 census, which Claude Code saved to a file and previewed at 2 KB). Past
COLLAPSE_MIN_LINES, a section that has subsections shows the text under its own heading
and the subsection outline; the cut is disclosed with the line range for the whole
section. Small sections, leaf sections, explicit line requests and explicit cuts are
untouched.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402

from reveal.display.element import COLLAPSE_MIN_LINES  # noqa: E402

pytestmark = pytest.mark.cli

_SUB = "## Sub {i}\n\n" + "\n".join(f"s{{i}} line {j}" for j in range(30)) + "\n\n"


def _subs(count: int) -> str:
    return "".join(_SUB.format(i=i).replace("{i}", str(i)) for i in range(count))


def _write(tmp_path, text: str) -> Path:
    p = tmp_path / "doc.md"
    p.write_text(text, encoding='utf-8')
    return p


@pytest.fixture
def with_intro(tmp_path):
    return _write(tmp_path, "# Big Doc\n\nIntro text.\nSecond intro line.\n\n" + _subs(6))


@pytest.fixture
def no_intro(tmp_path):
    return _write(tmp_path, "# Big Doc\n\n" + _subs(6))


def _run(doc, *args):
    result = _run_reveal_direct(str(doc), *args)
    assert result.returncode == 0, result.stderr
    return result.stdout


class TestCollapse:
    def test_h1_with_intro_shows_own_body_and_outline(self, with_intro):
        out = _run(with_intro, "Big Doc")
        assert "Intro text." in out and "Second intro line." in out
        assert "s0 line 0" not in out
        assert "Subsections (6):" in out
        assert ":6      Sub 0" in out and ":171    Sub 5" in out

    def test_cut_is_disclosed_with_the_line_range_for_everything(self, with_intro):
        out = _run(with_intro, "Big Doc")
        assert "Truncated source: showing 4 of 203" in out
        assert "doc.md :1-203" in out

    def test_the_disclosed_range_returns_the_whole_section(self, with_intro):
        out = _run(with_intro, ":1-203")
        assert "s5 line 29" in out and "Subsections" not in out and "Truncated" not in out

    def test_h1_without_text_shows_only_the_outline(self, no_intro):
        out = _run(no_intro, "Big Doc")
        assert out.splitlines()[1] == ""
        assert out.splitlines()[2] == "Subsections (6):"
        assert "s0 line 0" not in out

    def test_json_carries_body_outline_and_warning(self, with_intro):
        data = json.loads(_run(with_intro, "Big Doc", "--format", "json"))
        assert data['collapsed'] is True
        assert data['source'].endswith("Second intro line.")
        assert [h['name'] for h in data['headings']] == [f"Sub {i}" for i in range(6)]
        warning, = data['meta']['warnings']
        assert (warning['field'], warning['shown'], warning['total']) == ('source', 4, 203)

    def test_explicit_head_wins_over_collapse(self, with_intro):
        out = _run(with_intro, "Big Doc", "--head", "10")
        assert "Subsections" not in out and "showing 10 of 203" in out

    def test_a_subsection_is_a_leaf_and_stays_whole(self, with_intro):
        out = _run(with_intro, "Sub 3")
        assert "s3 line 29" in out and "Subsections" not in out


class TestNotCollapsed:
    def test_section_under_the_threshold_is_whole(self, tmp_path):
        doc = _write(tmp_path, "# Small\n\nhi\n\n## A\n\nx\n")
        out = _run(doc, "Small")
        assert "## A" in out and "Subsections" not in out

    def test_large_section_without_subsections_is_whole(self, tmp_path):
        doc = _write(tmp_path, "# Flat\n\n" + "\n".join(f"row {i}" for i in range(COLLAPSE_MIN_LINES + 20)))
        out = _run(doc, "Flat")
        assert f"row {COLLAPSE_MIN_LINES + 19}" in out and "Truncated" not in out

    def test_threshold_boundary(self, tmp_path):
        def doc_of(lines: int):
            body = "\n".join(f"row {i}" for i in range(lines - 4))
            return _write(tmp_path, f"# T\n\n{body}\n\n## S\n")   # total = lines
        assert "Subsections" not in _run(doc_of(COLLAPSE_MIN_LINES - 1), "T")
        assert "Subsections" in _run(doc_of(COLLAPSE_MIN_LINES + 1), "T")
