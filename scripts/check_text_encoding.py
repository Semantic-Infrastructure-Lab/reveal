"""Maintain the text-encoding ratchet (BACK-1354): list offenders, rewrite the baseline.

The check itself is rule V041, run by ``reveal reveal:// --check`` (BACK-1707): CI and
ci-local no longer run this script. It stays as the maintenance tool for the two things a
rule cannot do, and as a standalone run of the same scan (it shares V041's functions, so
the two cannot disagree).

Existing offenders are frozen in scripts/text_encoding_baseline.json (per-file counts).
A file may only stay at or below its baseline; fix a site with ``encoding='utf-8'`` (or
``'rb'`` mode), or suppress a false positive with ``# noqa: text-encoding``. See
reveal/docs/rules/V041.md for what is flagged and the STRICT class (never baselined).

Run:
    python scripts/check_text_encoding.py                  # exits 1 on regressions
    python scripts/check_text_encoding.py --update-baseline  # rewrite the baseline
    python scripts/check_text_encoding.py -v               # list every offender
"""

import json
import sys
from pathlib import Path

from reveal.rules.validation.V041 import (
    BASELINE_REL, TREES, load_baseline, regressions, scan_modules)

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / BASELINE_REL


def scan() -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    modules = []
    for tree_name in TREES:
        for path in sorted((ROOT / tree_name).rglob('*.py')):
            try:
                modules.append((path.relative_to(ROOT).as_posix(), path.read_text(encoding='utf-8')))
            except (OSError, UnicodeDecodeError) as e:
                print(f'skipped {path}: {type(e).__name__}: {e}', file=sys.stderr)
    unparsed: list[tuple[str, str]] = []
    found, strict = scan_modules(modules, unparsed)
    for display, error in unparsed:
        print(f'skipped {display}: {error}', file=sys.stderr)
    return found, strict


def main() -> int:
    found, strict = scan()
    counts = {f: len(v) for f, v in found.items()}
    if '--update-baseline' in sys.argv:
        if strict:
            print('refusing to baseline STRICT sites (repo-file reads); fix them:')
            for f, lines_ in strict.items():
                print(f'  {f}: {lines_}')
            return 1
        BASELINE.write_text(json.dumps(counts, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        print(f'baseline written: {sum(counts.values())} sites in {len(counts)} files')
        return 0
    baseline = load_baseline(ROOT)
    if '-v' in sys.argv:
        for f, lines_ in {**found, **strict}.items():
            print(f'{f}: {lines_}')
    regressed = regressions(found, baseline)
    if strict or regressed:
        print('Text I/O without encoding= (breaks on Windows cp1252):')
        for f, lines_ in sorted(strict.items()):
            print(f'  {f}: lines {lines_}  [STRICT: reads a repo file/fixture; never baselined]')
        for f, (was, now) in sorted(regressed.items()):
            print(f'  {f}: {was} -> {now}  lines {found[f]}')
        print("Add encoding='utf-8' (or use binary mode); see reveal/docs/rules/V041.md")
        return 1
    shrunk = sum(baseline.get(f, 0) - counts.get(f, 0) for f in baseline if counts.get(f, 0) < baseline[f])
    print(f'text-encoding ratchet OK ({sum(counts.values())} legacy sites'
          + (f'; {shrunk} fixed since baseline - run --update-baseline to lock in' if shrunk else '') + ')')
    return 0


if __name__ == '__main__':
    sys.exit(main())
