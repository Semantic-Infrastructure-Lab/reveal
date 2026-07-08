"""End-to-end regression tests for `reveal file.md --section NAME`.

These guard the CLI wiring that a mis-dispatched `_try_grep_extraction`
silently broke: `--section` was calling the markdown analyzer with the
section name in the *element_type* slot and an empty *name*, which the
analyzer answered with an empty-pattern = match-all result — so every
`--section` request degraded to a full-file dump banner-ed as
`# N sections matched "" — showing all`, with no error.

The unit layer had ~50 direct `MarkdownAnalyzer.extract_element('section',
name)` tests, all green, because they called the analyzer in the *correct*
argument order. Only the real CLI path swapped the arguments — and nothing
drove `--section` through the CLI on an actual `.md` file. That gap is what
these tests close: they exercise the same path a user's invocation does.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402


_DOC = """\
# Title

## Alpha
alpha content

## Beta
beta content

## Gamma
gamma content
"""


@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(_DOC)
    return p


class TestSectionExtractionCLI:
    """`reveal file.md --section X` must return only section X."""

    def test_section_extracts_only_named_section(self, doc):
        result = _run_reveal_direct(str(doc), "--section", "Alpha")
        assert result.returncode == 0, result.stderr
        out = result.stdout
        # The requested heading + its body are present...
        assert "## Alpha" in out
        assert "alpha content" in out
        # ...and no *other* section's body leaks in.
        assert "beta content" not in out
        assert "gamma content" not in out

    def test_section_does_not_report_empty_match_banner(self, doc):
        """The tell-tale symptom of the bug: banner said matched "" — showing all."""
        result = _run_reveal_direct(str(doc), "--section", "Alpha")
        assert 'matched ""' not in result.stdout
        assert "showing all" not in result.stdout

    def test_section_header_spans_only_the_section(self, doc):
        """The `path:START-END` header must bound the one section, not the file."""
        result = _run_reveal_direct(str(doc), "--section", "Alpha")
        # Alpha is at file lines 3-4; its span ends before the next `##` (line 6).
        assert f"{doc}:3-5" in result.stdout
        # A full-file dump would have spanned to the last line (11).
        assert f"{doc}:1-11" not in result.stdout

    def test_section_middle_section(self, doc):
        """Guard the non-first case too — Beta, not Alpha or Gamma."""
        result = _run_reveal_direct(str(doc), "--section", "Beta")
        assert result.returncode == 0, result.stderr
        assert "beta content" in result.stdout
        assert "alpha content" not in result.stdout
        assert "gamma content" not in result.stdout

    def test_nonexistent_section_errors_not_dumps(self, doc):
        """A missing section must fail, not silently dump the whole file."""
        result = _run_reveal_direct(str(doc), "--section", "Nonexistent")
        assert result.returncode != 0
        assert "alpha content" not in result.stdout
        assert "gamma content" not in result.stdout


class TestSectionCliMatchesPythonApi:
    """The CLI and the public `element()` API must agree on the same doc.

    They diverged silently before the fix — the API used the correct
    `(element_type, name)` contract and worked, while the CLI's swapped probe
    did not. An agreement test makes any future divergence a failing test
    rather than a user-reported bug.
    """

    def test_cli_and_api_return_same_span(self, doc):
        from reveal.api import element

        api_result = element(str(doc), "Alpha")
        assert api_result is not None
        assert api_result["line_start"] == 3
        assert api_result["line_end"] == 5

        cli = _run_reveal_direct(str(doc), "--section", "Alpha")
        assert f"{doc}:{api_result['line_start']}-{api_result['line_end']}" in cli.stdout


class TestHtmlSelectorStillWorks:
    """The extract_by_selector refactor must not regress HTML selector extraction."""

    @pytest.fixture
    def html(self, tmp_path):
        p = tmp_path / "page.html"
        p.write_text(
            "<!DOCTYPE html>\n<html><body>\n"
            '<div id="main"><p>hello main</p></div>\n'
            '<div class="side">sidebar</div>\n'
            "</body></html>\n"
        )
        return p

    def test_id_selector(self, html):
        result = _run_reveal_direct(str(html), "#main")
        assert result.returncode == 0, result.stderr
        assert 'id="main"' in result.stdout
        assert "hello main" in result.stdout

    def test_class_selector(self, html):
        result = _run_reveal_direct(str(html), ".side")
        assert result.returncode == 0, result.stderr
        assert "sidebar" in result.stdout
