"""BACK-530: every element get_structure() enumerates must be resolvable by the
same by-name path `reveal <file> <name>` uses.

Two code paths enumerate the file's elements by different logic: the structure
walker (get_structure()/--outline) and the by-name extractor
(display.element._extract_by_syntax, the exact resolver the CLI's
`reveal file X` calls). When they drift, an element lists in --outline but
`reveal file X` returns "not found" — a confusing, self-contradicting failure.

BACK-527 was one instance (JS class-field arrow methods). BACK-530 generalises:
a parametrised audit over the in-repo conformance + smoke fixtures asserts the
two paths agree for EVERY enumerated name, closing the whole family instead of
tripping over the next instance. The dedicated tests at the bottom pin the two
known-hard shapes (arrow-const, TS/TSX test-callback labels) directly.

BACK-1411 widened it to the format analyzers (fixtures/formats/: INI sections,
notebook cells, JSONL records, proto/GraphQL/HCL blocks were listed but "not
found", or found as their header line only), to dotted names, and to the
whole listed span -- returning `message User {` alone is not returning User.
"""

from pathlib import Path

import pytest

from reveal.registry import get_analyzer
from reveal.display.element import _parse_element_syntax, _extract_by_syntax, listed_item_line
from reveal.display.structure import _build_extractable_meta

# BACK-1149: component-layer test -- single module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_files():
    """All single-file fixtures under conformance/, smoke/ and formats/."""
    files = []
    for corpus in ("conformance", "smoke", "formats"):
        base = FIXTURES / corpus
        if not base.is_dir():
            continue
        for langdir in sorted(base.iterdir()):
            if not langdir.is_dir():
                continue
            for f in sorted(langdir.iterdir()):
                if f.is_file() and f.suffix and f.name != "expected.yaml":
                    files.append(f)
    return files


def _enumerated_items(analyzer):
    """Every (category, name, line) get_structure() advertises as a nameable
    element -- every category, not just functions/classes/structs (BACK-1400:
    Go `interfaces` were listed but not extractable). Located items only: a
    line-less summary (JSONL's record count) is metadata, not an element."""
    structure = analyzer.get_structure()
    items = []
    for category, elements in structure.items():
        if category == "imports" or not isinstance(elements, list):
            continue
        for element in elements:
            if isinstance(element, dict) and element.get("name"):
                line = listed_item_line(element)
                if line is None:
                    continue
                items.append((category, element["name"], line, element.get("line_end") or line))
    return items


def _names(analyzer):
    return [(category, name) for category, name, _, _ in _enumerated_items(analyzer)]


def _overlaps(start, end, span):
    """Same definition: the outline counts a decorated def from its decorator
    line, extraction from the `def`, so compare spans, not start lines."""
    return start <= span["line_end"] and span["line_start"] <= end


def _build(path: Path):
    cls = get_analyzer(str(path))
    if cls is None:
        return None
    return cls(str(path))


@pytest.mark.parametrize(
    "fixture", _fixture_files(), ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_every_outlined_element_is_resolvable_by_name(fixture):
    """For each fixture, every name in get_structure() resolves via the same
    by-name extractor the CLI uses — no --outline/extraction divergence.

    BACK-1400: resolving is not enough. The listed item must be the element
    returned, or a disclosed candidate when the name is ambiguous. Before,
    `pop` in `A.pop`/`B.pop` "resolved" (to A.pop) while B.pop was silently
    unreachable.
    """
    analyzer = _build(fixture)
    assert analyzer is not None, f"no analyzer for {fixture}"

    unresolved = []
    for category, name, line, line_end in _enumerated_items(analyzer):
        syntax = _parse_element_syntax(name)
        # A name whose text parses as line/ordinal syntax is a position, not a
        # name, by design. Dotted names (`tool.poetry`, `aws_instance.web`)
        # are names the user types as listed, so they are asserted too.
        if syntax["type"] not in ("name", "hierarchical"):
            continue
        result = _extract_by_syntax(analyzer, name, syntax)
        if result is None:
            unresolved.append(f"{category} '{name}'")
            continue
        spans = [result] + result.get("candidates", [])
        hits = [span for span in spans if _overlaps(line, line_end, span)]
        if not hits:
            unresolved.append(f"{category} '{name}' (line {line}: neither returned nor disclosed)")
        elif not any(span["line_end"] >= line_end for span in hits):
            unresolved.append(
                f"{category} '{name}' (listed {line}-{line_end}, returned "
                f"{result['line_start']}-{result['line_end']}: truncated)"
            )

    assert not unresolved, (
        f"{fixture.parent.name}/{fixture.name}: get_structure() enumerated "
        f"{len(unresolved)} element(s) the by-name extractor can't resolve "
        f"(--outline lists them, `reveal file <name>` returns not-found): "
        f"{unresolved}"
    )


@pytest.mark.parametrize(
    "fixture", _fixture_files(), ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_advertised_extraction_examples_extract(fixture):
    """BACK-1411: `--format json` advertises meta.extractable.examples as
    commands that work. Every one of them must -- JSONL advertised its
    line-less '📊 Summary' item and INI/ipynb advertised unreachable names."""
    analyzer = _build(fixture)
    meta = _build_extractable_meta(analyzer.get_structure(), str(fixture))
    failed = []
    for elements in meta["elements"].values():
        for name in elements:
            if _extract_by_syntax(analyzer, name, _parse_element_syntax(name)) is None:
                failed.append(name)
    assert not failed, f"{fixture.parent.name}/{fixture.name}: advertised but not extractable: {failed}"


# ─────────────────── directly pinned divergence shapes ────────────────────

def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


def test_ts_test_callback_labels_resolve(tmp_path):
    """BACK-530 root case: TS/TSX Jest/Vitest describe/test/it callbacks are
    listed by get_structure() under a synthetic `callee(label)` name
    (typescript._extract_test_callbacks, a BACK-334 feature) — that exact
    label must resolve by name too."""
    src = (
        'import { describe, test, beforeEach } from "vitest";\n'
        'describe("outer group", () => {\n'
        '  beforeEach(() => { setup(); });\n'
        '  test("does a thing (with parens)", () => { expect(1).toBe(1); });\n'
        '});\n'
    )
    f = _write(tmp_path, "sample.test.ts", src)
    analyzer = _build(f)

    names = {name for _, name in _names(analyzer)}
    assert 'describe(outer group)' in names
    assert 'test(does a thing (with parens))' in names
    assert 'beforeEach' in names  # no string label → bare callee name

    for label in ('describe(outer group)', 'test(does a thing (with parens))', 'beforeEach'):
        syntax = _parse_element_syntax(label)
        result = _extract_by_syntax(analyzer, label, syntax)
        assert result is not None, f"{label!r} listed in structure but not resolvable"
        assert result['name'] == label


def test_js_class_field_arrow_method_resolves(tmp_path):
    """BACK-527 (the original instance BACK-530 generalises): a JS class-field
    arrow method lists in --outline and must resolve by name."""
    src = (
        'class Widget {\n'
        '  handleClick = (e) => {\n'
        '    return e.target;\n'
        '  }\n'
        '}\n'
    )
    f = _write(tmp_path, "widget.js", src)
    analyzer = _build(f)

    names = {name for _, name in _names(analyzer)}
    assert 'handleClick' in names

    syntax = _parse_element_syntax('handleClick')
    assert _extract_by_syntax(analyzer, 'handleClick', syntax) is not None
