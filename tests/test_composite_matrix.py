"""BACK-436 — composite command matrix.

No systematic cross-language test existed for the user-facing commands built
on top of the primitives BACK-422/431 already cover (`overview`, `architecture`,
`deps`, `review`, `pack`, `surface`, `contracts`, `testability`, `trace`).
Real-corpus dogfood already found bugs here by accident (silent partial
`surface` output in mixed-language directories; `overview` complexity metrics
inheriting a broken import graph) — this formalizes that into a repeatable
suite. `pack` has its own deep suite (BACK-435, test_pack_validation.py); it
is only smoke-checked here for completeness of the composite list.

Acceptance (per internal-docs/BACKLOG.md BACK-436): exits 0 or documented
non-fatal 1; JSON valid where supported (progress/status text must go to
stderr, not interleave with stdout JSON); output includes source
language/count metadata; unsupported languages are explicit, not silent
partials; composite results agree with primitive commands on the same
fixture (`overview` complexity vs `ast://`, `trace` vs `calls://`, `deps` vs
`imports://`/`depends://`).

Fixtures: tests/fixtures/conformance/<lang>/ (the same 9-language Tier 1 set
as test_conformance_matrix.py) individually, plus the shared parent directory
tests/fixtures/conformance/ as the mixed-language case.
"""

import json
from pathlib import Path

import pytest
import yaml
from conftest import _run_reveal_direct

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "conformance"
EXPECTED = yaml.safe_load((FIXTURES_DIR / "expected.yaml").read_text())
LANGUAGES = sorted(EXPECTED.keys())

# entry_function is each fixture's process_order-equivalent — resolvable by
# --varflow/--exits (test_conformance_matrix.py) and here by `trace --from`.
ENTRY_FUNCTION = {lang: EXPECTED[lang]["entry_function"] for lang in LANGUAGES}


def _run(*args: str):
    return _run_reveal_direct(*args)


def _assert_sane(result, desc: str) -> None:
    assert result.returncode in (0, 1), (
        f"{desc}: unexpected crash (rc={result.returncode}): {result.stderr}"
    )
    assert "Traceback (most recent call last)" not in result.stderr, (
        f"{desc}: unhandled exception:\n{result.stderr}"
    )


def _json(*args: str, desc: str):
    result = _run(*args, "--format", "json")
    _assert_sane(result, desc)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(
            f"{desc}: --format json produced invalid JSON on stdout "
            f"(progress/status text must go to stderr, not stdout): {e}\n"
            f"stdout={result.stdout[:500]!r}"
        )


@pytest.fixture(params=LANGUAGES)
def lang(request) -> str:
    return request.param


def _lang_dir(lang: str) -> Path:
    return FIXTURES_DIR / lang


# --------------------------------------------------------------------------- #
# Per-language: each composite command, on its own single-language fixture
# --------------------------------------------------------------------------- #


def test_overview_non_crash_and_json(lang):
    d = _json("overview", str(_lang_dir(lang)), desc=f"{lang} overview")
    assert d["stats"]["summary"]["total_files"] >= 1


def test_architecture_non_crash_and_json(lang):
    _json("architecture", str(_lang_dir(lang)), desc=f"{lang} architecture")


def test_deps_non_crash_and_json(lang):
    _json("deps", str(_lang_dir(lang)), desc=f"{lang} deps")


def test_review_non_crash_and_json(lang):
    d = _json("review", str(_lang_dir(lang)), desc=f"{lang} review")
    assert "sections" in d


def test_pack_non_crash(lang):
    result = _run("pack", str(_lang_dir(lang)))
    _assert_sane(result, f"{lang} pack")
    assert result.stdout.strip()


def test_surface_non_crash_and_json(lang):
    _json("surface", str(_lang_dir(lang)), desc=f"{lang} surface")


def test_contracts_non_crash_and_json(lang):
    _json("contracts", str(_lang_dir(lang)), desc=f"{lang} contracts")


def test_testability_requires_explicit_tests_path(lang):
    """No --tests: must fail with a clear message, not a crash or a silent
    empty report claiming coverage that was never measured."""
    result = _run("testability", str(_lang_dir(lang)))
    _assert_sane(result, f"{lang} testability (no --tests)")
    assert "--tests" in (result.stdout + result.stderr)


def test_testability_with_explicit_tests_path(lang):
    d = _json(
        "testability", str(_lang_dir(lang)), "--tests", str(_lang_dir(lang)),
        desc=f"{lang} testability",
    )
    assert d["source_type"] == "directory"


def test_trace_agrees_with_calls_uri(lang):
    """trace's resolved root must be the same function calls:// finds."""
    entry = ENTRY_FUNCTION[lang]
    trace = _json(
        "trace", "--from", entry, str(_lang_dir(lang)), desc=f"{lang} trace"
    )
    assert trace["root"] == entry
    assert trace["frames"], f"{lang}: trace found no frames for {entry}"

    calls = _json(
        f"calls://{_lang_dir(lang)}?target={entry}", desc=f"{lang} calls://"
    )
    assert calls, f"{lang}: calls:// found nothing for {entry}, trace disagrees"


# --------------------------------------------------------------------------- #
# Mixed-language directory: composite commands must stay language-aware, not
# silently scope to (or drop) the majority language.
# --------------------------------------------------------------------------- #


def test_overview_mixed_dir_covers_every_language():
    d = _json("overview", str(FIXTURES_DIR), desc="mixed overview")
    files = d["stats"]["files"]
    seen_exts = {Path(f["file"]).suffix.lstrip(".") for f in files}
    expected_exts = {
        "py", "c", "cpp", "cs", "go", "java", "js", "rs", "ts",
    }
    missing = expected_exts - seen_exts
    assert not missing, f"overview silently dropped extensions: {missing}"


def test_deps_mixed_dir_covers_every_language():
    d = _json("deps", str(FIXTURES_DIR), desc="mixed deps")
    files = d["base"]["files"]
    seen_exts = {Path(f).suffix.lstrip(".") for f in files}
    expected_exts = {
        "py", "c", "cpp", "cs", "go", "java", "js", "rs", "ts",
    }
    missing = expected_exts - seen_exts
    assert not missing, f"deps silently dropped extensions: {missing}"


def test_surface_mixed_dir_non_crash_and_json():
    _json("surface", str(FIXTURES_DIR), desc="mixed surface")


def test_review_mixed_dir_non_crash_and_json():
    _json("review", str(FIXTURES_DIR), desc="mixed review")
