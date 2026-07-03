"""BACK-422 Tier 1 cross-language conformance matrix.

Runs the same set of generic, language-agnostic reveal paths (calls://,
imports://, --varflow, --sideeffects, name/signature extraction, and the
check/hotspots bounded-scan guard) against a hand-written fixture in each
supported language and asserts against tests/fixtures/conformance/expected.yaml.

Ships regression-proofing for exactly the class of bug the dogfood sweep found
one at a time (BACK-410/411/413/414/415/416/418/420): reveal was built
Python-first, and Python-shaped assumptions leak into code paths that are
supposed to be language-agnostic. Full Tier 1 language set (python, c, cpp,
csharp, go, java, javascript, rust, typescript) — see
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

EXTENSIONS = {
    "python": "py", "c": "c", "cpp": "cpp", "csharp": "cs", "go": "go",
    "java": "java", "javascript": "js", "rust": "rs", "typescript": "ts",
}

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
    # Class-bearing languages (java, csharp) nest methods under the class with
    # tree-drawing prefixes (`├─ `/`└─ `); flat-function languages don't.
    found = set(re.findall(r"^(?:[│├└─\s]*)(\w+)\([^)]*\)\s*\{?\s*\[\d+ lines", out, re.MULTILINE))
    expected_functions = set(EXPECTED[lang]["outline_functions"])
    assert expected_functions <= found, (
        f"{lang}: expected functions {expected_functions} not all found in outline: {found}\n{out}"
    )


# ─────────────────────────────────── calls:// ─────────────────────────────────

def test_calls_finds_cross_function_callers(lang):
    """calls://?target=validate must find the in-file caller, for every language."""
    target = EXPECTED[lang].get("validate_function", "validate")
    out = _run(f"calls://{_lang_dir(lang)}/?target={target}", "--format", "json")
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


# ─────────────────────────────────── --exits ──────────────────────────────────

def test_exits_finds_all_returns(lang):
    """--exits must list every return/exit node in entry_function, for every
    language — Tier 2 (BACK-422). Ground truth reflects *current* behavior,
    including two documented, un-fixed gaps found by this test on first
    contact: cpp's macro-hidden return (BACK-421 part 3) and rust's implicit
    `?`/tail-expression returns (BACK-428) are deliberately absent from the
    expected list, not silently passed over."""
    entry_fn = EXPECTED[lang]["entry_function"]
    out = _run(str(_sample_path(lang)), entry_fn, "--exits", "--format", "json")
    data = json.loads(out)
    findings = [{"kind": f["kind"], "line": f["line"]} for f in data["findings"]]
    assert findings == EXPECTED[lang]["exits"], f"{lang}: exits mismatch\n{out}"


# ─────────────────────────────────── --returns ─────────────────────────────────

def test_returns_finds_gate_chains(lang):
    """--returns must list every return with its enclosing if-condition gate
    chain, for every language — Tier 2 (BACK-422). A return inside a
    try/catch (not an if) correctly has an empty gate chain; only c/cpp/go's
    if-gated early returns have non-empty gates."""
    entry_fn = EXPECTED[lang]["entry_function"]
    out = _run(str(_sample_path(lang)), entry_fn, "--returns", "--format", "json")
    data = json.loads(out)
    findings = [
        {"line": f["line"], "gate_lines": [g["line"] for g in f["gates"]]}
        for f in data["findings"]
    ]
    assert findings == EXPECTED[lang]["returns"], f"{lang}: returns mismatch\n{out}"


# ──────────────────────────────────── --deps ───────────────────────────────────

def test_deps_finds_parameter_flowing_in(lang):
    """--deps must list every variable whose first event in entry_function is
    a READ (i.e. it flows in from outside) — every fixture's `order` parameter
    qualifies in every language, since it's read before ever being written."""
    entry_fn = EXPECTED[lang]["entry_function"]
    out = _run(str(_sample_path(lang)), entry_fn, "--deps", "--format", "json")
    data = json.loads(out)
    dep_vars = {f["var"] for f in data["findings"]}
    assert "order" in dep_vars, f"{lang}: 'order' param not found as a dep\n{out}"


# ─────────────────────────────────── --flowto ──────────────────────────────────

def test_flowto_reachability_verdict(lang):
    """--flowto reports exit nodes reachable within a line range — feeding it
    a range ending exactly on a known exit line must surface that exit
    (BLOCKED-equivalent); a range ending before any exit must be empty
    (CLEAR-equivalent). Reuses the exits ground truth as the range boundary,
    since flowto's JSON findings are exits-within-range, and the text-mode
    verdict is a rendering of exactly that."""
    entry_fn = EXPECTED[lang]["entry_function"]
    first_exit_line = EXPECTED[lang]["exits"][0]["line"]
    out = _run(
        str(_sample_path(lang)), entry_fn, "--flowto",
        "--range", f"1-{first_exit_line}", "--format", "json",
    )
    data = json.loads(out)
    lines_found = [f["line"] for f in data["findings"]]
    assert first_exit_line in lines_found, (
        f"{lang}: flowto range ending on exit line {first_exit_line} found no exit\n{out}"
    )


