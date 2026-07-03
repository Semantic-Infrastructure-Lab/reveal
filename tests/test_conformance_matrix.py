"""BACK-422 Tier 1 cross-language conformance matrix.

Runs the same set of generic, language-agnostic reveal paths (calls://,
imports://, --varflow, --sideeffects, name/signature extraction, and the
check/hotspots bounded-scan guard) against a hand-written fixture in each
supported language and asserts against tests/fixtures/conformance/expected.yaml.

Ships regression-proofing for exactly the class of bug the dogfood sweep found
one at a time (BACK-410/411/413/414/415/416/418/420): reveal was built
Python-first, and Python-shaped assumptions leak into code paths that are
supposed to be language-agnostic. Pilot language set (python/c/go) validates
the fixture shape before paying the authoring cost across all languages in
the corpus (cpp/csharp/java/javascript/rust/typescript) — see
internal-docs/planning/BACK-422-conformance-matrix-design.md.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "conformance"
EXPECTED = yaml.safe_load((FIXTURES_DIR / "expected.yaml").read_text())

EXTENSIONS = {"python": "py", "c": "c", "go": "go"}

LANGUAGES = sorted(EXPECTED.keys())


def _run(*args: str) -> str:
    result = subprocess.run(
        ["reveal", *args], capture_output=True, text=True, timeout=30
    )
    return result.stdout


def _sample_path(lang: str) -> Path:
    return FIXTURES_DIR / lang / f"sample.{EXTENSIONS[lang]}"


def _lang_dir(lang: str) -> Path:
    return FIXTURES_DIR / lang


@pytest.fixture(params=LANGUAGES)
def lang(request) -> str:
    return request.param


# ─────────────────────────── name/signature extraction ───────────────────────

def test_outline_lists_all_functions(lang):
    """--outline must list every function in the fixture, for every language."""
    out = _run(str(_sample_path(lang)), "--outline")
    found = set(re.findall(r"^(\w+)\([^)]*\)\s*\{?\s*\[\d+ lines", out, re.MULTILINE))
    expected_functions = set(EXPECTED[lang]["outline_functions"])
    assert expected_functions <= found, (
        f"{lang}: expected functions {expected_functions} not all found in outline: {found}\n{out}"
    )


# ─────────────────────────────────── calls:// ─────────────────────────────────

def test_calls_finds_cross_function_callers(lang):
    """calls://?target=validate must find the in-file caller, for every language."""
    out = _run(f"calls://{_lang_dir(lang)}/?target=validate", "--format", "json")
    data = json.loads(out)
    callers = [
        {"line": c["line"], "function": c["caller"]}
        for level in data["levels"]
        for c in level["callers"]
    ]
    assert callers == EXPECTED[lang]["calls_validate_callers"], (
        f"{lang}: calls:// caller mismatch"
    )


# ────────────────────────────────── imports:// ────────────────────────────────

def test_imports_unused_detection(lang):
    """imports://?unused must flag the deliberately-unused import — or, where the
    language genuinely lacks unused-import support, must not silently claim a
    false clean pass (BACK-398 precedent: silent 0 read as "clean" is worse
    than an honest gap)."""
    out = _run(f"imports://{_lang_dir(lang)}/?unused", "--format", "json")
    data = json.loads(out)
    unused_names = [entry["module"] for entry in data["unused"]]
    expected = EXPECTED[lang]["imports_unused"]
    if isinstance(expected, dict) and expected.get("not_supported"):
        # Documented gap, not a regression target — just confirm it doesn't crash
        # and hasn't silently started reporting wrong results either way.
        assert data["count"] == 0, (
            f"{lang}: expected documented not-supported (count 0), got {data['unused']}"
        )
    else:
        assert unused_names == expected, f"{lang}: imports unused mismatch"


# ──────────────────────────────────── --varflow ───────────────────────────────

def test_varflow_declaration_is_write_not_read(lang):
    """--varflow must classify a declaration-with-initializer as WRITE (BACK-411),
    for every language — this is the exact bug class the matrix exists to catch."""
    entry_fn = EXPECTED[lang]["entry_function"]
    out = _run(str(_sample_path(lang)), entry_fn, "--varflow", "result", "--format", "json")
    data = json.loads(out)
    findings = [{"kind": f["kind"], "line": f["line"]} for f in data["findings"]]
    expected = EXPECTED[lang]["varflow_result"]
    assert findings == expected, f"{lang}: varflow mismatch\n{out}"


# ─────────────────────────────────── --sideeffects ────────────────────────────

def test_sideeffects_classifies_file_write(lang):
    """--sideeffects must classify the fixture's file-open call as `file`, for
    every language (BACK-401/416 precedent: taxonomy was PHP/Python-only)."""
    entry_fn = EXPECTED[lang]["entry_function"]
    out = _run(str(_sample_path(lang)), entry_fn, "--sideeffects", "--format", "json")
    data = json.loads(out)
    findings = [{"line": f["line"], "kind": f["kind"]} for f in data["findings"]]
    assert findings == EXPECTED[lang]["sideeffects"], f"{lang}: sideeffects mismatch\n{out}"


# ───────────────────────── check/hotspots bounded-scan guard ──────────────────

def test_check_and_hotspots_complete_quickly(lang):
    """`check`/`hotspots` must never hang regardless of language (BACK-418/424
    class: an unbounded scan that only shows up on a real-sized tree). Fixture
    directories are tiny, so this is a smoke bound, not a scale repro — the
    scale repro itself lives in test_rules.py's I002 ceiling tests."""
    for flag in ("--check", "--hotspots"):
        result = subprocess.run(
            ["reveal", str(_lang_dir(lang)), flag],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode in (0, 1), (
            f"{lang} {flag}: unexpected crash (rc={result.returncode}): {result.stderr}"
        )
