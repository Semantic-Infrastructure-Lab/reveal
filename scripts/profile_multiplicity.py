#!/usr/bin/env python3
"""Find work done more than once per unit from a cProfile dump (BACK-1877).

The cheapest duplicate detector found in the bapotaji-1016 perf session was not
static analysis: divide each function's call count by the number of units the
run processed (files). Something that should happen once per file but shows
2.0x is a duplicate. By hand that found, on a 216-file run:

    get_structure     432 calls  2.0x   find_uncalled and build_callers_index both collected (BACK-1868)
    Parser.parse    1,475 calls  6.8x   several passes parse the same file
    split_lines    21,128 calls   98x   extract_function_body re-split the file per function (BACK-1869)

This script does that division and names the callers. It is a maintainer tool, not
a reveal feature: no adapter, no flag, nothing in `reveal --help`.

How to read the output: a ratio is only meaningful for per-file artifacts (a parse, a
structure, a read). Per-function and per-node work is legitimately many per file, so
look for ratios near a whole number (2.00, 3.00: ``xN`` in the output) and for
callers that should not both be asking. A ratio of exactly 1.00 is the expected
single pass and is never listed.

Profile with the work serialised and the cache cold, or the numbers are not per-file:

    REVEAL_DISK_CACHE=0 REVEAL_MAX_WORKERS=1 python -m cProfile -o /tmp/p.prof \\
        ~/.local/bin/reveal 'calls://some/dir?uncalled'
    python scripts/profile_multiplicity.py /tmp/p.prof --units 216
    python scripts/profile_multiplicity.py /tmp/p.prof --units-from get_structure   # units = that function's ncalls

cProfile inflates tiny-call-heavy code about 4x: use the times for ranking only, never
quote them as wall time. Worker processes are not in the parent's profile (use
REVEAL_MAX_WORKERS=1).
"""

import argparse
import json
import pstats
import sys
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_MIN_RATIO = 1.5
DEFAULT_MIN_CALLS = 20
INTEGER_TOLERANCE = 0.05
# A per-file artifact is not plausibly built more than ~10x per file; a whole number above that
# (dfs at exactly 2560.00/unit) is coincidence, so it is listed but not flagged xN.
INTEGER_MAX = 10


def _label(key: Tuple[str, int, str]) -> str:
    filename, lineno, name = key
    if filename == '~':
        return name
    parts = filename.replace('\\', '/').split('/')
    return f"{'/'.join(parts[-2:])}:{lineno} {name}"


def _matches(key: Tuple[str, int, str], needle: str) -> bool:
    return needle in key[2] or needle in key[0]


def units_from(stats: Dict[Tuple[str, int, str], tuple], name: str) -> int:
    """Total calls of every function matching ``name`` (substring of its name or file)."""
    return sum(v[1] for k, v in stats.items() if _matches(k, name))


def _integer_like(ratio: float) -> Optional[int]:
    nearest = round(ratio)
    if 2 <= nearest <= INTEGER_MAX and abs(ratio - nearest) <= INTEGER_TOLERANCE:
        return nearest
    return None


def analyze(stats: Dict[Tuple[str, int, str], tuple], units: int, total_time: float,
            min_ratio: float = DEFAULT_MIN_RATIO, min_calls: int = DEFAULT_MIN_CALLS,
            only: Optional[List[str]] = None, include_builtins: bool = False,
            callers: int = 3) -> List[Dict[str, Any]]:
    """Rows for functions called more than ``min_ratio`` times per unit, costliest first.

    ``stats`` is ``pstats.Stats.stats``: key -> (cc, nc, tt, ct, callers).
    """
    if units <= 0:
        raise ValueError("units must be positive")
    rows = []
    for key, (_cc, nc, _tt, ct, caller_map) in stats.items():
        if key[0] == '~' and not include_builtins:
            continue
        if only and not any(o in key[0] for o in only):
            continue
        ratio = nc / units
        if nc < min_calls or ratio < min_ratio:
            continue
        top_callers = sorted(caller_map.items(), key=lambda kv: -kv[1][0])[:callers]
        rows.append({
            'function': _label(key),
            'ncalls': nc,
            'per_unit': round(ratio, 2),
            'duplicate_of': _integer_like(ratio),
            'cumtime': round(ct, 2),
            'cum_share': round(ct / total_time, 3) if total_time else 0.0,
            'callers': [{'caller': _label(k), 'ncalls': v[0],
                         'per_unit': round(v[0] / units, 2)} for k, v in top_callers],
        })
    rows.sort(key=lambda r: -r['cumtime'])
    return rows