# ─────────────────────────────── --cross-calls (BACK-429) ─────────────────────

def test_cross_calls_varflow_json_does_not_crash(lang):
    """--varflow VAR --cross-calls --format json must not crash (BACK-429:
    cross_var_flow's frame events carried a raw tree-sitter Node object that
    was never stripped before JSON serialization, unlike the plain --varflow
    path — every language crashed with `TypeError: Object of type Node is not
    JSON serializable`). The root frame's events must match the plain
    --varflow result exactly."""
    entry_fn = EXPECTED[lang]["entry_function"]
    out = _run(
        str(_sample_path(lang)), entry_fn, "--varflow", "result",
        "--cross-calls", "--format", "json",
    )
    data = json.loads(out)  # raises if BACK-429 regresses
    root_frame = data["findings"][0]
    events = [{"kind": e["kind"], "line": e["line"]} for e in root_frame["events"]]
    assert events == EXPECTED[lang]["varflow_result"], f"{lang}: cross-calls root frame mismatch\n{out}"


# ─────────────────────────────────── --ifmap ──────────────────────────────────

def test_ifmap_finds_if_branches(lang):
    """--ifmap must list every if/elif/else branch in entry_function — or,
    where the fixture's entry_function genuinely has no bare if (it uses
    try/catch instead), assert the documented not-supported shape rather than
    silently passing on an empty list (BACK-398 precedent)."""
    entry_fn = EXPECTED[lang]["entry_function"]
    out = _run(str(_sample_path(lang)), entry_fn, "--ifmap", "--format", "json")
    data = json.loads(out)
    expected = EXPECTED[lang]["ifmap"]
    if isinstance(expected, dict) and expected.get("not_supported"):
        assert data["findings"] == [], (
            f"{lang}: expected no bare-if branches, got {data['findings']}"
        )
    else:
        findings = [{"keyword": f["keyword"], "line_start": f["line_start"]} for f in data["findings"]]
        assert findings == expected, f"{lang}: ifmap mismatch\n{out}"


# ────────────────────────────────── --catchmap ─────────────────────────────────

def test_catchmap_finds_try_catch(lang):
    """--catchmap must list every try/catch/except branch in entry_function —
    or, where the language genuinely has no try/catch construct (c/cpp/go/
    rust use return-code or Result-based error handling), assert the
    documented not-supported shape."""
    entry_fn = EXPECTED[lang]["entry_function"]
    out = _run(str(_sample_path(lang)), entry_fn, "--catchmap", "--format", "json")
    data = json.loads(out)
    expected = EXPECTED[lang]["catchmap"]
    if isinstance(expected, dict) and expected.get("not_supported"):
        assert data["findings"] == [], (
            f"{lang}: expected no try/catch branches, got {data['findings']}"
        )
    else:
        findings = [{"keyword": f["keyword"], "line_start": f["line_start"]} for f in data["findings"]]
        assert findings == expected, f"{lang}: catchmap mismatch\n{out}"


# ────────────────────────────────── --mutations ────────────────────────────────

def test_mutations_finds_read_after_write(lang):
    """--mutations is range-scoped: it flags a variable written inside the
    given range and read after the range ends (a potential return value).
    Passing a whole function is always empty by design (nothing is "after"
    the function) — so this probes a single-line range at the fixture's
    `result = validate(...)` write and checks the flagged next-read line."""
    probe = EXPECTED[lang]["mutations_probe"]
    out = _run(str(_sample_path(lang)), f":{probe['range']}", "--mutations", "--format", "json")
    data = json.loads(out)
    match = next((m for m in data["findings"] if m["var"] == probe["var"]), None)
    assert match is not None, f"{lang}: no mutation found for {probe['var']}\n{out}"
    assert match["next_read_line"] == probe["next_read_line"], (
        f"{lang}: mutations next_read_line mismatch\n{out}"
    )


# ───────────────────── BACK-427 (remaining): Rust loop/match ──────────────────

def test_rust_outline_recognizes_expression_oriented_control_flow():
    """Not parametrized across `lang` — this closes the part of BACK-427 left
    open when `if_expression` was fixed: Rust's `while`/`for`/`match` are also
    `_expression` nodes (`while_expression`/`for_expression`/
    `match_expression`/`match_arm`), not `_statement`/`_clause`, and were
    completely invisible to --outline (a Rust function with a while/for/match
    showed nothing but its own signature). Uses a dedicated `count_down`
    function in the rust fixture rather than process_order, so the line
    numbers backing every other rust assertion in this file don't shift."""
    out = _run(str(_sample_path("rust")), "count_down", "--outline", "--format", "json")
    data = json.loads(out)
    keywords = [f["keyword"] for f in data["findings"]]
    assert keywords == ["WHILE", "FOR", "MATCH", "CASE", "CASE"], (
        f"rust: count_down outline keywords mismatch\n{out}"
    )


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
