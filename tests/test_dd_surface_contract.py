"""BACK-442 — DD-critical-surface regression guard.

TechDNA's due-diligence playbook is a pipe composition of ~10 Reveal commands.
Every one is covered *in isolation* by some other suite, and `pack` has its own
battery (BACK-435, `test_pack_validation.py`) — but nothing asserts the DD
surface *as a set*: that `overview` / `architecture` / `surface` / `ast://` /
`imports://` / `calls://` / `check` / `git://?type=ownership` / `stats://` /
`pack` all still exit 0 and emit valid, shaped JSON together on one repo.

A silent regression — a schema field renamed, a category dropped, a `--format
json` path that starts crash-dumping — would break the cross-repo DD playbook
with *no CI signal*, and TechDNA would discover it mid-engagement. This suite
converts the DD-critical-surface contract in
`internal-docs/research/DD_READINESS_2026-07-04.md` into an executable one.

Scope, deliberately: exit 0 + *minimal* shape (only the fields TechDNA's
capability map actually reads), not exact values — the estimators/counts are
allowed to evolve. This is a contract guard, not a correctness matrix (that is
BACK-432). The three DD rows that need external data-room artifacts
(`xlsx://` models, `markdown://` doc trees, `diff://json` config pairs) are out
of scope here — they have no in-repo fixture and are covered by their own
adapter suites; the readiness doc names exactly the 10 source-tree commands
below as the guarded set.

Fixture: the existing `tests/fixtures/pack/sample_repo` (reused from BACK-435) —
a tiny but real repo (depended-on core module, entry point, leaf modules, a
test, a vendored file) that sits inside reveal's own git history, so
`git://?type=ownership` has real commits to attribute.
"""

import json
from pathlib import Path

import pytest
from conftest import _run_reveal_direct

REPO = Path(__file__).parent / "fixtures" / "pack" / "sample_repo"
REPO_STR = str(REPO)


def _run(*args):
    return _run_reveal_direct(*args)


def _assert_exit_ok(result, desc):
    """A DD command must exit cleanly (0 = clean, 1 = findings present) and never
    traceback — a crash mid-playbook is the regression this guard exists to catch."""
    assert result.returncode in (0, 1), (
        f"{desc}: unexpected crash (rc={result.returncode}): {result.stderr}"
    )
    assert "Traceback (most recent call last)" not in result.stderr, (
        f"{desc}: unhandled exception:\n{result.stderr}"
    )


def _json(desc, *args):
    """Run a DD command with JSON output, assert it exits cleanly and parses —
    'shaped JSON, not a crash dump' is the whole promise to a downstream agent."""
    result = _run(*args)
    _assert_exit_ok(result, desc)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:  # pragma: no cover - failure path
        raise AssertionError(
            f"{desc}: --format json did not emit valid JSON ({e}).\n"
            f"stdout head: {result.stdout[:400]!r}"
        )


def _assert_keys(d, keys, desc):
    for k in keys:
        assert k in d, f"{desc}: DD-contract JSON missing top-level key {k!r} (has {list(d)})"


# --------------------------------------------------------------------------- #
# Step 1 — Triage landscape
# --------------------------------------------------------------------------- #

def test_overview_emits_stats_summary_shape():
    d = _json("overview", "overview", REPO_STR, "--format", "json")
    _assert_keys(d, ("path", "stats"), "overview")
    _assert_keys(d["stats"], ("summary", "files"), "overview.stats")
    _assert_keys(
        d["stats"]["summary"],
        ("total_files", "total_functions", "avg_complexity"),
        "overview.stats.summary",
    )


# --------------------------------------------------------------------------- #
# Step 2 — Map what the system is / touches
# --------------------------------------------------------------------------- #

def test_architecture_emits_facts_shape():
    d = _json("architecture", "architecture", REPO_STR, "--format", "json")
    _assert_keys(d, ("path", "facts"), "architecture")
    _assert_keys(
        d["facts"],
        ("entry_points", "core_abstractions", "components"),
        "architecture.facts",
    )


def test_surface_emits_surfaces_taxonomy():
    d = _json("surface", "surface", REPO_STR, "--format", "json")
    _assert_keys(d, ("path", "surfaces"), "surface")
    # The DD AI-washing signal reads specific surface buckets; they must exist as
    # keys even when empty (a dropped category is exactly the silent regression).
    _assert_keys(
        d["surfaces"], ("cli", "http", "sdk", "db", "env"), "surface.surfaces"
    )


# --------------------------------------------------------------------------- #
# Step 3 — Complexity, refactorability, dead code, hidden failures
# --------------------------------------------------------------------------- #

def test_ast_complexity_query_emits_ranked_results():
    d = _json(
        "ast://complexity",
        f"ast://{REPO_STR}?complexity>0&sort=-complexity",
        "--format",
        "json",
    )
    _assert_keys(d, ("type", "results", "total_results"), "ast://")
    assert d["type"] == "ast_query", f"ast:// wrong contract type: {d['type']!r}"
    # Each result must carry the fields the DD complexity signal reads.
    for r in d["results"]:
        _assert_keys(r, ("file", "name", "complexity"), "ast:// result")


