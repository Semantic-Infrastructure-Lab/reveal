"""BACK-431 Issue G — smoke tier for full-analysis languages outside the
Tier 1/2 conformance matrix (tests/test_conformance_matrix.py, 9 languages).

reveal advertises 67 "Explicit Analyzers — full analysis" languages; the
conformance matrix's fixture-per-language x expected.yaml ground truth only
covers 9 of them. Every nav flag routes through the same generic engine for
the other 58, with zero verification. This is not "add 58 fixture languages"
— it's a cheap bound: one ~20-line fixture per language, asserting only that
every nav flag produces non-empty, non-crashing output. That's what catches
BACK-427-class total blindness (a flag silently returning nothing for an
entire language) at ~30 minutes per language, reserving full expected.yaml
ground truth for languages that earn it by usage.

Priority order (popularity x predicted-breakage, from
internal-docs/design/MULTI_LANGUAGE_ARCHITECTURE_2026-07-03.md's Issue G):
Kotlin, Swift, Ruby, PHP, Scala — all expression-oriented or statement-
modifier grammars, the exact shape that already broke Rust (BACK-427/430).
This first pass found and fixed three: Swift's entire --varflow was blind
(identifiers parse as `simple_identifier`, never matched); Kotlin and Scala
declarations (`property_declaration` / `val_definition`) were tracked but
mislabeled WRITE-as-READ; Scala's `throw` (`throw_expression`) was invisible
to --exits/--returns. See node_taxonomy.py and nav_varflow.py for the fixes.
"""

import json
from pathlib import Path

import pytest
from conftest import _run_reveal_direct

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "smoke"

# validate()/run() are named identically in every fixture; processOrder is
# camelCase or snake_case per language convention (matching the existing
# conformance-matrix fixtures' approach of respecting per-language idiom
# rather than forcing one naming scheme). `var` is the name --varflow should
# track inside the process function — PHP requires its `$` sigil (BACK-203,
# a deliberate, tested convention — see TestPhpVarflow in
# tests/adapters/test_ast_nav_probe_features.py).
LANGUAGES = {
    "kotlin": {"ext": "kt", "process": "processOrder", "var": "result"},
    "swift": {"ext": "swift", "process": "processOrder", "var": "result"},
    "ruby": {"ext": "rb", "process": "process_order", "var": "result"},
    "php": {"ext": "php", "process": "processOrder", "var": "$result"},
    "scala": {"ext": "scala", "process": "processOrder", "var": "result"},
}


def _sample_path(lang: str) -> Path:
    info = LANGUAGES[lang]
    return FIXTURES_DIR / lang / f"sample.{info['ext']}"


def _run(*args: str):
    return _run_reveal_direct(*args)


@pytest.fixture(params=sorted(LANGUAGES))
def lang(request) -> str:
    return request.param


def _assert_sane(result, desc: str) -> None:
    """Smoke bar: no crash, no unhandled traceback. Not "correct output" —
    that's the full conformance matrix's job for languages that earn it."""
    assert result.returncode in (0, 1), (
        f"{desc}: unexpected crash (rc={result.returncode}): {result.stderr}"
    )
    assert "Traceback (most recent call last)" not in result.stderr, (
        f"{desc}: unhandled exception:\n{result.stderr}"
    )


def test_outline_lists_functions(lang):
    info = LANGUAGES[lang]
    result = _run(str(_sample_path(lang)), "--outline")
    _assert_sane(result, f"{lang} --outline")
    assert "validate" in result.stdout
    assert info["process"] in result.stdout
    assert "run" in result.stdout


def test_varflow_non_empty(lang):
    info = LANGUAGES[lang]
    result = _run(str(_sample_path(lang)), info["process"], "--varflow", info["var"])
    _assert_sane(result, f"{lang} --varflow")
    assert result.stdout.strip(), f"{lang}: --varflow produced no output at all"
    assert "WRITE" in result.stdout or "READ" in result.stdout, (
        f"{lang}: --varflow found no read/write events for a variable declared "
        f"and used in-range:\n{result.stdout}"
    )


def test_exits_non_crash(lang):
    result = _run(str(_sample_path(lang)), "validate", "--exits")
    _assert_sane(result, f"{lang} --exits")
    assert result.stdout.strip()


def test_returns_non_crash(lang):
    result = _run(str(_sample_path(lang)), "validate", "--returns")
    _assert_sane(result, f"{lang} --returns")
    assert result.stdout.strip()


def test_ifmap_non_crash(lang):
    result = _run(str(_sample_path(lang)), "validate", "--ifmap")
    _assert_sane(result, f"{lang} --ifmap")
    assert result.stdout.strip()


def test_cross_calls_non_crash(lang):
    info = LANGUAGES[lang]
    result = _run(
        str(_sample_path(lang)), info["process"], "--varflow", info["var"], "--cross-calls"
    )
    _assert_sane(result, f"{lang} --cross-calls")
    assert result.stdout.strip()


def test_calls_uri_non_crash(lang):
    result = _run(f"calls://{_sample_path(lang)}?target=validate", "--format", "json")
    _assert_sane(result, f"{lang} calls://")
    json.loads(result.stdout)  # must be valid JSON, not a crash dump


def test_check_and_hotspots_non_crash(lang):
    """Bounded-scan guard (BACK-338/418's disease) — smoke-level only, not
    full conformance; see test_conformance_matrix.py's version of this test
    for the 9 matrix languages, which also pins the ceiling env var."""
    for flag in ("--check", "--hotspots"):
        result = _run(str(_sample_path(lang).parent), flag)
        _assert_sane(result, f"{lang} {flag}")
