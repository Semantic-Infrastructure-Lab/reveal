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
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import _run_reveal_direct

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "conformance"
EXPECTED = yaml.safe_load((FIXTURES_DIR / "expected.yaml").read_text())

EXTENSIONS = {
    "python": "py", "c": "c", "cpp": "cpp", "csharp": "cs", "go": "go",
    "java": "java", "javascript": "js", "rust": "rs", "typescript": "ts",
    "kotlin": "kt", "swift": "swift", "ruby": "rb", "php": "php",
}

LANGUAGES = sorted(EXPECTED.keys())


def _run(*args: str) -> str:
    result = _run_reveal_direct(*args)
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
    # Signature trailer varies by language: most (rust/go/c#/...) render
    # `name(args) [N lines...`, but Kotlin/Swift keep the arrow return type and
    # opening brace (`name(args) -> Type { [N lines...`) — match anything
    # between the args and the `[N lines` marker rather than assuming either
    # shape (found via BACK-477-successor fixture work, Kotlin/Swift matrix).
    found = set(re.findall(r"^(?:[│├└─\s]*)(\w+)\([^)]*\)[^\[\n]*\[\d+ lines", out, re.MULTILINE))
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


# ──────────────────────── reveal architecture (fan-in/out) ─────────────────────
#
# BACK-487/488: the high-level DD command `reveal architecture` depends on
# file-level import→file edges. Before, only Python/JS/TS/Go/Rust produced a
# real fan-in/fan-out graph; Java/PHP/Ruby got listing-but-no-edges and
# Swift/Kotlin got nothing at all, so `architecture` returned a bare directory
# listing (no entry points, no core abstractions) for half the matrix. These
# tiny 2-file projects pin that every graph-backed language resolves a
# same-project edge into the architecture brief.

# (importer_rel, importer_src, imported_rel, imported_src)
_EDGE_PROJECTS = {
    "java": (
        "com/app/Main.java", "package com.app;\nimport com.app.util.Helper;\npublic class Main { void run(){ new Helper(); } }\n",
        "com/app/util/Helper.java", "package com.app.util;\npublic class Helper {}\n",
    ),
    "php": (
        "src/Ctrl/Home.php", "<?php\nnamespace App\\Ctrl;\nuse App\\Models\\User;\nclass Home { function f(){ new User(); } }\n",
        "src/Models/User.php", "<?php\nnamespace App\\Models;\nclass User {}\n",
    ),
    "ruby": (
        "lib/main.rb", "require_relative 'helper'\nHelper.go\n",
        "lib/helper.rb", "module Helper\n  def self.go; end\nend\n",
    ),
    "kotlin": (
        "app/com/foo/Main.kt", "package com.foo\nimport com.foo.Bar\nfun main() { Bar() }\n",
        "app/com/foo/Bar.kt", "package com.foo\nclass Bar\n",
    ),
    "swift": (
        "Sources/Main.swift", "import Helper\nfunc run() { _ = Helper() }\n",
        "Sources/Helper.swift", "struct Helper {}\n",
    ),
    "c": (
        "main.c", "#include \"helper.h\"\nint main(){ return 0; }\n",
        "helper.h", "int helper(void);\n",
    ),
    "cpp": (
        "main.cpp", "#include \"engine.hpp\"\nint main(){ return 0; }\n",
        "engine.hpp", "struct Engine {};\n",
    ),
}

EDGE_LANGUAGES = sorted(_EDGE_PROJECTS)


@pytest.mark.parametrize("edge_lang", EDGE_LANGUAGES)
def test_architecture_resolves_same_project_edge(edge_lang, tmp_path):
    """`reveal architecture` must surface a resolved intra-project dependency as
    a fan-out entry point AND a fan-in core abstraction, for every graph-backed
    language (BACK-487/488)."""
    importer_rel, importer_src, imported_rel, imported_src = _EDGE_PROJECTS[edge_lang]
    for rel, src in ((importer_rel, importer_src), (imported_rel, imported_src)):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)

    out = _run("architecture", str(tmp_path), "--format", "json")
    facts = json.loads(out)["facts"]

    importer_name = Path(importer_rel).name
    imported_name = Path(imported_rel).name

    entry_points = {Path(e["file"]).name: e for e in facts["entry_points"]}
    core = {Path(e["file"]).name: e for e in facts["core_abstractions"]}

    assert importer_name in entry_points, (
        f"{edge_lang}: importer {importer_name} not an entry point — edge unresolved\n{out}"
    )
    assert entry_points[importer_name]["fan_out"] >= 1
    assert imported_name in core, (
        f"{edge_lang}: imported {imported_name} not a core abstraction — edge unresolved\n{out}"
    )
    assert core[imported_name]["fan_in"] >= 1