def test_imports_circular_query_emits_cycle_shape():
    d = _json(
        "imports://circular",
        f"imports://{REPO_STR}?circular",
        "--format",
        "json",
    )
    _assert_keys(d, ("type", "cycles", "count"), "imports://?circular")
    assert d["type"] == "circular_dependencies", (
        f"imports://?circular wrong contract type: {d['type']!r}"
    )


def test_calls_uncalled_query_emits_entries_shape():
    d = _json(
        "calls://uncalled",
        f"calls://{REPO_STR}?uncalled&type=function",
        "--format",
        "json",
    )
    _assert_keys(
        d, ("type", "entries", "total_uncalled", "total_defined"), "calls://?uncalled"
    )
    assert d["type"] == "calls_uncalled", (
        f"calls://?uncalled wrong contract type: {d['type']!r}"
    )


def test_check_selected_rules_emit_summary():
    d = _json("check B,S", "check", REPO_STR, "--select", "B,S", "--format", "json")
    _assert_keys(d, ("files", "summary"), "check --select B,S")
    _assert_keys(
        d["summary"],
        ("files_checked", "total_issues", "exit_code"),
        "check.summary",
    )


# --------------------------------------------------------------------------- #
# Step 4 — Attribution / bus factor
# --------------------------------------------------------------------------- #

def test_git_ownership_emits_attribution_shape():
    d = _json(
        "git://ownership",
        f"git://{REPO_STR}?type=ownership",
        "--format",
        "json",
    )
    _assert_keys(
        d,
        ("type", "contributor_count", "primary_author", "authors"),
        "git://?type=ownership",
    )
    assert d["type"] == "git_ownership", (
        f"git://?type=ownership wrong contract type: {d['type']!r}"
    )
    _assert_keys(
        d["primary_author"], ("name", "share"), "git://ownership.primary_author"
    )


# --------------------------------------------------------------------------- #
# Step 6 — Quantify & package
# --------------------------------------------------------------------------- #

def test_stats_emits_summary_shape():
    d = _json("stats://", f"stats://{REPO_STR}", "--format", "json")
    _assert_keys(d, ("type", "summary", "files"), "stats://")
    assert d["type"] == "stats_summary", (
        f"stats:// wrong contract type: {d['type']!r}"
    )


def test_pack_emits_budgeted_index_shape():
    # pack has its own deep battery (BACK-435); here we only assert it stays part
    # of the DD set — exits 0, valid JSON, the meta accounting the playbook reads.
    d = _json("pack", "pack", REPO_STR, "--format", "json", "--budget", "8000")
    _assert_keys(d, ("path", "meta", "files"), "pack")
    _assert_keys(
        d["meta"],
        ("total_candidates", "selected", "used_tokens_approx"),
        "pack.meta",
    )


# --------------------------------------------------------------------------- #
# The set, as a set
# --------------------------------------------------------------------------- #

# Each entry is (description, argv) — the full DD-critical source-tree surface.
# Kept as an explicit table so a future added/removed DD command is a one-line
# diff here, and so the "as a set" test can prove the whole pipe survives one run.
DD_SURFACE = [
    ("overview", ("overview", REPO_STR, "--format", "json")),
    ("architecture", ("architecture", REPO_STR, "--format", "json")),
    ("surface", ("surface", REPO_STR, "--format", "json")),
    ("ast://", (f"ast://{REPO_STR}?complexity>0&sort=-complexity", "--format", "json")),
    ("imports://", (f"imports://{REPO_STR}?circular", "--format", "json")),
    ("calls://", (f"calls://{REPO_STR}?uncalled&type=function", "--format", "json")),
    ("check", ("check", REPO_STR, "--select", "B,S", "--format", "json")),
    ("git://ownership", (f"git://{REPO_STR}?type=ownership", "--format", "json")),
    ("stats://", (f"stats://{REPO_STR}", "--format", "json")),
    ("pack", ("pack", REPO_STR, "--format", "json", "--budget", "8000")),
]


@pytest.mark.parametrize("desc,argv", DD_SURFACE, ids=[d for d, _ in DD_SURFACE])
def test_every_dd_surface_command_exits_clean_and_emits_json(desc, argv):
    """The guard's core assertion: every DD-playbook command, run over one
    fixture repo, exits cleanly and produces parseable JSON. If any single row
    regresses (crash, non-zero-non-one exit, HTML/text where JSON is promised),
    this fails in CI instead of mid-engagement."""
    _json(desc, *argv)


def test_dd_surface_is_ten_commands():
    """A tripwire on the contract itself: the DD-critical source-tree surface is
    exactly the 10 commands the readiness doc enumerates. If someone adds or
    removes a DD command, they must update DD_READINESS_2026-07-04.md and this
    count together — the guard should never silently cover a different set than
    the contract it claims to protect."""
    assert len(DD_SURFACE) == 10, (
        f"DD surface set is {len(DD_SURFACE)} commands, contract says 10 — "
        "reconcile with internal-docs/research/DD_READINESS_2026-07-04.md"
    )
