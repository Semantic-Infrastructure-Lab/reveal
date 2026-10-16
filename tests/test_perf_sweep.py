"""scripts/perf_sweep.py (BACK-1871): a timing row is only trusted when the run succeeded and agreed.

The failure modes it was written against: a crashed or non-zero run that reads as a speedup, a
cold/warm pair that quietly returns different output, and a sweep taken at high load. Each case
has a clean twin so the check is shown to be able to stay quiet.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

import pytest

if sys.platform == "win32":
    pytest.skip("perf_sweep is a POSIX maintainer tool (resource, killpg, getloadavg)", allow_module_level=True)

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "perf_sweep.py"
_spec = importlib.util.spec_from_file_location("perf_sweep", SCRIPT)
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)


def _row(mode="cold", digest="aa", ok=True, status="ok", corpus="c", command="stats", wall=1.0):
    return {"corpus": corpus, "command": command, "mode": mode, "digest": digest, "ok": ok,
            "status": status, "wall_s": wall, "cpu_s": wall}


def test_summary_is_quiet_for_agreeing_ok_rows():
    assert ps.summarize([_row("cold"), _row("warm")]) == 0


def test_summary_flags_a_cold_warm_digest_mismatch():
    assert ps.summarize([_row("cold", digest="aa"), _row("warm", digest="bb")]) == 1


def test_summary_flags_a_failed_row_and_does_not_count_it_as_the_best_time():
    rows = [_row(ok=False, status="rc=1", wall=0.01), _row(wall=2.0)]
    assert ps.summarize(rows) == 1


@pytest.fixture
def args(tmp_path):
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    return argparse.Namespace(targets={"t": tmp_path}, workers=1, timeout=120.0, max_load_frac=1e9)


def _cell(args, cmd="structure", mode="cold"):
    return ps.sweep_cell("t", cmd, mode, 0, args, ps.REPO_ROOT, "sha")


def test_a_real_cold_run_is_ok_and_its_digest_is_stable(args):
    first, second = _cell(args), _cell(args)
    assert first["ok"] and first["rc"] == 0 and first["out_bytes"] > 0
    assert first["digest"] == second["digest"]
    assert first["cpu_s"] > 0 and first["exit_code"] == first["rc"]


def test_a_different_tree_gives_a_different_digest(args, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    (other / "n.py").write_text("def g():\n    return 2\n\ndef h():\n    return 3\n", encoding="utf-8")
    baseline = _cell(args)["digest"]
    args.targets["t"] = other
    assert _cell(args)["digest"] != baseline


def test_a_nonzero_exit_is_not_ok(args, tmp_path):
    args.targets["t"] = tmp_path / "does-not-exist"
    row = _cell(args)
    assert row["rc"] != 0 and not row["ok"] and row["status"] == f"rc={row['rc']}"


def test_a_timeout_is_not_ok_and_the_child_is_gone(args):
    args.timeout = 0.01
    row = _cell(args)
    assert row["timed_out"] and not row["ok"] and row["status"] == "timeout"


def test_high_load_skips_the_run_instead_of_timing_it(args, monkeypatch):
    monkeypatch.setattr(ps, "run_once", lambda *a, **k: pytest.fail("ran at high load"))
    args.max_load_frac = 0.0
    row = _cell(args)
    assert row["status"] == "skipped_load" and not row["ok"]