# ──────────────────────────────────── --varflow ───────────────────────────────

def test_varflow_declaration_is_write_not_read(lang):
    """--varflow must classify a declaration-with-initializer as WRITE (BACK-411),
    for every language — this is the exact bug class the matrix exists to catch.

    Most languages spell the fixture's variable as bare `result`; PHP always
    requires the `$` sigil in both source and query (`expected.yaml`'s
    `varflow_var` overrides the default for it) — querying bare `result` for
    PHP is a correct non-match, not a bug (see BACK-477 progress log)."""
    entry_fn = EXPECTED[lang]["entry_function"]
    var = EXPECTED[lang].get("varflow_var", "result")
    out = _run(str(_sample_path(lang)), entry_fn, "--varflow", var, "--format", "json")
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
    qualifies in every language, since it's read before ever being written.

    PHP always spells its parameter `$order` (the same `$`-sigil rule that
    motivates `varflow_var` — see BACK-477 progress log)."""
    entry_fn = EXPECTED[lang]["entry_function"]
    order_var = EXPECTED[lang].get("deps_var", "order")
    out = _run(str(_sample_path(lang)), entry_fn, "--deps", "--format", "json")
    data = json.loads(out)
    dep_vars = {f["var"] for f in data["findings"]}
    assert order_var in dep_vars, f"{lang}: '{order_var}' param not found as a dep\n{out}"


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
    var = EXPECTED[lang].get("varflow_var", "result")
    out = _run(
        str(_sample_path(lang)), entry_fn, "--varflow", var,
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


# ─────────────────────────────────── --loopmap ─────────────────────────────────

def test_loopmap_finds_loop(lang):
    """--loopmap must find the fixture's Batch loop, for every language.

    Uses a dedicated `Batch` type added standalone to each fixture (BACK-439b/c
    conformance-matrix pass), not the shared entry_function — same precedent
    as Rust's count_down (BACK-427/430): a loop + field write + call effect
    that doesn't disturb any existing line-numbered assertion. Named
    Class.method extraction fails for cpp/go (BACK-451, filed not fixed);
    their batch_element is a :LINE-RANGE workaround instead."""
    element = EXPECTED[lang]["batch_element"]
    out = _run(str(_sample_path(lang)), element, "--loopmap", "--format", "json")
    data = json.loads(out)
    findings = [{"keyword": f["keyword"], "line_start": f["line_start"]} for f in data["findings"]]
    assert findings == EXPECTED[lang]["loopmap"], f"{lang}: loopmap mismatch\n{out}"


# ─────────────────────────────────── --fanout ──────────────────────────────────

def test_fanout_classifies_effect_inside_loop(lang):
    """--fanout must pair the Batch loop with its classified `cache.set(...)`
    call effect, for every language."""
    element = EXPECTED[lang]["batch_element"]
    out = _run(str(_sample_path(lang)), element, "--fanout", "--format", "json")
    data = json.loads(out)
    assert len(data["findings"]) == 1, f"{lang}: expected exactly one loop\n{out}"
    effects = [{"line": e["line"], "kind": e["kind"]} for e in data["findings"][0]["effects"]]
    assert effects == EXPECTED[lang]["fanout_effects"], f"{lang}: fanout mismatch\n{out}"


# ───────────────────────────────── --statewrites ───────────────────────────────

def test_statewrites_classifies_field_and_call(lang):
    """--statewrites must find the Batch field write (self/this/pointer-receiver,
    a distinct tree-sitter node kind per language — BACK-439c) plus the merged
    call-based cache write, for every language."""
    element = EXPECTED[lang]["batch_element"]
    out = _run(str(_sample_path(lang)), element, "--statewrites", "--format", "json")
    data = json.loads(out)
    findings = [{"kind": f["kind"], "line": f["line"]} for f in data["findings"]]
    assert findings == EXPECTED[lang]["statewrites"], f"{lang}: statewrites mismatch\n{out}"


# ─────────────────── BACK-450: C++ for_range_loop --varflow dispatch ──────────

def test_cpp_for_range_loop_classifies_declarator_as_write():
    """--varflow must classify a C++ range-based for loop's declarator
    (`for (int item : items)`) as WRITE, not READ.

    `for_range_loop`'s field shape (declarator=loop var, right=iterable) was
    added to node_taxonomy.py's SCOPE_NODES/GATE_NODES/KEYWORD_LABEL during
    the BACK-439b/c conformance-matrix pass, but nav_varflow.py's dispatch
    table had no branch for it — the loop var fell through to the generic
    child walk and was misread as a bare READ. Confirmed to fail pre-fix
    (line 42 reported as READ instead of WRITE)."""
    element = EXPECTED["cpp"]["batch_element"]
    out = _run(str(_sample_path("cpp")), element, "--varflow", "item", "--format", "json")
    data = json.loads(out)
    findings = [{"kind": f["kind"], "line": f["line"]} for f in data["findings"]]
    assert findings == [
        {"kind": "WRITE", "line": 42},
        {"kind": "READ", "line": 43},
        {"kind": "READ", "line": 44},
    ], f"cpp: for_range_loop varflow mismatch\n{out}"


def test_kotlin_throw_is_detected_by_exits():
    """--exits must detect Kotlin's `throw` as a THROW exit.

    Kotlin wraps both `throw` and `return` in a `jump_expression` node; the
    only distinguishing child is the bare `throw`/`return` keyword node. bare
    `return` was already in RETURN_NODES so returns worked, but THROW_NODES
    carried only `throw_statement`/`throw_expression` (Java/Scala shapes) — the
    bare `throw` keyword kind was missing, so `--exits`/`--returns` were blind
    to every Kotlin throw (BACK-427 class). Found via tivi deep-conformance
    dogfooding; the entry_function processOrder has no throw, so this pins
    `validate` (throw at L6) directly. Confirmed to report only the L8 return
    pre-fix."""
    out = _run(str(_sample_path("kotlin")), "validate", "--exits", "--format", "json")
    data = json.loads(out)
    findings = [{"kind": f["kind"], "line": f["line"]} for f in data["findings"]]
    assert findings == [
        {"kind": "THROW", "line": 6},
        {"kind": "RETURN", "line": 8},
    ], f"kotlin: validate exits mismatch (throw at L6 must be detected)\n{out}"


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


# ─────────────────── BACK-430: Rust loop/match varflow + gates ────────────────

def test_rust_varflow_classifies_expression_loop_conditions_as_cond():
    """Regression-pin for BACK-430 bug 1: the matrix's --outline coverage of
    count_down's while/for/match (test above) does NOT exercise --varflow,
    which has its own separate node-kind dispatch (nav_varflow.py) and had
    drifted independently — `while_expression`'s condition classified as
    plain READ instead of READ/COND, and `for_expression`'s loop variable
    wasn't recognized as a WRITE at all (different field names than Go's
    for_statement: pattern/value, not left/right)."""
    out = _run(str(_sample_path("rust")), "count_down", "--varflow", "n", "--format", "json")
    data = json.loads(out)
    events = [(f["kind"], f["line"]) for f in data["findings"]]
    assert ("READ/COND", 31) in events, f"rust: count_down `while n > 0` not READ/COND\n{out}"
    assert ("READ", 37) in events, f"rust: count_down `match n` scrutinee not READ\n{out}"

    out_i = _run(str(_sample_path("rust")), "count_down", "--varflow", "i", "--format", "json")
    data_i = json.loads(out_i)
    events_i = [(f["kind"], f["line"]) for f in data_i["findings"]]
    assert ("WRITE", 34) in events_i, f"rust: count_down `for i in 0..3` binding not WRITE\n{out_i}"


# ───────────────────────── check/hotspots bounded-scan guard ──────────────────

def test_check_and_hotspots_complete_quickly(lang):
    """`check`/`hotspots` must never hang regardless of language (BACK-418/424
    class: an unbounded scan that only shows up on a real-sized tree). Fixture
    directories are tiny, so this is a smoke bound, not a scale repro — the
    scale repro itself lives in test_rules.py's I002 ceiling tests."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parents[1])
    env["REVEAL_I002_MAX_FILES"] = "3"
    for flag in ("--check", "--hotspots"):
        result = subprocess.run(
            [sys.executable, "-m", "reveal.main", str(_lang_dir(lang)), flag],
            capture_output=True, text=True, timeout=10, env=env,
        )
        assert result.returncode in (0, 1), (
            f"{lang} {flag}: unexpected crash (rc={result.returncode}): {result.stderr}"
        )
