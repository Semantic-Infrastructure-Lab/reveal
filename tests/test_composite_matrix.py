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
tests/fixtures/conformance/ as the mixed-language case. The suite reads a copy
outside the repo (BACK-2144): in place, I002 resolves the project root to the
outer checkout and builds its import graph on every review/overview call --
~95% of this file's time, and the outer-root noise behind BACK-1881.
"""

import json
import shutil
from pathlib import Path

import pytest
import yaml
from conftest import _run_reveal_direct

# BACK-1149: exercises reveal.main's CLI entry point via conftest._run_reveal_direct/subprocess
pytestmark = pytest.mark.cli

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "conformance"
EXPECTED = yaml.safe_load((FIXTURES_DIR / "expected.yaml").read_text(encoding="utf-8"))
LANGUAGES = sorted(EXPECTED.keys())

# entry_function is each fixture's process_order-equivalent — resolvable by
# --varflow/--exits (test_conformance_matrix.py) and here by `trace --from`.
ENTRY_FUNCTION = {lang: EXPECTED[lang]["entry_function"] for lang in LANGUAGES}


def _run(*args: str):
    return _run_reveal_direct(*args)


def _i002_state() -> str:
    """What I002 holds in this process, for a failure message (BACK-1881: a review of a
    fixture dir sometimes reports I002 parse errors under the OUTER repo root)."""
    from reveal.rules.imports import I002
    keys = sorted(str(k) for k in I002._graph_cache)
    return f"I002._graph_cache keys: {keys}"


def _assert_sane(result, desc: str) -> None:
    assert result.returncode in (0, 1), (
        f"{desc}: unexpected crash (rc={result.returncode}): {result.stderr}\n"
        f"stdout tail: {result.stdout[-2000:]}\n{_i002_state()}"
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


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory) -> Path:
    dst = tmp_path_factory.mktemp("composite") / "conformance"
    shutil.copytree(FIXTURES_DIR, dst)
    return dst


@pytest.fixture(params=LANGUAGES)
def lang_dir(request, fixtures_dir) -> Path:
    return fixtures_dir / request.param


# --------------------------------------------------------------------------- #
# Per-language: each composite command, on its own single-language fixture
# --------------------------------------------------------------------------- #


def test_overview_non_crash_and_json(lang_dir):
    d = _json("overview", str(lang_dir), desc=f"{lang_dir.name} overview")
    assert d["stats"]["summary"]["total_files"] >= 1


def test_architecture_non_crash_and_json(lang_dir):
    _json("architecture", str(lang_dir), desc=f"{lang_dir.name} architecture")


def test_deps_non_crash_and_json(lang_dir):
    _json("deps", str(lang_dir), desc=f"{lang_dir.name} deps")


def test_review_non_crash_and_json(lang_dir):
    d = _json("review", str(lang_dir), desc=f"{lang_dir.name} review")
    assert "sections" in d


def test_pack_non_crash(lang_dir):
    result = _run("pack", str(lang_dir))
    _assert_sane(result, f"{lang_dir.name} pack")
    assert result.stdout.strip()


def test_surface_non_crash_and_json(lang_dir):
    _json("surface", str(lang_dir), desc=f"{lang_dir.name} surface")


def test_contracts_non_crash_and_json(lang_dir):
    _json("contracts", str(lang_dir), desc=f"{lang_dir.name} contracts")


def test_testability_requires_explicit_tests_path(lang_dir):
    """No --tests: must fail with a clear message, not a crash or a silent
    empty report claiming coverage that was never measured."""
    result = _run("testability", str(lang_dir))
    _assert_sane(result, f"{lang_dir.name} testability (no --tests)")
    assert "--tests" in (result.stdout + result.stderr)


def test_testability_with_explicit_tests_path(lang_dir):
    d = _json(
        "testability", str(lang_dir), "--tests", str(lang_dir),
        desc=f"{lang_dir.name} testability",
    )
    assert d["source_type"] == "directory"


def test_trace_agrees_with_calls_uri(lang_dir):
    """trace's resolved root must be the same function calls:// finds."""
    entry = ENTRY_FUNCTION[lang_dir.name]
    trace = _json(
        "trace", "--from", entry, str(lang_dir), desc=f"{lang_dir.name} trace"
    )
    assert trace["root"] == entry
    assert trace["frames"], f"{lang_dir.name}: trace found no frames for {entry}"

    calls = _json(
        f"calls://{lang_dir}?target={entry}", desc=f"{lang_dir.name} calls://"
    )
    assert calls, f"{lang_dir.name}: calls:// found nothing for {entry}, trace disagrees"


# --------------------------------------------------------------------------- #
# Mixed-language directory: composite commands must stay language-aware, not
# silently scope to (or drop) the majority language.
# --------------------------------------------------------------------------- #


def test_overview_mixed_dir_covers_every_language(fixtures_dir):
    d = _json("overview", str(fixtures_dir), desc="mixed overview")
    files = d["stats"]["files"]
    seen_exts = {Path(f["file"]).suffix.lstrip(".") for f in files}
    expected_exts = {
        "py", "c", "cpp", "cs", "go", "java", "js", "rs", "ts",
    }
    missing = expected_exts - seen_exts
    assert not missing, f"overview silently dropped extensions: {missing}"


def test_deps_mixed_dir_covers_every_language(fixtures_dir):
    d = _json("deps", str(fixtures_dir), desc="mixed deps")
    files = d["base"]["files"]
    seen_exts = {Path(f).suffix.lstrip(".") for f in files}
    expected_exts = {
        "py", "c", "cpp", "cs", "go", "java", "js", "rs", "ts",
    }
    missing = expected_exts - seen_exts
    assert not missing, f"deps silently dropped extensions: {missing}"


def test_surface_mixed_dir_non_crash_and_json(fixtures_dir):
    _json("surface", str(fixtures_dir), desc="mixed surface")


def test_review_mixed_dir_non_crash_and_json(fixtures_dir):
    _json("review", str(fixtures_dir), desc="mixed review")
