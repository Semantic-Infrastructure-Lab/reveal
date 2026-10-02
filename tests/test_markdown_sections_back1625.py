"""BACK-1625: markdown section extraction through one heading matcher.

A census of 1,564 real `reveal doc.md "Heading"` calls found extraction almost
never misses, but these inputs went wrong: a `## ` prefix and `--outline`
always missed; a miss gave a code-only hint and no heading suggestions; `:N`
past the end returned the last section; headings that read as a line number
or an ordinal were unreachable; a heading's own child printed twice; `A|B`
dropped a repeated heading silently (the two matchers disagreed).
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from conftest import _run_reveal_direct  # noqa: E402

from reveal.analyzers.markdown import MarkdownAnalyzer  # noqa: E402

pytestmark = pytest.mark.cli


_DOC = """\
# Title

Intro.

## Setup

Setup body.

### Setup details

Nested body.

## Install

```bash
## Not a heading
```

## See [the docs](other.md) here

Link body.

## Closing hashes ##

Closing body.

## Entities &amp; stuff

Entity body.

## 2026

Year body.

## Phase:1

Phase body.

## Label

## Setup

Second setup.

## Last
Last body.
"""


@pytest.fixture
def doc(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(_DOC, encoding='utf-8')
    return p


@pytest.fixture
def analyzer(doc):
    return MarkdownAnalyzer(str(doc))


def _section_line(name: str) -> int:
    return _DOC.splitlines().index(name) + 1


class TestOneMatcher:
    def test_hash_prefixed_query_matches_the_heading(self, analyzer):
        result = analyzer.extract_element('section', '## Install')
        assert result['line_start'] == _section_line('## Install')

    def test_link_entity_and_closing_hashes_match_visible_text(self, analyzer):
        assert analyzer.extract_element('section', 'See the docs here')['line_start'] == \
            _section_line('## See [the docs](other.md) here')
        assert analyzer.extract_element('section', 'Entities & stuff')['line_start'] == \
            _section_line('## Entities &amp; stuff')
        # Exact, not substring: the closing sequence is not part of the title
        assert ('Closing hashes', ) == tuple(
            t for _, _, t in analyzer._heading_index() if t.startswith('Closing'))

    def test_nested_substring_match_is_not_repeated(self, analyzer):
        # 'Setup' substring: '## Setup' (twice) and its own '### Setup details'
        result = analyzer.extract_element('section', 'etup')
        assert result['source'].count('Nested body.') == 1
        assert [s['line_start'] for s in result['sections']] == [
            _section_line('## Setup'), len(_DOC.splitlines()) - 5]

    def test_alternation_discloses_a_repeated_heading(self, analyzer):
        result = analyzer.extract_element('section', 'Setup|Last')
        candidates = result['term_candidates']['Setup']
        assert [c['selected'] for c in candidates] == [True, False]
        assert len(result['sections']) == 2

    def test_each_section_carries_its_heading(self, analyzer):
        result = analyzer.extract_element('section', 'Install|Last')
        assert [s['heading'] for s in result['sections']] == ['Install', 'Last']

    def test_label_only_is_a_section_without_body(self, analyzer):
        assert analyzer.extract_element('section', 'Label').get('label_only') is True
        assert 'label_only' not in analyzer.extract_element('section', 'Last')


class TestCLIRouting:
    def test_numeric_heading_wins_over_line_number(self, doc):
        result = _run_reveal_direct(str(doc), "2026")
        assert result.returncode == 0, result.stderr
        assert "Year body." in result.stdout

    def test_ordinal_shaped_heading_wins_over_ordinal(self, doc):
        result = _run_reveal_direct(str(doc), "Phase:1")
        assert result.returncode == 0, result.stderr
        assert "Phase body." in result.stdout

    def test_explicit_line_past_end_is_an_error(self, doc):
        result = _run_reveal_direct(str(doc), ":500")
        assert result.returncode == 1
        assert "past the end" in result.stderr
        assert "Last body." not in result.stdout

    def test_bare_number_past_end_is_an_error(self, doc):
        result = _run_reveal_direct(str(doc), "500")
        assert result.returncode == 1
        assert "past the end" in result.stderr

    def test_miss_suggests_headings_not_code_names(self, doc):
        result = _run_reveal_direct(str(doc), "Instal1")
        assert result.returncode == 1
        assert "Code extraction" not in result.stderr
        assert "substring" in result.stderr
        assert "Did you mean: Install?" in result.stderr

    def test_outline_on_a_section_lists_its_headings(self, doc):
        result = _run_reveal_direct(str(doc), "Title", "--outline")
        assert result.returncode == 0, result.stderr
        assert "Setup details" in result.stdout
        assert "Setup body." not in result.stdout  # headings, not text

    def test_outline_on_a_section_json(self, doc):
        result = _run_reveal_direct(str(doc), "Setup", "--outline", "--format", "json")
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert [h['name'] for h in data['headings']] == ['Setup', 'Setup details']

    def test_outline_on_a_missing_section_errors(self, doc):
        result = _run_reveal_direct(str(doc), "Nope", "--outline")
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_short_section_with_body_is_not_called_a_label(self, doc):
        result = _run_reveal_direct(str(doc), "Closing hashes")  # 4 lines, with a body
        assert result.returncode == 0, result.stderr
        assert "label only" not in result.stderr
        result = _run_reveal_direct(str(doc), "Label")
        assert "label only" in result.stderr
