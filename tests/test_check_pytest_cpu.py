"""The pytest-CPU push gate: noise on a shared machine must not fail a push, growth must.

Recorded full-suite runs of near-identical code spread 2,193-2,583 CPU seconds (about 5% standard
deviation; 15% peak to peak), so a single run over a +15% line failed pushes on noise alone. The
gate now fails on one run only far outside that spread, or on a sustained median, and a busy host
can only warn. Each case asserts the verdict, not that something was printed.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_pytest_cpu.py"
_spec = importlib.util.spec_from_file_location("check_pytest_cpu", _SCRIPT)
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate  # a dataclass resolves its module by name while it executes
_spec.loader.exec_module(gate)

BASE = 2400


def _verdict(cpu, history=(), load1=1.0, ncpu=12, skip=""):
    return gate.evaluate(cpu, BASE, list(history), load1, ncpu, skip)


def test_run_inside_the_noise_band_passes_silently():
    assert _verdict(2583, history=[2400, 2410, 2420, 2430]).level == "ok"


def test_single_run_over_ten_percent_warns_but_does_not_fail():
    v = _verdict(2700, history=[2400, 2410, 2420, 2430])
    assert v.level == "warn"
    assert "10%" in v.message


def test_single_run_far_outside_the_noise_fails():
    # BACK-2159 was +30%: 1,850 -> 2,371-2,436.
    v = _verdict(int(BASE * 1.30), history=[2400, 2410, 2420, 2430])
    assert v.level == "fail"
    assert "125%" in v.message


def test_sustained_growth_fails_even_when_no_single_run_is_extreme():
    history = [2800, 2810, 2790, 2820]
    v = _verdict(2800, history=history)
    assert v.level == "fail"
    assert "median" in v.message


def test_one_noisy_run_among_normal_ones_does_not_trip_the_median():
    assert _verdict(2900, history=[2400, 2410, 2390, 2420]).level == "warn"


def test_busy_host_downgrades_a_failing_number_to_a_warning():
    v = _verdict(int(BASE * 1.40), load1=9.0, ncpu=12)
    assert v.level == "warn"
    assert "busy" in v.message
    assert v.busy is True


def test_busy_host_boundary_is_half_the_cpus():
    assert _verdict(2400, load1=6.0, ncpu=12).busy is False
    assert _verdict(2400, load1=6.1, ncpu=12).busy is True


def test_skip_reason_never_fails_and_is_reported():
    v = _verdict(int(BASE * 1.40), skip="CI-only change, machine shared")
    assert v.level == "skipped"
    assert "CI-only change, machine shared" in v.message


def test_partial_runs_are_not_history():
    # a targeted `-- tests/foo.py` run records a few seconds; it must not drag the median down
    history = [12, 30, 40, 50, 2800]
    assert gate.trend_median(history + [2800], BASE) == 2800  # counted, the median would be 50


def test_trend_uses_only_the_last_five_full_runs():
    old, new = [100000] * 20, [2400] * 5
    assert gate.trend_median(old + new, BASE) == 2400


@pytest.mark.parametrize("cpu,level", [(2399, "ok"), (2640, "ok"), (2641, "warn"), (3000, "warn"), (3001, "fail")])
def test_single_run_thresholds_are_exact(cpu, level):
    assert _verdict(cpu, history=[2400] * 4).level == level


def test_main_appends_a_row_and_returns_the_exit_code(tmp_path):
    tsv = tmp_path / "timings.tsv"
    base = tmp_path / "baseline.txt"
    base.write_text(f"{BASE}\n", encoding="utf-8")
    args = ["--cpu", "2418", "--baseline-file", str(base), "--timings", str(tsv),
            "--py-tag", "py3.12", "--load1", "1.0", "--ncpu", "12"]
    assert gate.main(args) == 0
    row = tsv.read_text(encoding="utf-8").splitlines()[-1].split("\t")
    assert row[1:4] == ["py3.12", "2418", "pytest CPU seconds"]
    assert gate.main(["--cpu", "3500", *args[2:]]) == 1


def test_busy_host_row_is_labelled_and_left_out_of_later_trends(tmp_path):
    tsv = tmp_path / "timings.tsv"
    base = tmp_path / "baseline.txt"
    base.write_text(f"{BASE}\n", encoding="utf-8")
    common = ["--baseline-file", str(base), "--timings", str(tsv), "--py-tag", "py3.12", "--ncpu", "12"]
    assert gate.main(["--cpu", "3900", "--load1", "11", *common]) == 0
    assert "pytest CPU seconds (busy host)" in tsv.read_text(encoding="utf-8")
    assert gate.read_history(tsv, "py3.12") == []
