"""BACK-1411: `reveal <file> NAME` on the format analyzers.

The outline listed INI sections, notebook cells and JSONL records that
`reveal file NAME` answered "not found"; proto/GraphQL/HCL blocks resolved to
their header line only (`message User {`), because their outline items had no
line_end; XML had a tag lookup the CLI never reached. The by-name invariant in
test_back530_structure_resolvable.py covers "listed => extractable" over
fixtures/formats/; these tests pin the exact spans and the format-specific
shapes (decoded cells, multi-match sections).
"""

import json
from pathlib import Path

import pytest

from reveal.display.element import _extract_by_syntax, _parse_element_syntax
from reveal.registry import get_analyzer

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component

FORMATS = Path(__file__).parent / "fixtures" / "formats"


def _extract(path: Path, name: str):
    analyzer = get_analyzer(str(path))(str(path))
    return _extract_by_syntax(analyzer, name, _parse_element_syntax(name))


def _span(result):
    return result['line_start'], result['line_end']


@pytest.mark.parametrize("fixture, name, span", [
    ("protobuf/sample.proto", "Timestamp", (6, 9)),
    ("protobuf/sample.proto", "User", (11, 17)),
    ("protobuf/sample.proto", "Address", (13, 15)),
    ("protobuf/sample.proto", "Color", (19, 22)),
    ("protobuf/sample.proto", "UserService", (24, 27)),
    ("protobuf/sample.proto", "GetUser", (25, 25)),
    ("graphql/sample.graphql", "User", (6, 9)),
    ("graphql/sample.graphql", "Role", (11, 14)),
    ("graphql/sample.graphql", "UserInput", (16, 18)),
    ("hcl/sample.tf", "aws_instance.web", (9, 12)),
    ("hcl/sample.tf", "region", (1, 3)),
    ("ini/sample.ini", "database", (1, 3)),
    ("ini/sample.ini", "server", (6, 8)),
    ("systemd/sample.service", "Service", (5, 7)),
    ("jsonl/sample.jsonl", "event #2", (2, 2)),
    ("xml/pom.xml", "dependencies", (4, 9)),
    ("xml/pom.xml", "plugins", (11, 11)),
])
def test_block_extracts_whole_span(fixture, name, span):
    result = _extract(FORMATS / fixture, name)
    assert result is not None, f"{fixture}: {name} not found"
    assert _span(result) == span


def test_ini_section_drops_trailing_blank_lines_keeps_comments():
    source = _extract(FORMATS / "ini/sample.ini", "server")['source']
    assert source.splitlines() == ["[server]", "listen = 0.0.0.0", "; trailing comment"]


def test_notebook_cell_is_its_decoded_source_on_its_own_lines():
    """nbformat's layout: one source string per JSON line, so the decoded
    code is numbered by exactly the lines it sits on."""
    path = FORMATS / "jupyter/sample.ipynb"
    result = _extract(path, "Code [1]: import pandas as pd")
    assert result['source'] == "import pandas as pd\ndef load(path):\n    return pd.read_csv(path)"
    lines = path.read_text(encoding='utf-8').splitlines()
    first, last = _span(result)
    assert [json.loads(line.strip().rstrip(',')) for line in lines[first - 1:last]] == [
        "import pandas as pd\n", "def load(path):\n", "    return pd.read_csv(path)\n",
    ]


def test_compact_notebook_cell_falls_back_to_its_json_line():
    """No one-string-per-line layout: the raw line holding the cell, never
    decoded source under invented line numbers."""
    result = _extract(FORMATS / "jupyter/compact.ipynb", "# Analysis")
    assert _span(result) == (2, 2)
    assert '"cell_type": "markdown"' in result['source']


def test_same_named_notebook_cells_are_disclosed(tmp_path):
    notebook = json.loads((FORMATS / "jupyter/sample.ipynb").read_text(encoding='utf-8'))
    duplicate = dict(notebook['cells'][1], id="dup")
    notebook['cells'].append(duplicate)
    path = tmp_path / "dup.ipynb"
    path.write_text(json.dumps(notebook, indent=1, sort_keys=True), encoding='utf-8')
    result = _extract(path, "Code [1]: import pandas as pd")
    assert len(result['candidates']) == 2
    assert [c['selected'] for c in result['candidates']] == [True, False]


