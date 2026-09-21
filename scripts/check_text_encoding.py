"""Ratchet: no NEW text-mode file I/O without an explicit ``encoding=``.

On Windows the default text encoding is cp1252, not UTF-8, so a bare
``Path.read_text()`` / ``open(p)`` that touches a non-ASCII file raises
UnicodeDecodeError there while passing on Linux/macOS (BACK-1346/1347 CI:
tests/test_surface_matrix.py read scanner source without an encoding).

Existing offenders are frozen in scripts/text_encoding_baseline.json (per-file
counts).  A file may only stay at or below its baseline; new or increased
offenders fail.  Fix a site with ``encoding='utf-8'`` (or ``'rb'`` mode), or
suppress a false positive with ``# noqa: text-encoding`` on the call line.

Run:
    python scripts/check_text_encoding.py                  # exits 1 on regressions
    python scripts/check_text_encoding.py --update-baseline  # rewrite the baseline
    python scripts/check_text_encoding.py -v               # list every offender

Local repro of the failure class on Linux (ASCII locale):
    PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 LC_ALL=C pytest tests/<file>
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / 'scripts' / 'text_encoding_baseline.json'
TREES = ('reveal', 'tests', 'scripts')
NOT_FILES = {'os', 'io', 'webbrowser', 'gzip', 'zipfile', 'tarfile', 'urllib', 'codecs', 'subprocess'}


def _mode(call: ast.Call, positional: list[ast.expr]):
    for kw in call.keywords:
        if kw.arg == 'mode' and isinstance(kw.value, ast.Constant):
            return kw.value.value
    if positional and isinstance(positional[0], ast.Constant):
        return positional[0].value
    return None


def is_bare_text_io(call: ast.Call) -> bool:
    if any(kw.arg == 'encoding' or kw.arg is None for kw in call.keywords):
        return False
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in ('read_text', 'write_text'):
        return True
    if isinstance(func, ast.Name) and func.id == 'open':
        mode = _mode(call, call.args[1:2])
    elif isinstance(func, ast.Attribute) and func.attr == 'open':
        if isinstance(func.value, ast.Name) and func.value.id in NOT_FILES:
            return False
        mode = _mode(call, call.args[0:1])
    else:
        return False
    return not (isinstance(mode, str) and 'b' in mode)


def scan() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for tree_name in TREES:
        for path in sorted((ROOT / tree_name).rglob('*.py')):
            try:
                source = path.read_text(encoding='utf-8')
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue
            lines = source.splitlines()
            hits = [
                n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Call) and is_bare_text_io(n)
                and 'noqa: text-encoding' not in lines[n.lineno - 1]
            ]
            if hits:
                found[path.relative_to(ROOT).as_posix()] = sorted(hits)
    return found


def main() -> int:
    found = scan()
    counts = {f: len(v) for f, v in found.items()}
    if '--update-baseline' in sys.argv:
        BASELINE.write_text(json.dumps(counts, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        print(f'baseline written: {sum(counts.values())} sites in {len(counts)} files')
        return 0
    baseline = json.loads(BASELINE.read_text(encoding='utf-8')) if BASELINE.exists() else {}
    if '-v' in sys.argv:
        for f, lines_ in found.items():
            print(f'{f}: {lines_}')
    regressions = {f: (baseline.get(f, 0), n) for f, n in counts.items() if n > baseline.get(f, 0)}
    if regressions:
        print('Text I/O without encoding= (breaks on Windows cp1252):')
        for f, (was, now) in sorted(regressions.items()):
            print(f'  {f}: {was} -> {now}  lines {found[f]}')
        print("Add encoding='utf-8' (or use binary mode); see scripts/check_text_encoding.py")
        return 1
    shrunk = sum(baseline.get(f, 0) - counts.get(f, 0) for f in baseline if counts.get(f, 0) < baseline[f])
    print(f'text-encoding ratchet OK ({sum(counts.values())} legacy sites'
          + (f'; {shrunk} fixed since baseline - run --update-baseline to lock in' if shrunk else '') + ')')
    return 0


if __name__ == '__main__':
    sys.exit(main())