def render(rows: List[Dict[str, Any]], units: int, top: int) -> str:
    if not rows:
        return f"No function is called more than once per unit ({units} units)."
    out = [f"{len(rows)} function(s) called more than once per unit ({units} units); "
           f"showing {min(top, len(rows))} by cumulative time:", ""]
    for r in rows[:top]:
        flag = f"  x{r['duplicate_of']}" if r['duplicate_of'] else ''
        out.append(f"{r['per_unit']:>8.2f}/unit {r['ncalls']:>9,} calls {r['cumtime']:>7.2f}s cum "
                   f"({r['cum_share']:.0%}){flag}  {r['function']}")
        for c in r['callers']:
            out.append(f"{'':>12}<- {c['ncalls']:>9,} ({c['per_unit']:.2f}/unit)  {c['caller']}")
    return '\n'.join(out)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('profile', help='a cProfile/pstats dump (python -m cProfile -o FILE ...)')
    unit = ap.add_mutually_exclusive_group(required=True)
    unit.add_argument('--units', type=int, help='how many units (files) the run processed')
    unit.add_argument('--units-from', metavar='NAME',
                      help="take units from the ncalls of functions matching NAME "
                           "(substring of function or file name)")
    ap.add_argument('--min-ratio', type=float, default=DEFAULT_MIN_RATIO,
                    help=f"list functions called at least this often per unit (default {DEFAULT_MIN_RATIO})")
    ap.add_argument('--min-calls', type=int, default=DEFAULT_MIN_CALLS,
                    help=f"ignore functions called fewer times (default {DEFAULT_MIN_CALLS})")
    ap.add_argument('--only', action='append', metavar='SUBSTR',
                    help="only functions whose file path contains SUBSTR (repeatable), e.g. --only reveal/")
    ap.add_argument('--builtins', action='store_true', help="include C builtins and methods")
    ap.add_argument('--callers', type=int, default=3, help="callers shown per function (default 3)")
    ap.add_argument('--top', type=int, default=25, help="rows shown in text output (default 25)")
    ap.add_argument('--json', action='store_true', help="emit JSON instead of text")
    args = ap.parse_args(argv)

    try:
        profile = pstats.Stats(args.profile)
    except (OSError, EOFError, ValueError, TypeError) as exc:
        print(f"profile_multiplicity: cannot read {args.profile}: {exc}", file=sys.stderr)
        return 2
    stats = profile.stats  # type: ignore[attr-defined]
    units = args.units if args.units is not None else units_from(stats, args.units_from)
    if units <= 0:
        print(f"profile_multiplicity: no units ({'--units' if args.units is not None else args.units_from}"
              f" gave {units}); pass --units N or a function that ran once per file", file=sys.stderr)
        return 2

    rows = analyze(stats, units, profile.total_tt,  # type: ignore[attr-defined]
                   min_ratio=args.min_ratio, min_calls=args.min_calls, only=args.only,
                   include_builtins=args.builtins, callers=args.callers)
    if args.json:
        print(json.dumps({'units': units, 'rows': rows}, indent=2))
    else:
        print(render(rows, units, args.top))
    return 0


if __name__ == '__main__':
    sys.exit(main())
