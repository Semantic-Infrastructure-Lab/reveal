#!/usr/bin/env python3
"""Per-test-file cost on the Windows CI legs, from job logs (BACK-1747).

``tests/windows_test_durations.json`` is what tests/conftest.py uses to split the Windows
legs into balanced shards (REVEAL_TEST_SHARD=i/n). Linux timings are wrong for this: spawn
and temp-dir cost make the same file cost different amounts on Windows.

Regenerate (needs gh; job ids are in the run's job list, ``scripts/ci-watch.sh`` prints it)::

    for id in <windows job ids>; do
        gh api repos/{owner}/{repo}/actions/jobs/$id/logs > /tmp/win-$id.log
    done
    python3 scripts/windows_test_durations.py /tmp/win-*.log --run <run id> \\
        > tests/windows_test_durations.json

How it measures: the Windows job runs ``pytest -v -n auto`` (xdist), so result lines of
different workers interleave and a line-to-line delta is meaningless. Each xdist worker
runs one test at a time, though, so on one worker ``[gwN]`` the gap between two
consecutive result lines is the time of the later test. Those gaps are summed per test
file (cost = worker-seconds, the work the file adds to a shard). The first test of a
worker is measured from the ``N workers [M items]`` line. A file's cost is the median over
the logs given (the three Python versions run the same files). Log timestamps are the
runner's receive times, so single tests carry a few ms of jitter; file sums do not.
"""
import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone

_STAMP = r'(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)Z '
_START_RE = re.compile(_STAMP + r'\d+ workers \[\d+ items\]')
_RESULT_RE = re.compile(
    _STAMP + r'\[(?P<gw>gw\d+)\] \[\s*\d+%\] '
    r'(?:PASSED|FAILED|SKIPPED|XFAIL|XPASS|ERROR) (?P<node>\S+)')


def _seconds(stamp: str) -> float:
    whole, _, frac = stamp.partition('.')
    base = datetime.strptime(whole, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
    return base.timestamp() + float('0.' + frac)


def file_costs(log_text: str) -> dict:
    """{test file: worker-seconds} for one job log."""
    costs: dict = defaultdict(float)
    started = None
    last: dict = {}
    for line in log_text.splitlines():
        if started is None:
            match = _START_RE.search(line)
            if match:
                started = _seconds(match.group('ts'))
            continue
        match = _RESULT_RE.search(line)
        if not match:
            continue
        now = _seconds(match.group('ts'))
        previous = last.get(match.group('gw'), started)
        costs[match.group('node').split('::', 1)[0]] += max(0.0, now - previous)
        last[match.group('gw')] = now
    return dict(costs)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('logs', nargs='+', help='Windows job logs (gh api .../jobs/<id>/logs)')
    parser.add_argument('--run', default='', help='CI run id, recorded in the output header')
    args = parser.parse_args(argv)
    per_file: dict = defaultdict(list)
    for path in args.logs:
        with open(path, encoding='utf-8', errors='replace') as handle:
            for name, cost in file_costs(handle.read()).items():
                per_file[name].append(cost)
    if not per_file:
        print('no pytest result lines found (is this a Windows job log of `pytest -v -n auto`?)',
              file=sys.stderr)
        return 1
    files = {name: round(statistics.median(vals), 2) for name, vals in sorted(per_file.items())}
    header = {
        'what': 'Windows CI worker-seconds per test file; used by tests/conftest.py to balance '
                'REVEAL_TEST_SHARD. Regenerate with scripts/windows_test_durations.py (see its docstring).',
        'source_run': args.run,
        'logs': len(args.logs),
        'total_seconds': round(sum(files.values()), 1),
    }
    json.dump({'_meta': header, 'files': files}, sys.stdout, indent=1, sort_keys=False)
    print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