def test_jsonl_type_filter_returns_each_record_on_its_real_line():
    """`reveal f.jsonl user` (documented type filter) was unreachable from the
    CLI; its pretty-printed dump would have been numbered from the first
    match's line, inventing line numbers."""
    result = _extract(FORMATS / "jsonl/sample.jsonl", "user")
    assert result['name'] == "user records (2 total)"
    assert [(s['line_start'], s['source']) for s in result['sections']] == [
        (1, '{"type":"user","n":"Alice"}'),
        (3, '{"type":"user","n":"Bob"}'),
    ]


def test_jsonl_summary_is_not_advertised_or_extracted():
    result = _extract(FORMATS / "jsonl/sample.jsonl", "📊 Summary: 3 records")
    assert result is None


def test_xml_repeated_tag_returns_every_element(tmp_path):
    path = tmp_path / "doc.xml"
    path.write_text(
        '<root xmlns:xs="urn:x">\n'
        '  <xs:item n="1">\n'
        '    <v>1</v>\n'
        '  </xs:item>\n'
        '  <xs:item n="2"/>\n'
        '</root>\n',
        encoding='utf-8',
    )
    result = _extract(path, "item")
    assert result['name'] == "item (2 elements)"
    assert [(s['line_start'], s['line_end']) for s in result['sections']] == [(2, 4), (5, 5)]
    assert _extract(path, "xs:item")['sections'] == result['sections']


def test_xml_unknown_tag_and_malformed_file_are_not_found(tmp_path):
    assert _extract(FORMATS / "xml/pom.xml", "nosuch") is None
    broken = tmp_path / "broken.xml"
    broken.write_text("<root><a></root>\n", encoding='utf-8')
    assert _extract(broken, "a") is None


def test_repeated_markdown_heading_is_disclosed():
    """Exact heading match stopped at the first: every later '## Setup' (every
    release's '### Fixed' in a changelog) was unreachable and undisclosed."""
    result = _extract(FORMATS / "markdown/sample.md", "Setup")
    assert _span(result) == (3, 6)
    assert [(c['line_start'], c['address'], c['selected']) for c in result['candidates']] == [
        (3, ':3-6', True), (11, ':11-13', False),
    ]


def test_ambiguity_note_caps_listed_addresses():
    from reveal.element_resolve import ambiguity_note
    candidates = [{'name': 'Fixed', 'line_start': n, 'line_end': n + 1, 'address': f':{n}-{n + 1}',
                   'selected': n == 1} for n in range(1, 30, 2)]
    lines = ambiguity_note("CHANGELOG.md", "Code [1]: x", candidates)
    assert len(lines) == 1 + 10 + 1
    assert lines[-1] == "  ... and 5 more (all of them: reveal CHANGELOG.md 'Code [1]: x' --format json)"


@pytest.mark.parametrize("fixture, name, starts", [
    ("jsonl/sample.jsonl", "user", [1, 3]),
    ("markdown/sample.md", "Setup|setup.py notes", [3, 7]),
])
def test_mcp_numbers_each_span_from_its_own_line(fixture, name, starts):
    """reveal_element numbered the joined source from the first span's start,
    so every later span showed invented line numbers."""
    from reveal.mcp_server import reveal_element
    path = FORMATS / fixture
    out = reveal_element(str(path), name)
    lines = path.read_text(encoding='utf-8').splitlines()
    for start in starts:
        assert f"{start:>6}  {lines[start - 1]}" in out


def test_jsonl_non_string_type_and_non_object_records_do_not_crash(tmp_path):
    """Meilisearch's dump updates.jsonl has an object-valued "type": the
    outline raised 'unhashable type: dict'; a top-level array line would
    have raised AttributeError."""
    path = tmp_path / "odd.jsonl"
    path.write_text('[1, 2]\n"str"\n{"type": {"name": "Settings"}}\n{"type": "x"}\n', encoding='utf-8')
    analyzer = get_analyzer(str(path))(str(path))
    names = [r['name'] for r in analyzer.get_structure()['records']]
    assert names == ['📊 Summary: 4 records', 'record #1', 'record #2', 'record #3', 'x #4']
    assert _span(_extract(path, "x")) == (4, 4)
