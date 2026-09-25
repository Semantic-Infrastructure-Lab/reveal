#!/usr/bin/env python3
"""mypy ratchet: fail only when type errors INCREASE against a tracked baseline.

reveal has a few hundred pre-existing mypy errors (`disallow_untyped_defs` is
off on purpose -- see pyproject.toml). Zeroing them in one pass is a trap, and a
permanently-red check gets ignored. So, like scripts/check_doc_hygiene.py, this
gates on regression only. The baseline is keyed per (file, error-code) rather
than a single total, so fixing one error can't hide a new one elsewhere, and
line-number churn never matters.

Usage:
    python scripts/check_mypy_baseline.py            # check vs .github/mypy_baseline.json
    python scripts/check_mypy_baseline.py --update   # rewrite the baseline (after fixing errors)

Exit 1 if any (file, code) count rose or a new (file, code) appeared. Improvements
are reported; run --update to lock them in. The baseline reflects the mypy and
dependency versions in the maintainer environment -- a different mypy/mcp version
can shift counts, so this is a pre-release gate, not a CI gate.
"""

from __future__ import annotations

import collections
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / ".github" / "mypy_baseline.json"
_ERROR = re.compile(r"^(?P<file>[^:\n]+):\d+(?::\d+)?: error: .*\[(?P<code>[a-z0-9-]+)\]\s*$")


def run_mypy() -> collections.Counter:
    proc = subprocess.run([sys.executable, "-m", "mypy", "reveal", "--no-error-summary",
                           "--no-pretty", "--show-error-codes"],
                          cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode not in (0, 1) or (proc.returncode == 1 and not proc.stdout.strip()):
        sys.exit(f"mypy failed to run:\n{proc.stderr or proc.stdout}")
    counts: collections.Counter = collections.Counter()
    for line in proc.stdout.splitlines():
        m = _ERROR.match(line)
        if m:
            counts[f"{m['file']}::{m['code']}"] += 1
    return counts


def main() -> int:
    current = run_mypy()
    total = sum(current.values())
    if "--update" in sys.argv:
        BASELINE.write_text(json.dumps(dict(sorted(current.items())), indent=1) + "\n", encoding="utf-8")
        print(f"baseline updated: {total} errors in {len(current)} (file, code) buckets")
        return 0
    if not BASELINE.exists():
        sys.exit(f"no baseline at {BASELINE}; run with --update to create it")
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    worse = {k: (base.get(k, 0), v) for k, v in current.items() if v > base.get(k, 0)}
    better = sum(base[k] - current.get(k, 0) for k in base if current.get(k, 0) < base[k])
    print(f"mypy: {total} errors (baseline {sum(base.values())})")
    if worse:
        print(f"\n❌ {len(worse)} (file, code) bucket(s) got worse:")
        for k, (b, c) in sorted(worse.items()):
            print(f"   {k}: {b} -> {c}")
        return 1
    if better:
        print(f"✅ {better} fewer error(s) than baseline -- run --update to lock in the improvement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
