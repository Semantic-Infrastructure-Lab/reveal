"""Ratchet: a function over the C901 threshold may only get simpler.

Reliability program (BACK-1512). The complexity hotspots grow where fixes land: each
"don't render a failure as a clean zero" fix appended its own warning block to the
function that builds the result, so ``ast://``'s ``get_structure`` went from complexity
20 to 42 between v0.120.0 and v0.129.0, and functions at complexity 20+ went from 41 to
55. ``reveal check`` reports them (C901) but nothing gated on it, so nothing stopped it.

Each function whose complexity is over the C901 threshold in ``.reveal.yaml`` is frozen at
its score in ``scripts/complexity_baseline.json``. A frozen function may not score higher,
and no new function may cross the threshold. A function that got simpler (or dropped under
the threshold) must be locked in with ``--update-baseline``, so each score only ever falls.

The score is the one C901 and ``ast://`` report: the analyzer's per-function
``complexity``. The threshold is read from ``.reveal.yaml`` alone -- not through
RevealConfig, which merges user config and ``REVEAL_C901_THRESHOLD`` and so would make
the ratchet depend on the machine it runs on.

A function is keyed ``file::Class.name`` (``#2``, ``#3`` for repeats in one scope). Moving
or renaming a frozen function reads as one new offender plus one stale entry;
``--update-baseline`` accepts that as long as the number of offenders and their total
excess over the threshold do not rise. It refuses any frozen function scoring higher.

Run:
    python scripts/check_complexity.py                   # exits 1 on regression or stale baseline
    python scripts/check_complexity.py -v                # list every frozen function
    python scripts/check_complexity.py --update-baseline # lower the baseline after a fix
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'scripts' / 'complexity_baseline.json'
CONFIG = ROOT / '.reveal.yaml'
TREE = 'reveal'

sys.path.insert(0, str(ROOT))


def threshold() -> int:
    """C901's threshold from the repo's .reveal.yaml, else C901's own default."""
    from reveal.rules.complexity.C901 import C901
    rules = (yaml.safe_load(CONFIG.read_text(encoding='utf-8')) or {}).get('rules') or {}
    return int((rules.get('C901') or {}).get('threshold', C901.DEFAULT_THRESHOLD))


def _enclosing_class(line: int, classes: List[Dict[str, Any]]) -> str:
    """Name of the innermost class whose line range holds `line`, or ''."""
    holders = [c for c in classes if c.get('line', 0) < line <= c.get('line_end', 0)]
    return max(holders, key=lambda c: c['line'])['name'] if holders else ''


def function_scores(structure: Dict[str, Any]) -> List[Tuple[str, int]]:
    """(qualified name, complexity) for every function in one file's structure."""
    classes = structure.get('classes') or []
    seen: Dict[str, int] = {}
    out = []
    for func in sorted(structure.get('functions') or [], key=lambda f: f.get('line', 0)):
        cls = _enclosing_class(func.get('line', 0), classes)
        name = f"{cls}.{func['name']}" if cls else func['name']
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f'{name}#{seen[name]}'
        out.append((name, func.get('complexity') or 0))
    return out


def scan(limit: int) -> Dict[str, int]:
    """'file::qualname' -> complexity for every function over `limit`."""
    from reveal.registry import get_analyzer
    found: Dict[str, int] = {}
    for path in sorted((ROOT / TREE).rglob('*.py')):
        rel = path.relative_to(ROOT).as_posix()
        analyzer_class = get_analyzer(str(path))
        if analyzer_class is None:
            continue
        structure = analyzer_class(str(path)).get_structure() or {}
        for name, score in function_scores(structure):
            if score > limit:
                found[f'{rel}::{name}'] = score
    return found


def compare(baseline: Dict[str, int], now: Dict[str, int]
            ) -> Tuple[List[Tuple[str, Optional[int], int]], List[Tuple[str, int, Optional[int]]]]:
    """(regressions, stale): (key, baseline or None, now) and (key, baseline, now or None)."""
    regressions = [(k, baseline.get(k), n) for k, n in sorted(now.items())
                   if n > baseline.get(k, 0)]
    stale = [(k, b, now.get(k)) for k, b in sorted(baseline.items())
             if now.get(k, 0) < b]
    return regressions, stale


def _excess(scores: Dict[str, int], limit: int) -> int:
    return sum(s - limit for s in scores.values())


def _summary(scores: Dict[str, int], limit: int) -> str:
    return (f'{len(scores)} functions over C901 threshold {limit}, '
            f'total excess {_excess(scores, limit)}')


def _refusal(base: Dict[str, int], now: Dict[str, int], limit: int) -> List[str]:
    """Why --update-baseline must not accept `now`; empty when it may."""
    reasons = [f'{k}: {base[k]} -> {n}' for k, n in sorted(now.items())
               if k in base and n > base[k]]
    if len(now) > len(base):
        reasons.append(f'offenders {len(base)} -> {len(now)}')
    if _excess(now, limit) > _excess(base, limit):
        reasons.append(f'total excess {_excess(base, limit)} -> {_excess(now, limit)}')
    return reasons


def main(argv: List[str]) -> int:
    limit = threshold()
    stored = json.loads(BASELINE.read_text(encoding='utf-8')) if BASELINE.exists() else {}
    base: Dict[str, int] = stored.get('functions', {})
    base_limit = stored.get('threshold', limit)
    now = scan(limit)

    if '-v' in argv:
        for key, score in sorted(now.items(), key=lambda kv: -kv[1]):
            print(f'{score:4}  {key}')

    if base_limit != limit and '--update-baseline' not in argv:
        print(f'.reveal.yaml C901 threshold is {limit} but the baseline was taken at '
              f'{base_limit}. Re-baseline: python scripts/check_complexity.py --update-baseline')
        return 1

    if '--update-baseline' in argv:
        if limit > base_limit and stored:
            print(f'refusing to re-baseline at a higher C901 threshold ({base_limit} -> {limit}): '
                  'that drops frozen functions without simplifying them')
            return 1
        reasons = _refusal(base, now, limit) if stored and limit == base_limit else []
        if reasons:
            print('refusing to raise the baseline; simplify these first:')
            for reason in reasons:
                print(f'  {reason}')
            return 1
        BASELINE.write_text(json.dumps({'threshold': limit, 'functions': now},
                                       indent=1, sort_keys=True) + '\n', encoding='utf-8')
        print(f'baseline written: {_summary(now, limit)}')
        return 0

    regressions, stale = compare(base, now)
    if regressions:
        print('Functions got more complex (C901 score over the threshold may only fall):')
        for key, b, n in regressions:
            print(f'  {key}: {"new" if b is None else b} -> {n}')
        print('  fix: split the function, or move the added branch behind a shared seam '
              '(BACK-1512). A moved/renamed function: --update-baseline accepts it.')
    if stale:
        print('Functions got simpler but the baseline still allows the old score:')
        for key, b, n in stale:
            print(f'  {key}: {b} -> {"under threshold" if n is None else n}')
        print('Lock in the improvement: python scripts/check_complexity.py --update-baseline')
    if regressions or stale:
        return 1
    print(f'complexity ratchet OK ({_summary(now, limit)})')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
