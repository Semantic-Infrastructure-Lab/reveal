"""Ratchet: no NEW text-mode file I/O without an explicit ``encoding=``.

On Windows the default text encoding is cp1252, not UTF-8, so a bare
``Path.read_text()`` / ``open(p)`` that touches a non-ASCII file raises
UnicodeDecodeError there while passing on Linux/macOS (BACK-1346/1347 CI:
tests/test_surface_matrix.py read scanner source without an encoding).

Existing offenders are frozen in scripts/text_encoding_baseline.json (per-file
counts).  A file may only stay at or below its baseline; new or increased
offenders fail.  Fix a site with ``encoding='utf-8'`` (or ``'rb'`` mode), or
suppress a false positive with ``# noqa: text-encoding`` on the call line.

Flagged: ``open`` / ``io.open`` / ``Path.open`` / ``read_text`` / ``write_text`` in text mode,
``tempfile.NamedTemporaryFile``-family in text mode, and ``subprocess`` calls with
``text=True`` / ``universal_newlines=True`` / ``errors=`` but no ``encoding=`` (they decode
with cp1252 on Windows).  ``**kwargs`` is trusted (unknowable).  Not checked: stdout/stderr
(see ``reveal.main._setup_console``) and aliased ``open`` (``o = open``).

STRICT class -- never baselined: a bare read/open whose path derives from ``__file__`` or an
UPPERCASE module constant (repo sources, docs, fixtures).  Those files hold non-ASCII text and
are what broke Windows CI; they must always name an encoding.

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
NOT_FILES = {'os', 'io', 'webbrowser', 'gzip', 'zipfile', 'tarfile', 'urllib', 'codecs',
             'subprocess', 'opener', 'dist', 'session', 'client'}
TEMPFILES = {'NamedTemporaryFile', 'TemporaryFile', 'SpooledTemporaryFile'}
SUBPROCESS_FUNCS = {'run', 'Popen', 'check_output', 'check_call', 'call'}


def _mode(call: ast.Call, positional: list[ast.expr]):
    for kw in call.keywords:
        if kw.arg == 'mode' and isinstance(kw.value, ast.Constant):
            return kw.value.value
    if positional and isinstance(positional[0], ast.Constant):
        return positional[0].value
    return None


def _kw(call: ast.Call, name: str):
    return next((kw for kw in call.keywords if kw.arg == name), None)


def _has_encoding(call: ast.Call, positional_index: int | None = None) -> bool:
    """True if an encoding is given (keyword, ``**kwargs`` we cannot see, or positional)."""
    if any(kw.arg is None for kw in call.keywords):
        return True
    kw = _kw(call, 'encoding')
    if kw is not None:
        return not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
    return positional_index is not None and len(call.args) > positional_index


def _is_text_mode(mode) -> bool:
    return not (isinstance(mode, str) and 'b' in mode)


def is_bare_text_io(call: ast.Call) -> bool:
    func = call.func
    attr = func.attr if isinstance(func, ast.Attribute) else None
    owner = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None
    if attr == 'read_text':
        return owner not in NOT_FILES and not _has_encoding(call, 0)
    if attr == 'write_text':
        return owner not in NOT_FILES and not _has_encoding(call, 1)
    if isinstance(func, ast.Name) and func.id == 'open':
        return _is_text_mode(_mode(call, call.args[1:2])) and not _has_encoding(call)
    if attr == 'open':
        if owner in NOT_FILES and owner != 'io':
            return False
        return _is_text_mode(_mode(call, call.args[0:1])) and not _has_encoding(call)
    if (attr or getattr(func, 'id', None)) in TEMPFILES:
        mode = _mode(call, call.args[0:1])
        return isinstance(mode, str) and _is_text_mode(mode) and not _has_encoding(call)
    if owner == 'subprocess' and attr in SUBPROCESS_FUNCS:
        textual = any(
            (kw := _kw(call, name)) is not None and not (isinstance(kw.value, ast.Constant) and not kw.value.value)
            for name in ('text', 'universal_newlines', 'errors')
        )
        return textual and not _has_encoding(call)
    return False


def is_strict_site(call: ast.Call) -> bool:
    """A repo-file read: the path derives from __file__ or an UPPERCASE constant."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in ('read_text', 'open', 'write_text'):
        target: ast.AST | None = func.value
    elif isinstance(func, ast.Name) and func.id == 'open' and call.args:
        target = call.args[0]
    else:
        return False
    names = {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
    return '__file__' in names or any(n.isupper() and len(n) > 2 for n in names)


def scan() -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    found: dict[str, list[int]] = {}
    strict: dict[str, list[int]] = {}
    for tree_name in TREES:
        for path in sorted((ROOT / tree_name).rglob('*.py')):
            try:
                source = path.read_text(encoding='utf-8')
                tree = ast.parse(source)
            except (SyntaxError, UnicodeDecodeError):
                continue
            lines = source.splitlines()
            rel = path.relative_to(ROOT).as_posix()
            for n in ast.walk(tree):
                if not (isinstance(n, ast.Call) and is_bare_text_io(n)):
                    continue
                if 'noqa: text-encoding' in lines[n.lineno - 1]:
                    continue
                (strict if tree_name == 'tests' and is_strict_site(n) else found).setdefault(rel, []).append(n.lineno)
    return ({f: sorted(v) for f, v in found.items()}, {f: sorted(v) for f, v in strict.items()})


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
    baseline = json.loads(BASELINE.read_text(encoding='utf-8')) if BASELINE.exists() else {}
    if '-v' in sys.argv:
        for f, lines_ in {**found, **strict}.items():
            print(f'{f}: {lines_}')
    regressions = {f: (baseline.get(f, 0), n) for f, n in counts.items() if n > baseline.get(f, 0)}
    if strict or regressions:
        print('Text I/O without encoding= (breaks on Windows cp1252):')
        for f, lines_ in sorted(strict.items()):
            print(f'  {f}: lines {lines_}  [STRICT: reads a repo file/fixture; never baselined]')
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
