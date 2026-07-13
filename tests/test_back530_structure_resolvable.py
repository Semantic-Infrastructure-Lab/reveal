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
"""

from pathlib import Path

import pytest

from reveal.registry import get_analyzer
from reveal.display.element import _parse_element_syntax, _extract_by_syntax

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_files():
    """All single-file language fixtures under conformance/ and smoke/."""
    files = []
    for corpus in ("conformance", "smoke"):
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


def _enumerated_names(analyzer):
    """Every name get_structure() advertises as a nameable element."""
    structure = analyzer.get_structure()
    names = []
    for category in ("functions", "classes", "structs"):
        for element in structure.get(category, []):
            name = element.get("name")
            if name:
                names.append((category, name))
    return names


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
    by-name extractor the CLI uses — no --outline/extraction divergence."""
    analyzer = _build(fixture)
    assert analyzer is not None, f"no analyzer for {fixture}"

    unresolved = []
    for category, name in _enumerated_names(analyzer):
        syntax = _parse_element_syntax(name)
        # A name whose text parses as line/ordinal/hierarchical syntax routes
        # through a different extraction strategy by design — the divergence
        # this test guards is the bare name-based path, so only assert there.
        if syntax["type"] != "name":
            continue
        if _extract_by_syntax(analyzer, name, syntax) is None:
            unresolved.append(f"{category} '{name}'")

    assert not unresolved, (
        f"{fixture.parent.name}/{fixture.name}: get_structure() enumerated "
        f"{len(unresolved)} element(s) the by-name extractor can't resolve "
        f"(--outline lists them, `reveal file <name>` returns not-found): "
        f"{unresolved}"
    )


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

    names = {name for _, name in _enumerated_names(analyzer)}
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

    names = {name for _, name in _enumerated_names(analyzer)}
    assert 'handleClick' in names

    syntax = _parse_element_syntax('handleClick')
    assert _extract_by_syntax(analyzer, 'handleClick', syntax) is not None
