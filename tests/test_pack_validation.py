"""BACK-435 — `pack` validation.

`reveal pack` is the command that most directly embodies reveal's product
thesis: "help an agent spend fewer tokens." Yet it had zero dedicated test
coverage — every other suite tests the primitives pack is built on, not pack
itself. This suite pins the properties an agent actually relies on:

- budget-aware: pack never blows the token budget, and a tighter budget selects
  fewer files (the promise is a *bounded* snapshot);
- deterministic: the same repo + budget yields the same selection and order, so
  a packed context is reproducible and cacheable;
- honest accounting: every candidate is counted (selected or skipped) — a test
  or vendor file is never silently dropped without appearing in the totals;
- signal-ranked: high-signal files (depended-on core modules) outrank leaf/
  vendor/test files, so the highest-value context survives budget pressure;
- drill-back-friendly: every selected file carries a path anchor that an agent
  can hand straight back to `reveal <path> <element>` to expand — the packed
  snapshot is an index into the repo, not a dead-end summary.

Assertions are structural/relative, not exact token counts (the estimator is
allowed to evolve). Fixture: tests/fixtures/pack/sample_repo — a tiny repo with
a depended-on core module (high signal), leaf modules, a constants file, a test
file, and a vendored file (low signal), so signal ranking is unambiguous.
"""

import json
from pathlib import Path

import pytest
from conftest import _run_reveal_direct

REPO = Path(__file__).parent / "fixtures" / "pack" / "sample_repo"

# Every file in the fixture repo. pack must account for all of them (as selected
# or skipped) — none may vanish from the totals.
ALL_FILES = {
    "core.py", "api.py", "util.py", "constants.py",
    "tests/test_core.py", "vendor/thirdparty.py",
}
# High-signal: the depended-on core and its direct entry point.
HIGH_SIGNAL = {"core.py", "api.py"}
# Low-signal: vendored + test code an agent needs last, if at all.
LOW_SIGNAL = {"vendor/thirdparty.py", "tests/test_core.py"}


def _run(*args):
    return _run_reveal_direct(*args)


def _assert_sane(result, desc):
    assert result.returncode in (0, 1), (
        f"{desc}: unexpected crash (rc={result.returncode}): {result.stderr}"
    )
    assert "Traceback (most recent call last)" not in result.stderr, (
        f"{desc}: unhandled exception:\n{result.stderr}"
    )


def _pack_json(*extra):
    result = _run("pack", str(REPO), "--format", "json", *extra)
    _assert_sane(result, f"pack {' '.join(extra)}")
    return json.loads(result.stdout)  # must be valid JSON, not a crash dump


# --------------------------------------------------------------------------- #
# Structure & honest accounting
# --------------------------------------------------------------------------- #

def test_pack_json_is_valid_and_shaped():
    d = _pack_json("--budget", "8000")
    for key in ("path", "budget", "meta", "files"):
        assert key in d, f"pack JSON missing top-level key {key!r}"
    m = d["meta"]
    for key in ("total_candidates", "selected", "skipped", "used_tokens_approx",
                "budget_tokens"):
        assert key in m, f"pack meta missing {key!r}"


def test_accounting_is_honest():
    """selected + skipped == total_candidates, and len(files) == selected. No
    file is silently dropped from the totals an agent trusts."""
    d = _pack_json("--budget", "8000")
    m = d["meta"]
    assert m["selected"] + m["skipped"] == m["total_candidates"], (
        f"accounting leak: {m['selected']} + {m['skipped']} != {m['total_candidates']}"
    )
    assert len(d["files"]) == m["selected"], (
        f"files list ({len(d['files'])}) disagrees with selected ({m['selected']})"
    )


def test_all_repo_files_are_counted_as_candidates():
    """Test and vendor files must be *counted* (selected or skipped), never
    invisibly excluded — 'unsupported/skipped is explicit, not silent'."""
    d = _pack_json("--budget", "8000")
    assert d["meta"]["total_candidates"] == len(ALL_FILES), (
        f"pack saw {d['meta']['total_candidates']} candidates, expected "
        f"{len(ALL_FILES)} (fixture files: {sorted(ALL_FILES)})"
    )


