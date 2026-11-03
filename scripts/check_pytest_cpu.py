#!/usr/bin/env python3
"""Verdict on the full suite's pytest CPU seconds, for scripts/ci-local.sh.

Why this is not a single "over 115% of baseline" line: on this class of machine (a shared,
hybrid-core laptop) recorded full-suite runs of near-identical code spread 2,193-2,583 CPU
seconds -- about 5% standard deviation, 15% peak to peak -- and a quiet-host instruction count
is no steadier (it fell under load while CPU seconds rose). A one-run line inside that spread
fails pushes on noise and trains people to shave test seconds to pass the number.

The gate keeps what it was built for, a real regression (BACK-2159: +30% in one slice):

- fail:  one run over 125% of the baseline, or the median of the last five full runs over 115%
         (sustained growth, which no one noisy run can fake);
- warn:  one run over 110%;
- busy:  when the host's 1-minute load average at suite start is over half the CPUs the run is
         not a valid measurement (the rule in MAINTAINER_WORKFLOW "Measuring performance"):
         it can only warn, and its row is labelled so it stays out of later medians;
- skip:  `ci-local.sh --skip-cpu-gate REASON` records the reason and never fails.

A suite that really grew raises .github/pytest_cpu_baseline.txt in the commit that grew it, with
the reason in the message.
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

WARN_FRAC = 1.10
FAIL_FRAC = 1.25
TREND_FAIL_FRAC = 1.15
TREND_RUNS = 5
TREND_MIN_RUNS = 3
PARTIAL_FRAC = 0.5  # a targeted `-- tests/foo.py` run records a few seconds, not a suite
STEP = "pytest CPU seconds"
BUSY_STEP = STEP + " (busy host)"
SKIP_STEP = "pytest CPU gate skipped"


@dataclass(frozen=True)
class Verdict:
    level: str  # ok | warn | fail | skipped
    message: str
    busy: bool = False


def trend_median(values: list[int], baseline: int) -> float:
    """Median of the last TREND_RUNS full-suite values; partial runs are not history."""
    full = [v for v in values if v >= baseline * PARTIAL_FRAC]
    return statistics.median(full[-TREND_RUNS:])


def _classify(cpu: int, baseline: int, history: list[int]) -> tuple[str, str]:
    pct = 100.0 * cpu / baseline
    head = f"pytest CPU {cpu}s is {pct:.0f}% of the baseline {baseline}s"
    full = [v for v in history if v >= baseline * PARTIAL_FRAC]
    if cpu > baseline * FAIL_FRAC:
        return "fail", f"{head}: over {FAIL_FRAC:.0%} in one run"
    if len(full) + 1 >= TREND_MIN_RUNS:
        median = trend_median(history + [cpu], baseline)
        if median > baseline * TREND_FAIL_FRAC:
            return "fail", (f"{head}; the median of the last {TREND_RUNS} full runs is {median:.0f}s, "
                            f"over {TREND_FAIL_FRAC:.0%} (sustained growth)")
    if cpu > baseline * WARN_FRAC:
        return "warn", f"{head}: over {WARN_FRAC:.0%}"
    return "ok", head


def evaluate(cpu: int, baseline: int, history: list[int], load1: float, ncpu: int,
             skip_reason: str = "") -> Verdict:
    if skip_reason:
        return Verdict("skipped", f"CPU gate SKIPPED (recorded): {skip_reason}")
    busy = load1 > ncpu / 2
    level, message = _classify(cpu, baseline, history)
    if busy:
        note = f"host busy at suite start (load {load1:.1f} over half of {ncpu} CPUs): not a valid measurement"
        return Verdict("warn" if level != "ok" else "ok", f"{message}; {note}", busy=True)
    return Verdict(level, message)


def read_history(timings: Path, py_tag: str) -> list[int]:
    """Valid full-run CPU seconds for this interpreter tag; busy-host rows are labelled out."""
    if not timings.is_file():
        return []
    out = []
    for line in timings.read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) >= 4 and cols[1] == py_tag and cols[3] == STEP and cols[2].isdigit():
            out.append(int(cols[2]))
    return out


def _append_rows(timings: Path, py_tag: str, cpu: int, verdict: Verdict, skip_reason: str) -> None:
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    step = BUSY_STEP if verdict.busy else STEP
    rows = [f"{stamp}\t{py_tag}\t{cpu}\t{step}\t0\n"]
    if skip_reason:
        rows.append(f"{stamp}\t{py_tag}\t0\t{SKIP_STEP}: {skip_reason}\t0\n")
    with timings.open("a", encoding="utf-8") as fh:
        fh.writelines(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cpu", type=int, required=True, help="pytest user+sys CPU seconds")
    ap.add_argument("--baseline-file", type=Path, required=True)
    ap.add_argument("--timings", type=Path, required=True, help="timings.tsv to read and append to")
    ap.add_argument("--py-tag", required=True, help="e.g. py3.12")
    ap.add_argument("--load1", type=float, required=True, help="1-minute load average before the suite")
    ap.add_argument("--ncpu", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--skip-reason", default="")
    args = ap.parse_args(argv)
    baseline = int(args.baseline_file.read_text(encoding="utf-8").strip())
    history = read_history(args.timings, args.py_tag)
    verdict = evaluate(args.cpu, baseline, history, args.load1, args.ncpu, args.skip_reason)
    _append_rows(args.timings, args.py_tag, args.cpu, verdict, args.skip_reason)
    prefix = {"ok": "", "warn": "WARN: ", "fail": "FAIL: ", "skipped": "WARN: "}[verdict.level]
    print(prefix + verdict.message)
    if verdict.level == "fail":
        print("Find the slow tests in the log's --durations. If the suite really grew, raise "
              ".github/pytest_cpu_baseline.txt in the commit that grew it, with the reason; if "
              "the host was shared, rerun on a quiet one or use --skip-cpu-gate REASON.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