# --------------------------------------------------------------------------- #
# Budget awareness
# --------------------------------------------------------------------------- #

def test_never_exceeds_token_budget():
    for budget in (300, 1000, 8000):
        m = _pack_json("--budget", str(budget))["meta"]
        assert m["used_tokens_approx"] <= m["budget_tokens"], (
            f"pack used {m['used_tokens_approx']} tokens over a {budget} budget"
        )


def test_tighter_budget_selects_no_more_files():
    """A bounded snapshot: shrinking the budget never grows the selection."""
    tight = _pack_json("--budget", "300")["meta"]["selected"]
    loose = _pack_json("--budget", "8000")["meta"]["selected"]
    assert tight <= loose, (
        f"tighter budget selected more files ({tight}) than looser ({loose})"
    )
    assert loose == len(ALL_FILES), (
        "a budget large enough for the whole repo should select every file"
    )


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #

def test_deterministic_selection_and_order():
    a = [f["relative"] for f in _pack_json("--budget", "4000")["files"]]
    b = [f["relative"] for f in _pack_json("--budget", "4000")["files"]]
    assert a == b, f"pack is non-deterministic: {a} != {b}"


# --------------------------------------------------------------------------- #
# Signal ranking
# --------------------------------------------------------------------------- #

def test_priority_is_non_increasing():
    """Files are emitted best-first — priority never rises as you read down."""
    prios = [f["priority"] for f in _pack_json("--budget", "8000")["files"]]
    assert all(prios[i] >= prios[i + 1] for i in range(len(prios) - 1)), (
        f"pack priority is not non-increasing: {prios}"
    )


def test_high_signal_outranks_low_signal():
    """The depended-on core module and entry point must appear before vendored
    and test code — the highest-value context an agent needs first."""
    order = [f["relative"] for f in _pack_json("--budget", "8000")["files"]]
    for hi in HIGH_SIGNAL:
        for lo in LOW_SIGNAL:
            assert order.index(hi) < order.index(lo), (
                f"{hi} (high signal) ranked below {lo} (low signal): {order}"
            )


def test_high_signal_survives_budget_pressure():
    """Under a budget too small for the whole repo, the core module is still
    selected — signal, not file order, decides what makes the cut."""
    selected = {f["relative"] for f in _pack_json("--budget", "300")["files"]}
    assert selected, "tight-budget pack selected nothing at all"
    assert "core.py" in selected, (
        f"the highest-signal file was dropped under budget pressure: {selected}"
    )


# --------------------------------------------------------------------------- #
# Drill-back anchors — the whole point of packing
# --------------------------------------------------------------------------- #

def test_selected_files_carry_reusable_drill_back_anchors():
    """Every selected file must expose a real path an agent can hand back to
    `reveal <path> <element>` to expand — a pack is an index into the repo, not
    a terminal summary."""
    d = _pack_json("--budget", "8000")
    for f in d["files"]:
        assert "path" in f and "relative" in f, f"file entry missing path anchor: {f}"
        anchor = Path(f["path"])
        assert anchor.exists(), f"pack anchor path does not exist: {f['path']}"
        # The anchor must actually be re-revealable back into structure.
        outline = _run(f["path"], "--outline")
        _assert_sane(outline, f"reveal {f['path']} --outline (drill-back)")

    # And the drill-back must resolve a real element: core.py -> process_order.
    core = next(f for f in d["files"] if f["relative"] == "core.py")
    extracted = _run(core["path"], "process_order")
    _assert_sane(extracted, "drill-back reveal core.py process_order")
    assert "process_order" in extracted.stdout, (
        "packed anchor for core.py did not drill back into its function body"
    )


# --------------------------------------------------------------------------- #
# Output formats
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("fmt", ["json", "typed", "grep", "text"])
def test_all_output_formats_run_without_crashing(fmt):
    result = _run("pack", str(REPO), "--format", fmt, "--budget", "4000")
    _assert_sane(result, f"pack --format {fmt}")
    assert result.stdout.strip(), f"pack --format {fmt} produced no output"
